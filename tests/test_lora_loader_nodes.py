from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "LoraLoader_with_trigger_word"


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def install_package_stub():
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(REPO_ROOT)]
    sys.modules[PACKAGE_NAME] = package


def make_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


class _IOType:
    def __init__(self, type_name: str):
        self.type_name = type_name

    def Input(self, name, **kwargs):
        return types.SimpleNamespace(name=name, type=self.type_name, **kwargs)

    def Output(self, name, **kwargs):
        return types.SimpleNamespace(name=name, type=self.type_name, **kwargs)


class _Schema:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _node_output(*values):
    return values


def install_io_stub():
    io_stub = types.SimpleNamespace(
        ComfyNode=object,
        Schema=_Schema,
        NodeOutput=_node_output,
        Model=_IOType("MODEL"),
        Clip=_IOType("CLIP"),
        Combo=_IOType("COMBO"),
        Float=_IOType("FLOAT"),
        String=_IOType("STRING"),
    )
    latest_module = make_module("comfy_api.latest", io=io_stub)
    comfy_api_module = make_module("comfy_api", latest=latest_module)
    sys.modules["comfy_api"] = comfy_api_module
    sys.modules["comfy_api.latest"] = latest_module


class LoraLoaderModuleTests(unittest.TestCase):
    def tearDown(self):
        prefixes = (
            PACKAGE_NAME,
            "folder_paths",
            "comfy",
            "comfy.sd",
            "comfy.utils",
            "comfy_api",
            "comfy_api.latest",
        )
        for name in list(sys.modules):
            if name == PACKAGE_NAME or name.startswith(f"{PACKAGE_NAME}.") or name in prefixes:
                sys.modules.pop(name, None)

    def test_cached_loader_supports_model_and_clip_and_reuses_cache(self):
        install_package_stub()

        get_full_path_or_raise = Mock(return_value=r"C:\models\loras\hero.safetensors")
        folder_paths = make_module(
            "folder_paths",
            get_full_path_or_raise=get_full_path_or_raise,
        )
        sys.modules["folder_paths"] = folder_paths

        load_torch_file = Mock(return_value={"id": "hero-lora"})

        def fake_load_lora_for_models(model, clip, lora, strength_model, strength_clip):
            return (
                f"model:{model}:{strength_model}:{lora['id']}",
                None if clip is None else f"clip:{clip}:{strength_clip}:{lora['id']}",
            )

        comfy_sd = make_module("comfy.sd", load_lora_for_models=Mock(side_effect=fake_load_lora_for_models))
        comfy_utils = make_module("comfy.utils", load_torch_file=load_torch_file)
        comfy_module = make_module("comfy", sd=comfy_sd, utils=comfy_utils)
        sys.modules["comfy"] = comfy_module
        sys.modules["comfy.sd"] = comfy_sd
        sys.modules["comfy.utils"] = comfy_utils

        loader_module = load_module(
            f"{PACKAGE_NAME}.lora_model_loader",
            REPO_ROOT / "lora_model_loader.py",
        )
        loader = loader_module.CachedLoraModelLoader()

        model_result, clip_result = loader.load("base-model", "base-clip", "hero.safetensors", 1.25, 0.5)
        model_only_result = loader.load_model_only("base-model", "hero.safetensors", 0.75)

        self.assertEqual(model_result, "model:base-model:1.25:hero-lora")
        self.assertEqual(clip_result, "clip:base-clip:0.5:hero-lora")
        self.assertEqual(model_only_result, "model:base-model:0.75:hero-lora")
        self.assertEqual(load_torch_file.call_count, 1)
        self.assertEqual(get_full_path_or_raise.call_count, 2)

    def test_node_definitions_cover_both_variants_and_execute_through_services(self):
        install_package_stub()
        install_io_stub()

        folder_paths = make_module(
            "folder_paths",
            get_filename_list=Mock(return_value=["b.safetensors", "A.safetensors"]),
        )
        sys.modules["folder_paths"] = folder_paths

        services_module = make_module(
            f"{PACKAGE_NAME}.services",
            lora_model_loader=types.SimpleNamespace(
                load=Mock(return_value=("model+lora", "clip+lora")),
                load_model_only=Mock(return_value="model-only+lora"),
            ),
            trigger_word_resolver=types.SimpleNamespace(
                resolve_output=Mock(return_value="hero_tag, cinematic light"),
            ),
        )
        sys.modules[f"{PACKAGE_NAME}.services"] = services_module

        node_module = load_module(
            f"{PACKAGE_NAME}.node_definition",
            REPO_ROOT / "node_definition.py",
        )

        schema = node_module.LoraLoaderTriggerWordsNode.define_schema()
        self.assertEqual(schema.node_id, "LoraLoaderTriggerWords")
        self.assertEqual(
            [item.name for item in schema.inputs],
            [
                "model",
                "clip",
                "lora_name",
                "strength_model",
                "strength_clip",
                "loaded_trigger_words",
            ],
        )
        self.assertEqual([item.name for item in schema.outputs], ["model", "clip", "trigger_words"])

        result = node_module.LoraLoaderTriggerWordsNode.execute(
            "model",
            "clip",
            "A.safetensors",
            1.0,
            0.8,
            "preview text",
        )
        model_only_result = node_module.LoraLoaderModelOnlyTriggerWordsNode.execute(
            "model",
            "A.safetensors",
            1.0,
            "preview text",
        )

        services_module.lora_model_loader.load.assert_called_once_with(
            "model",
            "clip",
            "A.safetensors",
            1.0,
            0.8,
        )
        services_module.lora_model_loader.load_model_only.assert_called_once_with(
            "model",
            "A.safetensors",
            1.0,
        )
        self.assertEqual(result, ("model+lora", "clip+lora", "hero_tag, cinematic light"))
        self.assertEqual(model_only_result, ("model-only+lora", "hero_tag, cinematic light"))


if __name__ == "__main__":
    unittest.main()
