"""对 logic_test 的显著结果做稳健性检查：信号聚集、时间分布、按策略拆解、聚类 t 值。"""
import json, math, sys
import numpy as np
import pandas as pd
from logic_test import series, fixed_hold

sig = pd.read_csv("res_wide.csv")
sig = sig[sig.direction.isin(["long", "short"])].copy()
sig["hour"] = pd.to_datetime(sig.ts, unit="ms", utc=True).dt.hour
sig["date"] = pd.to_datetime(sig.ts, unit="ms", utc=True).dt.date

print("=== 1. 信号分布（每币每周期）===")
for tf in ("1h", "4h"):
    d = sig[sig.tf == tf]
    per = d.groupby("symbol").size()
    print(f"{tf}: 总 {len(d)}，单币 {per.min()}~{per.max()}；按小时 Top5:",
          d.hour.value_counts().head(5).to_dict())
    # 同一 bar 上的重复信号（同币同周期同时间戳）
    dup = d.groupby(["symbol", "ts"]).size()
    print(f"   同 bar 信号数：均值 {dup.mean():.2f}，最大 {dup.max()}；去重后 {len(dup)} 条")

print("\n=== 2. 去重后再看（每币每 bar 只留第一条）===")
ded = sig.sort_values("ts").groupby(["symbol", "tf", "ts"], as_index=False).first()
for tf, hold in (("1h", 4), ("4h", 3)):
    sub = list(ded[ded.tf == tf].itertuples())
    for off in (1, 2):
        ex, _ = fixed_hold(sub, off, hold)
        arr = np.asarray(ex)
        if len(arr) < 10: continue
        print(f"{tf} 去重 offset={off}: {len(arr)} 笔 / 超额 {arr.mean()*1e4:+.1f}bp / t={arr.mean()/(arr.std(ddof=1)/math.sqrt(len(arr))):+.1f}")

print("\n=== 3. 4h 延迟效应按策略拆解（h=3）===")
d4 = list(sig[sig.tf == "4h"].itertuples())
for name in sorted({r.strategy for r in d4}):
    part = [r for r in d4 if r.strategy == name]
    cells = []
    for off in (1, 2, 3):
        ex, _ = fixed_hold(part, off, 3)
        arr = np.asarray(ex)
        cells.append("样本不足" if len(arr) < 10 else f"{off}:{arr.mean()*1e4:+.0f}bp(n={len(arr)})")
    print(f"  {name:<24} " + "  ".join(cells))

print("\n=== 4. 4h 按信号小时看（offset=1/2, h=3）===")
for off in (1, 2):
    rows = []
    for hour, g in sig[sig.tf == "4h"].groupby("hour"):
        ex, _ = fixed_hold(list(g.itertuples()), off, 3)
        if len(ex) >= 10:
            rows.append((hour, len(ex), np.mean(ex) * 1e4))
    print(f"offset={off}: " + "  ".join(f"{h:02d}h:{m:+.0f}bp(n={n})" for h, n, m in rows))

print("\n=== 5. 聚类稳健 t 值（按 币+日期 聚合，避免同 bar 重叠放大显著性）===")
def cluster_t(sub, off, hold, tf):
    recs = []
    for r in sub:
        s = series(r.symbol, r.tf)
        i = s.index.get(int(r.ts))
        if i is None or i + off + hold >= len(s.close):
            continue
        sign = 1 if r.direction == "long" else -1
        entry = s.open[i + off]
        ret = sign * (s.close[i + off + hold] / entry - 1)
        recs.append((r.symbol, r.date, ret - s.drift(sign, off, hold)))
    df = pd.DataFrame(recs, columns=["symbol", "date", "ex"])
    g = df.groupby(["symbol", "date"]).ex.mean()
    t = g.mean() / (g.std(ddof=1) / math.sqrt(len(g)))
    return len(g), g.mean() * 1e4, t

for tf, hold in (("1h", 4), ("4h", 3)):
    sub = list(sig[sig.tf == tf].itertuples())
    for off in (1, 2):
        n, m, t = cluster_t(sub, off, hold, tf)
        print(f"{tf} offset={off}: {n} 个(币×日) 组 / 组均超额 {m:+.1f}bp / t={t:+.1f}")
