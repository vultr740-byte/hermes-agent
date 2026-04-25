#!/bin/bash
# Docker/Podman entrypoint: bootstrap config files into the mounted volume, then run hermes.
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
INSTALL_DIR="/opt/hermes"

# --- Privilege dropping via gosu ---
# When started as root (the default for Docker, or fakeroot in rootless Podman),
# optionally remap the hermes user/group to match host-side ownership, fix volume
# permissions, then re-exec as hermes.
if [ "$(id -u)" = "0" ]; then
    if [ -n "$HERMES_UID" ] && [ "$HERMES_UID" != "$(id -u hermes)" ]; then
        echo "Changing hermes UID to $HERMES_UID"
        usermod -u "$HERMES_UID" hermes
    fi

    if [ -n "$HERMES_GID" ] && [ "$HERMES_GID" != "$(id -g hermes)" ]; then
        echo "Changing hermes GID to $HERMES_GID"
        # -o allows non-unique GID (e.g. macOS GID 20 "staff" may already exist
        # as "dialout" in the Debian-based container image)
        groupmod -o -g "$HERMES_GID" hermes 2>/dev/null || true
    fi

    # Fix ownership of the data volume. When HERMES_UID remaps the hermes user,
    # files created by previous runs (under the old UID) become inaccessible.
    # Always chown -R when UID was remapped; otherwise only if top-level is wrong.
    actual_hermes_uid=$(id -u hermes)
    needs_chown=false
    if [ -n "$HERMES_UID" ] && [ "$HERMES_UID" != "10000" ]; then
        needs_chown=true
    elif [ "$(stat -c %u "$HERMES_HOME" 2>/dev/null)" != "$actual_hermes_uid" ]; then
        needs_chown=true
    fi
    if [ "$needs_chown" = true ]; then
        echo "Fixing ownership of $HERMES_HOME to hermes ($actual_hermes_uid)"
        # In rootless Podman the container's "root" is mapped to an unprivileged
        # host UID — chown will fail.  That's fine: the volume is already owned
        # by the mapped user on the host side.
        chown -R hermes:hermes "$HERMES_HOME" 2>/dev/null || \
            echo "Warning: chown failed (rootless container?) — continuing anyway"
    fi

    echo "Dropping root privileges"
    exec gosu hermes "$0" "$@"
fi

# --- Running as hermes from here ---
source "${INSTALL_DIR}/.venv/bin/activate"

configure_custom_model_endpoint() {
    if [ -z "${OPENAI_BASE_URL:-}" ]; then
        return 0
    fi

    export HERMES_HOME
    python3 - <<'PY'
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


def load_config(path: Path):
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def fetch_models(base_url: str, api_key: str) -> list[str]:
    normalized = base_url.rstrip("/")
    candidate_bases = [normalized]
    if normalized.endswith("/v1"):
        parent = normalized[:-3].rstrip("/")
        if parent:
            candidate_bases.append(parent)
    else:
        candidate_bases.append(normalized + "/v1")

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_error = None

    for candidate_base in dict.fromkeys(candidate_bases):
        url = candidate_base.rstrip("/") + "/models"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = (url, exc)
            continue

        models = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if model_id:
                models.append(model_id)
        if models:
            return models

    if last_error:
        url, exc = last_error
        print(f"[entrypoint] Warning: could not read {url}: {exc}")
    return []


config_path = Path(os.environ["HERMES_HOME"]) / "config.yaml"
config = load_config(config_path)
current_model = config.get("model")
if isinstance(current_model, dict):
    model_cfg = dict(current_model)
elif isinstance(current_model, str) and current_model.strip():
    model_cfg = {"default": current_model.strip()}
else:
    model_cfg = {}

base_url = os.environ["OPENAI_BASE_URL"].strip().rstrip("/")
api_key = os.environ.get("OPENAI_API_KEY", "").strip()
explicit_model = (
    os.environ.get("OPENAI_MODEL", "").strip()
)
available_models = fetch_models(base_url, api_key)
current_default = str(model_cfg.get("default") or "").strip()

selected_model = explicit_model
if not selected_model and available_models:
    if current_default and current_default in available_models:
        selected_model = current_default

if not selected_model and available_models:
    for candidate in (
        "gpt-5.4-mini",
        "gpt-5.4",
        "gpt-5",
        "gpt-5.1",
        "gpt-5.1-codex-mini",
        "gpt-5.1-codex",
        "gpt-4o-mini",
    ):
        if candidate in available_models:
            selected_model = candidate
            break

if not selected_model and available_models:
    selected_model = available_models[0]

if not selected_model and current_default and "/" not in current_default:
    selected_model = current_default

model_cfg["provider"] = "custom"
model_cfg["base_url"] = base_url
if selected_model:
    model_cfg["default"] = selected_model
else:
    model_cfg.pop("default", None)
    print(
        "[entrypoint] Warning: could not auto-detect models from the custom endpoint. "
        "Set OPENAI_MODEL if your endpoint does not expose /models."
    )

explicit_api_mode = os.environ.get("HERMES_API_MODE", "").strip()
if explicit_api_mode:
    model_cfg["api_mode"] = explicit_api_mode

config["model"] = model_cfg
config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

chosen = str(model_cfg.get("default") or "").strip() or "<unset>"
print(f"[entrypoint] Configured custom model endpoint: {base_url} (model={chosen})")
PY
}

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_hermes_dir().
# The "home/" subdirectory is a per-profile HOME for subprocesses (git,
# ssh, gh, npm …).  Without it those tools write to /root which is
# ephemeral and shared across profiles.  See issue #4426.
mkdir -p "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

# .env
if [ ! -f "$HERMES_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$HERMES_HOME/.env"
fi

# config.yaml
if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
fi

# Ensure the main config file remains accessible to the hermes runtime user
# even if it was edited on the host after initial ownership setup.
if [ -f "$HERMES_HOME/config.yaml" ]; then
    chown hermes:hermes "$HERMES_HOME/config.yaml"
    chmod 640 "$HERMES_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$HERMES_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

configure_custom_model_endpoint
if [ $# -gt 0 ] && command -v "$1" >/dev/null 2>&1; then
    exec "$@"
fi
exec hermes "$@"
