"""Trigger word metadata loading helpers."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from pathlib import Path
from urllib import error, request

try:
    from safetensors.torch import safe_open

    SAFETENSORS_AVAILABLE = True
except ImportError:
    SAFETENSORS_AVAILABLE = False

try:
    from .trigger_word_analyzer import TriggerWordAnalyzer
except ImportError:
    from trigger_word_analyzer import TriggerWordAnalyzer


class TriggerWordMetadataRepository:
    CACHE_FILENAME = "civitai_model_info_cache.json"

    def __init__(self, analyzer: TriggerWordAnalyzer | None = None):
        self._analyzer = analyzer or TriggerWordAnalyzer()

    def load_json_metadata(self, lora_path):
        base_path = os.path.splitext(lora_path)[0]
        loaded_metadata = None

        for candidate_path in (f"{base_path}.metadata.json", f"{base_path}.info"):
            if not os.path.exists(candidate_path):
                continue

            try:
                with open(candidate_path, "r", encoding="utf-8") as file:
                    payload = self.normalize_civitai_payload(json.load(file))
            except Exception as exc:
                self._warn(f"Failed to load {candidate_path}: {exc}")
                continue

            loaded_metadata = self._merge_metadata_documents(loaded_metadata, payload)

        return loaded_metadata

    def load_embedded_metadata(self, lora_path):
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
        trained_words.extend(self._analyzer.extract_direct_trigger_words(raw_metadata))
        trained_words.extend(self._analyzer.extract_trigger_words_from_tag_frequency(raw_metadata))
        trained_words = self._analyzer.dedupe_preserve_order(trained_words)

        civitai_format = {"civitai": {}, "_embedded_raw_metadata": raw_metadata}

        if trained_words:
            civitai_format["civitai"]["trainedWords"] = trained_words

        model_name = self._analyzer.string_or_empty(raw_metadata.get("ss_output_name", ""))
        if model_name:
            civitai_format["model_name"] = model_name

        return civitai_format if civitai_format["civitai"] or model_name else None

    def build_filename_fallback_metadata(self, lora_path):
        fallback_candidates = self.build_filename_fallback_candidates(lora_path)
        if not fallback_candidates:
            return None

        return {
            "civitai": {
                "trainedWords": fallback_candidates,
            },
            "_filename_fallback": True,
        }

    def build_filename_fallback_candidates(self, lora_path):
        stem = Path(lora_path).stem
        candidate = stem.replace("_", " ").replace("-", " ")
        candidate = re.sub(r"\b(?:epoch|step)\s*\d+\b", " ", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\bv?\d+(?:\.\d+)*\b", " ", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,._-")

        if not candidate:
            return []

        return [candidate]

    def load_civitai_metadata_by_hash(self, lora_path):
        cache = self.load_civitai_cache()
        sha256_hash = self.calculate_sha256(lora_path)

        if sha256_hash in cache:
            return self.normalize_civitai_payload(cache[sha256_hash])

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
                    self._warn(f"Civitai by-hash request returned HTTP {response.status}")
                    return None
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            self._warn(f"Civitai by-hash request failed: {exc}")
            return None
        except Exception as exc:
            self._warn(f"Failed to parse Civitai by-hash response: {exc}")
            return None

        cache[sha256_hash] = payload
        self.save_civitai_cache(cache)
        return self.normalize_civitai_payload(payload)

    def normalize_civitai_payload(self, payload):
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

    def build_civitai_model_card(self, metadata):
        metadata = self.normalize_civitai_payload(metadata)
        if not isinstance(metadata, dict):
            return None

        civitai_section = self._analyzer.get_civitai_section(metadata)
        if not civitai_section:
            return None

        direct_url = self._extract_civitai_url(metadata, civitai_section)
        parsed_url_model_id, parsed_url_version_id = self._parse_civitai_url(direct_url)
        parsed_air_model_id, parsed_air_version_id = self._parse_civitai_air(
            self._analyzer.string_or_empty(civitai_section.get("air") or metadata.get("air"))
        )
        model_id = self._coerce_int(
            civitai_section.get("modelId")
            or ((civitai_section.get("model") or {}).get("id"))
            or ((metadata.get("model") or {}).get("id"))
            or metadata.get("modelId")
            or parsed_url_model_id
            or parsed_air_model_id
        )
        version_id = self._coerce_int(
            civitai_section.get("modelVersionId")
            or civitai_section.get("id")
            or ((civitai_section.get("modelVersion") or {}).get("id"))
            or metadata.get("id")
            or metadata.get("modelVersionId")
            or ((metadata.get("modelVersion") or {}).get("id"))
            or parsed_url_version_id
            or parsed_air_version_id
        )
        if model_id is None:
            return None

        civitai_url = direct_url or f"https://civitai.com/models/{model_id}"
        if direct_url is None and version_id is not None:
            civitai_url += f"?modelVersionId={version_id}"

        model_name = self._analyzer.string_or_empty(
            ((civitai_section.get("model") or {}).get("name"))
            or ((metadata.get("model") or {}).get("name"))
            or metadata.get("model_name")
        )
        version_name = self._analyzer.string_or_empty(
            civitai_section.get("name") or metadata.get("name")
        )

        return {
            "civitai_url": civitai_url,
            "model_id": str(model_id),
            "version_id": str(version_id) if version_id is not None else None,
            "model_name": model_name or None,
            "version_name": version_name or None,
        }

    def build_civitai_model_card_details(self, metadata):
        metadata = self.normalize_civitai_payload(metadata)
        card = self.build_civitai_model_card(metadata)
        if not card:
            return None

        civitai_section = self._analyzer.get_civitai_section(metadata)
        trained_words = self._analyzer.dedupe_preserve_order(
            [
                self._analyzer.string_or_empty(item)
                for item in (civitai_section.get("trainedWords") or [])
                if self._analyzer.string_or_empty(item)
            ]
        )
        image_items = []
        for image in civitai_section.get("images") or []:
            if not isinstance(image, dict):
                continue
            image_url = self._analyzer.string_or_empty(image.get("url"))
            if not image_url:
                continue
            meta = image.get("meta") if isinstance(image.get("meta"), dict) else {}
            prompt = self._analyzer.string_or_empty(meta.get("prompt"))
            image_items.append(
                {
                    "url": image_url,
                    "width": self._coerce_int(image.get("width")),
                    "height": self._coerce_int(image.get("height")),
                    "prompt": prompt or None,
                }
            )
            if len(image_items) >= 12:
                break

        model_type = self._analyzer.string_or_empty(
            ((civitai_section.get("model") or {}).get("type")) or metadata.get("type")
        )
        base_model = self._analyzer.string_or_empty(
            civitai_section.get("baseModel") or metadata.get("baseModel")
        )
        stats = civitai_section.get("stats") if isinstance(civitai_section.get("stats"), dict) else {}

        return {
            **card,
            "description": self._sanitize_description(
                civitai_section.get("description") or metadata.get("description")
            ),
            "trained_words": trained_words,
            "images": image_items,
            "model_type": model_type or None,
            "base_model": base_model or None,
            "download_count": self._coerce_int(stats.get("downloadCount")),
            "thumbs_up_count": self._coerce_int(stats.get("thumbsUpCount")),
        }

    def calculate_sha256(self, file_path):
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def load_civitai_cache(self):
        cache_path = self.get_cache_path()
        if not os.path.exists(cache_path):
            return {}

        try:
            with open(cache_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            self._warn(f"Failed to read Civitai cache {cache_path}: {exc}")
            return {}

        return data if isinstance(data, dict) else {}

    def save_civitai_cache(self, cache):
        cache_path = self.get_cache_path()
        try:
            with open(cache_path, "w", encoding="utf-8") as file:
                json.dump(cache, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._warn(f"Failed to write Civitai cache {cache_path}: {exc}")

    def get_cache_path(self):
        return os.path.join(os.path.dirname(__file__), self.CACHE_FILENAME)

    def _merge_metadata_documents(self, primary, secondary):
        if primary is None:
            return secondary
        if secondary is None:
            return primary
        if isinstance(primary, dict) and isinstance(secondary, dict):
            merged = dict(primary)
            for key, value in secondary.items():
                if key in merged:
                    merged[key] = self._merge_metadata_documents(merged[key], value)
                else:
                    merged[key] = value
            return merged
        if isinstance(primary, list) and isinstance(secondary, list):
            if primary and secondary and all(not isinstance(item, dict) for item in primary + secondary):
                return self._analyzer.dedupe_preserve_order(
                    [
                        self._analyzer.string_or_empty(item)
                        for item in [*primary, *secondary]
                        if self._analyzer.string_or_empty(item)
                    ]
                )
            return primary or secondary
        return primary if self._has_value(primary) else secondary

    def _has_value(self, value):
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, dict, set)):
            return bool(value)
        return True

    def _extract_civitai_url(self, metadata, civitai_section):
        for candidate in (
            civitai_section.get("url"),
            civitai_section.get("modelUrl"),
            civitai_section.get("modelCardUrl"),
            civitai_section.get("civitaiUrl"),
            metadata.get("url"),
            metadata.get("modelUrl"),
            metadata.get("modelCardUrl"),
            metadata.get("civitaiUrl"),
        ):
            text = self._analyzer.string_or_empty(candidate)
            if text.startswith("https://civitai.com/models/"):
                return text
        return None

    def _parse_civitai_url(self, url):
        text = self._analyzer.string_or_empty(url)
        if not text:
            return None, None

        model_match = re.search(r"/models/(\d+)", text)
        version_match = re.search(r"[?&]modelVersionId=(\d+)", text)
        model_id = self._coerce_int(model_match.group(1)) if model_match else None
        version_id = self._coerce_int(version_match.group(1)) if version_match else None
        return model_id, version_id

    def _parse_civitai_air(self, air_value):
        text = self._analyzer.string_or_empty(air_value)
        if not text:
            return None, None

        match = re.search(r":civitai:(\d+)@(\d+)$", text)
        if not match:
            return None, None
        return self._coerce_int(match.group(1)), self._coerce_int(match.group(2))

    def _sanitize_description(self, value):
        text = self._analyzer.string_or_empty(value)
        if not text:
            return None

        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</pre\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<li\s*>", "- ", text, flags=re.IGNORECASE)
        text = re.sub(r"</li\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() or None

    def _warn(self, message):
        print(f"[LoraLoaderModelOnlyTriggerWords] Warning: {message}")

    def _get_civitai_section(self, metadata):
        if not isinstance(metadata, dict):
            return None
        civitai_section = metadata.get("civitai")
        return civitai_section if isinstance(civitai_section, dict) else None

    def _coerce_int(self, value):
        return self._analyzer.coerce_int(value)
