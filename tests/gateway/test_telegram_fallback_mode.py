import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig


def _ensure_telegram_mock():
    if "telegram" in sys.modules and hasattr(sys.modules["telegram"], "__file__"):
        return

    telegram_mod = MagicMock()
    telegram_mod.ext.ContextTypes.DEFAULT_TYPE = type(None)
    telegram_mod.constants.ParseMode.MARKDOWN_V2 = "MarkdownV2"
    telegram_mod.constants.ChatType.GROUP = "group"
    telegram_mod.constants.ChatType.SUPERGROUP = "supergroup"
    telegram_mod.constants.ChatType.CHANNEL = "channel"
    telegram_mod.constants.ChatType.PRIVATE = "private"

    for name in ("telegram", "telegram.ext", "telegram.constants", "telegram.request"):
        sys.modules.setdefault(name, telegram_mod)


_ensure_telegram_mock()

from gateway.platforms.telegram import TelegramAdapter  # noqa: E402


def _builder_with_app(app: SimpleNamespace) -> MagicMock:
    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = app
    return builder


def _mock_app() -> SimpleNamespace:
    updater = SimpleNamespace(
        start_polling=AsyncMock(),
        stop=AsyncMock(),
        running=True,
    )
    bot = SimpleNamespace(
        delete_webhook=AsyncMock(),
        set_my_commands=AsyncMock(),
    )
    return SimpleNamespace(
        bot=bot,
        updater=updater,
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_connect_disables_fallback_transport_when_mode_off(monkeypatch):
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="test-token"))

    monkeypatch.setenv("TELEGRAM_FALLBACK_MODE", "off")
    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (True, None),
    )
    monkeypatch.setattr(
        "gateway.status.release_scoped_lock",
        lambda scope, identity: None,
    )

    discover_mock = AsyncMock(return_value=["149.154.167.220"])
    fallback_cls = MagicMock()
    request_cls = MagicMock()
    app = _mock_app()
    builder = _builder_with_app(app)

    monkeypatch.setattr("gateway.platforms.telegram.discover_fallback_ips", discover_mock)
    monkeypatch.setattr("gateway.platforms.telegram.TelegramFallbackTransport", fallback_cls)
    monkeypatch.setattr("gateway.platforms.telegram.HTTPXRequest", request_cls)
    monkeypatch.setattr(
        "gateway.platforms.telegram.Application",
        SimpleNamespace(builder=MagicMock(return_value=builder)),
    )

    ok = await adapter.connect()

    assert ok is True
    discover_mock.assert_not_awaited()
    fallback_cls.assert_not_called()
    assert request_cls.call_count == 2
    for call in request_cls.call_args_list:
        kwargs = call.kwargs
        assert "httpx_kwargs" not in kwargs
    app.bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
