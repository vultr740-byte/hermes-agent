"""User-facing billing error formatting for gateway surfaces."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from agent.error_classifier import FailoverReason, classify_api_error

_DEFAULT_RECHARGE_BASE_URL = "https://www.xialiao.app/recharge/"
_DEFAULT_BILLING_MESSAGE = "⚠️ 模型余额不足，请充值后重试。"


@dataclass(frozen=True)
class BillingFailureResponse:
    """Structured gateway response for billing exhaustion."""

    message: str
    recharge_url: Optional[str] = None

    def as_messages(self) -> list[str]:
        """Return text messages in delivery order."""
        messages = [self.message]
        if self.recharge_url:
            messages.append(self.recharge_url)
        return messages


def format_billing_user_message(provider: str = "", model: str = "") -> str:
    """Return the user-facing billing exhaustion copy."""
    del provider, model
    return _DEFAULT_BILLING_MESSAGE


def _first_env_value(resolved_env: dict[str, str], *keys: str) -> str:
    """Return the first non-empty env value from the provided keys."""
    for key in keys:
        value = str(resolved_env.get(key) or "").strip()
        if value:
            return value
    return ""


def resolve_billing_recharge_url(env: Optional[dict[str, str]] = None) -> Optional[str]:
    """Build a recharge URL when a recharge target is configured."""
    resolved_env = env if env is not None else os.environ
    target = _first_env_value(resolved_env, "RECHARGE_TARGET")
    if not target:
        return None
    base_url = _first_env_value(resolved_env, "RECHARGE_BASE_URL")
    if not base_url:
        base_url = _DEFAULT_RECHARGE_BASE_URL
    if not base_url.endswith("/"):
        base_url += "/"
    from urllib.parse import quote

    return f"{base_url}{quote(target, safe='')}"


def is_billing_failure(
    error: object,
    *,
    provider: str = "",
    model: str = "",
) -> bool:
    """Return True when an error should be surfaced as a billing failure."""
    if error is None:
        return False
    exc = error if isinstance(error, Exception) else Exception(str(error))
    classified = classify_api_error(exc, provider=provider, model=model)
    return classified.reason == FailoverReason.billing


def format_billing_failure_response(
    error: object,
    *,
    provider: str = "",
    model: str = "",
    env: Optional[dict[str, str]] = None,
) -> Optional[BillingFailureResponse]:
    """Return a user-facing billing response, or ``None`` when not applicable."""
    if not is_billing_failure(error, provider=provider, model=model):
        return None
    message = format_billing_user_message(provider=provider, model=model)
    recharge_url = resolve_billing_recharge_url(env)
    return BillingFailureResponse(message=message, recharge_url=recharge_url)
