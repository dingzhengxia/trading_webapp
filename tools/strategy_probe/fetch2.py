"""扩大样本：拉 8 个主流币的 1h/4h K 线到 ./data/（data-api.binance.vision 可达时运行）。"""
import json
import os
import time
import urllib.request

BASE = "https://data-api.binance.vision/api/v3/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
           "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
PLAN = {"1h": 4000, "4h": 1500}


def get(sym, itv, end=None, limit=1000):
    url = f"{BASE}?symbol={sym}&interval={itv}&limit={limit}"
    if end:
        url += f"&endTime={end}"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def main():
    os.makedirs("data", exist_ok=True)
    for itv, total in PLAN.items():
        for sym in SYMBOLS:
            out, end = [], None
            while len(out) < total:
                batch = get(sym, itv, end, min(1000, total - len(out)))
                if not batch:
                    break
                out = batch + out
                end = batch[0][0] - 1
                time.sleep(0.15)
            rows = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in out]
            json.dump(rows, open(f"data/{sym}_{itv}.json", "w"))
            print(sym, itv, len(rows),
                  time.strftime("%Y-%m-%d", time.gmtime(rows[0][0] / 1000)), "->",
                  time.strftime("%Y-%m-%d", time.gmtime(rows[-1][0] / 1000)), flush=True)


if __name__ == "__main__":
    main()
