"""Remote metadata provider implementations."""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from copy import deepcopy

try:
    from .civarchive_client import CivArchiveMetadataClient
    from .civitai_client import CivitaiMetadataClient
except ImportError:
    from civarchive_client import CivArchiveMetadataClient
    from civitai_client import CivitaiMetadataClient


class RemoteModelMetadataProvider(ABC):
    @abstractmethod
    def load_metadata_by_hash(self, lora_path):
        """Load remote metadata using a local model file path."""


class BaseHashMetadataProvider(RemoteModelMetadataProvider):
    def __init__(
        self,
        *,
        cache_path: str | None = None,
        warn_handler=None,
    ):
        self._cache_path = cache_path or os.path.join(os.getcwd(), self.CACHE_FILENAME)
        self._warn_handler = warn_handler or (lambda message: None)

    def load_metadata_by_hash(self, lora_path):
        cache = self.load_cache()
        sha256_hash = self.calculate_sha256(lora_path)

        if sha256_hash in cache:
            return self.normalize_payload(cache[sha256_hash])

        payload, warning_message = self._fetch_metadata_by_hash(sha256_hash)
        if payload is None:
            if warning_message:
                self._warn_handler(warning_message)
            return None

        cache[sha256_hash] = payload
        self.save_cache(cache)
        return self.normalize_payload(payload)

    def calculate_sha256(self, file_path):
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def load_cache(self):
        cache_path = self.get_cache_path()
        if not os.path.exists(cache_path):
            return {}

        try:
            with open(cache_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            self._warn_handler(f"Failed to read {self.CACHE_LABEL} cache {cache_path}: {exc}")
            return {}

        return data if isinstance(data, dict) else {}

    def save_cache(self, cache):
        cache_path = self.get_cache_path()
        try:
            with open(cache_path, "w", encoding="utf-8") as file:
                json.dump(cache, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._warn_handler(f"Failed to write {self.CACHE_LABEL} cache {cache_path}: {exc}")

    def get_cache_path(self):
        return self._cache_path

    @abstractmethod
    def _fetch_metadata_by_hash(self, sha256_hash):
        """Fetch raw remote metadata using a hash string."""

    def normalize_payload(self, payload):
        return payload


class CivitaiMetadataProvider(BaseHashMetadataProvider):
    CACHE_FILENAME = "civitai_model_info_cache.json"
    CACHE_LABEL = "Civitai"

    def __init__(
        self,
        *,
        client: CivitaiMetadataClient | None = None,
        cache_path: str | None = None,
        warn_handler=None,
    ):
        super().__init__(cache_path=cache_path, warn_handler=warn_handler)
        self._client = client or CivitaiMetadataClient()

    def _fetch_metadata_by_hash(self, sha256_hash):
        return self._client.fetch_model_version_by_hash(sha256_hash)


class CivArchiveMetadataProvider(BaseHashMetadataProvider):
    CACHE_FILENAME = "civarchive_model_info_cache.json"
    CACHE_LABEL = "CivArchive"

    def __init__(
        self,
        *,
        client: CivArchiveMetadataClient | None = None,
        cache_path: str | None = None,
        warn_handler=None,
    ):
        super().__init__(cache_path=cache_path, warn_handler=warn_handler)
        self._client = client or CivArchiveMetadataClient()

    def _fetch_metadata_by_hash(self, sha256_hash):
        return self._client.fetch_model_version_by_hash(sha256_hash)

    def normalize_payload(self, payload):
        context, version_data, fallback_files = self._split_context(payload)
        normalized_version = self._transform_version(context, version_data, fallback_files)
        if normalized_version:
            return normalized_version
        return self._resolve_version_from_files(payload)

    def _resolve_version_from_files(self, payload):
        data = self._normalize_payload(payload)
        files = data.get("files") or payload.get("files") or []
        if not isinstance(files, list):
            files = [files]
        for file_data in files:
            if not isinstance(file_data, dict):
                continue
            model_id = file_data.get("model_id") or file_data.get("modelId")
            version_id = file_data.get("model_version_id") or file_data.get("modelVersionId")
            if model_id is None or version_id is None:
                continue
            version_payload, warning_message = self._client.fetch_model_version(model_id, version_id)
            if version_payload is None:
                if warning_message:
                    self._warn_handler(warning_message)
                continue
            context, version_data, fallback_files = self._split_context(version_payload)
            normalized_version = self._transform_version(context, version_data, fallback_files)
            if normalized_version:
                return normalized_version
        return None

    @staticmethod
    def _normalize_payload(payload):
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    @classmethod
    def _split_context(cls, payload):
        data = cls._normalize_payload(payload)
        context = {}
        fallback_files = []
        version = {}

        for key, value in data.items():
            if key in {"version", "model"}:
                continue
            context[key] = value

        if isinstance(data.get("version"), dict):
            version = data["version"]

        model_block = data.get("model")
        if isinstance(model_block, dict):
            for key, value in model_block.items():
                if key == "version":
                    if not version and isinstance(value, dict):
                        version = value
                    continue
                context.setdefault(key, value)
            fallback_files = fallback_files or model_block.get("files") or []

        fallback_files = fallback_files or data.get("files") or []
        return context, version, fallback_files

    @staticmethod
    def _ensure_list(value):
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]

    @staticmethod
    def _build_model_info(context):
        tags = context.get("tags")
        if not isinstance(tags, list):
            tags = list(tags) if isinstance(tags, (set, tuple)) else ([] if tags is None else [tags])
        return {
            "name": context.get("name"),
            "type": context.get("type"),
            "nsfw": bool(context.get("is_nsfw", context.get("nsfw", False))),
            "description": context.get("description"),
            "tags": tags,
        }

    @staticmethod
    def _build_creator_info(context):
        username = context.get("creator_username") or context.get("username") or ""
        image = context.get("creator_image") or context.get("creator_avatar") or ""
        creator = {
            "username": username,
            "image": image,
        }
        if context.get("creator_name"):
            creator["name"] = context["creator_name"]
        if context.get("creator_url"):
            creator["url"] = context["creator_url"]
        return creator

    @staticmethod
    def _transform_file_entry(file_data):
        mirrors = file_data.get("mirrors") or []
        if not isinstance(mirrors, list):
            mirrors = [mirrors]
        available_mirror = next(
            (
                mirror
                for mirror in mirrors
                if isinstance(mirror, dict) and mirror.get("deletedAt") is None
            ),
            None,
        )
        download_url = file_data.get("downloadUrl")
        if not download_url and available_mirror:
            download_url = available_mirror.get("url")
        name = file_data.get("name")
        if not name and available_mirror:
            name = available_mirror.get("filename")

        transformed = {
            "id": file_data.get("id"),
            "sizeKB": file_data.get("sizeKB"),
            "name": name,
            "type": file_data.get("type"),
            "downloadUrl": download_url,
            "primary": True,
            "mirrors": mirrors,
        }

        sha256 = file_data.get("sha256")
        if sha256:
            transformed["hashes"] = {"SHA256": str(sha256).upper()}
        elif isinstance(file_data.get("hashes"), dict):
            transformed["hashes"] = file_data["hashes"]

        if "metadata" in file_data:
            transformed["metadata"] = file_data["metadata"]

        if file_data.get("modelVersionId") is not None:
            transformed["modelVersionId"] = file_data.get("modelVersionId")
        elif file_data.get("model_version_id") is not None:
            transformed["modelVersionId"] = file_data.get("model_version_id")

        if file_data.get("modelId") is not None:
            transformed["modelId"] = file_data.get("modelId")
        elif file_data.get("model_id") is not None:
            transformed["modelId"] = file_data.get("model_id")

        return transformed

    def _transform_files(self, files, fallback_files=None):
        candidates = []
        if isinstance(files, list) and files:
            candidates = files
        elif isinstance(fallback_files, list):
            candidates = fallback_files

        transformed_files = []
        for file_data in candidates:
            if isinstance(file_data, dict):
                transformed_files.append(self._transform_file_entry(file_data))
        return transformed_files

    def _transform_version(self, context, version, fallback_files=None):
        if not version:
            return None

        version_copy = deepcopy(version)
        version_copy.pop("model", None)
        version_copy.pop("creator", None)

        if "trigger" in version_copy:
            triggers = version_copy.pop("trigger")
            if isinstance(triggers, list):
                version_copy["trainedWords"] = triggers
            elif triggers is None:
                version_copy["trainedWords"] = []
            else:
                version_copy["trainedWords"] = [triggers]

        if "trainedWords" in version_copy and isinstance(version_copy["trainedWords"], str):
            version_copy["trainedWords"] = [version_copy["trainedWords"]]

        if "nsfw_level" in version_copy:
            version_copy["nsfwLevel"] = version_copy.pop("nsfw_level")
        elif "nsfwLevel" not in version_copy and context.get("nsfw_level") is not None:
            version_copy["nsfwLevel"] = context.get("nsfw_level")

        stats_keys = ["downloadCount", "ratingCount", "rating"]
        stats = {key: version_copy.pop(key) for key in stats_keys if key in version_copy}
        if stats:
            version_copy["stats"] = stats

        version_copy["files"] = self._transform_files(version_copy.get("files"), fallback_files)
        version_copy["images"] = self._ensure_list(version_copy.get("images"))
        if isinstance(context.get("meta"), dict):
            version_copy["meta"] = deepcopy(context["meta"])
        if context.get("platform") is not None:
            version_copy.setdefault("platform", context.get("platform"))
        if context.get("platform_name") is not None:
            version_copy.setdefault("platform_name", context.get("platform_name"))
        version_copy["model"] = self._build_model_info(context)
        version_copy["creator"] = self._build_creator_info(context)
        version_copy["source"] = "civarchive"
        version_copy["is_deleted"] = bool(context.get("deletedAt")) or bool(version.get("deletedAt"))

        return version_copy



