"""Preview and browse APIs for the frontend extension."""

import server
from aiohttp import web

from .constants import BROWSE_ROUTE, PREVIEW_PREFIX, PREVIEW_ROUTE
from .services import trigger_word_resolver


def _coerce_downstream_trigger_words(text):
    cleaned = str(text or "").strip()
    if cleaned.startswith(PREVIEW_PREFIX):
        return ""
    return cleaned


@server.PromptServer.instance.routes.post(PREVIEW_ROUTE)
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
                    "trigger_words": f"{PREVIEW_PREFIX} LoRA が選択されていません。",
                },
                status=400,
            )

        raw_trigger_words = trigger_word_resolver.resolve(
            lora_name=lora_name,
            trigger_word_source=trigger_word_source,
            enable_civitai_fallback=enable_civitai_fallback,
        )
        return web.json_response(
            {
                "success": not str(raw_trigger_words).startswith(PREVIEW_PREFIX),
                "trigger_words": raw_trigger_words,
                "raw_trigger_words": raw_trigger_words,
                "downstream_trigger_words": _coerce_downstream_trigger_words(raw_trigger_words),
            }
        )
    except Exception as exc:
        message = f"{PREVIEW_PREFIX} preview 取得エラー: {exc}"
        print(message)
        return web.json_response(
            {
                "success": False,
                "trigger_words": message,
            },
            status=500,
        )


@server.PromptServer.instance.routes.post(BROWSE_ROUTE)
async def browse_model_card(request):
    try:
        payload = await request.json()
        lora_name = payload.get("lora_name", "")
        enable_civitai_fallback = bool(payload.get("enable_civitai_fallback", False))

        if not lora_name:
            return web.json_response(
                {
                    "success": False,
                    "display_text": "[Browse] LoRA が選択されていません。",
                },
                status=400,
            )

        result = trigger_word_resolver.resolve_model_card(
            lora_name=lora_name,
            enable_civitai_fallback=enable_civitai_fallback,
        )
        return web.json_response(result)
    except Exception as exc:
        message = f"[Browse] model card 取得エラー: {exc}"
        print(message)
        return web.json_response(
            {
                "success": False,
                "display_text": message,
            },
            status=500,
        )
