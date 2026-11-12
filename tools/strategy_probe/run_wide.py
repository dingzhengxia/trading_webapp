"""8 币种 × (1h 4000 / 4h 1500) 回放当前配置，产出 res_wide.csv。"""
import json
import multiprocessing as mp
import time

import bt

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
           "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")
PLAN = {"1h": (4000, (1, 4, 12)), "4h": (1500, (1, 3, 6))}


def task(args):
    sym, tf, bars, horizons = args
    bt.RECORDS.clear()
    out, df = bt.replay(sym, tf, bars, bt.variant_config("base"), horizons=horizons)
    out["variant"] = "v3"
    return out, bt.baseline(df, horizons), f"v3|{tf}|{sym}"


if __name__ == "__main__":
    tasks = [(s, tf, bars, hz) for tf, (bars, hz) in PLAN.items() for s in SYMBOLS]
    t0 = time.time()
    with mp.Pool(4) as pool:
        results = pool.map(task, tasks)
    import pandas as pd
    frames, bases = [], {}
    for out, base, key in results:
        frames.append(out)
        bases[key] = base
    pd.concat(frames, ignore_index=True).to_csv("res_wide.csv", index=False)
    json.dump(bases, open("res_wide_baselines.json", "w"))
    print("done", f"{time.time() - t0:.0f}s")
