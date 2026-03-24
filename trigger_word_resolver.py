"""Trigger word resolution logic for LoRA metadata and fallback APIs."""

import hashlib
import json
import os
import random
import re
from pathlib import Path
from urllib import error, request

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from .constants import PREVIEW_PREFIX
except ImportError:
    from constants import PREVIEW_PREFIX

try:
    from safetensors.torch import safe_open

    SAFETENSORS_AVAILABLE = True
except ImportError:
    SAFETENSORS_AVAILABLE = False


class TriggerWordResolver:
    CACHE_FILENAME = "civitai_model_info_cache.json"
    STYLE_PLACEHOLDER = "@style_name"
    FALLBACK_SCORE_THRESHOLD = 20
    GENERIC_TAGS = {
        "1girl",
        "1 boy",
        "1boy",
        "animal ears",
        "blush",
        "breasts",
        "closed eyes",
        "day",
        "gloves",
        "indoors",
        "jacket",
        "large breasts",
        "long hair",
        "multiple girls",
        "night",
        "no humans",
        "open mouth",
        "outdoors",
        "school uniform",
        "shirt",
        "short hair",
        "skirt",
        "smile",
        "solo",
        "weapon",
        "white shirt",
    }

    def resolve(self, lora_name, trigger_word_source, enable_civitai_fallback):
        if folder_paths is None:
            raise RuntimeError("folder_paths is not available outside ComfyUI")

        lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
        return self.resolve_path(
            lora_path=lora_path,
            trigger_word_source=trigger_word_source,
            enable_civitai_fallback=enable_civitai_fallback,
        )

    def resolve_path(self, lora_path, trigger_word_source, enable_civitai_fallback):
        source_handlers = {
            "json_sample_prompt": self._get_sample_prompt_text,
            "json_random": self._get_trigger_words_random,
            "metadata": self._get_trigger_words_from_embedded,
            "json_combined": self._get_trigger_words_combined,
        }
        handler = source_handlers.get(trigger_word_source, self._get_trigger_words_combined)
        return handler(
            lora_path=str(lora_path),
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
        civitai_section = self._get_civitai_section(metadata)
        images = civitai_section.get("images", []) if civitai_section else []
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

        if enable_civitai_fallback and self._should_attempt_fallback_for_words(
            trained_words,
            lora_path,
        ):
            fallback = self._load_civitai_metadata_by_hash(lora_path)
            fallback_words = self._extract_trained_words(fallback)
            if fallback_words and self._should_prefer_fallback(
                local_words=trained_words,
                fallback_words=fallback_words,
                lora_path=lora_path,
            ):
                trained_words = fallback_words
                source_label = "Civitai by-hash fallback"

        if not trained_words:
            filename_fallback = self._build_filename_fallback_metadata(lora_path)
            trained_words = self._extract_trained_words(filename_fallback)
            if trained_words:
                source_label = "filename fallback"

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
            best_metadata = metadata
            best_label = source_label
        else:
            best_metadata = None
            best_label = source_label

        if not prefer_embedded_only:
            embedded = self._load_embedded_metadata(lora_path)
            if self._metadata_satisfies_request(embedded, require_images):
                best_metadata, best_label = self._pick_better_metadata(
                    current_metadata=best_metadata,
                    current_label=best_label,
                    candidate_metadata=embedded,
                    candidate_label="embedded metadata",
                    lora_path=lora_path,
                    require_images=require_images,
                )

        if enable_civitai_fallback and self._should_attempt_fallback_for_metadata(
            best_metadata,
            lora_path,
            require_images,
        ):
            fallback = self._load_civitai_metadata_by_hash(lora_path)
            if self._metadata_satisfies_request(fallback, require_images):
                best_metadata, best_label = self._pick_better_metadata(
                    current_metadata=best_metadata,
                    current_label=best_label,
                    candidate_metadata=fallback,
                    candidate_label="Civitai by-hash fallback",
                    lora_path=lora_path,
                    require_images=require_images,
                )

        filename_fallback = self._build_filename_fallback_metadata(lora_path)
        if self._metadata_satisfies_request(filename_fallback, require_images):
            best_metadata, best_label = self._pick_better_metadata(
                current_metadata=best_metadata,
                current_label=best_label,
                candidate_metadata=filename_fallback,
                candidate_label="filename fallback",
                lora_path=lora_path,
                require_images=require_images,
            )

        if best_metadata is not None:
            return best_metadata, best_label

        return metadata, source_label

    def _metadata_satisfies_request(self, metadata, require_images):
        if not metadata:
            return False
        if require_images:
            civitai_section = self._get_civitai_section(metadata)
            images = civitai_section.get("images", []) if civitai_section else []
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
                    "[LoraLoaderModelOnlyTriggerWords] Warning: "
                    f"Failed to load {metadata_json_path}: {exc}"
                )

        info_path = f"{base_path}.info"
        if os.path.exists(info_path):
            try:
                with open(info_path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception as exc:
                print(
                    "[LoraLoaderModelOnlyTriggerWords] Warning: "
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
        trained_words.extend(self._extract_direct_trigger_words(raw_metadata))
        trained_words.extend(self._extract_trigger_words_from_tag_frequency(raw_metadata))
        trained_words = self._dedupe_preserve_order(trained_words)

        civitai_format = {"civitai": {}, "_embedded_raw_metadata": raw_metadata}

        if trained_words:
            civitai_format["civitai"]["trainedWords"] = trained_words

        model_name = self._string_or_empty(raw_metadata.get("ss_output_name", ""))
        if model_name:
            civitai_format["model_name"] = model_name

        return civitai_format if civitai_format["civitai"] or model_name else None

    def _extract_direct_trigger_words(self, raw_metadata):
        trained_words = []

        for key in ("trained_words", "ss_trained_words"):
            trained_words.extend(self._parse_trigger_word_value(raw_metadata.get(key)))

        for key in (
            "modelspec.trigger_phrase",
            "modelspec.trigger_word",
            "modelspec.usage_hint",
            "modelspec.description",
        ):
            value = self._string_or_empty(raw_metadata.get(key, ""))
            if value:
                trained_words.append(value)

        return self._dedupe_preserve_order(trained_words)

    def _parse_trigger_word_value(self, value):
        if value is None:
            return []

        if isinstance(value, list):
            return [self._string_or_empty(item) for item in value if self._string_or_empty(item)]

        if isinstance(value, tuple):
            return [self._string_or_empty(item) for item in value if self._string_or_empty(item)]

        text = self._string_or_empty(value)
        if not text:
            return []

        if text.startswith("[") or text.startswith("{"):
            try:
                decoded = json.loads(text)
            except Exception:
                decoded = None
            if isinstance(decoded, list):
                return [self._string_or_empty(item) for item in decoded if self._string_or_empty(item)]
            if isinstance(decoded, str):
                text = decoded

        if "," in text:
            parts = [part.strip() for part in text.split(",")]
            compact_parts = [part for part in parts if part]
            if compact_parts:
                return compact_parts

        return [text]

    def _extract_trigger_words_from_tag_frequency(self, raw_metadata):
        raw_tag_frequency = raw_metadata.get("ss_tag_frequency")
        if not raw_tag_frequency:
            return []

        try:
            tag_frequency = json.loads(raw_tag_frequency)
        except Exception:
            return []

        if not isinstance(tag_frequency, dict):
            return []

        dataset_dirs = self._parse_json_dict(raw_metadata.get("ss_dataset_dirs"))
        output_name = self._string_or_empty(raw_metadata.get("ss_output_name", ""))
        total_image_count = self._coerce_int(raw_metadata.get("ss_num_train_images"))

        primary_tags = []
        at_tags = []
        for dataset_name, tags in tag_frequency.items():
            if not isinstance(tags, dict) or not tags:
                continue

            expected_count = self._extract_expected_count(
                dataset_name=dataset_name,
                dataset_dirs=dataset_dirs,
                total_image_count=total_image_count,
                dataset_count=len(tag_frequency),
            )
            best_tag = self._select_primary_tag_from_dataset(
                dataset_name=dataset_name,
                tags=tags,
                expected_count=expected_count,
                output_name=output_name,
            )
            if best_tag:
                primary_tags.append(best_tag)
                if best_tag.startswith("@"):
                    at_tags.append(best_tag)

        primary_tags = self._dedupe_preserve_order(primary_tags)
        if len(primary_tags) >= 4 and len(at_tags) >= 4:
            return [self.STYLE_PLACEHOLDER]

        return primary_tags

    def _extract_expected_count(
        self,
        dataset_name,
        dataset_dirs,
        total_image_count,
        dataset_count,
    ):
        dataset_info = dataset_dirs.get(dataset_name, {})
        if isinstance(dataset_info, dict):
            image_count = self._coerce_int(dataset_info.get("img_count"))
            if image_count is not None:
                return image_count

        if dataset_count == 1:
            return total_image_count

        return None

    def _select_primary_tag_from_dataset(self, dataset_name, tags, expected_count, output_name):
        best_tag = ""
        best_score = None

        for raw_tag, raw_count in tags.items():
            tag = self._string_or_empty(raw_tag)
            count = self._coerce_int(raw_count)
            if not tag or count is None:
                continue

            score = self._score_trigger_candidate(
                candidate=tag,
                count=count,
                dataset_name=dataset_name,
                expected_count=expected_count,
                output_name=output_name,
            )
            rank = (score, count, len(tag))
            if best_score is None or rank > best_score:
                best_tag = tag
                best_score = rank

        return best_tag

    def _score_trigger_candidate(
        self,
        candidate,
        count,
        dataset_name,
        expected_count,
        output_name,
    ):
        normalized_candidate = self._normalize_token(candidate)
        normalized_dataset = self._normalize_dataset_name(dataset_name)
        normalized_output = self._normalize_token(output_name)

        score = int(count)

        if candidate.startswith("@"):
            score += 100000
        if expected_count is not None and count == expected_count:
            score += 50000
        if normalized_dataset and normalized_candidate:
            if normalized_candidate in normalized_dataset:
                score += 30000
            if normalized_dataset in normalized_candidate:
                score += 20000
        if normalized_output and normalized_candidate:
            if normalized_candidate in normalized_output:
                score += 10000
        if normalized_candidate in self.GENERIC_TAGS:
            score -= 20000
        if candidate.startswith("|||"):
            score -= 10000

        return score

    def _normalize_dataset_name(self, text):
        text = re.sub(r"^\d+[_\-\s]*", "", self._string_or_empty(text))
        return self._normalize_token(text)

    def _normalize_token(self, text):
        text = self._string_or_empty(text).lower().replace("_", " ").replace("-", " ")
        text = re.sub(r"[^0-9a-z@ ]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _parse_json_dict(self, value):
        if value is None:
            return {}

        if isinstance(value, dict):
            return value

        text = self._string_or_empty(value)
        if not text:
            return {}

        try:
            decoded = json.loads(text)
        except Exception:
            return {}

        return decoded if isinstance(decoded, dict) else {}

    def _pick_better_metadata(
        self,
        current_metadata,
        current_label,
        candidate_metadata,
        candidate_label,
        lora_path,
        require_images,
    ):
        if candidate_metadata is None:
            return current_metadata, current_label
        if current_metadata is None:
            return candidate_metadata, candidate_label
        if require_images:
            current_score = self._score_image_metadata(current_metadata)
            candidate_score = self._score_image_metadata(candidate_metadata)
        else:
            current_score = self._score_trained_word_set(
                self._extract_trained_words(current_metadata),
                lora_path,
            )
            candidate_score = self._score_trained_word_set(
                self._extract_trained_words(candidate_metadata),
                lora_path,
            )
        if candidate_score > current_score:
            return candidate_metadata, candidate_label
        return current_metadata, current_label

    def _should_prefer_fallback(self, local_words, fallback_words, lora_path):
        local_score = self._score_trained_word_set(local_words, lora_path)
        fallback_score = self._score_trained_word_set(fallback_words, lora_path)
        return fallback_score > local_score

    def _should_attempt_fallback_for_metadata(self, metadata, lora_path, require_images):
        if metadata is None:
            return True
        if require_images:
            return self._score_image_metadata(metadata) <= 0
        return self._should_attempt_fallback_for_words(
            self._extract_trained_words(metadata),
            lora_path,
        )

    def _should_attempt_fallback_for_words(self, trained_words, lora_path):
        score = self._score_trained_word_set(trained_words, lora_path)
        return score < self.FALLBACK_SCORE_THRESHOLD

    def _score_trained_word_set(self, trained_words, lora_path):
        if not trained_words:
            return -1

        return max(
            self._score_trigger_phrase_candidate(candidate, lora_path)
            for candidate in trained_words
        )

    def _score_trigger_phrase_candidate(self, candidate, lora_path):
        text = self._string_or_empty(candidate)
        if not text:
            return -1

        score = len(text)
        normalized_candidate = self._normalize_token(text)
        filename_hint = self._normalize_token(Path(lora_path).stem)

        parts = [part.strip() for part in text.split(",") if part.strip()]
        score += len(parts) * 50
        if text.startswith("@"):
            score += 250
        if text == self.STYLE_PLACEHOLDER:
            score += 500
        if filename_hint and normalized_candidate == filename_hint:
            score -= 200
        elif filename_hint and normalized_candidate and normalized_candidate in filename_hint:
            score -= 75
        if normalized_candidate in self.GENERIC_TAGS:
            score -= 150
        if re.search(r"[A-Z].*[a-z]|[a-z].*[A-Z]", text):
            score -= 25

        return score

    def _score_image_metadata(self, metadata):
        civitai_section = self._get_civitai_section(metadata)
        images = civitai_section.get("images", []) if civitai_section else []
        valid_images = [image for image in images if image.get("meta")]
        if not valid_images:
            return -1

        prompts = 0
        for image in valid_images:
            prompt = self._string_or_empty(image.get("meta", {}).get("prompt", ""))
            if prompt:
                prompts += 1
        return prompts

    def _get_civitai_section(self, metadata):
        if not isinstance(metadata, dict):
            return {}

        civitai_section = metadata.get("civitai")
        if isinstance(civitai_section, dict):
            return civitai_section

        return metadata

    def _build_filename_fallback_metadata(self, lora_path):
        fallback_candidates = self._build_filename_fallback_candidates(lora_path)
        if not fallback_candidates:
            return None

        return {
            "civitai": {
                "trainedWords": fallback_candidates,
            },
            "_filename_fallback": True,
        }

    def _build_filename_fallback_candidates(self, lora_path):
        stem = Path(lora_path).stem
        candidate = stem.replace("_", " ").replace("-", " ")
        candidate = re.sub(r"\b(?:epoch|step)\s*\d+\b", " ", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\bv?\d+(?:\.\d+)*\b", " ", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,._-")

        if not candidate:
            return []

        return [candidate]

    def _load_civitai_metadata_by_hash(self, lora_path):
        cache = self._load_civitai_cache()
        sha256_hash = self._calculate_sha256(lora_path)

        if sha256_hash in cache:
            return self._normalize_civitai_payload(cache[sha256_hash])

        api_url = f"https://civitai.com/api/v1/model-versions/by-hash/{sha256_hash}"
        request_obj = request.Request(
            api_url,
            headers={
                "User-Agent": "LoraLoader-with-trigger-word/0.1",
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(request_obj, timeout=10) as response:
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
        return self._normalize_civitai_payload(payload)

    def _extract_trained_words(self, metadata):
        if not metadata:
            return []

        civitai_section = self._get_civitai_section(metadata)
        trained_words = civitai_section.get("trainedWords", []) if civitai_section else []
        if not trained_words:
            return []

        output = []
        for item in trained_words:
            cleaned = self._string_or_empty(item)
            if cleaned:
                output.append(cleaned)
        return self._dedupe_preserve_order(output)

    def _normalize_civitai_payload(self, payload):
        if not isinstance(payload, dict):
            return None
        if isinstance(payload.get("civitai"), dict):
            return payload
        if "trainedWords" in payload or "images" in payload:
            return {
                "civitai": payload,
                "_civitai_raw": payload,
            }
        return payload

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
        message = f"{PREVIEW_PREFIX} {lora_name}: {reason}"
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

    def _coerce_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _dedupe_preserve_order(self, values):
        output = []
        seen = set()
        for value in values:
            key = value.lower()
            if key not in seen:
                output.append(value)
                seen.add(key)
        return output
