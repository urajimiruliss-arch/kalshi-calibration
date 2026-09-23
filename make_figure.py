# -*- coding: utf-8 -*-
"""График калибровки по посчитанным результатам: цена против фактической доли исходов YES."""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs", "calibration.png")

TITLES = {"h24": "24 hours before close", "h1": "1 hour before close"}
NOTES = {"h24": "no bucket above 0.7 clears the 30-market floor:\nbaseball a day out is near a coin flip and\nweather strikes split the probability",
         "h1": "full price range: games in progress\npush contracts to the edges"}


def load(split):
    p = os.path.join(BASE, "outputs", split, "results.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    expl, hold = load("exploration"), load("holdout")
    if not expl:
        sys.exit("нет outputs/exploration/results.json — сначала посчитайте разведку")

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 6.8), dpi=130, sharey=True)
    for ax, horizon in zip(axes, ("h24", "h1")):
        ax.plot([0, 1], [0, 1], color="#999", lw=1.2, ls="--", label="perfect calibration")
        for data, name, color, marker in ((expl, "exploration", "#9db8d2", "o"),
                                          (hold, "holdout", "#1f4e79", "s")):
            if not data or horizon not in data:
                continue
            b = data[horizon]["buckets"]
            for x in b:
                lo, hi = x["ci99"]
                ax.plot([x["mean_price"]] * 2,
                        [x["mean_price"] + lo, x["mean_price"] + hi],
                        color=color, lw=1.4, alpha=0.7, zorder=2)
            ax.scatter([x["mean_price"] for x in b], [x["settle_rate"] for x in b],
                       s=[max(30, min(360, x["n"] / 3)) for x in b], color=color, marker=marker,
                       alpha=0.9, edgecolor="white", zorder=3,
                       label=f"{name} (n = {data[horizon]['n']:,})")
        ax.set_title(TITLES[horizon], fontsize=12)
        ax.set_xlabel("price (implied probability)")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_box_aspect(1)
        ax.grid(alpha=0.25)
        ax.legend(frameon=False, loc="upper left", fontsize=9)
        ax.text(0.97, 0.06, NOTES[horizon], transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8.5, color="#5b6470")

    axes[0].set_ylabel("share of contracts that settled YES")
    fig.suptitle("Kalshi event contracts: price against outcome  —  bars are 99% intervals, "
                 "marker size ∝ markets in the bucket", fontsize=11)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.88, bottom=0.12, wspace=0.08)
    fig.savefig(OUT)
    print("написано:", OUT)


if __name__ == "__main__":
    main()
