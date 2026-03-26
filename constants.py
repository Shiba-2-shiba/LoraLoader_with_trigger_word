"""Shared constants for the LoRA loader custom node package."""

NODE_ID = "LoraLoaderModelOnlyTriggerWords"
NODE_DISPLAY_NAME = "Load LoRA + Trigger Words (Model Only)"
NODE_CATEGORY = "loaders/lora"

PREVIEW_ROUTE = "/lora_loader_with_trigger_word/preview"
BROWSE_ROUTE = "/lora_loader_with_trigger_word/browse"
PREVIEW_PREFIX = "[LoRA Trigger Words]"
DEFAULT_TRIGGER_WORD_SOURCE = "metadata"
ENABLE_REMOTE_METADATA_FALLBACK = True

TRIGGER_WORD_SOURCES = (
    "json_combined",
    "json_random",
    "json_sample_prompt",
    "metadata",
)
