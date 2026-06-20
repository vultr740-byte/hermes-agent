"""Tests for the bundled Xialiao Mainbox skill helper."""

from __future__ import annotations

import importlib.util
from types import SimpleNamespace
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "email"
    / "xialiao-mainbox"
    / "scripts"
    / "xialiao_mainbox.py"
)


@pytest.fixture(scope="module")
def xialiao_mainbox_module():
    spec = importlib.util.spec_from_file_location("xialiao_mainbox_skill_helper", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normal_mailbox_name_requires_letters_digits_and_length(xialiao_mainbox_module):
    assert xialiao_mainbox_module.normalize_local_part("mail01") == "mail01"

    with pytest.raises(xialiao_mainbox_module.MailboxError):
        xialiao_mainbox_module.normalize_local_part("mail")

    with pytest.raises(xialiao_mainbox_module.MailboxError):
        xialiao_mainbox_module.normalize_local_part("research")


def test_normal_mailbox_name_disallows_plus(xialiao_mainbox_module):
    with pytest.raises(xialiao_mainbox_module.MailboxError):
        xialiao_mainbox_module.normalize_local_part("agent+1")


def test_plus_local_part_requires_separate_agent_id_mode(xialiao_mainbox_module):
    assert (
        xialiao_mainbox_module.normalize_local_part("agent+1", allow_plus=True)
        == "agent+1"
    )
    assert xialiao_mainbox_module.normalize_local_part("agent01") == "agent01"


def test_ack_updates_local_state_after_remote_failure(xialiao_mainbox_module, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    xialiao_mainbox_module.save_config(
        {
            "api_base": "https://mainbox.example.com",
            "agent_id": "agent01",
            "read_token": "read-token",
        }
    )
    xialiao_mainbox_module.save_state(
        {"messages": {"msg-1": {"status": "leased", "attempts": 1}}}
    )
    monkeypatch.setattr(
        xialiao_mainbox_module,
        "post_message_action",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            xialiao_mainbox_module.MailboxError("offline", status=503)
        ),
    )

    result = xialiao_mainbox_module.cmd_ack(
        SimpleNamespace(message_id=["msg-1"], all_leased=False)
    )

    assert result == 0
    state = xialiao_mainbox_module.load_state()
    assert state["messages"]["msg-1"]["status"] == "acked"
