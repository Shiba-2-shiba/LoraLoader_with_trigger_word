"""
LoRA Loader (Model Only) + Trigger Words for ComfyUI.
"""

import hashlib
import json
import os
import random
import re
from urllib import error, request

import comfy.sd
import comfy.utils
import folder_paths
import server
from aiohttp import web
from comfy_api.latest import io

try:
    from safetensors.torch import safe_open

    SAFETENSORS_AVAILABLE = True
except ImportError:
    SAFETENSORS_AVAILABLE = False


class TriggerWordResolver:
    CACHE_FILENAME = "civitai_model_info_cache.json"

    def __init__(self):
        self.loaded_lora = None

    def load_lora_model_only(self, model, lora_name, strength_model):
        if strength_model == 0:
            return model

        lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
        lora = None

        if self.loaded_lora is not None:
            if self.loaded_lora[0] == lora_path:
                lora = self.loaded_lora[1]
            else:
                self.loaded_lora = None

        if lora is None:
            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
            self.loaded_lora = (lora_path, lora)

        return comfy.sd.load_lora_for_models(model, None, lora, strength_model, 0)[0]

    def resolve(self, lora_name, trigger_word_source, enable_civitai_fallback):
        lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)

        if trigger_word_source == "json_sample_prompt":
            return self._get_sample_prompt_text(
                lora_path=lora_path,
                enable_civitai_fallback=enable_civitai_fallback,
            )
        if trigger_word_source == "json_random":
            return self._get_trigger_words_random(
                lora_path=lora_path,
                enable_civitai_fallback=enable_civitai_fallback,
            )
        if trigger_word_source == "metadata":
            return self._get_trigger_words_from_embedded(
                lora_path=lora_path,
                enable_civitai_fallback=enable_civitai_fallback,
            )
        return self._get_trigger_words_combined(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
        )

    def _get_trigger_words_combined(self, lora_path, enable_civitai_fallback):
        metadata, source_label = self._get_metadata_with_optional_fallback(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
            require_images=False,
            prefer_embedded_only=False,
        )
        trained_words = self._extract_trained_words(metadata)
        if not trained_words:
            return self._failure_message(
                lora_path,
                "トリガーワードが見つかりません。trainedWords、埋め込みメタデータ"
                "（ss_tag_frequency、modelspec.trigger_phrase、modelspec.trigger_word、"
                "modelspec.usage_hint、modelspec.description）を確認しました。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        all_words = []
        for pattern in trained_words:
            cleaned_pattern = self._remove_lora_syntax(pattern)
            all_words.extend(word.strip() for word in cleaned_pattern.split(","))

        unique_words = []
        seen = set()
        for word in all_words:
            lowered = word.lower()
            if word and lowered not in seen:
                unique_words.append(word)
                seen.add(lowered)

        if not unique_words:
            return self._failure_message(
                lora_path,
                "候補は見つかりましたが、整形後に空になりました。",
            )
        return ", ".join(unique_words)

    def _get_trigger_words_random(self, lora_path, enable_civitai_fallback):
        metadata, source_label = self._get_metadata_with_optional_fallback(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
            require_images=False,
            prefer_embedded_only=False,
        )
        trained_words = self._extract_trained_words(metadata)
        if not trained_words:
            return self._failure_message(
                lora_path,
                "ランダム選択できるトリガーワード候補が見つかりません。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        selected = self._remove_lora_syntax(random.choice(trained_words)).strip()
        if not selected:
            return self._failure_message(
                lora_path,
                "トリガーワード候補は見つかりましたが、整形後に空になりました。",
            )
        return selected

    def _get_sample_prompt_text(self, lora_path, enable_civitai_fallback):
        metadata, source_label = self._get_metadata_with_optional_fallback(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
            require_images=True,
            prefer_embedded_only=False,
        )
        images = metadata.get("civitai", {}).get("images", []) if metadata else []
        if not images:
            return self._failure_message(
                lora_path,
                "json_sample_prompt 用の sample images が見つかりません。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        valid_images = [image for image in images if image.get("meta")]
        if not valid_images:
            return self._failure_message(
                lora_path,
                "sample images は見つかりましたが、images.meta がすべて null か空です。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        selected_image = random.choice(valid_images)
        meta = selected_image["meta"]
        positive = self._cleanup_prompt_text(
            self._remove_lora_syntax(meta.get("prompt", ""))
        )
        if not positive:
            return self._failure_message(
                lora_path,
                "sample prompt は見つかりましたが、整形後の positive prompt が空です。",
            )
        return positive

    def _get_trigger_words_from_embedded(self, lora_path, enable_civitai_fallback):
        embedded = self._load_embedded_metadata(lora_path)
        source_label = "embedded metadata"
        trained_words = self._extract_trained_words(embedded)

        if not trained_words and enable_civitai_fallback:
            fallback = self._load_civitai_metadata_by_hash(lora_path)
            if fallback is not None:
                trained_words = self._extract_trained_words(fallback)
                source_label = "Civitai by-hash fallback"

        if not trained_words:
            return self._failure_message(
                lora_path,
                "埋め込みメタデータに使えるトリガーワードがありません。"
                " ss_tag_frequency、modelspec.trigger_phrase、modelspec.trigger_word、"
                "modelspec.usage_hint、modelspec.description を確認しました。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        return self._remove_lora_syntax(trained_words[0]).strip()

    def _get_metadata_with_optional_fallback(
        self,
        lora_path,
        enable_civitai_fallback,
        require_images,
        prefer_embedded_only,
    ):
        if prefer_embedded_only:
            metadata = self._load_embedded_metadata(lora_path)
            source_label = "embedded metadata"
        else:
            metadata = self._load_json_metadata(lora_path)
            source_label = "local metadata"

        if self._metadata_satisfies_request(metadata, require_images):
            return metadata, source_label

        if not prefer_embedded_only:
            embedded = self._load_embedded_metadata(lora_path)
            if self._metadata_satisfies_request(embedded, require_images):
                return embedded, "embedded metadata"

        if enable_civitai_fallback:
            fallback = self._load_civitai_metadata_by_hash(lora_path)
            if self._metadata_satisfies_request(fallback, require_images):
                return fallback, "Civitai by-hash fallback"

        return metadata, source_label

    def _metadata_satisfies_request(self, metadata, require_images):
        if not metadata:
            return False
        if require_images:
            images = metadata.get("civitai", {}).get("images", [])
            return any(image.get("meta") for image in images)
        return bool(self._extract_trained_words(metadata))

    def _load_json_metadata(self, lora_path):
        base_path = os.path.splitext(lora_path)[0]

        metadata_json_path = f"{base_path}.metadata.json"
        if os.path.exists(metadata_json_path):
            try:
                with open(metadata_json_path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception as exc:
                print(
                    f"[LoraLoaderModelOnlyTriggerWords] Warning: "
                    f"Failed to load {metadata_json_path}: {exc}"
                )

        info_path = f"{base_path}.info"
        if os.path.exists(info_path):
            try:
                with open(info_path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception as exc:
                print(
                    f"[LoraLoaderModelOnlyTriggerWords] Warning: "
                    f"Failed to load {info_path}: {exc}"
                )

        return None

    def _load_embedded_metadata(self, lora_path):
        if not SAFETENSORS_AVAILABLE:
            return None

        try:
            with safe_open(lora_path, framework="pt", device="cpu") as file:
                raw_metadata = file.metadata()
        except Exception:
            return None

        if not raw_metadata:
            return None

        trained_words = []

        if "ss_tag_frequency" in raw_metadata:
            try:
                tag_freq = json.loads(raw_metadata.get("ss_tag_frequency", "{}"))
                all_tags = []
                for tags_dict in tag_freq.values():
                    sorted_tags = sorted(
                        tags_dict.items(), key=lambda item: item[1], reverse=True
                    )
                    all_tags.extend(tag for tag, _ in sorted_tags[:20])
                if all_tags:
                    unique_tags = list(dict.fromkeys(all_tags))
                    trained_words.append(", ".join(unique_tags))
            except Exception:
                pass

        for key in (
            "modelspec.trigger_phrase",
            "modelspec.trigger_word",
            "modelspec.usage_hint",
            "modelspec.description",
        ):
            value = self._string_or_empty(raw_metadata.get(key, ""))
            if value:
                trained_words.append(value)

        trained_words = self._dedupe_preserve_order(trained_words)
        civitai_format = {"civitai": {}, "_embedded_raw_metadata": raw_metadata}

        if trained_words:
            civitai_format["civitai"]["trainedWords"] = trained_words

        model_name = self._string_or_empty(raw_metadata.get("ss_output_name", ""))
        if model_name:
            civitai_format["model_name"] = model_name

        return civitai_format if civitai_format["civitai"] or model_name else None

    def _load_civitai_metadata_by_hash(self, lora_path):
        cache = self._load_civitai_cache()
        sha256_hash = self._calculate_sha256(lora_path)

        if sha256_hash in cache:
            return cache[sha256_hash]

        api_url = f"https://civitai.com/api/v1/model-versions/by-hash/{sha256_hash}"
        try:
            with request.urlopen(api_url, timeout=10) as response:
                if response.status != 200:
                    print(
                        "[LoraLoaderModelOnlyTriggerWords] Warning: "
                        f"Civitai by-hash request returned HTTP {response.status}"
                    )
                    return None
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            print(
                "[LoraLoaderModelOnlyTriggerWords] Warning: "
                f"Civitai by-hash request failed: {exc}"
            )
            return None
        except Exception as exc:
            print(
                "[LoraLoaderModelOnlyTriggerWords] Warning: "
                f"Failed to parse Civitai by-hash response: {exc}"
            )
            return None

        cache[sha256_hash] = payload
        self._save_civitai_cache(cache)
        return payload

    def _extract_trained_words(self, metadata):
        if not metadata:
            return []

        trained_words = metadata.get("civitai", {}).get("trainedWords", [])
        if not trained_words:
            return []

        output = []
        for item in trained_words:
            cleaned = self._string_or_empty(item)
            if cleaned:
                output.append(cleaned)
        return self._dedupe_preserve_order(output)

    def _calculate_sha256(self, file_path):
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def _load_civitai_cache(self):
        cache_path = self._get_cache_path()
        if not os.path.exists(cache_path):
            return {}

        try:
            with open(cache_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            print(
                "[LoraLoaderModelOnlyTriggerWords] Warning: "
                f"Failed to read Civitai cache {cache_path}: {exc}"
            )
            return {}

        return data if isinstance(data, dict) else {}

    def _save_civitai_cache(self, cache):
        cache_path = self._get_cache_path()
        try:
            with open(cache_path, "w", encoding="utf-8") as file:
                json.dump(cache, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(
                "[LoraLoaderModelOnlyTriggerWords] Warning: "
                f"Failed to write Civitai cache {cache_path}: {exc}"
            )

    def _get_cache_path(self):
        return os.path.join(os.path.dirname(__file__), self.CACHE_FILENAME)

    def _failure_message(self, lora_path, reason):
        lora_name = os.path.basename(lora_path)
        message = f"[LoRA Trigger Words] {lora_name}: {reason}"
        print(message)
        return message

    def _fallback_suffix(self, enable_civitai_fallback, source_label):
        if enable_civitai_fallback:
            if source_label == "Civitai by-hash fallback":
                return " Civitai fallback を使用しました。"
            return " Civitai fallback は有効でしたが、使えるデータを返しませんでした。"
        return " Civitai fallback は無効です。"

    def _remove_lora_syntax(self, text):
        return re.sub(r"<lora:[^>]+>", "", text)

    def _cleanup_prompt_text(self, text):
        text = re.sub(r"\s*,\s*,+\s*", ", ", text)
        text = re.sub(r"^\s*,\s*|\s*,\s*$", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _string_or_empty(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def _dedupe_preserve_order(self, values):
        output = []
        seen = set()
        for value in values:
            key = value.lower()
            if key not in seen:
                output.append(value)
                seen.add(key)
        return output


class LoraLoaderModelOnlyTriggerWordsNode(io.ComfyNode):
    _resolver = TriggerWordResolver()

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LoraLoaderModelOnlyTriggerWords",
            display_name="Load LoRA + Trigger Words (Model Only)",
            category="loaders/lora",
            description=(
                "LoRA を MODEL に適用し、sidecar JSON、埋め込み safetensors metadata、"
                "必要に応じて Civitai by-hash fallback からトリガーワード文字列を返します。"
            ),
            search_aliases=[
                "lora trigger words",
                "load lora model only",
                "civitai trained words",
                "auto trigger words",
                "lora metadata",
            ],
            inputs=[
                io.Model.Input(
                    "model",
                    tooltip="LoRA を適用する MODEL。",
                ),
                io.Combo.Input(
                    "lora_name",
                    options=sorted(folder_paths.get_filename_list("loras"), key=str.lower),
                    tooltip="適用する LoRA 名。",
                ),
                io.Float.Input(
                    "strength_model",
                    default=1.0,
                    min=-100.0,
                    max=100.0,
                    tooltip="MODEL に適用する LoRA 強度。負の値も指定可能です。",
                ),
                io.Combo.Input(
                    "trigger_word_source",
                    options=["json_combined", "json_random", "json_sample_prompt", "metadata"],
                    default="json_combined",
                    tooltip="トリガーワードの取得モード。",
                ),
                io.Boolean.Input(
                    "enable_civitai_fallback",
                    default=False,
                    advanced=True,
                    tooltip="ローカル metadata で不足した場合に SHA256 から Civitai by-hash API を参照します。",
                ),
                io.String.Input(
                    "loaded_trigger_words",
                    multiline=True,
                    default="",
                    tooltip="Load Trigger Words ボタンで取得した内容の表示欄。実行時の MODEL 適用には影響しません。",
                ),
            ],
            outputs=[
                io.Model.Output(
                    display_name="MODEL",
                    tooltip="LoRA 適用後の MODEL。",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        model,
        lora_name,
        strength_model,
        trigger_word_source,
        enable_civitai_fallback,
        loaded_trigger_words,
    ):
        model_lora = cls._resolver.load_lora_model_only(model, lora_name, strength_model)
        return io.NodeOutput(model_lora)


@server.PromptServer.instance.routes.post("/lora_loader_with_trigger_word/preview")
async def preview_trigger_words(request):
    try:
        payload = await request.json()
        lora_name = payload.get("lora_name", "")
        trigger_word_source = payload.get("trigger_word_source", "json_combined")
        enable_civitai_fallback = bool(payload.get("enable_civitai_fallback", False))

        if not lora_name:
            return web.json_response(
                {
                    "success": False,
                    "trigger_words": "[LoRA Trigger Words] LoRA が選択されていません。",
                },
                status=400,
            )

        trigger_words = LoraLoaderModelOnlyTriggerWordsNode._resolver.resolve(
            lora_name=lora_name,
            trigger_word_source=trigger_word_source,
            enable_civitai_fallback=enable_civitai_fallback,
        )
        return web.json_response({"success": True, "trigger_words": trigger_words})
    except Exception as exc:
        message = f"[LoRA Trigger Words] preview 取得エラー: {exc}"
        print(message)
        return web.json_response(
            {
                "success": False,
                "trigger_words": message,
            },
            status=500,
        )
