# ClockCross Sep 3 adaptive-regime investigation

## Scope

This pass tests whether the Sep 1-3 prospective evidence justifies refitting ClockCross toward very recent outcomes before the final Sep 4 competition session.

Production was not modified. All challengers were evaluated chronologically using only completed prior signal outcomes, behind the existing 1.00% residual gate. No order endpoint was instantiated.

The accepted production benchmark remains the Sep 1 six-month replay: 39 signals, 36 AI trades, 3 AI abstentions, 21-15 directional record, and +50.7 bps mean chosen-direction 60-minute COIN return. Those values are underlying-direction diagnostics, not exact historical option P&L.

## Predeclared adaptive challengers

Three challengers were fixed before reading their outcomes:

1. `previous_signal`: choose whichever residual thesis (continuation or reversion) would have won on the immediately preceding signal episode.
2. `ewma_half_life_3_signals`: exponentially weight completed continuation outcomes with a 3-signal half-life and choose continuation/reversion from the sign of that score.
3. `rolling_ridge_10_signals`: ridge regression (`lambda = 1`) on the previous 10 signal episodes using only residual and 09:30-09:40 opening return, then map the predicted absolute COIN return to continuation/reversion.

No window, lambda, feature set, gate, or threshold was tuned after seeing Sep 3.

## Results

| Challenger | Six-month directional result | Recent Aug 3-Sep 3 | Sep 3 choice | Sep 3 underlying-direction result |
| --- | --- | --- | --- | ---: |
| Previous signal | 24-15, 61.5%, +62.1 bps mean | 4-2, **+0.6 bps mean** | reversion | **-314.2 bps** |
| 3-signal EWMA | 21-16, 56.8%, +19.3 bps mean | 3-3, **-65.1 bps mean** | reversion | **-314.2 bps** |
| Rolling ridge-10 | 17-13, 56.7%, +57.3 bps mean | 3-3, **+10.8 bps mean** | continuation | **+314.2 bps** |

The user's proposed intuition — refit the thesis from the previous day / previous signal — is therefore falsified by the exact prospective Sep 3 case. It would have converted a correct abstention into a very large wrong-direction underlying call.

The ridge challenger called Sep 3 correctly, but its recent record is only 3-3 and the six-month hit rate is below the accepted AI benchmark. Sep 3 is one observation, so promoting ridge now would be post-selection on the same day that made it look attractive.

ClockCross already performs a more defensible form of daily adaptation: beta-40 is recomputed from prior completed sessions, while the residual gate and authority boundaries remain stable.

## Company-specific-news veto

The live adjudicator currently converts any schema-valid `idiosyncratic_news_detected = true` decision into an unconditional `ABSTAIN`.

Sep 3 is the first prospective case in this competition where that hard veto clearly forfeited a large favorable underlying move:

- residual: approximately +1.148%;
- opening confirmation: approximately +3.050%, same sign as the residual;
- live AI: `company_specific -> abstain`;
- COIN 09:55-10:55: approximately +3.142%.

The company-specific context was genuine: Coinbase announced a new board member and a regulated Canadian derivatives launch on Sep 2.

A historical raw-news replay surfaced a contrasting May 5 case where company-specific context coincided with an opening move opposite the residual and continuation subsequently lost. That makes a sign-conditional news policy an interesting hypothesis, but not an accepted production change.

Critically, retrospective Alpaca REST News payloads did not reproduce the live Sep 3 MCP decision even after respecting the Basic account's delayed-news information boundary. The historical raw-news replay also did not reproduce the already accepted production-context aggregate. Therefore it is not a faithful enough counterfactual to score a hard-veto override for Sep 4.

## Decision

No production strategy change is justified tonight.

Keep:

- beta-40 daily recalibration;
- 1.00% raw residual gate;
- 09:55 ET decision;
- 60-minute / 10:55 ET exit;
- current continuation / reversion / abstain AI authority;
- current company-specific-news hard veto;
- current option-constructor and risk invariants.

Do **not** promote previous-signal refitting, 3-signal EWMA, or ridge-10 before Sep 4.

The company-news veto is the only genuinely interesting next research target, but changing it requires a faithful historical production-context sample of prior vetoes. Sep 3 alone is not sufficient evidence.

## Interpretation

This pass distinguishes adaptive estimation from reactive fitting. Re-estimating a stable relation from a rolling historical sample (the existing beta-40) is materially different from choosing tomorrow's directional policy because yesterday happened to win or lose. The latter failed the recent walk-forward check here.
