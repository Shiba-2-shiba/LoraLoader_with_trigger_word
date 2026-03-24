"""Shared constants for the LoRA loader custom node package."""

NODE_ID = "LoraLoaderModelOnlyTriggerWords"
NODE_DISPLAY_NAME = "Load LoRA + Trigger Words (Model Only)"
NODE_CATEGORY = "loaders/lora"

PREVIEW_ROUTE = "/lora_loader_with_trigger_word/preview"
PREVIEW_PREFIX = "[LoRA Trigger Words]"

TRIGGER_WORD_SOURCES = (
    "json_combined",
    "json_random",
    "json_sample_prompt",
    "metadata",
)
