# 2026-09-04 — Featherless directional bakeoff

## Decision

**Do not give Featherless trading authority for the Sep 4 competition session.**

The predeclared read-only bakeoff did not produce a challenger that cleared every promotion gate before the untouched Sep 1–3 holdout. The holdout therefore remained sealed and no strategy mutation was promoted.

The appropriate production use of Featherless is the already-proposed **shadow/model-risk observer**: Cloudflare Llama remains authoritative, a Featherless model may independently review the same bounded context, and deterministic code records agreement/disagreement without allowing Featherless to create, veto, reverse, resize, or delay a trade.

## Protocol

The protocol was frozen before the accepted run in `artifacts/research/featherless-bakeoff-protocol-2026-09-03.json`.

Selection used 38 signal episodes from March 2 through August 31, 2026. Sep 1, Sep 2, and Sep 3 were held out. Every challenger was called five times per episode and required at least four identical actions to count as stable.

Only two candidate policies were admitted:

1. Featherless directional replacement, while preserving the incumbent company-news veto.
2. Incumbent + Featherless consensus filter.

Promotion required all of the following before the holdout could be opened:

- positive paired mean improvement versus the incumbent;
- positive lower bound of a paired 95% bootstrap confidence interval;
- positive leave-one-episode-out minimum mean improvement;
- positive leave-one-month-out minimum mean improvement;
- stable actions on every selection episode.

The models did not see future 60-minute returns. Historical raw Alpaca REST news was intentionally excluded from model input because the prior Sep 3 investigation showed that it did not faithfully recreate the production MCP-news context. That makes this a directional model-quality comparison, not a faithful replay of the live company-news decision path.

No order client or mutation endpoint was instantiated.

## Accepted run

GitHub Actions run: `33813521319`  
Head SHA: `3693dd178b02bcef78abf41cfe460f26aeed6cd6`  
Evidence artifact ID: `9916320816`  
Evidence ZIP SHA-256: `15cd10bc54f3a8b64aa8774ecce08628ba6bd8a7dfb7821bda4475b9a080e990`

The accepted run passed Ruff, strict mypy, and the full test suite (`223 passed, 1 skipped`) before the credentialed research step.

Accepted-run Featherless usage accounted for **$0.30269687**.

### GLM-5.3

`zai-org/GLM-5.3` was the only challenger with a positive paired mean improvement, but it did not clear the robustness gates.

| Policy | Candidate trades | Trade hit rate | Candidate mean | Mean improvement vs incumbent | 95% paired CI | Stable episodes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Directional replacement | 19 | 57.9% | +37.13 bps | **+9.22 bps** | -27.48 to +48.42 bps | 26/38 |
| Consensus filter | 18 | 61.1% | +39.65 bps | **+11.74 bps** | -23.22 to +50.90 bps | 26/38 |

For the stronger consensus result, leave-one-episode-out minimum improvement was approximately **-0.91 bps** and leave-one-month-out minimum improvement was approximately **-3.38 bps**. Action stability also failed materially: 12 of 38 episodes did not reach the required 4/5 action agreement.

This is interesting model-risk evidence, but it is not sufficient evidence for production authority.

### DeepSeek V4 Flash

`deepseek-ai/DeepSeek-V4-Flash-0731` was stable on 37/38 episodes but materially underperformed the paired incumbent:

- candidate trades: 7;
- trade hit rate: 57.1%;
- candidate mean: +8.02 bps;
- incumbent mean in this directional comparison: +27.91 bps;
- paired mean improvement: **-19.89 bps**;
- 95% paired CI: approximately -77.07 to +36.37 bps.

It therefore failed the economic and robustness gates.

### GLM-5.3-Flash

The initial GLM runs exhausted the original 220-token ceiling before emitting JSON. Before the accepted rerun, a transport-only amendment was frozen: GLM received a 512-token bounded completion allowance, `reasoning_effort=low`, and `enable_thinking=false`; the model set, prompts, scoring, selection window, holdout, and promotion gates did not change.

Even after that correction, `zai-org/GLM-5.3-Flash` produced no schema-valid JSON in 190/190 selection calls. All calls ended normally (`finish_reason=stop`), but parsing failed with `JSONDecodeError`. Its derived all-abstain score is therefore not interpreted as model-quality evidence.

### Llama 3.3 70B provider-control

`meta-llama/Llama-3.3-70B-Instruct` was reported active/available by model metadata but its attempted request was rejected by the gated access boundary. No provider-control model-quality conclusion is drawn.

## Holdout

The Sep 1–3 holdout was **not evaluated** because no selection candidate cleared all predeclared gates. This is intentional. Opening the holdout and then iterating would turn the final competition day into post-selection fitting.

## Spend accounting

Research-harness accounted Featherless spend across the executed diagnostics was:

- initial diagnostic run: approximately `$0.36824601`;
- duplicate amended run started before the final protocol-amendment commit: `$0.30035043` — spend accounting only, not accepted model evidence;
- final accepted amended run: `$0.30269687`.

Total harness-accounted spend: approximately **$0.97129331**. This is not a claim about the live account balance; provider billing views remain authoritative for remaining credits.

## Interpretation

The experiment found no defensible reason to replace or gate the validated Cloudflare adjudicator tomorrow.

GLM-5.3 is nevertheless useful precisely because it sometimes disagrees with the incumbent and because its repeated actions were not stable enough for authority. That makes it appropriate as a **non-authoritative shadow observer** for prospective model-risk evidence.

The accepted next architecture is therefore:

> Cloudflare Llama authoritative adjudicator → deterministic trading/risk path unchanged; Featherless GLM-5.3 independently observes the same bounded decision context → deterministic agreement/disagreement audit → zero Featherless execution authority.

This preserves the validated ClockCross policy while adding a real second-provider/model-risk signal for the final prospective session.
