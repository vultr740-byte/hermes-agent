---
name: privy-agent-onboarding
description: Set up Privy agent wallets and paid API requests.
version: 1.0.0
author: Privy
license: MIT
platforms: [linux, macos, windows]
homepage: https://agents.privy.io
metadata:
  author: privy
  version: 1
  hermes:
    tags: [privy, wallets, ethereum, solana, onchain, crypto, x402, mpp]
    related_skills: [hermes-agent]
    requires_toolsets: [terminal]
---

# Privy Agent Wallets

Use Privy to give Hermes its own Ethereum and Solana wallets on the real host machine. Once logged in, Hermes can sign messages, send transactions, interact with smart contracts, and make paid API requests using x402 or MPP payment protocols.

The upstream reference for this workflow is `https://agents.privy.io/skill.md`. Re-fetch it when Privy changes auth flow, CLI command names, wallet methods, or paid-request support.

## When to Use

- The user wants to set up or restore Privy agent wallet access.
- The user wants Hermes to fund a wallet, list wallet addresses, sign messages, send transactions, or call Privy wallet RPC methods.
- The user wants to make paid HTTP requests through x402 or MPP.
- The user asks about `privy-agent-wallet`, `agents.privy.io`, agent wallets, or Privy CLI wallet onboarding.

## Prerequisites

- Use the `terminal` tool on the real host machine where Hermes runs.
- Node.js and `pnpm` must be available. If only `corepack` is present, enable or invoke `corepack pnpm`.
- The command prefix is always:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet
```

Important: the npm package is `@privy-io/agent-wallet-cli`, but the binary is `privy-agent-wallet`. Do not use `npx`, bare `pnpm dlx` against the package name, or the old two-step credentials-copy login flow.

## How to Run

Use the Privy CLI through `pnpm --package` so the package and binary names are both explicit:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet <command>
```

If `pnpm` is only available through Corepack, use:

```bash
corepack pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet <command>
```

Run commands on the real host, not in a disposable sandbox.

## Quick Reference

Login with OAuth device flow:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet login
```

Fund the agent wallet:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet fund
```

List wallets:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet list-wallets
```

Send a wallet RPC payload:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet rpc --json '<body>'
```

Or from stdin:

```bash
echo '<body>' | pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet rpc
```

Make an x402 paid request:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet fetch-x402 <url> --max-value <base-units>
```

Make an MPP paid request:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet fetch-mpp <url> --max-value <base-units>
```

Logout:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet logout
```

## Procedure

### Optional Host Setup

macOS usually needs no extra setup because the CLI can use the system keychain.

Linux:

```bash
sudo apt install -y libsecret-tools
```

Windows PowerShell, run as admin:

```powershell
Install-Module Microsoft.PowerShell.SecretManagement -Scope CurrentUser
Install-Module Microsoft.PowerShell.SecretStore -Scope CurrentUser
```

Without a working OS credential manager, the CLI falls back to an encrypted file at `~/.privy/session.json`.

1. Confirm whether the current environment runs terminal commands on the user's real host. Codex, Claude Code, Cursor, Windsurf, Cline, and this Hermes terminal flow normally do. If commands run in an ephemeral sandbox that will be discarded, do not log in there.
2. Check for `pnpm`:

```bash
pnpm --version 2>/dev/null || corepack pnpm --version 2>/dev/null || true
```

3. If the user is setting up Privy access, run the device-flow login yourself from the host:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet login
```

4. When the CLI prints the verification URL and user code, show the code prominently to the user. They must verify that the browser page shows the same code before approving.
5. Wait for the CLI to finish polling. Successful login prints wallet addresses and stores the session in the OS credential manager or `~/.privy/session.json`.
6. Persist non-secret wallet facts in memory or deployment notes: Ethereum address, Solana address, login date, and the command prefix. Do not store OAuth tokens or session JSON in memory, logs, commits, or chat.
7. Verify wallet access:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet list-wallets
```

## Wallet RPC

The CLI infers Ethereum or Solana from the RPC method and routes to the correct wallet.

Supported Ethereum methods:

- `personal_sign`
- `eth_sendTransaction`
- `eth_signTransaction`
- `eth_signTypedData_v4`
- `secp256k1_sign`
- `eth_sign7702Authorization`
- `eth_signUserOperation`

Supported Solana methods:

- `signTransaction`
- `signAndSendTransaction`
- `signMessage`

Ethereum `eth_sendTransaction` and `eth_signTransaction` require `caip2` at the top level and the transaction object under `params.transaction`:

```json
{
  "method": "eth_sendTransaction",
  "caip2": "eip155:8453",
  "params": {
    "transaction": {
      "to": "0x...",
      "value": "0x...",
      "data": "0x..."
    }
  }
}
```

Common chain IDs:

| Chain | `caip2` |
| --- | --- |
| Ethereum | `eip155:1` |
| Base | `eip155:8453` |
| Optimism | `eip155:10` |
| Arbitrum | `eip155:42161` |
| Sepolia | `eip155:11155111` |

## Examples

Sign an Ethereum message:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet rpc --json '{
  "method": "personal_sign",
  "params": {
    "message": "Hello from Hermes"
  }
}'
```

Send ETH on Base:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet rpc --json '{
  "method": "eth_sendTransaction",
  "caip2": "eip155:8453",
  "params": {
    "transaction": {
      "to": "0xRecipientAddress",
      "value": "0x2386F26FC10000"
    }
  }
}'
```

Send a Solana transaction:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet rpc --json '{
  "method": "signAndSendTransaction",
  "params": {
    "transaction": "<base64-encoded-transaction>"
  }
}'
```

## Paid Requests

The CLI can call APIs that charge per request. When a server responds with `402 Payment Required`, the CLI signs and submits payment from the agent wallet.

Use `fetch-x402` for x402 APIs. It pays with USDC on Base via EIP-712 typed data signatures:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet fetch-x402 "https://x402-gateway-production.up.railway.app/api/crypto/trending" --max-value 1500
```

Use `fetch-mpp` for MPP APIs. It pays with stablecoins on Tempo via the `tempo` payment method:

```bash
pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet fetch-mpp --method POST --body '{"query":"latest AI research"}' "https://parallelmpp.dev/api/search" --max-value 100000
```

Options for both commands:

| Option | Meaning |
| --- | --- |
| `--method <method>` | HTTP method, default `GET`. |
| `--body <json>` | JSON request body. |
| `--header <header>` | Additional header, repeatable, formatted as `"Name: Value"`. |
| `--max-value <n>` | Maximum payment in base units, default `1000000` = 1 USDC. |

Both commands fail closed if the payment amount cannot be determined or exceeds `--max-value`. Make sure the wallet has sufficient USDC for x402 on Base, or stablecoins for MPP on Tempo. Use `fund` first when needed.

## Pitfalls

- Do not run login in a disposable sandbox whose home directory or keychain will be reset.
- Do not ask the user to run login manually when the `terminal` tool can run on the real host.
- Do not use `npx`.
- Do not use the old two-step credentials-copy login flow.
- Do not ask the user for a credentials JSON blob; OAuth device flow no longer requires copy/paste credentials.
- Do not paste session JSON, OAuth tokens, private keys, checkout secrets, or keychain output into chat or logs.
- Before any transaction or paid API call, summarize the action, chain, recipient/API, and maximum spend. Ask for confirmation when the user's intent is not already explicit.
- If login appears stuck, show the device code again and ask the user to approve the browser prompt.
- If wallet commands say the user is logged out, rerun `login`; do not try to reconstruct old session files.

## Verification

- `metadata.version` is `1`.
- The login command is `pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet login`.
- The skill says not to use `npx`, and no command example invokes `npx`.
- The skill does not contain the old two-step credentials-copy login command.
- `list-wallets` shows Ethereum and Solana wallet addresses after login.
- `fetch-x402` and `fetch-mpp` examples include explicit `--max-value` spending caps.
