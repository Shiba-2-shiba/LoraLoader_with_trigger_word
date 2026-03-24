"""Shared service instances for the custom node package."""

from .lora_model_loader import CachedLoraModelLoader
from .trigger_word_resolver import TriggerWordResolver

lora_model_loader = CachedLoraModelLoader()
trigger_word_resolver = TriggerWordResolver()
