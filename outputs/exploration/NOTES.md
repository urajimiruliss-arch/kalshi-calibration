# Exploration notes (half A) — written before the holdout was opened

Frozen design: [PREREGISTRATION.md](../../PREREGISTRATION.md). Numbers below come from
`python analysis.py exploration` and are the exploration half only. Nothing here changes a
hypothesis, a horizon, a bucket, a spread limit or a volume floor; the holdout is opened once
with the same code.

## Sample

5,381 observations built from the download; 2,778 fall in half A. At the 24-hour horizon:
1,701 markets across 665 events. Drops: no two-sided quote 223, spread above 10 cents 59,
no candle inside the ±90-minute window 2.

## What the overall H1 number actually measures

The pre-registered statistic is the unweighted mean of (outcome − price). In this sample it mixes
two very different kinds of market, so the single number is not "how miscalibrated Kalshi is":

| Group | n | mean price | settled YES | deviation | 99% CI |
|---|---|---|---|---|---|
| sports (MLB, NFL, EPL, UCL, NHL) | 1,160 | 0.479 | 0.480 | +0.09 pp | [−0.02, +0.27] |
| weather (daily high in NY, CHI, LAX) | 541 | 0.206 | 0.198 | −0.82 pp | [−1.41, −0.53] |

Sports markets come in pairs — one contract per team, two per event — and the two mids sum to
0.9986 on average, so their deviations cancel by construction and the group is calibrated.
Weather markets are sets of 3–6 mutually exclusive temperature strikes, most of them cheap; those
legs settle YES slightly less often than their price implies. The pooled −0.20 pp (99% CI
[−0.41, −0.03]) that rejects H1 is the weather group showing through the pooled average.

This breakdown is descriptive. It was added to `analysis.py` before the holdout was touched, and it
is printed for both halves, but it is not a pre-registered test and no conclusion rests on it alone.

## Price coverage at 24 hours

At the 24-hour horizon the sample barely reaches above 0.7 (0.7–0.8: 21, 0.8–0.9: 8, 0.9–1.0: 2),
so only seven buckets clear the 30-observation floor. This is not a filter artifact — I checked:

- MLB, the largest series, spans 0.2–0.7 only. A baseball game a day out is close to a coin flip.
- Of 401 MLB candles at the horizon, **zero** were dropped for `ask ≥ 1` and only 6 had a bid above 0.7.
- In weather, the highest-priced leg of an event is usually 0.4–0.6, because the day's high has to
  land in one of several buckets. Across the three cities only 10 candles at the horizon had a bid
  above 0.7, and every one of them passed the eligibility rules.

So the conclusion at 24 hours covers prices roughly from 0.02 to 0.70, and says nothing about heavy
favourites. The 1-hour horizon does cover the full range (0.9–1.0: n=187) because games in progress
push prices to the edges — but there the weather markets are nearly all gone (1,424 dropped for a
missing two-sided quote), so h1 is effectively a sports-only sample.

## Size of the deviation against the cost of trading it

The weather deviation is real in this half but small relative to what it costs to take it:

- half the quoted spread: ≈0.7 cent (mean spread 1.45 cents);
- taker fee at a price of 0.20: 0.07 · 0.2 · 0.8 = 1.12 cents, **rounded up to 2 cents**;
- total round-trip friction ≈2.7 cents against a deviation of 0.82 cents.

The rounding-up in Kalshi's fee formula alone is larger than the mispricing. This is why H3 is
tested at the quoted bid and not at the mid.

## Exploration verdicts (half A)

| | 24 hours | 1 hour |
|---|---|---|
| Brier | 0.1993 vs 0.2380 for a constant forecast | 0.1399 vs 0.2497 |
| H1 calibration | rejected, −0.20 pp [−0.41, −0.03] | not rejected, +0.03 pp [−0.05, +0.13] |
| H2 longshot bias ≤0.10 | not confirmed, −0.49 pp [−3.17, +2.86] | not confirmed, −0.06 pp [−3.71, +4.47] |
| H3 tradability after fees | not confirmed, −1.15% of collateral [−4.59, +1.66] | not confirmed, −1.73% [−6.57, +2.19] |

What I expect the holdout to show, stated before opening it: the sports group calibrated, the
weather group slightly negative, H2 and H3 not confirmed. If the holdout disagrees, the holdout wins.
