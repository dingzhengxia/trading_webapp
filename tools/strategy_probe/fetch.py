"""拉取 Binance 现货 K 线到 ./data/（需在 data-api.binance.vision 可达的网络下运行）。"""
import json, time, urllib.request, os
BASE = "https://data-api.binance.vision/api/v3/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
PLAN = {"1h": 3000, "4h": 1200}

def get(sym, itv, end=None, limit=1000):
    url = f"{BASE}?symbol={sym}&interval={itv}&limit={limit}"
    if end:
        url += f"&endTime={end}"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)

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
        path = f"data/{sym}_{itv}.json"
        json.dump(rows, open(path, "w"))
        print(sym, itv, len(rows), time.strftime('%Y-%m-%d %H:%M', time.gmtime(rows[0][0]/1000)), "->",
              time.strftime('%Y-%m-%d %H:%M', time.gmtime(rows[-1][0]/1000)))
