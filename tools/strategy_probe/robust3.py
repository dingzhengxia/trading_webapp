"""决定性对照：把「无条件漂移」改成「同时段（同一天内小时）漂移」，
排除『信号集中在某个 4h 时点 + 该时点系统性上涨』造成的假超额。"""
import json
import math
import numpy as np
import pandas as pd

COST_BP = 8.0


class S:
    def __init__(self, symbol, tf):
        df = pd.DataFrame(json.load(open(f"data/{symbol}_{tf}.json")),
                          columns=["timestamp", "open", "high", "low", "close", "volume"])
        self.open = df.open.to_numpy(); self.close = df.close.to_numpy()
        self.hour = (df.timestamp // 3600_000 % 24).to_numpy()
        self.index = {int(t): i for i, t in enumerate(df.timestamp)}
        self._d = {}

    def drift(self, sign, offset, hold, hour=None):
        key = (sign, offset, hold, hour)
        if key not in self._d:
            n = len(self.close)
            starts = np.arange(0, n - offset - hold)
            if hour is not None:
                starts = starts[self.hour[starts] == hour]
            if len(starts) < 20:
                self._d[key] = None
            else:
                e = starts + offset
                self._d[key] = float(np.mean(sign * (self.close[e + hold] / self.open[e] - 1)))
        return self._d[key]


CACHE = {}
def series(sym, tf):
    if (sym, tf) not in CACHE:
        CACHE[(sym, tf)] = S(sym, tf)
    return CACHE[(sym, tf)]


sig = pd.read_csv("res_wide.csv")
sig = sig[sig.direction.isin(["long", "short"])].copy()

def run(tf, offset, hold, condition_hour):
    out = []
    for r in sig[sig.tf == tf].itertuples():
        s = series(r.symbol, r.tf)
        i = s.index.get(int(r.ts))
        if i is None or i + offset + hold >= len(s.close):
            continue
        sign = 1 if r.direction == "long" else -1
        base = s.drift(sign, offset, hold, int(s.hour[i])) if condition_hour else s.drift(sign, offset, hold, None)
        if base is None:
            continue
        ret = sign * (s.close[i + offset + hold] / s.open[i + offset] - 1)
        out.append((r.symbol, ret - base))
    df = pd.DataFrame(out, columns=["symbol", "ex"])
    n = len(df)
    m = df.ex.mean() * 1e4
    t = m / (df.ex.std(ddof=1) * 1e4 / math.sqrt(n))
    g = df.groupby("symbol").ex.mean()
    pos = (g > 0).sum()
    return f"{n:>6d} 笔 / {m:+7.1f}bp / 净 {m - COST_BP:+7.1f}bp / t={t:+5.1f} / 正收益币 {pos}/{len(g)}"

print("                未控时段漂移                          控时段漂移（同小时）")
print(f"4h off1 h3 : {run('4h', 1, 3, False)}   |   {run('4h', 1, 3, True)}")
print(f"4h off2 h3 : {run('4h', 2, 3, False)}   |   {run('4h', 2, 3, True)}")
print(f"4h off1 h4 : {run('4h', 1, 4, False)}   |   {run('4h', 1, 4, True)}")
print(f"1h off1 h4 : {run('1h', 1, 4, False)}   |   {run('1h', 1, 4, True)}")
print(f"1h off1 h2 : {run('1h', 1, 2, False)}   |   {run('1h', 1, 2, True)}")
