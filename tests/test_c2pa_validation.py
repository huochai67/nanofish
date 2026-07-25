import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Self
from unittest.mock import patch


def _load_c2pa_validation() -> ModuleType:
    plugin_dir = Path(__file__).parents[1] / "src/plugins/genai_detect"
    module_path = plugin_dir / "c2pa_validation.py"
    spec = importlib.util.spec_from_file_location("c2pa_validation_test", module_path)
    if spec is None or spec.loader is None:
        msg = "unable to load C2PA validation module"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


c2pa_validation = _load_c2pa_validation()


class _Context:
    settings: dict[str, object] | None = None

    @classmethod
    def from_dict(cls, settings: dict[str, object]) -> "_Context":
        cls.settings = settings
        return cls()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _Reader:
    def __init__(self, state: str, manifest: dict[object, object]) -> None:
        self._state = state
        self._manifest = manifest

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get_active_manifest(self) -> dict[object, object]:
        return self._manifest

    def get_validation_state(self) -> str:
        return self._state


class C2paValidationTests(unittest.TestCase):
    def test_trusted_manifest_uses_claim_generator(self) -> None:
        reader = _Reader("Trusted", {"claim_generator": "Adobe Photoshop"})
        with (
            patch.object(c2pa_validation.c2pa, "Context", _Context),
            patch.object(
                c2pa_validation.c2pa,
                "Reader",
                type(
                    "Reader",
                    (),
                    {"try_create": staticmethod(lambda *_args, **_kwargs: reader)},
                ),
            ),
        ):
            result = c2pa_validation.inspect_embedded_c2pa(b"image", "image/jpeg")

        self.assertTrue(result.trusted)
        self.assertEqual(result.claim_generator, "Adobe Photoshop")
        settings = _Context.settings
        self.assertIsNotNone(settings)
        assert settings is not None
        verify = settings["verify"]
        self.assertIsInstance(verify, dict)
        assert isinstance(verify, dict)
        self.assertFalse(verify["remote_manifest_fetch"])
        self.assertTrue(verify["verify_trust"])

    def test_official_trust_anchors_are_passed_to_sdk(self) -> None:
        reader = _Reader("Trusted", {"claim_generator": "Google"})
        with (
            patch.object(c2pa_validation.c2pa, "Context", _Context),
            patch.object(
                c2pa_validation.c2pa,
                "Reader",
                type(
                    "Reader",
                    (),
                    {"try_create": staticmethod(lambda *_args, **_kwargs: reader)},
                ),
            ),
        ):
            result = c2pa_validation.inspect_embedded_c2pa(
                b"image",
                "image/png",
                "-----BEGIN CERTIFICATE-----\ntrusted\n-----END CERTIFICATE-----",
            )

        self.assertTrue(result.trusted)
        settings = _Context.settings
        self.assertIsNotNone(settings)
        assert settings is not None
        self.assertEqual(
            settings["trust"],
            {
                "trust_anchors": (
                    "-----BEGIN CERTIFICATE-----\ntrusted\n-----END CERTIFICATE-----"
                )
            },
        )

    def test_manifest_without_trusted_chain_is_not_trusted(self) -> None:
        reader = _Reader("Invalid", {"claim_generator_info": [{"name": "Unknown"}]})
        with (
            patch.object(c2pa_validation.c2pa, "Context", _Context),
            patch.object(
                c2pa_validation.c2pa,
                "Reader",
                type(
                    "Reader",
                    (),
                    {"try_create": staticmethod(lambda *_args, **_kwargs: reader)},
                ),
            ),
        ):
            result = c2pa_validation.inspect_embedded_c2pa(b"image", "image/png")

        self.assertFalse(result.trusted)
        self.assertEqual(result.status, c2pa_validation.C2paStatus.NOT_TRUSTED)
        self.assertEqual(result.claim_generator, "Unknown")

    def test_image_without_manifest_is_silent_result(self) -> None:
        with (
            patch.object(c2pa_validation.c2pa, "Context", _Context),
            patch.object(
                c2pa_validation.c2pa,
                "Reader",
                type(
                    "Reader",
                    (),
                    {"try_create": staticmethod(lambda *_args, **_kwargs: None)},
                ),
            ),
        ):
            result = c2pa_validation.inspect_embedded_c2pa(b"image", "image/webp")

        self.assertEqual(result.status, c2pa_validation.C2paStatus.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
