# Pre-registration: are prediction-market prices calibrated?

**Frozen on 2026-09-23, before any result was computed.** The question: when a Kalshi contract trades at
70 cents a day before it closes, does it settle YES about 70% of the time — and if it does not, is the
deviation large enough to trade after fees and the spread.

Kalshi is a CFTC-regulated exchange for event contracts. A contract pays $1 if the event happens and $0 if
it does not, so its price is a direct probability statement. That makes calibration testable without any
model of the underlying events.

## Data

Public REST API, no account and no key:

- `GET /trade-api/v2/markets?series_ticker=…&status=settled` — settled markets with the resolved `result`.
- `GET /trade-api/v2/series/{series}/markets/{ticker}/candlesticks` — hourly candles with traded price,
  best bid, best ask, volume and open interest.

**Series fixed in advance** (two sports groups, one weather group, all with enough settled markets):

| Series | What it is |
|---|---|
| KXMLBGAME | winner of an MLB game |
| KXNFLGAME | winner of an NFL game |
| KXEPLGAME | winner of a Premier League match |
| KXUCLWGAME | winner of a Champions League match |
| KXNHLGAME | winner of an NHL game |
| KXHIGHNY, KXHIGHCHI, KXHIGHLAX | daily high temperature in New York, Chicago, Los Angeles |

Everything the API returns for these series as of the download date is used; nothing is filtered by outcome,
volume or price after the fact, except the eligibility rules below.

**Observation.** One settled market = one observation. Its price is taken from the hourly candle whose end
falls closest to **24 hours before the market's close time**, and only if that candle ends within ±90 minutes
of the target. The secondary horizon is **1 hour before close**, same rule.

**Eligibility.** `result` is exactly `yes` or `no`; a usable candle exists at the horizon; the candle has a
two-sided quote (`yes_bid` > 0 and `yes_ask` < 1) with `yes_ask − yes_bid ≤ 0.10`; traded volume of the
market is at least 100 contracts. Markets that fail any rule are dropped, and the number dropped is reported.

**Price.** The mid of the quote, `p = (yes_bid + yes_ask) / 2`, rounded to the cent. The last traded price is
reported as a robustness check but is not the primary input.

## Split

Exploration and confirmation are separated by event, not by market, because markets inside one event share an
outcome: `sha1("kalshi-calibration-2026-09-23" + event_ticker)`, last byte odd → **A (exploration)**,
even → **B (holdout)**.

The holdout is read **once**, after the exploration write-up is finished, by running
`python analysis.py holdout --one-look`, which refuses to run twice and writes a lock file with a timestamp.

## Hypotheses

Fixed before any number was produced. All tests are two-sided, **p < 0.01**, with a bootstrap over events
(10,000 resamples, seed 20260923), because markets inside an event are dependent.

- **H1 — calibration.** Across ten price buckets (0.00–0.10, …, 0.90–1.00), the settlement rate equals the
  average price in the bucket. Statistic: the volume-unweighted mean of (outcome − price). H1 is rejected if
  the 99% interval for that mean excludes zero.
- **H2 — longshot bias.** Contracts priced at or below 0.10 settle YES **less** often than their price implies.
  This is the prediction-market analogue of the favourite–longshot bias confirmed out of sample in my football
  study. Statistic: mean (outcome − price) inside the bucket; H2 is confirmed only if the interval lies
  entirely below zero.
- **H3 — tradability.** A rule that sells the YES side of every eligible contract priced ≤ 0.10 at the quoted
  bid and holds to settlement returns more than zero **after costs**.

## Cost model (stated in advance)

- Execution at the **quoted** side, never at the mid: selling YES fills at `yes_bid`, buying at `yes_ask`.
- Taker fee per contract `0.07 · p · (1 − p)`, rounded up to the next cent — Kalshi's published formula.
  It is a parameter of the analysis: if the exchange's current schedule differs, the fee rate is changed in
  one place and the conclusion is re-checked.
- No leverage, no financing: a YES contract sold at price p ties up `1 − p` of collateral until settlement,
  and returns are stated per dollar of collateral.

## Interpretation fixed in advance

- If H1 holds, the market is calibrated and there is nothing to trade; that is a result, not a failure.
- If H1 is rejected but H3 fails, prices are biased but the bias is inside the spread and the fee — the same
  conclusion the football study reached about bookmaker margin.
- Any effect found only in exploration and not in the holdout is reported as not confirmed. No parameter of
  the rule (horizon, bucket, spread limit, volume floor) is tuned after the holdout is opened.

## Known limitations

1. The public API returns roughly two months of settled markets, so this is a snapshot, not a long history.
2. Sports and weather dominate the sample; politics and macro markets are not covered.
3. Hourly candles hide what happened inside the hour, so the quote used is an approximation of what a trader
   would have seen.
4. Settlement is taken as correct; disputed resolutions are not modelled.
