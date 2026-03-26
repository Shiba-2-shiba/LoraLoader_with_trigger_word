"""Compatibility module for the LoRA + CLIP trigger word node."""

from .node_definition import LoraLoaderTriggerWordsNode
from .preview_api import preview_trigger_words

__all__ = ["LoraLoaderTriggerWordsNode", "preview_trigger_words"]
