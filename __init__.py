"""
ComfyUI custom node package entrypoint.
"""

from typing_extensions import override

from comfy_api.latest import ComfyExtension

from .lora_loader_model_only_trigger_words import LoraLoaderModelOnlyTriggerWordsNode


class LoraLoaderWithTriggerWordExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[LoraLoaderModelOnlyTriggerWordsNode]]:
        return [LoraLoaderModelOnlyTriggerWordsNode]


async def comfy_entrypoint() -> LoraLoaderWithTriggerWordExtension:
    return LoraLoaderWithTriggerWordExtension()


WEB_DIRECTORY = "./web"


__all__ = ["comfy_entrypoint", "WEB_DIRECTORY"]
