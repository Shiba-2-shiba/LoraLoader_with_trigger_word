"""CivArchive API client helpers."""

from __future__ import annotations

import json
from urllib import error, parse, request


class CivArchiveMetadataClient:
    BASE_URL = "https://civarchive.com/api"
    USER_AGENT = "LoraLoader-with-trigger-word/0.1"

    def fetch_model_version_by_hash(self, sha256_hash):
        return self._request_json(f"/sha256/{sha256_hash.lower()}")

    def fetch_model_version(self, model_id, version_id=None):
        params = {}
        if version_id is not None:
            params["modelVersionId"] = str(version_id)
        query = f"?{parse.urlencode(params)}" if params else ""
        return self._request_json(f"/models/{model_id}{query}")

    def _request_json(self, path):
        request_obj = request.Request(
            f"{self.BASE_URL}{path}",
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(request_obj, timeout=10) as response:
                if response.status != 200:
                    return None, f"CivArchive request returned HTTP {response.status}"
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            return None, f"CivArchive request failed: {exc}"
        except Exception as exc:
            return None, f"Failed to parse CivArchive response: {exc}"

        return payload, None
