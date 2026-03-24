# LoraLoader with Trigger Word

`MODEL` に LoRA を適用しつつ、その LoRA に対応するトリガーワードをノード内で確認できる ComfyUI 用カスタムノードです。  
LoRA の適用は `Model Only` 相当で行い、トリガーワードは複数のメタデータ経路から取得します。

このパッケージは **ComfyUI V3 スキーマ / Nodes 2.0 / 現行フロントエンド互換** を前提にしています。  
バックエンドは V3 schema、フロントエンドは `web/` 配下の軽量な JavaScript 拡張で構成されています。

## 特徴

- `MODEL` に LoRA を適用
- `TRIGGER_WORDS` 出力として取得文字列を downstream に流せる
- `Load Trigger Words` / `Load Model Card` / `Browse Model Card` の 3 操作ボタンで確認可能
- ノード内の表示欄には直前の操作結果を表示
- `json_combined / json_random / json_sample_prompt / metadata` の4モード
- `.metadata.json` / `.info` / `.safetensors` 埋め込みメタデータに対応
- `.metadata.json` と `.info` が両方ある場合は不足情報を補完しながら併用
- `modelspec.trigger_phrase` に対応
- `modelspec.usage_hint` と `modelspec.description` も候補に使用
- 任意で Civitai `by-hash` API fallback を使用
- Civitai model card URL を解決し、ComfyUI 内の viewer で閲覧できる
- `trainedWords` が空、`images.meta` が null などの失敗理由を文字列で返す

## 内部構成

- `node_definition.py`
  - ComfyUI ノード定義と schema / execute の公開面
- `preview_api.py`
  - フロントエンドの `Trigger Words` / `Browse` タブから呼ばれる API
- `lora_model_loader.py`
  - LoRA の読み込みと簡易キャッシュ
- `trigger_word_resolver.py`
  - 既存の公開インターフェースを維持する薄い facade
- `trigger_word_analyzer.py`
  - トリガーワード候補の抽出、整形、スコアリング
- `trigger_word_repository.py`
  - sidecar JSON、埋め込み metadata、Civitai cache / fallback の入出力
- `tests/test_trigger_word_resolver.py`
  - `resolve_path()` ベースの回帰テスト

拡張時の目安:

- 新しい候補抽出ルールを足す場合は `trigger_word_analyzer.py`
- 新しい metadata ソースを足す場合は `trigger_word_repository.py`
- ノード入力や UI を変える場合は `node_definition.py` と `web/`
- 外部呼び出し互換を維持したい場合は `trigger_word_resolver.py` の public surface を維持

## 対応環境

- ComfyUI V3 系
- Nodes 2.0 フロントエンド
- Python 3.10 以上推奨
- `safetensors` が利用可能な ComfyUI 環境

## インストール

`ComfyUI/custom_nodes` 配下にこのフォルダを置き、ComfyUI を再起動してください。

例:

```text
ComfyUI/
  custom_nodes/
    LoraLoader_with_trigger_word/
      __init__.py
      trigger_word_resolver.py
      trigger_word_analyzer.py
      trigger_word_repository.py
      pyproject.toml
      README.md
```

## ノード

### Load LoRA + Trigger Words (Model Only)

カテゴリ: `loaders/lora`

#### 入力

- `model`
  - LoRA を適用する `MODEL`
- `lora_name`
  - `models/loras` 内の LoRA ファイル名
- `strength_model`
  - MODEL への適用強度
- `trigger_word_source`
  - 取得モード
- `enable_civitai_fallback`
  - デフォルトで有効
  - ローカル metadata が不足した場合に、SHA256 から Civitai `by-hash` API を参照するか
- `loaded_trigger_words`
  - `Trigger Words` / `Browse` タブの表示欄
  - 実際の `TRIGGER_WORDS` 出力とは別です

#### 出力

- `MODEL`
  - LoRA 適用後の `MODEL`
- `TRIGGER_WORDS`
  - `trigger_word_source` に応じて解決された文字列
  - 失敗時は空文字

#### ノード内 UI

このノードの UI は「3 つの操作ボタン」と「1 つの表示欄」で構成されます。

- 表示欄
  - 直前に実行した操作の結果や失敗理由を表示
- `Load Trigger Words`
  - 現在の `lora_name`、`trigger_word_source`、`enable_civitai_fallback` を使って preview API を実行
- `Load Model Card`
  - 現在の `lora_name` と `enable_civitai_fallback` を使って model card URL を解決
- `Browse Model Card`
  - 解決済み model card 情報を ComfyUI 内の viewer で開く
  - 未読込時は必要に応じて `Load Model Card` 相当の解決を先に行う

## trigger_word_source の仕様

### `json_combined`

ローカル metadata または fallback metadata の `civitai.trainedWords` をすべて結合し、重複を除去して返します。

処理順:

1. `.metadata.json`
2. `.info`
3. `.safetensors` 埋め込み metadata
4. デフォルトで有効な Civitai `by-hash` fallback

### `json_random`

`civitai.trainedWords` の候補から1件をランダムに返します。

### `json_sample_prompt`

`civitai.images[].meta.prompt` から sample prompt を1件ランダムに返します。  
`<lora:...>` 構文は削除されます。

`images` があっても `meta` が全部 `null` の場合は、失敗理由を返します。

### `metadata`

埋め込み metadata を優先してトリガーワードを返します。  
候補に使うキー:

- `ss_tag_frequency`
- `modelspec.trigger_phrase`
- `modelspec.trigger_word`
- `modelspec.usage_hint`
- `modelspec.description`

埋め込み metadata に十分な情報が無い場合、デフォルトで有効な Civitai fallback を試します。

## 埋め込み metadata の扱い

このノードは `safetensors` の metadata から次の情報を利用します。

- `ss_tag_frequency`
  - 各データセットのタグ頻度を集約し、頻度順でタグ候補を作成
- `modelspec.trigger_phrase`
  - 標準的な trigger phrase
- `modelspec.trigger_word`
  - 旧来または独自の trigger word
- `modelspec.usage_hint`
  - 使用ヒント
- `modelspec.description`
  - 説明文
- `ss_output_name`
  - モデル名保持用

## Civitai fallback

`enable_civitai_fallback=true` が既定値で、必要時に LoRA ファイルの SHA256 を計算し、以下を参照します。

```text
https://civitai.com/api/v1/model-versions/by-hash/<sha256>
```

取得したレスポンスは同フォルダ内の `civitai_model_info_cache.json` にキャッシュされます。

注意:

- ネットワークに接続できない環境では fallback は失敗します
- Civitai 側に hash 情報が無い LoRA では何も返らないことがあります
- fallback はローカル metadata の代替であり、完全保証ではありません

## Browse タブ

`Browse` タブは現在選択中の LoRA に対応する Civitai model card URL を解決して表示します。  
優先順は次の通りです。

1. sidecar `.metadata.json` / `.info`
2. `civitai_model_info_cache.json`
3. 必要時の Civitai `by-hash` fallback

URL が解決できた場合は `Browse Model Card` から ComfyUI 内 viewer で閲覧できます。

## 失敗時の動作

このノードは、以下のようなケースで空文字ではなく失敗理由の文字列を表示欄に返します。

- `trainedWords` が空
- sample images が無い
- `images.meta` が全部 `null`
- prompt を整形したら空になった
- 埋め込み metadata に使える候補が無い
- Civitai fallback が無効、または有効でも解決できない


## 既知の制限

- Civitai に登録されていない LoRA は by-hash fallback が使えません
- `json_sample_prompt` は `images[].meta` が存在するモデルでのみ有効です
- `PickleTensor` など `safetensors` 以外の埋め込み metadata は扱いません
- `modelspec.description` は短い trigger 候補だけを抽出対象にしており、説明文全体はそのまま返しません
