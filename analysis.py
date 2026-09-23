# -*- coding: utf-8 -*-
"""Калибровка цен Kalshi строго по PREREGISTRATION.md.

    python analysis.py exploration          # половина A
    python analysis.py holdout --one-look   # половина B, ОДИН раз (пишет outputs/holdout/LOCK)

Только стандартная библиотека.
"""
import collections
import datetime
import hashlib
import json
import math
import os
import random
import statistics
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "raw")
OUT = os.path.join(BASE, "outputs")

SALT = "kalshi-calibration-2026-09-23"
SERIES = ["KXMLBGAME", "KXNFLGAME", "KXEPLGAME", "KXUCLWGAME", "KXNHLGAME",
          "KXHIGHNY", "KXHIGHCHI", "KXHIGHLAX"]
HORIZONS = {"h24": 24 * 3600, "h1": 1 * 3600}
TOLERANCE = 90 * 60           # свеча должна лежать в ±90 минутах от горизонта
MAX_SPREAD = 0.10
MIN_VOLUME = 100.0
LONGSHOT_MAX = 0.10
FEE_RATE = 0.07               # комиссия тейкера: 0.07·p·(1−p) за контракт, округление вверх до цента
N_BOOT = 10_000
SEED = 20260923
ALPHA = 0.01
BUCKETS = [(i / 10, (i + 1) / 10) for i in range(10)]


def group(event_ticker):
    """A — разведка, B — холдаут. Делим по событию: рынки внутри события зависимы."""
    return "A" if hashlib.sha1((SALT + str(event_ticker)).encode()).digest()[-1] % 2 else "B"


def to_ts(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def load():
    """Возвращает наблюдения: по одному на рынок и горизонт."""
    obs = []
    dropped = collections.Counter()
    for series in SERIES:
        mpath = os.path.join(RAW, f"markets_{series}.json")
        cpath = os.path.join(RAW, f"candles_{series}.jsonl")
        if not (os.path.exists(mpath) and os.path.exists(cpath)):
            continue
        with open(mpath, encoding="utf-8") as fh:
            markets = {m["ticker"]: m for m in json.load(fh)}
        with open(cpath, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                m = markets.get(rec["ticker"])
                if not m:
                    continue
                result = m.get("result")
                if result not in ("yes", "no"):
                    dropped["result"] += 1
                    continue
                volume = f(m.get("volume_fp"), 0.0) or 0.0
                if volume < MIN_VOLUME:
                    dropped["volume"] += 1
                    continue
                close_ts = to_ts(m["close_time"])
                for name, back in HORIZONS.items():
                    target = close_ts - back
                    best, best_gap = None, None
                    for c in rec["candles"]:
                        gap = abs(c["end_period_ts"] - target)
                        if best_gap is None or gap < best_gap:
                            best, best_gap = c, gap
                    if best is None or best_gap > TOLERANCE:
                        dropped[f"no_candle_{name}"] += 1
                        continue
                    bid = f((best.get("yes_bid") or {}).get("close_dollars"))
                    ask = f((best.get("yes_ask") or {}).get("close_dollars"))
                    last = f((best.get("price") or {}).get("close_dollars"))
                    if bid is None or ask is None or bid <= 0 or ask >= 1 or ask <= bid:
                        dropped[f"quote_{name}"] += 1
                        continue
                    if ask - bid > MAX_SPREAD:
                        dropped[f"spread_{name}"] += 1
                        continue
                    obs.append({
                        "series": series, "ticker": rec["ticker"], "event": m.get("event_ticker") or rec["ticker"],
                        "horizon": name, "half": group(m.get("event_ticker") or rec["ticker"]),
                        "price": round((bid + ask) / 2, 2), "bid": bid, "ask": ask, "last": last,
                        "spread": round(ask - bid, 4), "outcome": 1 if result == "yes" else 0,
                        "volume": volume, "close_time": m["close_time"],
                    })
    return obs, dropped


def boot_mean(values_by_event, seed=SEED, n_boot=N_BOOT):
    """99% ДИ среднего, бутстрап по событиям."""
    events = list(values_by_event.values())
    if len(events) < 20:
        return float("nan"), float("nan")
    rnd = random.Random(seed)
    n = len(events)
    means = []
    for _ in range(n_boot):
        s = c = 0
        for _ in range(n):
            vals = events[rnd.randrange(n)]
            s += sum(vals)
            c += len(vals)
        means.append(s / c if c else 0.0)
    means.sort()
    return means[int(0.005 * n_boot)], means[min(int(0.995 * n_boot), n_boot - 1)]


def by_event(rows, value):
    d = collections.defaultdict(list)
    for r in rows:
        d[r["event"]].append(value(r))
    return d


def fee(p):
    """Комиссия тейкера за контракт: 0.07·p·(1−p), округление вверх до цента."""
    return math.ceil(FEE_RATE * p * (1 - p) * 100) / 100


def analyse(rows, horizon):
    rows = [r for r in rows if r["horizon"] == horizon]
    res = {"horizon": horizon, "n": len(rows), "n_events": len({r["event"] for r in rows})}
    if not rows:
        return res

    # H1: калибровка по корзинам и в целом
    dev = by_event(rows, lambda r: r["outcome"] - r["price"])
    lo, hi = boot_mean(dev)
    res["mean_deviation"] = statistics.fmean(r["outcome"] - r["price"] for r in rows)
    res["deviation_ci99"] = [lo, hi]
    res["brier"] = statistics.fmean((r["price"] - r["outcome"]) ** 2 for r in rows)
    res["base_rate"] = statistics.fmean(r["outcome"] for r in rows)
    res["brier_of_base_rate"] = statistics.fmean((res["base_rate"] - r["outcome"]) ** 2 for r in rows)

    buckets = []
    for lo_b, hi_b in BUCKETS:
        sub = [r for r in rows if lo_b <= r["price"] < hi_b or (hi_b == 1.0 and r["price"] == 1.0)]
        if len(sub) < 30:
            continue
        d_lo, d_hi = boot_mean(by_event(sub, lambda r: r["outcome"] - r["price"]))
        buckets.append({
            "bucket": f"{lo_b:.1f}-{hi_b:.1f}", "n": len(sub),
            "mean_price": statistics.fmean(r["price"] for r in sub),
            "settle_rate": statistics.fmean(r["outcome"] for r in sub),
            "deviation": statistics.fmean(r["outcome"] - r["price"] for r in sub),
            "ci99": [d_lo, d_hi],
        })
    res["buckets"] = buckets

    # Описательная разбивка (НЕ преднарегистрированный тест; добавлена до открытия холдаута).
    # Нужна потому, что общее среднее смешивает два разных вида рынков: двусторонние
    # спортивные (цены обеих сторон в сумме дают единицу) и погодные наборы взаимно
    # исключающих страйков, где почти все ноги дешёвые.
    groups = {}
    for name, keep in (("sports", lambda r: not r["series"].startswith("KXHIGH")),
                       ("weather", lambda r: r["series"].startswith("KXHIGH"))):
        sub = [r for r in rows if keep(r)]
        if len(sub) < 30:
            continue
        g_lo, g_hi = boot_mean(by_event(sub, lambda r: r["outcome"] - r["price"]))
        groups[name] = {
            "n": len(sub), "mean_price": statistics.fmean(r["price"] for r in sub),
            "settle_rate": statistics.fmean(r["outcome"] for r in sub),
            "deviation": statistics.fmean(r["outcome"] - r["price"] for r in sub),
            "ci99": [g_lo, g_hi],
            "mean_spread": statistics.fmean(r["spread"] for r in sub),
            "mean_fee_at_mean_price": fee(statistics.fmean(r["price"] for r in sub)),
        }
    res["groups_descriptive"] = groups

    # H2: лонгшоты ≤ 0.10
    longs = [r for r in rows if r["price"] <= LONGSHOT_MAX]
    if longs:
        l_lo, l_hi = boot_mean(by_event(longs, lambda r: r["outcome"] - r["price"]))
        res["longshot"] = {
            "n": len(longs), "mean_price": statistics.fmean(r["price"] for r in longs),
            "settle_rate": statistics.fmean(r["outcome"] for r in longs),
            "deviation": statistics.fmean(r["outcome"] - r["price"] for r in longs),
            "ci99": [l_lo, l_hi],
        }

        # H3: продать YES по биду, держать до расчёта, доход на доллар залога
        def pnl(r):
            proceeds = r["bid"] - fee(r["bid"])          # получили при продаже, минус комиссия
            payout = 1.0 if r["outcome"] else 0.0        # столько отдаём при расчёте
            collateral = 1.0 - r["bid"]
            return (proceeds - payout) / collateral if collateral > 0 else 0.0

        t_lo, t_hi = boot_mean(by_event(longs, pnl))
        res["trade_sell_longshots"] = {
            "n": len(longs), "mean_return_per_dollar_collateral": statistics.fmean(pnl(r) for r in longs),
            "ci99": [t_lo, t_hi],
            "mean_fee_per_contract": statistics.fmean(fee(r["bid"]) for r in longs),
            "mean_spread": statistics.fmean(r["spread"] for r in longs),
        }
    return res


def verdict(res):
    out = []
    d = res.get("deviation_ci99") or [float("nan")] * 2
    if not math.isnan(d[0]):
        out.append(("H1 calibration", "rejected" if (d[0] > 0 or d[1] < 0) else "not rejected",
                    f"mean deviation {res['mean_deviation'] * 100:+.2f} pp, 99% CI [{d[0] * 100:+.2f}, {d[1] * 100:+.2f}]"))
    ls = res.get("longshot")
    if ls:
        c = ls["ci99"]
        out.append(("H2 longshot bias", "confirmed" if c[1] < 0 else "not confirmed",
                    f"price {ls['mean_price']:.3f} vs settle rate {ls['settle_rate']:.3f}, "
                    f"deviation {ls['deviation'] * 100:+.2f} pp, 99% CI [{c[0] * 100:+.2f}, {c[1] * 100:+.2f}]"))
    tr = res.get("trade_sell_longshots")
    if tr:
        c = tr["ci99"]
        out.append(("H3 tradability", "confirmed" if c[0] > 0 else "not confirmed",
                    f"return {tr['mean_return_per_dollar_collateral'] * 100:+.2f}% of collateral, "
                    f"99% CI [{c[0] * 100:+.2f}, {c[1] * 100:+.2f}]"))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    split = sys.argv[1] if len(sys.argv) > 1 else ""
    if split not in ("exploration", "holdout"):
        sys.exit("usage: python analysis.py exploration | holdout --one-look")
    outdir = os.path.join(OUT, split)
    os.makedirs(outdir, exist_ok=True)
    if split == "holdout":
        lock = os.path.join(outdir, "LOCK")
        if "--one-look" not in sys.argv:
            sys.exit("The holdout is looked at once. Run with --one-look when the exploration write-up is done.")
        if os.path.exists(lock):
            sys.exit(f"Holdout already opened ({open(lock, encoding='utf-8').read().strip()}). Re-running is not allowed.")
        with open(lock, "w", encoding="utf-8") as fh:
            fh.write(datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))

    obs, dropped = load()
    half = "A" if split == "exploration" else "B"
    rows = [r for r in obs if r["half"] == half]
    print(f"наблюдений всего {len(obs)}, в половине {half}: {len(rows)}")
    print("отброшено:", dict(dropped))

    results = {"split": split, "half": half, "n_observations": len(rows), "dropped": dict(dropped),
               "by_series": dict(collections.Counter(r["series"] for r in rows if r["horizon"] == "h24"))}
    for horizon in HORIZONS:
        res = analyse(rows, horizon)
        results[horizon] = res
        print(f"\n== горизонт {horizon}: {res['n']} наблюдений, событий {res['n_events']}")
        if res["n"]:
            print(f"   Brier {res['brier']:.4f} против {res['brier_of_base_rate']:.4f} у постоянного прогноза")
            for b in res["buckets"]:
                print(f"   {b['bucket']}  n={b['n']:>5}  цена {b['mean_price']:.3f}  доля YES {b['settle_rate']:.3f}"
                      f"  отклонение {b['deviation'] * 100:+.2f} pp  ДИ [{b['ci99'][0] * 100:+.2f}, {b['ci99'][1] * 100:+.2f}]")
            for gname, g in (res.get("groups_descriptive") or {}).items():
                print(f"   [описательно] {gname}: n={g['n']}, цена {g['mean_price']:.3f}, доля YES {g['settle_rate']:.3f},"
                      f" отклонение {g['deviation'] * 100:+.2f} pp, ДИ [{g['ci99'][0] * 100:+.2f}, {g['ci99'][1] * 100:+.2f}],"
                      f" спред {g['mean_spread'] * 100:.2f} c, комиссия {g['mean_fee_at_mean_price'] * 100:.0f} c")
            for name, status, detail in verdict(res):
                print(f"   {name}: {status.upper()} — {detail}")

    with open(os.path.join(outdir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nрезультаты: {os.path.join(outdir, 'results.json')}")


if __name__ == "__main__":
    main()
