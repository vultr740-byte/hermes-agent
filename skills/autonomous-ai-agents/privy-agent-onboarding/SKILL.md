---
name: privy-agent-onboarding
description: Set up Privy agent wallets for login, funding, signing, and onchain transactions. Use when Hermes needs Ethereum or Solana wallet access through Privy on the host machine.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [privy, wallets, ethereum, solana, onchain, crypto, setup]
    related_skills: [hermes-agent]
    requires_toolsets: [terminal]
    homepage: https://agents.privy.io
---

# Privy Agent Onboarding

Use Privy to give Hermes Ethereum and Solana wallets on the real host machine.

The upstream reference for this workflow lives at `https://agents.privy.io/skill.md`.
Re-check it if the auth flow, CLI flags, or supported RPC methods change.

## When to Use

Load this skill when the user wants Hermes to:

- log into Privy agent wallets
- restore or back up an existing Privy session
- fund the agent wallet
- list wallet addresses
- sign messages or transactions
- send raw Privy wallet RPC payloads

## Guardrails

- Run these commands on the host machine with the `terminal` toolset, not in a sandboxed code runner.
- Commands need access to the host keychain or `~/.privy/`, so they must execute where Hermes actually runs.
- Treat the returned credentials JSON blob like a secret. Do not paste it into logs, commits, or public channels.
- Prefer `pnpm dlx @privy-io/agent-wallet-cli ...` for ad hoc use.
- If only `corepack` exists, use `corepack pnpm dlx ...`.
- Do not switch this workflow to `npx`.
- Step 1 login must happen before Step 2 completion. The pending session created in Step 1 is required.

## Quick Check

Before starting, detect which CLI entrypoint is available:

```bash
pnpm --version 2>/dev/null || true
corepack --version 2>/dev/null || true
```

Use one of these command prefixes:

```bash
pnpm dlx @privy-io/agent-wallet-cli
```

or:

```bash
corepack pnpm dlx @privy-io/agent-wallet-cli
```

In the examples below, replace the prefix if you need the `corepack pnpm` fallback.

## Host Prerequisites

macOS usually needs no extra setup.

Linux:

```bash
sudo apt install -y libsecret-tools
```

Windows PowerShell:

```powershell
Install-Module Microsoft.PowerShell.SecretManagement -Scope CurrentUser
Install-Module Microsoft.PowerShell.SecretStore -Scope CurrentUser
```

Without a working keychain or secret store, the CLI falls back to `~/.privy/session.json`.

## Login Flow

Run the login flow yourself from Hermes on the real target host.
Do not ask the user to run the command manually unless Hermes cannot reach the correct machine.

When you run Step 1, deliver the raw command output to the user as its own standalone message.
Do not merge that output into a summary, narration, or a combined reply.

### Step 1: Initiate Login

```bash
pnpm dlx @privy-io/agent-wallet-cli login --non-interactive
```

This creates a pending session and opens the browser authentication flow.
The output from this command is user-facing and should be forwarded as-is so the user can finish the browser step and send back the credentials blob.

### Step 2: Finish Login with the Credentials Blob

After the user completes browser authentication and sends back the JSON blob, run:

```bash
pnpm dlx @privy-io/agent-wallet-cli login --non-interactive '{"ethereum":{"wallet_id":"...","address":"0x..."},"solana":{"wallet_id":"...","address":"..."}}'
```

### Back Up the Session Immediately

Some environments fail to persist keychain state reliably, so back up the session after a successful login:

```bash
cat ~/.privy/session.json > ~/.privy/session.backup.json 2>/dev/null || security find-generic-password -s "privy-agent-cli" -w | tee ~/.privy/session.backup.json > /dev/null
```

If later commands report that the agent is logged out, restore from the backup:

```bash
cp ~/.privy/session.backup.json ~/.privy/session.json && chmod 600 ~/.privy/session.json
```

## Persist Wallet Details

After login succeeds, record the wallet addresses in Hermes memory or deployment notes so later conversations know wallet access exists:

```text
Privy Agent Wallets (via @privy-io/agent-wallet-cli):
  Ethereum: 0x<address>
  Solana:   <address>
  Logged in: <date>
  Session expires: about 7 days from login
```

## Common Commands

Fund the wallets:

```bash
pnpm dlx @privy-io/agent-wallet-cli fund
```

List wallets:

```bash
pnpm dlx @privy-io/agent-wallet-cli list-wallets
```

Send RPC payloads:

```bash
pnpm dlx @privy-io/agent-wallet-cli rpc --json '<body>'
```

Or from stdin:

```bash
echo '<body>' | pnpm dlx @privy-io/agent-wallet-cli rpc
```

## Supported RPC Categories

Ethereum:

- `personal_sign`
- `eth_sendTransaction`
- `eth_signTransaction`
- `eth_signTypedData_v4`
- `secp256k1_sign`
- `eth_sign7702Authorization`
- `eth_signUserOperation`

Solana:

- `signTransaction`
- `signAndSendTransaction`
- `signMessage`

## Examples

Sign an Ethereum message:

```bash
pnpm dlx @privy-io/agent-wallet-cli rpc --json '{
  "method": "personal_sign",
  "params": {
    "message": "Hello from Hermes"
  }
}'
```

Send an Ethereum transaction:

```bash
pnpm dlx @privy-io/agent-wallet-cli rpc --json '{
  "method": "eth_sendTransaction",
  "params": {
    "transaction": {
      "to": "0xRecipientAddress",
      "value": "0x2386F26FC10000",
      "chainId": 1
    }
  }
}'
```

Sign and send a Solana transaction:

```bash
pnpm dlx @privy-io/agent-wallet-cli rpc --json '{
  "method": "signAndSendTransaction",
  "params": {
    "transaction": "<base64-encoded-transaction>"
  }
}'
```

## Verification

After setup, verify with:

```bash
pnpm dlx @privy-io/agent-wallet-cli list-wallets
```

Successful verification should show wallet addresses without forcing a new login.

## Pitfalls

- If Step 2 fails because the pending session expired, restart from Step 1.
- If the CLI says the agent is logged out unexpectedly, restore `~/.privy/session.backup.json` and retry.
- If neither `pnpm` nor `corepack` exists, stop and tell the user Privy CLI cannot be used from this host yet.
- If the host lacks a working keychain, expect session persistence to rely on `~/.privy/session.json`.
