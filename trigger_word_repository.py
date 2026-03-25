"""Trigger word metadata loading helpers."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

try:
    from safetensors.torch import safe_open

    SAFETENSORS_AVAILABLE = True
except ImportError:
    SAFETENSORS_AVAILABLE = False

try:
    from .trigger_word_analyzer import TriggerWordAnalyzer
    from .remote_metadata import GenurGalleryClient
    from .remote_metadata.providers import (
        CivitaiMetadataProvider,
        CivArchiveMetadataProvider,
    )
except ImportError:
    from trigger_word_analyzer import TriggerWordAnalyzer
    from remote_metadata import GenurGalleryClient
    from remote_metadata.providers import (
        CivitaiMetadataProvider,
        CivArchiveMetadataProvider,
    )


class TriggerWordMetadataRepository:
    CACHE_FILENAME = "civitai_model_info_cache.json"
    HUGGINGFACE_REFERENCE_CATALOG = os.path.join(
        os.path.dirname(__file__),
        "reference_metadata",
        "huggingface_lora_catalog.json",
    )

    def __init__(
        self,
        analyzer: TriggerWordAnalyzer | None = None,
        civitai_provider: CivitaiMetadataProvider | None = None,
        civarchive_provider: CivArchiveMetadataProvider | None = None,
        genur_client: GenurGalleryClient | None = None,
    ):
        self._analyzer = analyzer or TriggerWordAnalyzer()
        self._civitai_provider = civitai_provider or CivitaiMetadataProvider(
            cache_path=os.path.join(os.path.dirname(__file__), self.CACHE_FILENAME),
            warn_handler=self._warn,
        )
        self._civarchive_provider = civarchive_provider or CivArchiveMetadataProvider(
            cache_path=os.path.join(os.path.dirname(__file__), "civarchive_model_info_cache.json"),
            warn_handler=self._warn,
        )
        self._genur_client = genur_client or GenurGalleryClient()
        self._huggingface_reference_catalog_cache = None

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
        raw_metadata = self._read_safetensors_metadata(lora_path)

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

    def load_huggingface_reference_metadata(self, lora_path):
        raw_metadata = self._read_safetensors_metadata(lora_path)
        if not raw_metadata:
            return None

        catalog = self._load_huggingface_reference_catalog()
        if not catalog:
            return None

        candidates = self._build_reference_match_candidates(lora_path, raw_metadata)
        if not candidates:
            return None

        for entry in catalog:
            if not isinstance(entry, dict):
                continue
            if self._reference_entry_matches(entry, candidates):
                return self._build_huggingface_reference_payload(entry)

        return None

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
        payload = self._civitai_provider.load_metadata_by_hash(lora_path)
        return self.normalize_civitai_payload(payload)

    def load_civarchive_metadata_by_hash(self, lora_path):
        payload = self._civarchive_provider.load_metadata_by_hash(lora_path)
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

    def build_model_card(self, metadata):
        metadata = self.normalize_civitai_payload(metadata)
        if not isinstance(metadata, dict):
            return None

        civitai_section = self._analyzer.get_civitai_section(metadata)
        if not civitai_section:
            return None

        direct_url = self._extract_model_card_url(metadata, civitai_section)
        parsed_url_model_id, parsed_url_version_id = self._parse_model_card_url(direct_url)
        parsed_air_model_id, parsed_air_version_id = self._parse_civitai_air(
            self._analyzer.string_or_empty(civitai_section.get("air") or metadata.get("air"))
        )
        model_id = self._coerce_int(
            civitai_section.get("civitai_model_id")
            or civitai_section.get("modelId")
            or ((civitai_section.get("model") or {}).get("id"))
            or ((metadata.get("model") or {}).get("id"))
            or metadata.get("modelId")
            or parsed_url_model_id
            or parsed_air_model_id
        )
        version_id = self._coerce_int(
            civitai_section.get("civitai_model_version_id")
            or civitai_section.get("modelVersionId")
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

        prefer_civarchive = self._is_civarchive_model_card(metadata, civitai_section)
        primary_url = direct_url or self._build_model_card_url(
            model_id,
            version_id,
            prefer_civarchive=prefer_civarchive,
        )
        civarchive_url = self._extract_civarchive_url(metadata, civitai_section)
        if not civarchive_url and prefer_civarchive:
            civarchive_url = self._build_model_card_url(
                model_id,
                version_id,
                prefer_civarchive=True,
            )

        civitai_model_id = self._coerce_int(civitai_section.get("civitai_model_id") or model_id)
        civitai_version_id = self._coerce_int(
            civitai_section.get("civitai_model_version_id") or version_id
        )
        civitai_url = self._extract_civitai_url(metadata, civitai_section)
        if not civitai_url and civitai_model_id is not None:
            civitai_url = self._build_model_card_url(
                civitai_model_id,
                civitai_version_id,
                prefer_civarchive=False,
            )

        model_name = self._analyzer.string_or_empty(
            ((civitai_section.get("model") or {}).get("name"))
            or ((metadata.get("model") or {}).get("name"))
            or metadata.get("model_name")
        )
        version_name = self._analyzer.string_or_empty(
            civitai_section.get("name") or metadata.get("name")
        )

        return {
            "primary_url": primary_url,
            "civitai_url": civitai_url or None,
            "civarchive_url": civarchive_url or None,
            "alternate_urls": {
                "civitai": civitai_url or None,
                "civarchive": civarchive_url or None,
            },
            "model_id": str(model_id),
            "version_id": str(version_id) if version_id is not None else None,
            "civitai_model_id": str(civitai_model_id) if civitai_model_id is not None else None,
            "civitai_version_id": (
                str(civitai_version_id) if civitai_version_id is not None else None
            ),
            "model_name": model_name or None,
            "version_name": version_name or None,
            "url_source": "civarchive" if self._is_civarchive_url(primary_url) else "civitai",
        }

    def build_model_card_details(self, metadata):
        metadata = self.normalize_civitai_payload(metadata)
        card = self.build_model_card(metadata)
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
        image_items = self._build_image_items(civitai_section.get("images") or [])
        if not image_items:
            image_items = self._load_genur_gallery_images(card, metadata)

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

    def _build_image_items(self, images):
        image_items = []
        for image in images:
            if not isinstance(image, dict):
                continue
            media_type = self._normalize_media_type(image)
            media_url = self._extract_media_url(image, media_type)
            if not media_url:
                continue
            meta = image.get("meta") if isinstance(image.get("meta"), dict) else {}
            prompt = self._analyzer.string_or_empty(meta.get("prompt") or image.get("prompt"))
            poster_url = self._extract_media_poster_url(image, media_type)
            image_items.append(
                {
                    "url": media_url,
                    "width": self._coerce_int(image.get("width")),
                    "height": self._coerce_int(image.get("height")),
                    "media_type": media_type,
                    "poster_url": poster_url or None,
                    "prompt": prompt or None,
                }
            )
            if len(image_items) >= 12:
                break
        return image_items

    def _load_genur_gallery_images(self, card, metadata):
        civitai_section = self._get_civitai_section(metadata) or {}
        civitai_version_id = self._coerce_int(
            card.get("civitai_version_id")
            or civitai_section.get("civitai_model_version_id")
            or metadata.get("civitai_model_version_id")
        )
        if civitai_version_id is None:
            return []

        nsfw_level = self._coerce_int(
            civitai_section.get("nsfwLevel")
            or metadata.get("nsfwLevel")
            or ((civitai_section.get("model") or {}).get("nsfwLevel"))
            or ((metadata.get("model") or {}).get("nsfwLevel"))
        )
        is_nsfw = None if nsfw_level is None else nsfw_level > 0

        payload, warning_message = self._genur_client.fetch_model_gallery(
            civitai_version_id,
            is_nsfw=is_nsfw,
        )
        if payload is None:
            if warning_message:
                self._warn(warning_message)
            return []

        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list):
            return []

        return self._build_image_items(results)

    def build_civitai_model_card(self, metadata):
        return self.build_model_card(metadata)

    def build_civitai_model_card_details(self, metadata):
        return self.build_model_card_details(metadata)

    def calculate_sha256(self, file_path):
        return self._civitai_provider.calculate_sha256(file_path)

    def load_civitai_cache(self):
        return self._civitai_provider.load_cache()

    def save_civitai_cache(self, cache):
        self._civitai_provider.save_cache(cache)

    def get_cache_path(self):
        return self._civitai_provider.get_cache_path()

    def _read_safetensors_metadata(self, lora_path):
        if not SAFETENSORS_AVAILABLE:
            return None

        try:
            with safe_open(lora_path, framework="pt", device="cpu") as file:
                return file.metadata()
        except Exception:
            return None

    def _normalize_huggingface_sidecar_payload(self, payload, text_sidecar=None):
        if not isinstance(payload, dict):
            return None

        huggingface_keys = {
            "activation text",
            "sd version",
            "preferred weight",
            "negative text",
            "notes",
        }
        if not (huggingface_keys & set(payload.keys())):
            return None

        activation_text = self._analyzer.string_or_empty(payload.get("activation text"))
        description = self._analyzer.string_or_empty(payload.get("description"))
        notes = self._analyzer.string_or_empty(payload.get("notes"))
        negative_text = self._analyzer.string_or_empty(payload.get("negative text"))
        sd_version = self._analyzer.string_or_empty(payload.get("sd version"))
        text_body = self._analyzer.string_or_empty(text_sidecar)

        normalized = {
            "civitai": {
                "trainedWords": [activation_text] if activation_text else [],
            },
            "description": text_body or description or None,
            "baseModel": sd_version or None,
            "_huggingface_sidecar_raw": payload,
            "_huggingface_text_sidecar": text_body or None,
        }

        if notes:
            normalized["notes"] = notes
        if negative_text:
            normalized["negative_text"] = negative_text

        return normalized

    def _load_huggingface_reference_catalog(self):
        if self._huggingface_reference_catalog_cache is not None:
            return self._huggingface_reference_catalog_cache

        path = self.HUGGINGFACE_REFERENCE_CATALOG
        if not os.path.exists(path):
            self._huggingface_reference_catalog_cache = []
            return self._huggingface_reference_catalog_cache
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except Exception as exc:
            self._warn(f"Failed to load Hugging Face reference catalog {path}: {exc}")
            self._huggingface_reference_catalog_cache = []
            return self._huggingface_reference_catalog_cache

        if isinstance(payload, dict):
            entries = payload.get("entries")
            self._huggingface_reference_catalog_cache = entries if isinstance(entries, list) else []
            return self._huggingface_reference_catalog_cache
        self._huggingface_reference_catalog_cache = payload if isinstance(payload, list) else []
        return self._huggingface_reference_catalog_cache

    def _build_reference_match_candidates(self, lora_path, raw_metadata):
        candidates = [
            self._analyzer.string_or_empty(raw_metadata.get("ss_output_name")),
            self._analyzer.string_or_empty(raw_metadata.get("modelspec.title")),
            Path(lora_path).stem,
        ]
        return {
            self._analyzer.normalize_token(candidate)
            for candidate in candidates
            if self._analyzer.normalize_token(candidate)
        }

    def _reference_entry_matches(self, entry, candidates):
        reference_keys = [
            entry.get("model_key"),
            *(entry.get("aliases") or []),
        ]
        normalized_keys = {
            self._analyzer.normalize_token(key)
            for key in reference_keys
            if self._analyzer.normalize_token(key)
        }
        return bool(candidates & normalized_keys)

    def _build_huggingface_reference_payload(self, entry):
        payload = self._normalize_huggingface_sidecar_payload(
            {
                "description": entry.get("description"),
                "sd version": entry.get("sd_version"),
                "activation text": entry.get("activation_text"),
                "preferred weight": entry.get("preferred_weight", 0),
                "negative text": entry.get("negative_text"),
                "notes": entry.get("notes"),
            },
            text_sidecar=entry.get("text_body"),
        )
        if payload is None:
            return None

        payload["model_name"] = entry.get("model_key") or payload.get("model_name")
        payload["_huggingface_reference"] = {
            "source": entry.get("source"),
            "model_key": entry.get("model_key"),
            "aliases": entry.get("aliases") or [],
        }
        return payload

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

    def _extract_model_card_url(self, metadata, civitai_section):
        return self._extract_civarchive_url(metadata, civitai_section) or self._extract_civitai_url(
            metadata,
            civitai_section,
        )

    def _extract_civarchive_url(self, metadata, civitai_section):
        meta_section = civitai_section.get("meta") if isinstance(civitai_section.get("meta"), dict) else {}
        metadata_meta = metadata.get("meta") if isinstance(metadata.get("meta"), dict) else {}
        for candidate in (
            civitai_section.get("archiveUrl"),
            civitai_section.get("civarchiveUrl"),
            civitai_section.get("canonicalUrl"),
            meta_section.get("canonical"),
            metadata.get("archiveUrl"),
            metadata.get("civarchiveUrl"),
            metadata.get("canonicalUrl"),
            metadata_meta.get("canonical"),
        ):
            text = self._analyzer.string_or_empty(candidate)
            if self._is_civarchive_url(text):
                return text
        return None

    def _extract_civitai_url(self, metadata, civitai_section):
        for candidate in (
            civitai_section.get("url"),
            civitai_section.get("platform_url"),
            civitai_section.get("modelUrl"),
            civitai_section.get("modelCardUrl"),
            civitai_section.get("civitaiUrl"),
            metadata.get("url"),
            metadata.get("platform_url"),
            metadata.get("modelUrl"),
            metadata.get("modelCardUrl"),
            metadata.get("civitaiUrl"),
        ):
            text = self._analyzer.string_or_empty(candidate)
            if self._is_civitai_url(text):
                return text
        return None

    def _parse_model_card_url(self, url):
        text = self._analyzer.string_or_empty(url)
        if not text:
            return None, None

        model_match = re.search(r"/models/(\d+)", text)
        version_match = re.search(r"[?&]modelVersionId=(\d+)", text)
        model_id = self._coerce_int(model_match.group(1)) if model_match else None
        version_id = self._coerce_int(version_match.group(1)) if version_match else None
        return model_id, version_id

    def _build_model_card_url(self, model_id, version_id, prefer_civarchive):
        base_url = "https://civarchive.com/models" if prefer_civarchive else "https://civitai.com/models"
        url = f"{base_url}/{model_id}"
        if version_id is not None:
            url += f"?modelVersionId={version_id}"
        return url

    def _is_civarchive_model_card(self, metadata, civitai_section):
        if self._extract_civarchive_url(metadata, civitai_section):
            return True
        source = self._analyzer.string_or_empty(civitai_section.get("source") or metadata.get("source"))
        return source == "civarchive"

    def _is_civarchive_url(self, url):
        text = self._analyzer.string_or_empty(url)
        return text.startswith("https://civarchive.com/models/")

    def _is_civitai_url(self, url):
        text = self._analyzer.string_or_empty(url)
        return text.startswith("https://civitai.com/models/")

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

    def _normalize_media_type(self, image):
        explicit_type = self._analyzer.string_or_empty(image.get("type")).lower()
        if explicit_type in {"image", "video"}:
            return explicit_type
        if self._analyzer.string_or_empty(image.get("video_url")):
            return "video"

        media_url = self._analyzer.string_or_empty(
            image.get("url") or image.get("image_url") or image.get("video_url")
        ).lower()
        if any(token in media_url for token in (".mp4", ".webm", ".mov", ".m4v")):
            return "video"
        return "image"

    def _extract_media_url(self, image, media_type):
        candidates = []
        if media_type == "video":
            candidates.extend((image.get("video_url"), image.get("url"), image.get("image_url")))
        else:
            candidates.extend((image.get("image_url"), image.get("url"), image.get("video_url")))

        for candidate in candidates:
            text = self._analyzer.string_or_empty(candidate)
            if text:
                return text
        return None

    def _extract_media_poster_url(self, image, media_type):
        if media_type != "video":
            return None
        for candidate in (image.get("image_url"), image.get("thumbnail_url")):
            text = self._analyzer.string_or_empty(candidate)
            if text:
                return text
        return None

    def _get_civitai_section(self, metadata):
        if not isinstance(metadata, dict):
            return None
        civitai_section = metadata.get("civitai")
        return civitai_section if isinstance(civitai_section, dict) else None

    def _coerce_int(self, value):
        return self._analyzer.coerce_int(value)


