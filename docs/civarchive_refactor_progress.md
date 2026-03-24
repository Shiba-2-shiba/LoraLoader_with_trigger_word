# CivArchive 対応リファクタリング進捗確認書

## 1. 文書情報

- 作成日: 2026-03-24
- 対象プロジェクト: `LoraLoader_with_trigger_word`
- 用途:
  - 着手前の基準線確認
  - 実装フェーズの進捗管理
  - 完了判定の確認

## 2. 現在の総合ステータス

- 全体状況: Phase 5 完了
- 基準日: 2026-03-25
- 今回時点でのコード変更: あり
- 今回時点での成果物:
  - `docs/civarchive_refactor_plan.md`
  - 本進捗確認書
  - `remote_metadata/`
  - `trigger_word_repository.py`
  - `trigger_word_resolver.py`
  - `web/lora_loader_with_trigger_word.js`
  - `tests/test_trigger_word_resolver.py`
  - `README.md`

## 3. 現状確認結果

### 3.1 実装面

- `Civitai by-hash` fallback は provider 化済み
- `CivArchive API` 呼び出しは実装済み
- trigger words fallback は `Civitai -> CivArchive` 順で実装済み
- model card 表示は `CivArchive -> Civitai` 順で実装済み
- viewer 文言は provider-neutral 化済み
- cache は `civitai_model_info_cache.json` と `civarchive_model_info_cache.json` を分離

### 3.2 設計面

- provider 抽象: 導入済み
- client / adapter 分離: 導入済み
- model card presenter 分離: repository/resolver 内で共通 card schema 化済み
- provider-neutral 命名: Browse 系を中心に導入済み

### 3.3 テスト面

- trigger words の既存回帰テスト: あり
- `CivArchive` provider テスト: あり
- Browse の provider 切替テスト: あり
- Browse の provider-neutral 契約テスト: あり
- 現在のテスト結果: `python -m unittest discover -s tests` で 21 件成功

## 4. 現時点の主要論点

1. `enable_civitai_fallback` を後方互換のため残すか、`enable_remote_fallback` に改名するか
2. provider 別 cache と viewer 表示項目を今後さらに分離するか
3. Browse / Preview の API 契約を README から専用文書へ切り出すか

## 5. フェーズ別進捗チェック

### Phase 0: 既存仕様固定

- 状態: 完了
- 内容:
  - 現行構造確認
  - 既存 fallback 経路確認
  - 既存テスト確認

確認メモ:

- `trigger_word_repository.py` に API / cache / card 整形が集中
- `trigger_word_resolver.py` が UI 返却の集約点
- `web/lora_loader_with_trigger_word.js` が `civitai_url` を直接参照

### Phase 1: Civitai 実装切り出し

- 状態: 完了
- 完了条件:
  - `Civitai` リモート取得が専用 client/provider に分離される
  - resolver から直接 API 実装詳細が見えない

確認メモ:

- `remote_metadata/civitai_client.py` と `CivitaiMetadataProvider` を追加
- `trigger_word_repository.py` から hash / cache / 通信責務を分離
- 監査結果: blocking issue なし

### Phase 2: CivArchive provider 追加

- 状態: 完了
- 完了条件:
  - `CivArchive` から hash ベースで metadata を取得できる
  - payload が内部共通形式に正規化される

確認メモ:

- `remote_metadata/civarchive_client.py` と `CivArchiveMetadataProvider` を追加
- `data/version/files` 差分を provider 内で吸収
- 監査結果: blocking issue なし

### Phase 3: resolver 再編

- 状態: 完了
- 完了条件:
  - trigger words と model card の優先順がコード上で明示される
  - fallback 条件が provider 単位で整理される

確認メモ:

- trigger words fallback を `Civitai -> CivArchive` として明示
- `json_sample_prompt` / `metadata` 系で `CivArchive` fallback を利用可能化
- 監査結果: blocking issue なし

### Phase 4: model card の CivArchive 寄せ

- 状態: 完了
- 完了条件:
  - Browse で `CivArchive` URL が優先される
  - viewer 文言が provider-neutral になる

確認メモ:

- `primary_url` / `civarchive_url` / `alternate_urls` を Browse API に追加
- model card fallback を `CivArchive -> Civitai` に変更
- viewer は `primary_url` を優先表示・コピー
- 監査結果: `python -m unittest discover -s tests` で 20 件成功、blocking issue なし

### Phase 5: 文書・テスト更新

- 状態: 完了
- 完了条件:
  - README 更新
  - provider 別テスト追加
  - 回帰テスト維持

確認メモ:

- README に remote fallback 優先順、Browse API 応答項目、`primary_url` 契約を追記
- model card 成功/失敗レスポンスの provider-neutral 項目をテストで固定
- 監査結果: `python -m unittest discover -s tests` で 21 件成功、blocking issue なし

## 6. 成果物チェックリスト

- [x] リファクタリング計画書
- [x] 進捗確認書
- [x] provider 抽象
- [x] Civitai client/provider 分離
- [x] CivArchive client/provider
- [x] resolver 再編
- [x] Browse API 再設計
- [x] viewer 文言整理
- [x] テスト追加
- [x] README 更新

## 7. リスク管理表

| No | リスク | 現状 | 対応方針 |
|---|---|---|---|
| 1 | `CivArchive` payload 差異 | 継続監視 | client / provider 層で正規化 |
| 2 | URL 優先順の混乱 | 対応済み | `primary_url` / `alternate_urls` 導入 |
| 3 | 既存 UI 文言とのズレ | 対応済み | viewer 文言を provider-neutral 化 |
| 4 | cache 互換性崩れ | 継続監視 | 旧 cache 読み込み互換維持 |

## 8. 次回着手時の推奨順

1. `enable_civitai_fallback` 命名の後方互換整理要否を再評価
2. Browse / Preview の API 契約を必要に応じて専用文書へ分離
3. 必要なら provider 別 test file へ分割

## 9. 更新履歴

### 2026-03-24

- 現状実装、参考 PDF、`ComfyUI-Lora-Manager` を確認
- `CivArchive` 対応方針を整理
- 計画書および進捗確認書を新規作成
- Phase 1 完了: `Civitai` client/provider 分離
- Phase 2 完了: `CivArchive` client/provider 追加と payload 正規化
- Phase 3 完了: trigger words fallback に `CivArchive` を接続
- Phase 4 完了: model card を `CivArchive` 優先へ変更し viewer を provider-neutral 化

### 2026-03-25

- Phase 5 完了: README と model card 契約テストを更新
