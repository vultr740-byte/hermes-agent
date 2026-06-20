# Provider Message Metadata Sanitization

## Summary

Hermes gateway can attach platform metadata to live conversation messages before
the session is persisted. That metadata must not be sent to OpenAI-compatible
providers.

The production failure on `hermes-weixin-3ed38ae5a1-5p7354` was caused by a
`timestamp` key leaking into `messages[]` for `/v1/chat/completions`.

## Symptoms

- Hermes retries the model call and then returns:
  `HTTP 502 - [upstream] | 502: Bad gateway`
- Later replays may return:
  `403 GROUP_DISABLED`
- The same request succeeds when the non-standard `timestamp` field is removed
  from every chat message object.

## Root Cause

`feat(gateway): inject stable human-readable message timestamps` added platform
event timestamps as persisted user-message metadata. The timestamp is valid
Hermes session metadata, but it is not part of the OpenAI chat message schema.

Some providers ignore extra message keys. Clawfather/OneAPI does not: a user
message shaped like this can be rejected or routed incorrectly:

```json
{
  "role": "user",
  "content": "hi",
  "timestamp": 1781936400.0
}
```

## Fix

Strip `timestamp` at the API boundary, not at the persistence boundary.

Current fix location:

- `agent/agent_runtime_helpers.py`
- Function: `sanitize_api_messages`

This keeps session DB timestamps intact while ensuring provider request payloads
only contain provider-facing message fields.

Regression test:

- `tests/run_agent/test_agent_guardrails.py`
- Test: `test_internal_timestamp_metadata_is_stripped_from_api_copy`

## Verification

Production replay evidence:

- Full request with `messages[].timestamp`: provider returned an upstream error.
- Same request with only `timestamp` removed: provider returned HTTP 200.
- Tools schema, developer/system prompt length, and `max_completion_tokens` were
  not sufficient to reproduce the failure by themselves.

Local verification command:

```bash
.venv/bin/python -m pytest \
  tests/run_agent/test_agent_guardrails.py \
  tests/run_agent/test_session_meta_filtering.py \
  -q
```

Expected result:

```text
41 passed
```

## Operational Note

If this appears again on a strict OpenAI-compatible provider, inspect the request
debug dump first:

```bash
jq '.request.body.messages[] | keys' request_dump_*.json
```

Provider-bound messages should not contain Hermes-only keys such as
`timestamp`. If more internal metadata fields are added in the future, extend
the API-bound sanitizer instead of removing metadata from session persistence.
