"""Main-runtime-backed image generation backend.

Uses the same Hermes runtime source as the primary chat/TUI path:

- `~/.hermes/.env` / project `.env` loaded via `load_hermes_dotenv()`
- runtime endpoint + auth resolved via `resolve_runtime_provider(requested="custom")`

This keeps image generation on the same custom OpenAI-compatible runtime
configuration as the user's primary dialog path, reusing the configured
`base_url` / `api_key` rather than binding behavior to a specific endpoint
name.

Selection precedence (first hit wins):

1. `HERMES_CUSTOM_IMAGE_MODEL` env var
2. `image_gen.custom.model` in `config.yaml`
3. `image_gen.model` in `config.yaml` when it matches one of our tier IDs
4. `DEFAULT_MODEL`
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.model_metadata import is_local_endpoint
from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)
from utils import base_url_host_matches

logger = logging.getLogger(__name__)


API_MODEL = "gpt-image-2"
_DEFAULT_HOST_MODEL = "gpt-5.4"
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 180.0
_RESPONSES_INSTRUCTIONS = (
    "You are an assistant that must fulfill image generation requests by "
    "using the image_generation tool when provided."
)

_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-2-low": {
        "display": "GPT Image 2 (Low)",
        "speed": "~15s",
        "strengths": "Fast iteration, lowest cost",
        "quality": "low",
    },
    "gpt-image-2-medium": {
        "display": "GPT Image 2 (Medium)",
        "speed": "~40s",
        "strengths": "Balanced — default",
        "quality": "medium",
    },
    "gpt-image-2-high": {
        "display": "GPT Image 2 (High)",
        "speed": "~2min",
        "strengths": "Highest fidelity, strongest prompt adherence",
        "quality": "high",
    },
}

DEFAULT_MODEL = "gpt-image-2-medium"

_SIZES = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}


def _runtime_has_usable_auth(runtime: Dict[str, Any]) -> bool:
    base_url = str(runtime.get("base_url") or "").strip()
    api_key = str(runtime.get("api_key") or "").strip()
    if not base_url:
        return False
    if api_key and api_key != "no-key-required":
        return True
    # Local OpenAI-compatible servers are allowed to omit auth entirely.
    return bool(api_key) and api_key == "no-key-required" and is_local_endpoint(base_url)


def _load_image_gen_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen config: %s", exc)
        return {}


def _resolve_model() -> Tuple[str, Dict[str, Any]]:
    env_override = os.environ.get("HERMES_CUSTOM_IMAGE_MODEL")
    if env_override and env_override in _MODELS:
        return env_override, _MODELS[env_override]

    cfg = _load_image_gen_config()
    custom_cfg = cfg.get("custom") if isinstance(cfg.get("custom"), dict) else {}
    candidate: Optional[str] = None

    if isinstance(custom_cfg, dict):
        value = custom_cfg.get("model")
        if isinstance(value, str) and value in _MODELS:
            candidate = value

    if candidate is None:
        top = cfg.get("model")
        if isinstance(top, str) and top in _MODELS:
            candidate = top

    if candidate is not None:
        return candidate, _MODELS[candidate]

    return DEFAULT_MODEL, _MODELS[DEFAULT_MODEL]


def _resolve_runtime() -> Dict[str, Any]:
    from hermes_cli.config import get_hermes_home
    from hermes_cli.env_loader import load_hermes_dotenv
    from hermes_cli.runtime_provider import resolve_runtime_provider

    load_hermes_dotenv(
        hermes_home=get_hermes_home(),
        project_env=Path(__file__).resolve().parents[3] / ".env",
    )
    runtime = resolve_runtime_provider(requested="custom")
    return runtime if isinstance(runtime, dict) else {}


def _resolve_host_model() -> str:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        model_cfg = cfg.get("model") if isinstance(cfg, dict) else None
        if isinstance(model_cfg, dict):
            candidate = model_cfg.get("default") or model_cfg.get("model")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    except Exception as exc:
        logger.debug("Could not resolve host model for custom image generation: %s", exc)

    return _DEFAULT_HOST_MODEL


def _resolve_request_timeout(runtime: Dict[str, Any], host_model: str) -> float:
    try:
        from hermes_cli.timeouts import get_provider_request_timeout

        provider_id = str(
            runtime.get("requested_provider") or runtime.get("provider") or "custom"
        ).strip()
        configured = get_provider_request_timeout(provider_id, host_model)
        if configured is not None:
            return configured
    except Exception as exc:
        logger.debug("Could not resolve custom image request timeout: %s", exc)
    return _DEFAULT_REQUEST_TIMEOUT_SECONDS


def _runtime_default_headers(base_url: str, api_key: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}

    if base_url_host_matches(base_url, "api.kimi.com"):
        headers["User-Agent"] = "claude-code/0.1.0"
    elif base_url_host_matches(base_url, "api.githubcopilot.com"):
        from hermes_cli.copilot_auth import copilot_request_headers

        headers.update(copilot_request_headers(is_agent_turn=True, is_vision=False))
    elif base_url_host_matches(base_url, "chatgpt.com"):
        from agent.auxiliary_client import _codex_cloudflare_headers

        headers.update(_codex_cloudflare_headers(api_key))

    return headers


def _build_runtime_client(
    base_url: str,
    api_key: str,
    *,
    timeout_seconds: Optional[float] = None,
):
    import openai
    from agent.auxiliary_client import _extract_url_query_params

    clean_base, default_query = _extract_url_query_params(base_url)
    effective_timeout = _DEFAULT_REQUEST_TIMEOUT_SECONDS
    if isinstance(timeout_seconds, (int, float)) and timeout_seconds > 0:
        effective_timeout = float(timeout_seconds)
    extra: Dict[str, Any] = {
        "timeout": effective_timeout,
        "max_retries": 0,
    }
    if default_query:
        extra["default_query"] = default_query

    default_headers = _runtime_default_headers(clean_base, api_key)
    if default_headers:
        extra["default_headers"] = default_headers

    return openai.OpenAI(base_url=clean_base, api_key=api_key, **extra), clean_base


def _extract_image_from_images_response(
    response: Any,
    *,
    tier_id: str,
) -> Tuple[str, Optional[str]]:
    data = getattr(response, "data", None) or []
    if not data:
        raise ValueError("Shared custom runtime returned no image data")

    first = data[0]
    b64 = getattr(first, "b64_json", None)
    url = getattr(first, "url", None)
    revised_prompt = getattr(first, "revised_prompt", None)

    if b64:
        saved_path = save_b64_image(b64, prefix=f"custom_{tier_id}")
        return str(saved_path), revised_prompt

    if isinstance(url, str) and url.strip():
        return url.strip(), revised_prompt

    raise ValueError("Shared custom runtime response contained neither b64_json nor URL")


def _extract_image_from_responses_result(
    response: Any,
    *,
    tier_id: str,
) -> Tuple[str, Optional[str]]:
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "image_generation_call":
            continue
        result = getattr(item, "result", None)
        if isinstance(result, str) and result:
            saved_path = save_b64_image(result, prefix=f"custom_{tier_id}")
            return str(saved_path), None

    raise ValueError("Shared custom runtime response contained no image_generation_call result")


def _extract_image_from_streamed_result(
    image_b64: Optional[str],
    *,
    tier_id: str,
) -> Tuple[str, Optional[str]]:
    if isinstance(image_b64, str) and image_b64:
        saved_path = save_b64_image(image_b64, prefix=f"custom_{tier_id}")
        return str(saved_path), None

    raise ValueError("Shared custom runtime stream contained no image_generation_call result")


def _collect_streamed_image_b64(
    client: Any,
    *,
    host_model: str,
    prompt: str,
    size: str,
    quality: str,
) -> Optional[str]:
    image_b64: Optional[str] = None

    with client.responses.stream(
        model=host_model,
        store=False,
        instructions=_RESPONSES_INSTRUCTIONS,
        input=[{
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }],
        tools=[{
            "type": "image_generation",
            "model": API_MODEL,
            "size": size,
            "quality": quality,
            "output_format": "png",
            "background": "opaque",
            "partial_images": 1,
        }],
        tool_choice={
            "type": "allowed_tools",
            "mode": "required",
            "tools": [{"type": "image_generation"}],
        },
    ) as stream:
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_item.done":
                item = getattr(event, "item", None)
                if getattr(item, "type", None) == "image_generation_call":
                    result = getattr(item, "result", None)
                    if isinstance(result, str) and result:
                        image_b64 = result
            elif event_type == "response.image_generation_call.partial_image":
                partial = getattr(event, "partial_image_b64", None)
                if isinstance(partial, str) and partial:
                    image_b64 = partial

        final = stream.get_final_response()

    for item in getattr(final, "output", None) or []:
        if getattr(item, "type", None) == "image_generation_call":
            result = getattr(item, "result", None)
            if isinstance(result, str) and result:
                image_b64 = result

    return image_b64


def _generate_via_responses_api(
    client: Any,
    *,
    host_model: str,
    prompt: str,
    size: str,
    quality: str,
) -> Any:
    return client.responses.create(
        model=host_model,
        store=False,
        instructions=_RESPONSES_INSTRUCTIONS,
        input=[{
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }],
        tools=[{
            "type": "image_generation",
            "model": API_MODEL,
            "size": size,
            "quality": quality,
            "output_format": "png",
            "background": "opaque",
        }],
        tool_choice={
            "type": "allowed_tools",
            "mode": "required",
            "tools": [{"type": "image_generation"}],
        },
    )


class CustomImageGenProvider(ImageGenProvider):
    """Image generation via the same custom-provider runtime as the main dialog path."""

    @property
    def name(self) -> str:
        return "custom"

    @property
    def display_name(self) -> str:
        return "Main Runtime"

    def is_available(self) -> bool:
        try:
            import openai  # noqa: F401
        except ImportError:
            return False

        runtime = _resolve_runtime()
        return _runtime_has_usable_auth(runtime)

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta["display"],
                "speed": meta["speed"],
                "strengths": meta["strengths"],
                "price": "runtime-defined",
            }
            for model_id, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Main Runtime",
            "badge": "shared",
            "tag": "Reuse the same custom-provider runtime config as Hermes chat/TUI",
            "env_vars": [],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)

        if not prompt:
            return error_response(
                error="Prompt is required and must be a non-empty string",
                error_type="invalid_argument",
                provider="custom",
                aspect_ratio=aspect,
            )

        try:
            import openai
        except ImportError:
            return error_response(
                error="openai Python package not installed (pip install openai)",
                error_type="missing_dependency",
                provider="custom",
                aspect_ratio=aspect,
            )

        runtime = _resolve_runtime()
        base_url = str(runtime.get("base_url") or "").strip().rstrip("/")
        api_key = str(runtime.get("api_key") or "").strip()

        if not base_url:
            return error_response(
                error=(
                    "No custom runtime is configured. Set the main Hermes "
                    "model provider to a custom OpenAI-compatible endpoint first."
                ),
                error_type="auth_required",
                provider="custom",
                aspect_ratio=aspect,
            )

        if not _runtime_has_usable_auth(runtime):
            return error_response(
                error=(
                    "The shared custom runtime resolved without usable auth. "
                    "Remote custom endpoints need a real API key; only local "
                    "OpenAI-compatible servers may use no-key-required."
                ),
                error_type="auth_required",
                provider="custom",
                aspect_ratio=aspect,
            )

        tier_id, meta = _resolve_model()
        size = _SIZES.get(aspect, _SIZES["square"])
        host_model = _resolve_host_model()
        request_timeout = _resolve_request_timeout(runtime, host_model)

        payload: Dict[str, Any] = {
            "model": API_MODEL,
            "prompt": prompt,
            "size": size,
            "n": 1,
            "quality": meta["quality"],
        }

        try:
            client, clean_base_url = _build_runtime_client(
                base_url,
                api_key,
                timeout_seconds=request_timeout,
            )
        except Exception as exc:
            logger.debug("Custom image generation failed", exc_info=True)
            return error_response(
                error=f"Could not initialize the shared custom-runtime image client: {exc}",
                error_type="api_error",
                provider="custom",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        # Prefer the same streamed Responses image-generation path already used
        # by the dedicated Codex/OpenAI backend, then widen compatibility by
        # falling back to non-stream Responses and finally the legacy Images API.
        transports = [
            (
                "responses.stream(image_generation)",
                lambda: _collect_streamed_image_b64(
                    client,
                    host_model=host_model,
                    prompt=prompt,
                    size=size,
                    quality=meta["quality"],
                ),
                lambda image_b64: _extract_image_from_streamed_result(image_b64, tier_id=tier_id),
            ),
            (
                "responses.create(image_generation)",
                lambda: _generate_via_responses_api(
                    client,
                    host_model=host_model,
                    prompt=prompt,
                    size=size,
                    quality=meta["quality"],
                ),
                lambda response: _extract_image_from_responses_result(response, tier_id=tier_id),
            ),
            (
                "images.generate",
                lambda: client.images.generate(**payload),
                lambda response: _extract_image_from_images_response(response, tier_id=tier_id),
            ),
        ]

        revised_prompt: Optional[str] = None
        image_ref: Optional[str] = None
        transport_errors: List[str] = []

        for transport_name, request_fn, decode_fn in transports:
            try:
                response = request_fn()
                image_ref, revised_prompt = decode_fn(response)
                break
            except Exception as exc:
                logger.debug(
                    "Custom image generation attempt failed via %s",
                    transport_name,
                    exc_info=True,
                )
                transport_errors.append(f"{transport_name}: {exc}")

        if not image_ref:
            return error_response(
                error=(
                    "Shared custom-runtime image generation failed. "
                    + " ; ".join(transport_errors)
                ),
                error_type="api_error",
                provider="custom",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        extra: Dict[str, Any] = {
            "size": size,
            "quality": meta["quality"],
            "api_model": API_MODEL,
            "base_url": clean_base_url,
            "host_model": host_model,
            "request_timeout_seconds": request_timeout,
        }
        if revised_prompt:
            extra["revised_prompt"] = revised_prompt

        return success_response(
            image=image_ref,
            model=tier_id,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="custom",
            extra=extra,
        )


def register(ctx) -> None:
    """Plugin entry point — wire the shared-runtime provider into the registry."""
    ctx.register_image_gen_provider(CustomImageGenProvider())
