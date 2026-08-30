# ClockCross SIP Endpoint Clarification

**Date:** 2026-08-29  
**Applies to:** market-data timing amendment and live implementation  
**Status:** implementation clarification; information set unchanged

Alpaca's current stock **latest/snapshot/stream** surfaces accept `delayed_sip`, which is SIP delayed by 15 minutes. Alpaca's `/v2/stocks/bars` historical-bars endpoint accepts `sip`, `iex`, `boats`, and `otc`, but not `delayed_sip`.

ClockCross therefore preserves the same consolidated information boundary using endpoint-appropriate parameters:

- research history: `feed=sip`;
- live latest/snapshot surfaces when used: `feed=delayed_sip`;
- live historical-bar reconstruction at the 09:55 ET decision: `feed=sip` with the request end capped at **09:40 ET**, so no observation newer than 15 minutes enters the decision.

This is not a model/feed change. Both research and live reconstruction remain consolidated SIP; the live historical request is explicitly time-capped to reproduce the delayed information set.

References:

- https://docs.alpaca.markets/us/reference/stockbars
- https://docs.alpaca.markets/us/reference/stocklatestbarsingle-1
- https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
