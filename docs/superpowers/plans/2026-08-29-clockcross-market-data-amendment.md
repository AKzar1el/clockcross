# ClockCross Market-Data Amendment Implementation Notes

This note amends `docs/superpowers/plans/2026-08-29-clockcross-implementation.md` without changing task order.

- Task 1 time tests use `09:25` feature freeze, `09:30` open, `09:40` confirmation end, and `09:55` earliest decision.
- `Settings` uses `historical_stock_feed=sip` and `live_stock_feed=delayed_sip` by default.
- Task 3 historical targets start at the 09:55 decision reference: 10:25 for 30m and 10:55 for 60m.
- Task 3 beta is the centered covariance/variance slope with a zero-variance fail-closed result; the expected-move baseline is `beta * crypto_return`.
- Task 5 research output records both historical and live feed names alongside the decision clock.
- Any later real-time SIP entitlement is treated as a frozen-config change, not a transparent substitution.

The research/falsification checkpoint remains unchanged: Tasks 6+ do not proceed until the real historical run produces a defensible `GO` or an explicitly approved `MUTATE` result.
