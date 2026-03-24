"""Preview API for trigger word lookup in the frontend extension."""

from pathlib import PurePosixPath

import server
from aiohttp import web

from .constants import PREVIEW_PREFIX, PREVIEW_ROUTE
from .services import trigger_word_resolver


@server.PromptServer.instance.routes.post(PREVIEW_ROUTE)
async def preview_trigger_words(request):
    try:
        payload = await request.json()
        lora_name = payload.get("lora_name", "")
        trigger_word_source = payload.get("trigger_word_source", "json_combined")
        enable_civitai_fallback = bool(payload.get("enable_civitai_fallback", False))
        strength_model = _coerce_strength_model(payload.get("strength_model", 1.0))

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
        trigger_words = _format_preview_text(
            lora_name=lora_name,
            strength_model=strength_model,
            trigger_words=raw_trigger_words,
        )
        return web.json_response(
            {
                "success": True,
                "trigger_words": trigger_words,
                "raw_trigger_words": raw_trigger_words,
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


def _coerce_strength_model(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _format_preview_text(lora_name, strength_model, trigger_words):
    if not trigger_words:
        return _build_lora_tag(lora_name, strength_model)

    cleaned_trigger_words = str(trigger_words).strip()
    if cleaned_trigger_words.startswith(PREVIEW_PREFIX):
        return cleaned_trigger_words

    lora_tag = _build_lora_tag(lora_name, strength_model)
    return f"{lora_tag}, {cleaned_trigger_words}" if cleaned_trigger_words else lora_tag


def _build_lora_tag(lora_name, strength_model):
    prompt_lora_name = PurePosixPath(str(lora_name).replace("\\", "/")).with_suffix("").as_posix()
    strength_text = format(strength_model, "g")
    return f"<lora:{prompt_lora_name}:{strength_text}>"
