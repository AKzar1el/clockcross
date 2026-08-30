# ClockCross Cloudflare AI Gateway Amendment

**Date:** 2026-08-30  
**Status:** Implemented and live-verified  
**Scope:** AI provider transport only; no change to signal, AI authority, option construction, risk, or Alpaca execution

## Trigger

The approved ClockCross design requires a bounded autonomous AI adjudicator but does not require a specific model vendor. During external preflight, no Featherless credential was available. Existing Cloudflare credentials also lacked direct Workers AI REST permission, but a scoped Workers deployment credential could deploy a Worker with an `AI` binding.

Disposable cloud probes established that the Workers AI binding could execute current Cloudflare-hosted models. A final structured-output probe using `@cf/meta/llama-3.3-70b-instruct-fp8-fast` returned the exact ClockCross five-field decision schema.

The project therefore removes the unnecessary Featherless dependency and uses a small authenticated Cloudflare Worker as an OpenAI-compatible adapter.

## Decision

Production AI path:

```text
ClockCross Python adjudicator
  -> authenticated POST /v1/chat/completions
  -> clockcross-ai-gateway Cloudflare Worker
  -> fixed Workers AI model: Llama 3.3 70B fast
  -> provider JSON-schema mode
  -> Worker schema validation
  -> OpenAI-compatible response wrapper
  -> Python Pydantic schema validation
```

Stable gateway base URL:

`https://clockcross-ai-gateway.tomi-seregi99.workers.dev/v1`

Runtime model label:

`clockcross-cloudflare-llama-3.3-70b`

The client-provided `model`, temperature, or arbitrary generation parameters do not select the provider model. The Worker fixes the underlying model and decision schema.

## Gateway constraints

The Worker:

- exposes public read-only `GET /health`;
- accepts AI requests only at `POST /v1/chat/completions`;
- requires `Authorization: Bearer <CLOCKCROSS_AI_AUTH>`;
- accepts only bounded `system` / `user` messages;
- caps request and prompt size;
- fixes temperature to `0` and output to `220` tokens;
- requests a JSON schema with exactly `action`, `confidence`, `idiosyncratic_news_detected`, `driver`, and `reason`;
- rejects additional fields and invalid enums/types;
- validates provider output before returning it;
- returns the OpenAI chat-completions shape expected by the Python adjudicator;
- never receives Alpaca credentials and has no Alpaca trading capability.

The Python adjudicator remains fail-closed and performs an independent schema validation. The model still cannot choose symbols/contracts, change risk limits, or submit orders.

## Security

`CLOCKCROSS_AI_AUTH` is a Cloudflare Worker secret and is not present in repository source/configuration.

For the hackathon bootstrap, the cloud runner derives a domain-separated SHA-256 bearer from the encrypted Cloudflare deployment token and masks it immediately. The matching derived value is piped to the Worker secret binding. This avoids committing or printing another credential while working around the current connector's inability to create a dedicated repository secret directly.

This coupling is temporary. When the temporary Cloudflare credential is rotated after the event, replace it with a dedicated random gateway bearer and rotate `CLOCKCROSS_AI_AUTH` at the same time.

Do not treat the current derivation scheme as long-term key-management guidance.

## Verification evidence

Before adopting the gateway:

- disposable Workers AI binding probes returned successful Cloudflare model executions;
- Llama 3.3 70B JSON-mode probe returned all five required decision fields with valid enums/types;
- the production Worker deployed successfully;
- Worker `/health` returned success;
- an authenticated production gateway call returned an OpenAI-compatible response and valid ClockCross decision schema;
- exact `clockcross preflight` then passed **5/5** against the real development paper environment on 2026-08-30:
  - account active/unblocked;
  - options approved/trading Level 3;
  - 416 parseable COIN contracts in the 7–21 DTE window via indicative feed;
  - Alpaca MCP `get_clock` succeeded;
  - AI provider returned a schema-valid bounded decision.

No order endpoint was used by these preflight checks.

## Rollback

The Python adjudicator remains OpenAI-compatible by contract. If the Cloudflare gateway is unavailable, an alternate compatible endpoint may be supplied through `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` without changing AI authority, deterministic risk, or execution semantics.

Provider failure remains an `abstain`, never a reason to bypass the AI/risk boundary.
