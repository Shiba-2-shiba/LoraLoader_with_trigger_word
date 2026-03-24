# CivArchive 対応リファクタリング計画書

## 1. 文書情報

- 作成日: 2026-03-24
- 対象プロジェクト: `LoraLoader_with_trigger_word`
- 目的:
  - トリガーワード取得経路に `CivArchive API` を追加する
  - ブラウザ表示用のモデルカード取得を `CivArchive API` 中心へ寄せる
  - 既存の `Civitai API` 依存箇所を整理し、責務分離しやすい構造へリファクタリングする

## 2. 背景

現状の実装は、ローカル sidecar / embedded metadata を優先しつつ、外部 API fallback として `Civitai by-hash` のみを利用している。  
一方で参考資料から、`CivArchive` は `SHA256` ベースの照合と `Civitai` 互換に近いデータ提供を前提としており、削除済みモデルやアーカイブ用途に強い。

今回の方針は次の 2 点である。

1. トリガーワード取得は `Civitai API` に加えて `CivArchive API` も使えるようにする
2. モデルカード閲覧は `CivArchive API` と `CivArchive URL` を優先する方向へ寄せる

## 3. 現状整理

### 3.1 現行構成

- `trigger_word_repository.py`
  - sidecar 読み込み
  - embedded metadata 読み込み
  - SHA256 計算
  - `Civitai by-hash` 呼び出し
  - cache 読み書き
  - model card URL / viewer 用データ整形
- `trigger_word_resolver.py`
  - trigger word source ごとの分岐
  - fallback 判定
  - Browse 用レスポンス整形
- `preview_api.py`
  - `/preview`
  - `/browse`
- `web/lora_loader_with_trigger_word.js`
  - ボタン UI
  - viewer UI
  - `civitai_url` 前提の表示

### 3.2 現状の問題点

1. `trigger_word_repository.py` に責務が集中している
2. 外部メタデータ取得が `Civitai by-hash` 固定で、拡張点がない
3. モデルカード周りの命名と表示が `Civitai` 固定で、`CivArchive` への寄せ替えが難しい
4. cache 名やレスポンス項目が `civitai_*` 前提で、複数 provider 管理に向かない
5. テストが `Civitai` 前提ケースに偏っている

### 3.3 参考資料から得た示唆

- 調査 PDF
  - `CivArchive` は `SHA256` ベースでモデル照合できる
  - `Civitai` と近い JSON 構造を返すため、正規化層を作れば統合しやすい
  - 実装方針としては `Civitai` 優先、失敗時 `CivArchive` fallback が適している
- `ComfyUI-Lora-Manager`
  - `ModelMetadataProvider` 抽象により provider を差し替えている
  - `civarchive_client.py` で `CivArchive` 独自 payload を Civitai 互換寄りに正規化している
  - `source = civarchive` を保持して provider 起源を区別している

## 4. 到達目標

## 4.1 機能目標

1. trigger words 取得で `Civitai` と `CivArchive` の両方を利用できる
2. モデルカード表示で `CivArchive` 情報を優先利用できる
3. 既存のローカル metadata / embedded metadata / `.info` との互換を保つ
4. フロントエンド UI が provider 非依存の表現に整理される

### 4.2 設計目標

1. ローカル metadata 取得とリモート API 取得を分離する
2. provider ごとの差分は client / adapter 層に閉じ込める
3. resolver 層では「どの provider をどう優先するか」だけを扱う
4. viewer 用データは `card_data` の共通スキーマで返す

## 5. 基本方針

### 5.1 Provider 抽象を導入する

新たに「リモートモデルメタデータ provider」概念を導入する。最低限、以下を共通化対象とする。

- `get_model_by_hash(sha256)`
- `build_trigger_word_metadata(...)`
- `build_model_card_data(...)`

想定 provider:

- `CivitaiMetadataProvider`
- `CivArchiveMetadataProvider`

### 5.2 正規化スキーマを導入する

provider から返る生 payload をそのまま resolver に渡さず、内部共通スキーマへ正規化する。

最低限必要な正規化項目:

- `source`
- `platform`
- `model_id`
- `version_id`
- `model_name`
- `version_name`
- `trained_words`
- `images`
- `description`
- `base_model`
- `model_type`
- `stats`
- `primary_url`
- `alternate_urls`

### 5.3 互換維持と命名整理を分ける

外部互換のため、最初の段階では sidecar 内の `civitai` バケットや既存 API の返却項目を急に壊さない。  
ただし内部コードでは、`civitai 固有` の名前を段階的に `remote metadata` / `provider metadata` へ寄せる。

## 6. 目標アーキテクチャ

### 6.1 バックエンド

- `local_metadata_repository`
  - `.metadata.json`
  - `.info`
  - embedded metadata
- `remote_metadata_clients`
  - `civitai_client`
  - `civarchive_client`
- `remote_metadata_providers`
  - provider ごとの取得と正規化
- `metadata_resolver`
  - provider 優先順
  - fallback 条件
  - merge 方針
- `model_card_presenter`
  - viewer 用 `card_data` の生成

### 6.2 フロントエンド

- API 返却項目を `provider-neutral` に寄せる
- viewer 文言から `Civitai metadata` 固定表現を外す
- URL 表示は `primary_url` を使う
- `source_label` は `Civitai` / `CivArchive` / `local metadata` を識別可能にする

## 7. 優先順ルール案

### 7.1 Trigger Words

1. sidecar metadata
2. embedded metadata
3. `Civitai by-hash`
4. `CivArchive by-hash`
5. filename fallback

補足:

- `Civitai` は既存互換維持のため先に試す
- `CivArchive` は削除済みモデルや `Civitai` 未解決時の補完を担う
- provider ごとの `trainedWords` 品質差を考慮し、単純な「最初に取れたもの勝ち」ではなくスコア評価を残す

### 7.2 Model Card

1. sidecar / `.info` に明示 URL や ID がある場合はそれを起点に解決
2. `CivArchive` から card 用データを優先取得
3. `CivArchive` で不足する場合のみ `Civitai` を補助利用

補足:

- Browse 用 URL は `CivArchive canonical URL` を第一候補にする
- 補助情報として `Civitai URL` を alternate URL に保持する

## 8. 実施フェーズ

### Phase 0: 既存仕様の固定化

- 現行テストの棚卸し
- `Civitai` 前提の挙動を回帰仕様として固定
- `CivArchive` 対応時に維持すべき UI/出力の明確化

成果物:

- 既存仕様一覧
- 回帰対象ケース一覧

### Phase 1: リモート取得責務の分離

- `trigger_word_repository.py` から次を分離
  - SHA256 / cache
  - `Civitai` API 呼び出し
  - model card URL 生成
- `Civitai` 用 client / provider を切り出す

成果物:

- provider 抽象
- `Civitai` provider 実装

### Phase 2: CivArchive client / provider 追加

- `ComfyUI-Lora-Manager` の `civarchive_client.py` を参考に、必要最小限の client を実装
- `CivArchive` payload を内部共通スキーマへ正規化
- `source = civarchive` を保持

成果物:

- `CivArchive` client
- `CivArchive` provider
- 正規化テスト

### Phase 3: resolver の再編

- trigger words と model card を別ユースケースとして整理
- provider 優先順と fallback 条件を resolver に集約
- `enable_civitai_fallback` の命名見直しを検討

候補:

- 後方互換優先:
  - UI 入力名は当面 `enable_civitai_fallback`
  - 内部では `enable_remote_fallback`
- 整理優先:
  - UI/README/API すべて `enable_remote_fallback` へ移行

推奨:

- このフェーズでは後方互換優先
- 変数名の完全改名は最終フェーズで実施

### Phase 4: Model Card の CivArchive 寄せ

- `build_civitai_model_card*` を provider-neutral な名称に変更
- URL 抽出ロジックを `Civitai` / `CivArchive` 両対応へ変更
- `meta.canonical` や `platform_url` を活用し `CivArchive` URL を優先
- viewer 文言を provider-neutral 化

成果物:

- card presenter
- Browse API の新レスポンス
- フロントエンド viewer 調整

### Phase 5: ドキュメントとテスト整理

- README 更新
- 新旧命名の整合確認
- provider ごとの単体テスト追加
- Browse / Preview の結合テスト追加

## 9. 具体的な変更対象

### 高優先

- `trigger_word_repository.py`
- `trigger_word_resolver.py`
- `preview_api.py`
- `web/lora_loader_with_trigger_word.js`
- `tests/test_trigger_word_resolver.py`

### 追加候補

- `remote_metadata/clients/*.py`
- `remote_metadata/providers/*.py`
- `model_card_presenter.py`
- provider 別 test file

## 10. テスト計画

### 10.1 単体テスト

- `Civitai` provider の正規化
- `CivArchive` provider の正規化
- provider 優先順
- trigger words マージ / スコア判定
- model card URL 優先順

### 10.2 回帰テスト

- 既存 `json_combined`
- 既存 `json_random`
- 既存 `json_sample_prompt`
- 既存 `metadata`
- sidecar のみで動くケース
- fallback 無効時の失敗文言

### 10.3 UI/API テスト

- `/browse` のレスポンスが provider-neutral であること
- `CivArchive` URL が viewer に表示されること
- `source_label` が期待どおり出ること

## 11. リスクと対策

### リスク 1

`CivArchive` の実 payload が `Civitai` と完全一致しない

対策:

- client 層で正規化を吸収する
- resolver は raw payload を直接参照しない

### リスク 2

`CivArchive` では画像や説明文が不足する場合がある

対策:

- model card は `CivArchive` 優先だが、足りない項目だけ `Civitai` 補完を許可する

### リスク 3

`civitai_*` 命名の一括改名で回帰が増える

対策:

- 内部抽象化を先行
- 外部公開名の改名は最後に分離して行う

### リスク 4

cache 仕様変更で既存キャッシュを読めなくなる

対策:

- 旧 `civitai_model_info_cache.json` の読み込み互換を残す
- 新キャッシュは provider 識別付きへ段階移行する

## 12. 実装判断メモ

1. `CivArchive` 対応の主目的は「削除済みモデルへの耐性強化」であり、`Civitai` の完全置換ではない
2. Trigger Words と Model Card は優先 provider を分ける
3. Browse では `CivArchive` を前面に出すが、trigger words は品質優先で `Civitai` 先行を維持する
4. sidecar の `civitai` キーは当面互換維持し、内部設計だけ先に抽象化する

## 13. 着手順推奨

1. provider 抽象の導入
2. `Civitai` 実装の切り出し
3. `CivArchive` 実装の追加
4. resolver の再編
5. model card の CivArchive 寄せ
6. UI 文言と README の整理

## 14. 完了条件

1. trigger words 取得で `Civitai` / `CivArchive` の両 provider が選択的に利用される
2. 削除済みモデルでも `CivArchive` 経由で model card を表示できる
3. viewer の URL と表示文言が `CivArchive` 優先方針に沿う
4. 既存の trigger words 回帰テストが維持される
5. 新規 provider テストが追加される
