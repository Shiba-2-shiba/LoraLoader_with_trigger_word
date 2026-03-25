"""Civitai API client helpers."""

from __future__ import annotations

import json
from urllib import error, request


class CivitaiMetadataClient:
    BASE_URL = "https://civitai.com/api/v1"
    USER_AGENT = "LoraLoader-with-trigger-word/0.1"

    def fetch_model_version_by_hash(self, sha256_hash):
        api_url = f"{self.BASE_URL}/model-versions/by-hash/{sha256_hash}"
        request_obj = request.Request(
            api_url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(request_obj, timeout=10) as response:
                if response.status != 200:
                    return None, f"Civitai by-hash request returned HTTP {response.status}"
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            return None, f"Civitai by-hash request failed: {exc}"
        except Exception as exc:
            return None, f"Failed to parse Civitai by-hash response: {exc}"

        return payload, None
