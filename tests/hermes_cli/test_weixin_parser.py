"""Argparse-level coverage for the `hermes weixin` subcommand."""

from pathlib import Path


def test_weixin_command_is_registered():
    source = Path(__file__).resolve().parents[2] / "hermes_cli" / "main.py"
    text = source.read_text(encoding="utf-8")

    assert 'subparsers.add_parser(\n        "weixin"' in text or 'subparsers.add_parser("weixin"' in text
    assert "cmd_weixin" in text
