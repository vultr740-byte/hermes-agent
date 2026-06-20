---
title: "Recharge Link — Provide recharge links for low model balance"
sidebar_label: "Recharge Link"
description: "Provide recharge links for low model balance"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Recharge Link

Provide recharge links for low model balance.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/productivity/recharge-link` |
| Version | `1.0.0` |
| Author | Hermes Agent |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `recharge`, `billing`, `balance`, `payment`, `top-up` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Recharge Link Skill

Provide the current user's recharge entry point when they ask how to recharge,
request a recharge link, or hit a model billing failure. This skill only builds
the Webclaw recharge page URL; it does not create a payment checkout session.

## When to Use

- The user asks "充值链接", "怎么充值", "余额不足怎么办", "top up", or "recharge".
- A model/API call fails with billing language such as "insufficient balance",
  "insufficient credits", "Payment Required", or HTTP 402.
- The user asks for the payment page for the current bot/agent instance.

## Prerequisites

- `RECHARGE_TARGET` must be set in the agent runtime environment.
- `RECHARGE_TARGET` should look like
  `weixin_0123456789abcdef`, `telegram_0123456789abcdef`, `discord_...`,
  `qq_...`, or `feishu_...`.
- `RECHARGE_BASE_URL` is optional. If absent, use
  `https://www.xialiao.app/recharge/`.

## How to Run

If the target is not already visible in context, use `terminal` to read the
runtime environment and build the URL deterministically:

```bash
python3 - <<'PY'
import os
from urllib.parse import quote

target = (os.environ.get("RECHARGE_TARGET") or "").strip()
base = (os.environ.get("RECHARGE_BASE_URL") or "https://www.xialiao.app/recharge/").strip()

if not target:
    print("")
else:
    if not base.endswith("/"):
        base += "/"
    print(f"{base}{quote(target, safe='')}")
PY
```

## Quick Reference

- Default base URL: `https://www.xialiao.app/recharge/`
- Target env var: `RECHARGE_TARGET`
- Optional base override: `RECHARGE_BASE_URL`
- Final URL shape: `https://www.xialiao.app/recharge/<RECHARGE_TARGET>`
- Billing message: `⚠️ 模型余额不足，请充值后重试。`

## Procedure

1. Read `RECHARGE_TARGET`.
2. If it is missing, say:
   `当前实例还没有配置充值目标，暂时无法生成专属充值链接。`
3. Build the recharge URL by appending the URL-encoded target to
   `RECHARGE_BASE_URL` or the default base URL.
4. If this is a billing failure, answer with two short lines:
   ```text
   ⚠️ 模型余额不足，请充值后重试。
   <recharge-url>
   ```
5. If the user simply asks for the link, answer:
   ```text
   你的充值链接是：
   <recharge-url>
   ```
6. If the user asks for the provider checkout URL, explain that checkout links
   are created only after they open the recharge page and choose a package.

## Pitfalls

- Do not invent a `RECHARGE_TARGET`.
- Do not expose API keys, bot tokens, checkout secrets, or webhook secrets.
- Do not call payment APIs directly from this skill.
- Do not promise a balance update before the payment provider webhook confirms
  the order.
- In group chats, keep the response short and avoid showing unrelated account
  details. The recharge link itself is enough.

## Verification

- The generated URL must contain exactly one slash between the base URL and
  encoded target.
- The target should match the Webclaw recharge account format:
  `^(weixin|telegram|discord|qq|feishu)_[a-f0-9]{16}$`.
- Opening the URL should land on the Webclaw recharge page where the user can
  choose a package.
