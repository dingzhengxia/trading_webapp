"""4h 延迟入场效应的稳定性检查：分段、分币、分月、按出场时点。"""
import math
import numpy as np
import pandas as pd
from logic_test import series, fixed_hold

sig = pd.read_csv("res_wide.csv")
sig = sig[sig.direction.isin(["long", "short"])].copy()
sig["dt"] = pd.to_datetime(sig.ts, unit="ms", utc=True)
sig["date"] = sig.dt.dt.date
sig["month"] = sig.dt.dt.strftime("%Y-%m")
sig["exit_hour"] = (sig.dt.dt.hour + 4 * 3) % 24   # offset=2 + h=3 -> +5 根 4h = +20h

def ex_for(rows, off, hold):
    out = []
    for r in rows:
        s = series(r.symbol, r.tf)
        i = s.index.get(int(r.ts))
        if i is None or i + off + hold >= len(s.close):
            continue
        sign = 1 if r.direction == "long" else -1
        entry = s.open[i + off]
        ret = sign * (s.close[i + off + hold] / entry - 1)
        out.append((r.symbol, r.date, r.month, ret - s.drift(sign, off, hold)))
    return pd.DataFrame(out, columns=["symbol", "date", "month", "ex"])

d4 = list(sig[sig.tf == "4h"].itertuples())
print("=== 4h offset=2 h=3 分段稳定性（超额 bp）===")
df = ex_for(d4, 2, 3)
dates = sorted(df.date.unique())
mid = dates[len(dates) // 2]
for label, part in (("前半段", df[df.date < mid]), ("后半段", df[df.date >= mid])):
    print(f"{label}: {len(part)} 笔 / {part.ex.mean()*1e4:+.1f}bp")

print("\n按月：")
for m, g in df.groupby("month"):
    print(f"  {m}: {len(g):>4d} 笔 / {g.ex.mean()*1e4:+7.1f}bp")

print("\n分币：")
for s, g in df.groupby("symbol"):
    print(f"  {s:<9} {len(g):>4d} 笔 / {g.ex.mean()*1e4:+7.1f}bp")

print("\n=== 对照：4h offset=1 h=3 同口径 ===")
df1 = ex_for(d4, 1, 3)
for label, part in (("前半段", df1[df1.date < mid]), ("后半段", df1[df1.date >= mid])):
    print(f"{label}: {len(part)} 笔 / {part.ex.mean()*1e4:+.1f}bp")

print("\n=== 1h 同样分段（offset=1 h=4，检验前面的矛盾）===")
d1 = list(sig[sig.tf == "1h"].itertuples())
dfh = ex_for(d1, 1, 4)
dh = sorted(dfh.date.unique()); midh = dh[len(dh) // 2]
for label, part in (("前半段", dfh[dfh.date < midh]), ("后半段", dfh[dfh.date >= midh])):
    print(f"{label}: {len(part)} 笔 / {part.ex.mean()*1e4:+.1f}bp")
print("日等权:", f"{dfh.groupby(['symbol','date']).ex.mean().mean()*1e4:+.1f}bp",
      "| 笔等权:", f"{dfh.ex.mean()*1e4:+.1f}bp")
