"""Genur gallery API client helpers."""

from __future__ import annotations

import json
from urllib import error, parse, request


class GenurGalleryClient:
    BASE_URL = "https://genur.art/api"
    USER_AGENT = "LoraLoader-with-trigger-word/0.1"

    def fetch_model_gallery(self, model_version_id, *, is_nsfw=None, sort="top"):
        params = {
            "model_version_id": str(model_version_id),
            "sort": sort,
        }
        if is_nsfw is not None:
            params["is_nsfw"] = "true" if is_nsfw else "false"
        return self._request_json(f"/search?{parse.urlencode(params)}")

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
                    return None, f"Genur gallery request returned HTTP {response.status}"
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            return None, f"Genur gallery request failed: {exc}"
        except Exception as exc:
            return None, f"Failed to parse Genur gallery response: {exc}"

        return payload, None
