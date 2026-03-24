"""Trigger word metadata loading helpers."""

from __future__ import annotations

import hashlib
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

        metadata_json_path = f"{base_path}.metadata.json"
        if os.path.exists(metadata_json_path):
            try:
                with open(metadata_json_path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception as exc:
                self._warn(f"Failed to load {metadata_json_path}: {exc}")

        info_path = f"{base_path}.info"
        if os.path.exists(info_path):
            try:
                with open(info_path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception as exc:
                self._warn(f"Failed to load {info_path}: {exc}")

        return None

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

    def _warn(self, message):
        print(f"[LoraLoaderModelOnlyTriggerWords] Warning: {message}")
