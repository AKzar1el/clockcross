# Featherless Phase-2 robustness search — 2026-09-04

## Why this pass exists

The first Featherless bakeoff found an interesting but non-promotable result: GLM-5.3's incumbent-consensus policy had a positive retrospective mean improvement, but the confidence interval crossed zero, leave-one-out robustness failed, and only 26 of 38 episodes were action-stable. Rather than promote that result after seeing it, this Phase-2 pass broadened the model family under a protocol frozen before credentialed calls.

The research question was deliberately narrow:

> Can a predeclared Featherless challenger beat the existing ClockCross adjudicator on the same 38 pre-holdout signal episodes, survive stability and chronology gates, survive multiple-testing correction, and only then earn access to the Sep 1-3 holdout?

No order client or portfolio mutation endpoint was instantiated.

## Frozen protocol

The protocol SHA-256 was `3bddffbb005ba6752243f50ffde0a8a3f216482689c4c4cd59a5b0ba1f82ae9f` and was verified by the harness before credentialed calls.

The eight new predeclared models were:

- `Qwen/Qwen3.8-Flash-Next`;
- `moonshotai/Kimi-K3`;
- `deepseek-ai/DeepSeek-V4-Pro`;
- `MiniMaxAI/MiniMax-M3`;
- `openai/gpt-oss-120b`;
- `google/gemma-4-31B-it`;
- `SUFE-AIFLM-Lab/Fin-R1`;
- `NousResearch/DeepHermes-Financial-Fundamentals-Prediction-Specialist-Atropos`.

GLM-5.3 was rerun only as a prior-result correction control and was not eligible for Phase-2 promotion.

Before historical evaluation, each model had to pass a nine-call synthetic contract screen: three fixed contexts, three repetitions each, strict five-field JSON validity, unanimous action within each context, p95 latency no greater than 12 seconds, and maximum latency no greater than 20 seconds.

Historical selection then used the same 38 signal episodes from 2026-03-02 through 2026-08-31, five repetitions per model/episode, the same bounded ClockCross prompt and evidence boundary, temperature zero, and no retrospective raw news reconstruction. Direct replacement and incumbent-consensus were the only individual-model policy families. A fixed five-model frontier ensemble could run only if every predeclared member passed the contract screen.

Promotion required positive paired mean improvement; a positive moving-block-bootstrap 95% lower bound; positive leave-one-episode and leave-one-month minima; positive first-half and second-half chronological improvements; complete schema validity; complete action stability; bounded historical latency; a selection-adjusted Sharpe probability of at least 0.95; White Reality Check p < 0.05; and CSCV-style PBO <= 0.20. The search universe counted 25 total policy trials, including earlier ClockCross/Featherless attempts.

## Contract screen

Six models reached historical selection:

| Model | Contract | Key observation |
| --- | --- | --- |
| Qwen3.8-Flash-Next | pass | 9/9 schema-valid and unanimous; ~1.54 s p95 |
| Fin-R1 | pass | 9/9 schema-valid and unanimous; ~7.32 s p95 |
| Gemma 4 31B | pass | 9/9 schema-valid and unanimous; ~6.30 s p95 |
| Kimi-K3 | pass | 9/9 schema-valid and unanimous; ~5.53 s p95 |
| GPT-OSS-120B | pass | 9/9 schema-valid and unanimous; ~1.80 s p95 |
| GLM-5.3 correction control | pass | 9/9 schema-valid and unanimous; ~3.86 s p95 |

Three new challengers were rejected before historical returns could influence selection:

- MiniMax-M3 used the full 512-token allowance and ended with `finish_reason=length`, so strict JSON validation failed on all synthetic calls despite acceptable latency.
- DeepHermes Financial produced one invalid response and was not unanimous; its contract p95 was also about 15.93 seconds.
- DeepSeek-V4-Pro produced valid schema but failed the unanimity requirement; its recorded model availability was also `offline` during the run and its maximum contract latency reached about 14.59 seconds.

Because MiniMax and DeepSeek were members of the fixed five-model frontier ensemble, the ensemble was not evaluated. Its membership was frozen; substituting another model after seeing contract results would have changed the predeclared experiment.

## Historical selection result

**No candidate beat the incumbent on mean paired policy return.** This makes the result stronger than merely failing an exotic statistical threshold: every evaluated policy was already behind before the multiple-testing corrections were applied.

The closest result overall was the non-promotable GLM-5.3 correction control:

- direct replacement: **-1.37 bps mean improvement** versus the incumbent;
- incumbent consensus: **-3.31 bps mean improvement**.

The closest *new* challenger was Gemma 4 31B incumbent-consensus:

- candidate mean policy return: about **+28.26 bps**;
- incumbent mean policy return in this directional/no-retrospective-news comparison: about **+31.38 bps**;
- paired improvement: **-3.12 bps**;
- 38/38 action-stable episodes;
- 190/190 valid historical responses;
- but historical p95 latency was about **16.53 seconds**, above the frozen 12-second production gate;
- moving-block-bootstrap interval still crossed zero;
- first-half chronological improvement was negative;
- leave-one-episode and leave-one-month robustness were negative.

Other new models were farther behind:

- Qwen direct replacement: about **-28.41 bps** mean improvement; 37/38 stable episodes and 186/190 valid calls.
- Qwen incumbent consensus: about **-20.12 bps**.
- Fin-R1 direct replacement: about **-23.49 bps**; consensus about **-9.03 bps**.
- Kimi-K3 direct replacement: about **-37.52 bps**; consensus about **-29.23 bps**. It was schema-valid on all 190 historical calls but only stable on 35/38 episodes and exceeded the frozen historical p95-latency gate.
- GPT-OSS-120B direct replacement: about **-26.52 bps**; consensus about **-25.05 bps**. It was only stable on 27/38 episodes and produced 153 valid responses out of 190.
- Gemma direct replacement: about **-11.39 bps**.

Fin-R1 was stable on 37/38 episodes with 186/190 valid calls. Its behavior was heavily reversion-oriented, but that did not translate into superior paired returns.

## Multiple-testing result

The search-level diagnostics strongly reject the idea that we found a hidden winner:

- observed best mean improvement: **-1.37 bps**;
- White Reality Check p-value: **0.9196**;
- CSCV-style probability of backtest overfitting: **0.70** across 20 splits;
- no candidate passed the base gates;
- no candidate passed the multiple-testing gates;
- no candidate passed full selection.

These corrections were intentionally conservative. White's Reality Check asks whether the best model encountered in a specification search has genuine predictive superiority over the benchmark rather than simply being the luckiest model in the search. The PBO/CSCV family addresses the risk that the strategy selected in-sample degrades out-of-sample, while the Deflated-Sharpe-style diagnostic penalizes repeated trials and non-normal return behavior.

## The most useful replication finding: GLM-5.3's apparent edge disappeared

Phase 1 had shown approximately **+11.74 bps** mean improvement for GLM-5.3 as an incumbent-consensus filter. Phase 2 reran GLM-5.3 under the new frozen search only as a correction control.

The apparent edge did not replicate:

- Phase-1 consensus improvement: **+11.74 bps**;
- Phase-2 consensus improvement: **-3.31 bps**;
- Phase-2 direct replacement improvement: **-1.37 bps**;
- Phase-1 stable episodes: **26/38**;
- Phase-2 stable episodes: **23/38**;
- the effective action or stability classification changed on **10/38 episodes** between the two accepted runs.

That is exactly the failure mode the earlier promotion gate was protecting against. A superficially attractive one-run mean was not durable enough to justify putting GLM-5.3 in the money path.

## Holdout discipline

The Sep 1-3 holdout was **not opened**. The protocol required a candidate to clear every pre-holdout gate first, and none did.

This preserves the holdout rather than repeatedly spending it until a model happens to fit those three known competition sessions. Sep 3's recorded company-news veto also remains non-overridable.

## Cost and execution evidence

Accepted GitHub Actions run: `33819396652` at head `2ed416ec80c546e1ec1f2c5250cc5264dcb85457`.

The research workflow passed Alpaca MCP compatibility, Ruff, strict mypy, and **231 tests with 1 skipped** before running the credentialed bakeoff. The evidence artifact was uploaded as artifact `9919245155` with ZIP SHA-256 `ca8de03ee70ea4af3df42a3ca6400cf670c9c446368060aed9bb6331a75438ce`.

Phase-2 Featherless harness-accounted spend was **$1.01298647**, well below the frozen $8 additional ceiling. This is harness accounting, not a claim about the provider dashboard's current remaining credit.

## Decision

**Do not give any Phase-2 Featherless model trading authority for Sep 4.**

The current production strategy remains the strongest supported policy:

- beta-40 residual;
- 1.00% raw residual gate;
- 09:55 ET decision;
- current Cloudflare Llama continuation/reversion/abstain authority;
- company-news hard veto;
- 60-minute / 10:55 ET exit;
- current hardened vertical constructor and risk envelope;
- one contract;
- Featherless GLM-5.3 as a non-blocking shadow/model-risk observer only.

The Phase-2 search increased confidence in that decision rather than producing a last-minute replacement. Most importantly, it independently falsified the tempting Phase-1 GLM promotion thesis.
