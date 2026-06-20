---
title: "Recharge Link — 为模型余额不足场景提供充值链接"
sidebar_label: "Recharge Link"
description: "为模型余额不足场景提供充值链接"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Recharge Link

为模型余额不足场景提供充值链接。

## Skill 元数据

| | |
|---|---|
| 来源 | 内置（默认安装） |
| 路径 | `skills/productivity/recharge-link` |
| 版本 | `1.0.0` |
| 作者 | Hermes Agent |
| 许可证 | MIT |
| 平台 | linux, macos, windows |
| 标签 | `recharge`, `billing`, `balance`, `payment`, `top-up` |

## 参考：完整 SKILL.md

:::info
以下是 Hermes 在触发该 skill 时加载的完整 skill 定义。这是 skill 激活时 agent 所看到的指令内容。
:::

# Recharge Link Skill

当用户询问如何充值、索要充值链接，或遇到模型计费失败时，提供当前用户的充值入口。此 skill 只生成 Webclaw 充值页 URL；不会创建支付 checkout 会话。

## When to Use

- 用户询问“充值链接”、“怎么充值”、“余额不足怎么办”、“top up”或“recharge”。
- 模型/API 调用失败，并出现 “insufficient balance”、“insufficient credits”、“Payment Required” 或 HTTP 402 等计费相关信息。
- 用户询问当前 bot/agent 实例的支付页面。

## Prerequisites

- agent 运行环境中必须设置 `RECHARGE_TARGET`。
- `RECHARGE_TARGET` 应类似：
  `weixin_0123456789abcdef`、`telegram_0123456789abcdef`、`discord_...`、
  `qq_...` 或 `feishu_...`。
- `RECHARGE_BASE_URL` 可选。未设置时使用：
  `https://www.xialiao.app/recharge/`。

## How to Run

如果上下文中还看不到 target，使用 `terminal` 读取运行时环境，并确定性地生成 URL：

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

- 默认 base URL：`https://www.xialiao.app/recharge/`
- 目标环境变量：`RECHARGE_TARGET`
- 可选 base 覆盖：`RECHARGE_BASE_URL`
- 最终 URL 形态：`https://www.xialiao.app/recharge/<RECHARGE_TARGET>`
- 余额不足提示：`⚠️ 模型余额不足，请充值后重试。`

## Procedure

1. 读取 `RECHARGE_TARGET`。
2. 如果缺失，回复：
   `当前实例还没有配置充值目标，暂时无法生成专属充值链接。`
3. 将 URL 编码后的 target 追加到 `RECHARGE_BASE_URL` 或默认 base URL 后。
4. 如果这是计费失败，回复两行：
   ```text
   ⚠️ 模型余额不足，请充值后重试。
   <recharge-url>
   ```
5. 如果用户只是询问链接，回复：
   ```text
   你的充值链接是：
   <recharge-url>
   ```
6. 如果用户询问 provider checkout URL，说明 checkout 链接只会在打开充值页并选择套餐后创建。

## Pitfalls

- 不要编造 `RECHARGE_TARGET`。
- 不要暴露 API key、bot token、checkout secret 或 webhook secret。
- 不要从这个 skill 直接调用支付 API。
- 不要在支付 provider webhook 确认订单前承诺余额已更新。
- 在群聊中保持回复简短，不展示无关账户信息。充值链接本身就足够。

## Verification

- 生成的 URL 在 base URL 和 encoded target 之间必须只有一个斜杠。
- target 应匹配 Webclaw 充值账号格式：
  `^(weixin|telegram|discord|qq|feishu)_[a-f0-9]{16}$`。
- 打开该 URL 应进入 Webclaw 充值页面，用户可以在那里选择套餐。
