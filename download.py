# -*- coding: utf-8 -*-
"""Скачивает с публичного API Kalshi расчётные рынки и почасовые свечи за сутки до закрытия.

Ключ и аккаунт не нужны. Сырые файлы не публикуются: их восстанавливает этот скрипт,
а data/manifest.json хранит sha256 каждого файла.

    python download.py
"""
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "raw")
API = "https://api.elections.kalshi.com/trade-api/v2"

SERIES = ["KXMLBGAME", "KXNFLGAME", "KXEPLGAME", "KXUCLWGAME", "KXNHLGAME",
          "KXHIGHNY", "KXHIGHCHI", "KXHIGHLAX"]

HORIZON_HOURS = 24           # основной горизонт
WINDOW_HOURS = 30            # сколько часов свечей тянем (24 ч + запас на секундный горизонт)
PAUSE = 0.15                 # пауза между запросами, чтобы не долбить API


def fetch(url, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "calibration-research/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return None


def settled_markets(series):
    """Все расчётные рынки серии (API отдаёт страницами по курсору)."""
    out, cursor = [], None
    while True:
        url = f"{API}/markets?series_ticker={series}&status=settled&limit=1000"
        if cursor:
            url += "&cursor=" + cursor
        data = fetch(url)
        markets = data.get("markets") or []
        out.extend(markets)
        cursor = data.get("cursor")
        if not cursor or not markets:
            break
        time.sleep(PAUSE)
    return out


def candles(series, ticker, close_ts):
    """Почасовые свечи в окне [close − WINDOW_HOURS, close]."""
    start = int(close_ts - WINDOW_HOURS * 3600)
    end = int(close_ts)
    url = (f"{API}/series/{series}/markets/{ticker}/candlesticks"
           f"?start_ts={start}&end_ts={end}&period_interval=60")
    try:
        return fetch(url).get("candlesticks") or []
    except Exception:
        return []


def to_ts(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(RAW, exist_ok=True)
    manifest = {"downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "api": API, "series": SERIES, "horizon_hours": HORIZON_HOURS, "files": {}}

    for series in SERIES:
        print(f"\n== {series}", flush=True)
        markets = settled_markets(series)
        print(f"   расчётных рынков: {len(markets)}", flush=True)
        path = os.path.join(RAW, f"markets_{series}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(markets, f)

        out_path = os.path.join(RAW, f"candles_{series}.jsonl")
        done = 0
        with open(out_path, "w", encoding="utf-8") as f:
            for i, m in enumerate(markets, 1):
                if m.get("result") not in ("yes", "no") or not m.get("close_time"):
                    continue
                cs = candles(series, m["ticker"], to_ts(m["close_time"]))
                if cs:
                    f.write(json.dumps({"ticker": m["ticker"], "candles": cs}) + "\n")
                    done += 1
                if i % 100 == 0:
                    print(f"   {i}/{len(markets)} рынков, свечи есть у {done}", flush=True)
                time.sleep(PAUSE)
        print(f"   свечи скачаны для {done} рынков", flush=True)

        for p in (path, out_path):
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            manifest["files"][os.path.basename(p)] = {"sha256": h.hexdigest(), "bytes": os.path.getsize(p)}

    with open(os.path.join(BASE, "data", "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print("\nманифест записан: data/manifest.json")


if __name__ == "__main__":
    main()
