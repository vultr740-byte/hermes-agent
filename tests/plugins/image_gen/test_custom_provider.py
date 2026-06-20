"""Tests for the bundled main-runtime-backed custom image_gen plugin."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import plugins.image_gen.custom as custom_plugin


_PNG_HEX = (
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6300010000000500010d0a2db40000000049454e44"
    "ae426082"
)


def _b64_png() -> str:
    import base64
    return base64.b64encode(bytes.fromhex(_PNG_HEX)).decode()


def _fake_response(*, b64=None, url=None, revised_prompt=None):
    item = SimpleNamespace(b64_json=b64, url=url, revised_prompt=revised_prompt)
    return SimpleNamespace(data=[item])


def _fake_responses_response(*, b64=None):
    item = SimpleNamespace(type="image_generation_call", result=b64)
    return SimpleNamespace(output=[item])


class _FakeStream:
    def __init__(self, events, final_response):
        self._events = list(events)
        self._final = final_response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_response(self):
        return self._final


@pytest.fixture(autouse=True)
def _tmp_hermes_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    yield tmp_path


@pytest.fixture
def provider():
    return custom_plugin.CustomImageGenProvider()


def _patched_openai(fake_client: MagicMock):
    fake_openai = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    return fake_openai, patch.dict("sys.modules", {"openai": fake_openai})


class TestMetadata:
    def test_name(self, provider):
        assert provider.name == "custom"

    def test_display_name(self, provider):
        assert provider.display_name == "Main Runtime"

    def test_default_model(self, provider):
        assert provider.default_model() == "gpt-image-2-medium"

    def test_list_models_three_tiers(self, provider):
        ids = [m["id"] for m in provider.list_models()]
        assert ids == ["gpt-image-2-low", "gpt-image-2-medium", "gpt-image-2-high"]

    def test_setup_schema_requires_no_extra_env_vars(self, provider):
        schema = provider.get_setup_schema()
        assert schema["env_vars"] == []
        assert schema["badge"] == "shared"


class TestAvailability:
    def test_unavailable_without_runtime(self, monkeypatch):
        monkeypatch.setattr(custom_plugin, "_resolve_runtime", lambda: {})
        assert custom_plugin.CustomImageGenProvider().is_available() is False

    def test_available_with_runtime(self, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "https://clawfather.up.railway.app/v1", "api_key": "sk-test"},
        )
        assert custom_plugin.CustomImageGenProvider().is_available() is True

    def test_remote_runtime_with_placeholder_key_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "https://clawfather.up.railway.app/v1", "api_key": "no-key-required"},
        )
        assert custom_plugin.CustomImageGenProvider().is_available() is False

    def test_local_runtime_with_placeholder_key_is_available(self, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "http://127.0.0.1:11434/v1", "api_key": "no-key-required"},
        )
        assert custom_plugin.CustomImageGenProvider().is_available() is True


class TestModelResolution:
    def test_default_is_medium(self):
        model_id, meta = custom_plugin._resolve_model()
        assert model_id == "gpt-image-2-medium"
        assert meta["quality"] == "medium"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("HERMES_CUSTOM_IMAGE_MODEL", "gpt-image-2-high")
        model_id, meta = custom_plugin._resolve_model()
        assert model_id == "gpt-image-2-high"
        assert meta["quality"] == "high"


class TestGenerate:
    def test_empty_prompt_rejected(self, provider):
        result = provider.generate("", aspect_ratio="square")
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_missing_runtime_rejected(self, provider, monkeypatch):
        monkeypatch.setattr(custom_plugin, "_resolve_runtime", lambda: {})
        result = provider.generate("a cat")
        assert result["success"] is False
        assert result["error_type"] == "auth_required"

    def test_remote_placeholder_key_rejected(self, provider, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "https://clawfather.up.railway.app/v1", "api_key": "no-key-required"},
        )
        result = provider.generate("a cat")
        assert result["success"] is False
        assert result["error_type"] == "auth_required"

    def test_b64_saves_to_cache(self, provider, monkeypatch, tmp_path):
        png_bytes = bytes.fromhex(_PNG_HEX)
        fake_client = MagicMock()
        done_event = SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="image_generation_call", result=_b64_png()),
        )
        fake_client.responses.stream.return_value = _FakeStream(
            [done_event],
            SimpleNamespace(output=[], status="completed", output_text=""),
        )
        fake_client.images.generate.return_value = _fake_response(b64=_b64_png())
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "https://clawfather.up.railway.app/v1", "api_key": "sk-test"},
        )

        fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat", aspect_ratio="landscape")

        assert result["success"] is True
        assert result["model"] == "gpt-image-2-medium"
        assert result["aspect_ratio"] == "landscape"
        assert result["provider"] == "custom"
        assert result["quality"] == "medium"
        assert result["api_model"] == "gpt-image-2"
        assert result["base_url"] == "https://clawfather.up.railway.app/v1"
        saved = Path(result["image"])
        assert saved.exists()
        assert saved.parent == tmp_path / "cache" / "images"
        assert saved.read_bytes() == png_bytes

        call_kwargs = fake_client.responses.stream.call_args.kwargs
        assert call_kwargs["model"] == "gpt-5.4"
        assert call_kwargs["tools"][0]["model"] == "gpt-image-2"
        assert call_kwargs["tools"][0]["quality"] == "medium"
        assert call_kwargs["tools"][0]["size"] == "1536x1024"

        openai_kwargs = fake_openai.OpenAI.call_args.kwargs
        assert openai_kwargs["base_url"] == "https://clawfather.up.railway.app/v1"
        assert openai_kwargs["api_key"] == "sk-test"

    @pytest.mark.parametrize("tier,expected_quality", [
        ("gpt-image-2-low", "low"),
        ("gpt-image-2-medium", "medium"),
        ("gpt-image-2-high", "high"),
    ])
    def test_tier_maps_to_quality(self, provider, monkeypatch, tier, expected_quality):
        monkeypatch.setenv("HERMES_CUSTOM_IMAGE_MODEL", tier)
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "https://clawfather.up.railway.app/v1", "api_key": "sk-test"},
        )
        fake_client = MagicMock()
        done_event = SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="image_generation_call", result=_b64_png()),
        )
        fake_client.responses.stream.return_value = _FakeStream(
            [done_event],
            SimpleNamespace(output=[], status="completed", output_text=""),
        )
        fake_client.images.generate.return_value = _fake_response(b64=_b64_png())

        _fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat")

        assert result["model"] == tier
        assert result["quality"] == expected_quality
        call_kwargs = fake_client.responses.stream.call_args.kwargs
        assert call_kwargs["model"] == "gpt-5.4"
        assert call_kwargs["tools"][0]["quality"] == expected_quality
        assert call_kwargs["tools"][0]["model"] == "gpt-image-2"

    def test_runtime_failure_returns_api_error(self, provider, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "https://clawfather.up.railway.app/v1", "api_key": "sk-test"},
        )
        fake_client = MagicMock()
        fake_client.images.generate.side_effect = RuntimeError("boom")

        _fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat")

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "boom" in result["error"]

    def test_prefers_responses_api_first_for_shared_runtime(self, provider, monkeypatch, tmp_path):
        png_bytes = bytes.fromhex(_PNG_HEX)
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {
                "base_url": "https://clawfather.up.railway.app/v1",
                "api_key": "sk-test",
                "api_mode": "chat_completions",
            },
        )
        monkeypatch.setattr(custom_plugin, "_resolve_host_model", lambda: "gpt-5.4")

        fake_client = MagicMock()
        done_event = SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="image_generation_call", result=_b64_png()),
        )
        fake_client.responses.stream.return_value = _FakeStream(
            [done_event],
            SimpleNamespace(output=[], status="completed", output_text=""),
        )

        _fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat", aspect_ratio="portrait")

        assert result["success"] is True
        assert result["provider"] == "custom"
        assert result["host_model"] == "gpt-5.4"
        saved = Path(result["image"])
        assert saved.exists()
        assert saved.parent == tmp_path / "cache" / "images"
        assert saved.read_bytes() == png_bytes

        fake_client.responses.stream.assert_called_once()
        fake_client.responses.create.assert_not_called()
        fake_client.images.generate.assert_not_called()
        call_kwargs = fake_client.responses.stream.call_args.kwargs
        assert call_kwargs["model"] == "gpt-5.4"
        assert call_kwargs["tools"][0]["type"] == "image_generation"
        assert call_kwargs["tools"][0]["model"] == "gpt-image-2"
        assert call_kwargs["tools"][0]["quality"] == "medium"
        assert call_kwargs["tools"][0]["size"] == "1024x1536"
        assert call_kwargs["tools"][0]["partial_images"] == 1

    def test_falls_back_to_responses_create_when_stream_path_fails(self, provider, monkeypatch, tmp_path):
        png_bytes = bytes.fromhex(_PNG_HEX)
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {
                "base_url": "https://clawfather.up.railway.app/v1",
                "api_key": "sk-test",
                "api_mode": "chat_completions",
            },
        )
        monkeypatch.setattr(custom_plugin, "_resolve_host_model", lambda: "gpt-5.4")

        fake_client = MagicMock()
        fake_client.responses.stream.side_effect = RuntimeError("stream path unsupported")
        fake_client.responses.create.return_value = _fake_responses_response(b64=_b64_png())

        _fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat", aspect_ratio="portrait")

        assert result["success"] is True
        assert result["provider"] == "custom"
        saved = Path(result["image"])
        assert saved.exists()
        assert saved.parent == tmp_path / "cache" / "images"
        assert saved.read_bytes() == png_bytes

        fake_client.responses.stream.assert_called_once()
        fake_client.responses.create.assert_called_once()
        fake_client.images.generate.assert_not_called()
        call_kwargs = fake_client.responses.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-5.4"
        assert call_kwargs["tools"][0]["model"] == "gpt-image-2"
        assert call_kwargs["tools"][0]["quality"] == "medium"
        assert call_kwargs["tools"][0]["size"] == "1024x1536"

    def test_falls_back_to_images_api_when_both_responses_paths_fail(self, provider, monkeypatch, tmp_path):
        png_bytes = bytes.fromhex(_PNG_HEX)
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {
                "base_url": "https://clawfather.up.railway.app/v1",
                "api_key": "sk-test",
                "api_mode": "chat_completions",
            },
        )
        monkeypatch.setattr(custom_plugin, "_resolve_host_model", lambda: "gpt-5.4")

        fake_client = MagicMock()
        fake_client.responses.stream.side_effect = RuntimeError("stream path unsupported")
        fake_client.responses.create.side_effect = RuntimeError("responses path unsupported")
        fake_client.images.generate.return_value = _fake_response(b64=_b64_png())

        _fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat", aspect_ratio="portrait")

        assert result["success"] is True
        assert result["provider"] == "custom"
        saved = Path(result["image"])
        assert saved.exists()
        assert saved.parent == tmp_path / "cache" / "images"
        assert saved.read_bytes() == png_bytes

        fake_client.responses.stream.assert_called_once()
        fake_client.responses.create.assert_called_once()
        fake_client.images.generate.assert_called_once()
        call_kwargs = fake_client.images.generate.call_args.kwargs
        assert call_kwargs["model"] == "gpt-image-2"
        assert call_kwargs["quality"] == "medium"
        assert call_kwargs["size"] == "1024x1536"

    def test_prefers_responses_api_first_for_codex_style_runtime(self, provider, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {
                "base_url": "https://chatgpt.com/backend-api/codex",
                "api_key": "codex-token",
                "api_mode": "codex_responses",
            },
        )
        monkeypatch.setattr(custom_plugin, "_resolve_host_model", lambda: "gpt-5.4")

        fake_client = MagicMock()
        done_event = SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="image_generation_call", result=_b64_png()),
        )
        fake_client.responses.stream.return_value = _FakeStream(
            [done_event],
            SimpleNamespace(output=[], status="completed", output_text=""),
        )

        _fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat")

        assert result["success"] is True
        fake_client.responses.stream.assert_called_once()
        fake_client.responses.create.assert_not_called()
        fake_client.images.generate.assert_not_called()

    def test_partial_image_event_is_accepted(self, provider, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {"base_url": "https://clawfather.up.railway.app/v1", "api_key": "sk-test"},
        )
        monkeypatch.setattr(custom_plugin, "_resolve_host_model", lambda: "gpt-5.4")

        fake_client = MagicMock()
        partial_event = SimpleNamespace(
            type="response.image_generation_call.partial_image",
            partial_image_b64=_b64_png(),
        )
        fake_client.responses.stream.return_value = _FakeStream(
            [partial_event],
            SimpleNamespace(output=[], status="completed", output_text=""),
        )

        _fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat")

        assert result["success"] is True
        assert Path(result["image"]).exists()

    def test_timeout_uses_provider_timeout_config(self, provider, monkeypatch):
        monkeypatch.setattr(
            custom_plugin,
            "_resolve_runtime",
            lambda: {
                "base_url": "https://clawfather.up.railway.app/v1",
                "api_key": "sk-test",
                "provider": "custom",
                "requested_provider": "custom",
            },
        )
        monkeypatch.setattr(custom_plugin, "_resolve_host_model", lambda: "gpt-5.4")
        monkeypatch.setattr(custom_plugin, "_resolve_request_timeout", lambda runtime, host_model: 240.0)

        fake_client = MagicMock()
        done_event = SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="image_generation_call", result=_b64_png()),
        )
        fake_client.responses.stream.return_value = _FakeStream(
            [done_event],
            SimpleNamespace(output=[], status="completed", output_text=""),
        )

        fake_openai, patcher = _patched_openai(fake_client)
        with patcher:
            result = provider.generate("a cat")

        assert result["success"] is True
        assert result["request_timeout_seconds"] == 240.0
        assert fake_openai.OpenAI.call_args.kwargs["timeout"] == 240.0


class TestRegistration:
    def test_register_calls_register_image_gen_provider(self):
        registered = []

        class _Ctx:
            def register_image_gen_provider(self, prov):
                registered.append(prov)

        custom_plugin.register(_Ctx())
        assert len(registered) == 1
        assert registered[0].name == "custom"
