#!/usr/bin/env python3
"""Xialiao Mainbox helper for Hermes skills.

The script intentionally uses only the Python standard library so it can run in
cron jobs without extra setup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import ssl
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MIN_LOCAL_PART_LENGTH = 6
MAX_LOCAL_PART_LENGTH = 32
LOCAL_PART_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
PLUS_LOCAL_PART_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_+-]*[a-z0-9])?$")
RESERVED_LOCAL_PARTS = {
    "abuse",
    "admin",
    "administrator",
    "hostmaster",
    "mailer-daemon",
    "noreply",
    "no-reply",
    "postmaster",
    "root",
    "security",
    "webmaster",
}
DEFAULT_LEASE_SECONDS = 10 * 60
DEFAULT_LIMIT = 10
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_MAX_BODY_CHARS = 12000
SYSTEM_CA_FILES = (
    "/etc/ssl/cert.pem",
    "/opt/homebrew/etc/openssl@3/cert.pem",
    "/usr/local/etc/openssl@3/cert.pem",
)
CONFIG_ENV_KEYS = {
    "api_base": ("XIALIAO_MAINBOX_API_BASE", "MAINBOX_API_BASE", "HERMES_MAILBOX_API_BASE"),
    "domain": ("XIALIAO_MAINBOX_DOMAIN", "MAINBOX_DOMAIN", "HERMES_MAILBOX_DOMAIN", "MAIL_DOMAIN"),
    "agent_id": ("XIALIAO_MAINBOX_AGENT_ID", "MAINBOX_AGENT_ID", "HERMES_MAILBOX_AGENT_ID"),
    "address": ("XIALIAO_MAINBOX_ADDRESS", "MAINBOX_ADDRESS", "HERMES_AGENT_EMAIL_ADDRESS", "HERMES_MAILBOX_ADDRESS"),
    "api_token": ("XIALIAO_MAINBOX_API_TOKEN", "MAINBOX_API_TOKEN", "HERMES_MAILBOX_API_TOKEN", "MAILBOX_API_TOKEN"),
    "read_token": ("XIALIAO_MAINBOX_READ_TOKEN", "MAINBOX_READ_TOKEN", "HERMES_MAILBOX_READ_TOKEN"),
}


class MailboxError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".hermes"


def app_dir() -> Path:
    return hermes_home() / "xialiao-mainbox"


def config_path() -> Path:
    return app_dir() / "config.json"


def state_path() -> Path:
    return app_dir() / "state.json"


def scripts_dir() -> Path:
    return hermes_home() / "scripts"


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise MailboxError(f"Invalid JSON in {path}: {exc}") from exc


def write_json_file(path: Path, value: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if private:
        try:
            tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    tmp.replace(path)
    if private:
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def load_config() -> dict[str, Any]:
    cfg = load_saved_config()
    if not isinstance(cfg, dict):
        raise MailboxError(f"Config must be a JSON object: {config_path()}")
    for key, env_names in CONFIG_ENV_KEYS.items():
        for env_name in env_names:
            value = os.environ.get(env_name)
            if value:
                cfg[key] = value
                break
    return cfg


def load_saved_config() -> dict[str, Any]:
    cfg = read_json_file(config_path(), {})
    if not isinstance(cfg, dict):
        raise MailboxError(f"Config must be a JSON object: {config_path()}")
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    write_json_file(config_path(), cfg, private=True)


def load_state() -> dict[str, Any]:
    state = read_json_file(state_path(), {"messages": {}})
    if not isinstance(state, dict):
        return {"messages": {}}
    if not isinstance(state.get("messages"), dict):
        state["messages"] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    write_json_file(state_path(), state, private=True)


def normalize_local_part(value: str, *, allow_plus: bool = False) -> str:
    local_part = value.strip().lower()
    if len(local_part) < MIN_LOCAL_PART_LENGTH or len(local_part) > MAX_LOCAL_PART_LENGTH:
        raise MailboxError(f"Invalid mailbox name. Use {MIN_LOCAL_PART_LENGTH} to {MAX_LOCAL_PART_LENGTH} characters.")
    pattern = PLUS_LOCAL_PART_RE if allow_plus else LOCAL_PART_RE
    if not pattern.fullmatch(local_part):
        allowed = "lowercase letters, digits, underscores, or hyphens"
        if allow_plus:
            allowed = "lowercase letters, digits, underscores, plus signs, or hyphens"
        raise MailboxError(
            f"Invalid mailbox name. Use {allowed}; start and end with a letter or digit."
        )
    if not re.search(r"[a-z]", local_part) or not re.search(r"[0-9]", local_part):
        raise MailboxError("Invalid mailbox name. Include at least one letter and one digit.")
    if local_part in RESERVED_LOCAL_PARTS:
        raise MailboxError(f"Mailbox name is reserved: {local_part}")
    return local_part


def normalize_domain(value: str | None) -> str:
    domain = (value or "").strip().lower()
    if not domain:
        raise MailboxError("Mailbox domain is required.")
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
        raise MailboxError(f"Invalid mailbox domain: {domain}")
    return domain


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def safe_config_view(cfg: dict[str, Any]) -> dict[str, Any]:
    hidden = dict(cfg)
    for key in ("api_token", "read_token"):
        if key in hidden:
            hidden[key] = mask_secret(str(hidden.get(key) or ""))
    return hidden


def safe_registration_view(payload: dict[str, Any], *, reveal_tokens: bool = False) -> dict[str, Any]:
    hidden = dict(payload)
    if reveal_tokens:
        return hidden
    for key in ("agentToken", "readToken"):
        if key in hidden:
            hidden[key] = mask_secret(str(hidden.get(key) or ""))
    return hidden


def require_cfg(cfg: dict[str, Any], key: str) -> str:
    value = str(cfg.get(key) or "").strip()
    if not value:
        raise MailboxError(f"Missing required config value: {key}")
    return value


def build_url(api_base: str, path: str, query: dict[str, Any] | None = None) -> str:
    base = api_base.rstrip("/")
    url = base + path
    if query:
        clean = {k: v for k, v in query.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return url


def https_context() -> ssl.SSLContext | None:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass

    for path in SYSTEM_CA_FILES:
        if Path(path).exists():
            return ssl.create_default_context(cafile=path)
    return None


def request_json(
    method: str,
    url: str,
    *,
    cfg: dict[str, Any],
    body: dict[str, Any] | None = None,
    tolerate: set[int] | None = None,
) -> tuple[int, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "hermes-xialiao-mainbox-skill/1.0",
    }
    api_token = str(cfg.get("api_token") or "").strip()
    read_token = str(cfg.get("read_token") or "").strip()
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    if read_token:
        headers["X-Agent-Mailbox-Token"] = read_token
        headers["X-Agent-Mailbox-Read-Token"] = read_token
        headers["X-Mailbox-Read-Token"] = read_token

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=30, context=https_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return resp.status, None
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError as exc:
                raise MailboxError("Mainbox API returned invalid JSON.", status=resp.status, payload=raw) from exc
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        payload: Any = raw
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            pass
        if tolerate and exc.code in tolerate:
            return exc.code, payload
        message = payload.get("error") if isinstance(payload, dict) else raw
        raise MailboxError(message or f"HTTP {exc.code}", status=exc.code, payload=payload) from exc
    except urllib.error.URLError as exc:
        raise MailboxError(f"Request failed: {exc.reason}") from exc


def cmd_check_name(args: argparse.Namespace) -> int:
    local_part = normalize_local_part(args.local_part)
    domain = normalize_domain(args.domain)
    output({"ok": True, "localPart": local_part, "address": f"{local_part}@{domain}"})
    return 0


def cmd_configure(args: argparse.Namespace) -> int:
    cfg = load_saved_config()
    updates = {
        "api_base": args.api_base,
        "domain": args.domain,
        "agent_id": args.agent_id,
        "address": args.address,
        "api_token": args.api_token,
        "read_token": args.read_token,
    }
    for key, value in updates.items():
        if value:
            cfg[key] = value.strip()
    if cfg.get("domain"):
        cfg["domain"] = normalize_domain(str(cfg["domain"]))
    if cfg.get("agent_id"):
        cfg["agent_id"] = normalize_local_part(str(cfg["agent_id"]))
    save_config(cfg)
    output({"ok": True, "configPath": str(config_path()), "config": safe_config_view(cfg)})
    return 0


def cmd_show_config(_: argparse.Namespace) -> int:
    cfg = load_config()
    output({"ok": True, "configPath": str(config_path()), "statePath": str(state_path()), "config": safe_config_view(cfg)})
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    local_part = normalize_local_part(args.local_part, allow_plus=bool(args.agent_id))
    cfg = load_config()
    if args.api_base:
        cfg["api_base"] = args.api_base.strip()
    if args.domain:
        cfg["domain"] = normalize_domain(args.domain)
    domain = normalize_domain(str(cfg.get("domain") or ""))
    api_base = require_cfg(cfg, "api_base")
    if not cfg.get("api_token"):
        raise MailboxError("Registration requires XIALIAO_MAINBOX_API_TOKEN, MAINBOX_API_TOKEN, HERMES_MAILBOX_API_TOKEN, or MAILBOX_API_TOKEN.")

    agent_id = normalize_local_part(args.agent_id or local_part)
    body: dict[str, Any] = {
        "id": agent_id,
        "localPart": local_part,
        "domain": domain,
        "displayName": args.display_name or f"{agent_id} Agent",
    }
    if args.hermes_profile:
        body["hermesProfile"] = args.hermes_profile

    url = build_url(api_base, "/agents")
    _status, payload = request_json("POST", url, cfg=cfg, body=body)
    if not isinstance(payload, dict):
        raise MailboxError("Mainbox API returned a non-object response.")

    saved = False
    if args.save_config:
        saved_cfg = load_saved_config()
        saved_cfg["api_base"] = api_base
        saved_cfg["agent_id"] = str(payload.get("id") or agent_id)
        saved_cfg["address"] = str(payload.get("address") or f"{local_part}@{domain}")
        saved_cfg["domain"] = domain
        saved_cfg.pop("api_token", None)
        if payload.get("agentToken"):
            saved_cfg["read_token"] = str(payload["agentToken"])
        elif payload.get("readToken"):
            saved_cfg["read_token"] = str(payload["readToken"])
        save_config(saved_cfg)
        saved = True

    output(
        {
            "ok": True,
            "registered": safe_registration_view(payload, reveal_tokens=args.print_token),
            "savedConfig": saved,
            "configPath": str(config_path()) if saved else None,
            "agentTokenSaved": bool(saved and (payload.get("agentToken") or payload.get("readToken"))),
            "agentTokenHidden": bool((payload.get("agentToken") or payload.get("readToken")) and not args.print_token),
        }
    )
    return 0


def trim_message(message: dict[str, Any], max_body_chars: int, *, include_raw_preview: bool = False) -> dict[str, Any]:
    result = dict(message)
    if not include_raw_preview:
        result.pop("rawPreview", None)
    for field in ("text", "html", "rawPreview"):
        value = result.get(field)
        if isinstance(value, str) and len(value) > max_body_chars:
            result[field] = value[:max_body_chars] + "\n[... truncated ...]"
    return result


def message_id(message: Any) -> str:
    if isinstance(message, dict):
        mid = message.get("id") or message.get("messageId")
        if mid:
            return str(mid)
    raise MailboxError("Mailbox message missing id.")


def is_available_for_poll(entry: dict[str, Any], now: float, max_attempts: int) -> bool:
    status = str(entry.get("status") or "")
    if status == "acked":
        return False
    attempts = int(entry.get("attempts") or 0)
    if max_attempts > 0 and attempts >= max_attempts and status != "acked":
        return False
    lease_until = float(entry.get("leaseUntil") or 0)
    if status == "leased" and lease_until > now:
        return False
    return True


def cmd_poll(args: argparse.Namespace) -> int:
    cfg = load_config()
    api_base = require_cfg(cfg, "api_base")
    agent_id = require_cfg(cfg, "agent_id")
    request_cfg = agent_request_config(cfg)
    query = {"limit": args.limit, "status": "unprocessed"}
    url = build_url(api_base, f"/agents/{urllib.parse.quote(agent_id, safe='')}/messages", query)
    _status, payload = request_json("GET", url, cfg=request_cfg)
    if not isinstance(payload, dict):
        raise MailboxError("Mainbox API returned a non-object response.")

    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        raise MailboxError("Mainbox API response field 'messages' must be a list.")

    state = load_state()
    state_messages = state.setdefault("messages", {})
    now = time.time()
    ready: list[dict[str, Any]] = []
    lease_seconds = args.lease_seconds

    for message in messages:
        mid = message_id(message)
        entry = state_messages.get(mid)
        if not isinstance(entry, dict):
            entry = {"status": "new", "attempts": 0}
        if not is_available_for_poll(entry, now, args.max_attempts):
            continue
        entry["status"] = "leased"
        entry["attempts"] = int(entry.get("attempts") or 0) + 1
        entry["leaseUntil"] = now + lease_seconds
        entry["leasedAt"] = utc_now_iso()
        state_messages[mid] = entry
        ready.append(trim_message(message, args.max_body_chars, include_raw_preview=args.include_raw_preview))

    save_state(state)
    if not ready:
        return 0

    output(
        {
            "ok": True,
            "agentId": agent_id,
            "address": cfg.get("address") or payload.get("address"),
            "messageCount": len(ready),
            "leaseSeconds": lease_seconds,
            "messages": ready,
            "ackCommand": f"python3 {scripts_dir() / 'xialiao_mainbox_poll.py'} ack --message-id <id>",
        }
    )
    return 0


def post_message_action(cfg: dict[str, Any], action: str, mid: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    api_base = require_cfg(cfg, "api_base")
    agent_id = require_cfg(cfg, "agent_id")
    url = build_url(api_base, f"/agents/{urllib.parse.quote(agent_id, safe='')}/messages/{urllib.parse.quote(mid, safe='')}/{action}")
    status, payload = request_json("POST", url, cfg=agent_request_config(cfg), body=body or {}, tolerate={404, 405})
    return {"status": status, "payload": payload}


def agent_request_config(cfg: dict[str, Any]) -> dict[str, Any]:
    request_cfg = dict(cfg)
    if not str(request_cfg.get("read_token") or "").strip():
        raise MailboxError(
            "Missing required config value: read_token. Register the inbox first or save the returned agent token."
        )
    request_cfg.pop("api_token", None)
    return request_cfg


def cmd_ack(args: argparse.Namespace) -> int:
    cfg = load_config()
    state = load_state()
    state_messages = state.setdefault("messages", {})
    ids = list(args.message_id or [])
    if args.all_leased:
        ids.extend(
            mid
            for mid, entry in state_messages.items()
            if isinstance(entry, dict) and entry.get("status") == "leased"
        )
    if not ids:
        raise MailboxError("Provide --message-id or --all-leased.")

    results = []
    for mid in sorted(set(ids)):
        remote = None
        try:
            remote = post_message_action(cfg, "ack", mid)
        except MailboxError as exc:
            remote = {"error": str(exc), "status": exc.status}
        entry = state_messages.get(mid)
        if not isinstance(entry, dict):
            entry = {}
        entry.update({"status": "acked", "ackedAt": utc_now_iso(), "leaseUntil": 0})
        state_messages[mid] = entry
        results.append({"messageId": mid, "remote": remote})
    save_state(state)
    output({"ok": True, "acked": results})
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
    cfg = load_config()
    state = load_state()
    state_messages = state.setdefault("messages", {})
    ids = list(args.message_id or [])
    if not ids:
        raise MailboxError("Provide at least one --message-id.")

    results = []
    for mid in sorted(set(ids)):
        remote = None
        body = {"error": args.error or "Processing failed"}
        try:
            remote = post_message_action(cfg, "fail", mid, body)
        except MailboxError as exc:
            remote = {"error": str(exc), "status": exc.status}
        entry = state_messages.get(mid)
        if not isinstance(entry, dict):
            entry = {}
        entry.update({"status": "failed", "failedAt": utc_now_iso(), "leaseUntil": 0, "lastError": body["error"]})
        state_messages[mid] = entry
        results.append({"messageId": mid, "remote": remote})
    save_state(state)
    output({"ok": True, "failed": results})
    return 0


def cmd_install_cron_script(_: argparse.Namespace) -> int:
    scripts_dir().mkdir(parents=True, exist_ok=True)
    target = scripts_dir() / "xialiao_mainbox_poll.py"
    shutil.copy2(Path(__file__).resolve(), target)
    try:
        target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass
    output({"ok": True, "script": "xialiao_mainbox_poll.py", "path": str(target)})
    return 0


def output(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a Hermes Xialiao Mainbox inbox.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check-name", help="Validate a mailbox local part.")
    p.add_argument("local_part")
    p.add_argument("--domain", required=True)
    p.set_defaults(func=cmd_check_name)

    p = sub.add_parser("configure", help="Save mailbox client configuration.")
    p.add_argument("--api-base")
    p.add_argument("--domain")
    p.add_argument("--agent-id")
    p.add_argument("--address")
    p.add_argument("--api-token")
    p.add_argument("--read-token")
    p.set_defaults(func=cmd_configure)

    p = sub.add_parser("show-config", help="Print non-secret mailbox configuration.")
    p.set_defaults(func=cmd_show_config)

    p = sub.add_parser("register", help="Register an agent inbox through the Mainbox API.")
    p.add_argument("local_part")
    p.add_argument("--agent-id")
    p.add_argument("--api-base")
    p.add_argument("--domain")
    p.add_argument("--display-name")
    p.add_argument("--hermes-profile")
    p.add_argument("--save-config", dest="save_config", action="store_true", default=True, help="Save the returned agent inbox config locally. This is the default.")
    p.add_argument("--no-save-config", dest="save_config", action="store_false", help="Do not save returned config; use only when managing tokens externally.")
    p.add_argument("--print-token", action="store_true", help="Print returned agent tokens instead of masking them.")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("install-cron-script", help="Install this helper under HERMES_HOME/scripts.")
    p.set_defaults(func=cmd_install_cron_script)

    p = sub.add_parser("poll", help="Poll unprocessed messages and lease them locally.")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    p.add_argument("--max-body-chars", type=int, default=DEFAULT_MAX_BODY_CHARS)
    p.add_argument("--include-raw-preview", action="store_true", help="Include raw email preview headers for debugging.")
    p.set_defaults(func=cmd_poll)

    p = sub.add_parser("ack", help="Mark messages processed locally and remotely when supported.")
    p.add_argument("--message-id", action="append")
    p.add_argument("--all-leased", action="store_true")
    p.set_defaults(func=cmd_ack)

    p = sub.add_parser("fail", help="Mark messages failed locally and remotely when supported.")
    p.add_argument("--message-id", action="append", required=True)
    p.add_argument("--error")
    p.set_defaults(func=cmd_fail)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["poll"]
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except MailboxError as exc:
        payload = {"ok": False, "error": str(exc)}
        if exc.status is not None:
            payload["status"] = exc.status
        if exc.payload is not None:
            payload["payload"] = exc.payload
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
