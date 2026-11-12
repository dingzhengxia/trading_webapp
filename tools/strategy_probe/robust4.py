"""4h「T+1 入场」在更真实的出场（ATR 止损/止盈）下是否仍成立。"""
import numpy as np
import pandas as pd
from logic_test import series, atr_trade, stats

sig = pd.read_csv("res_wide.csv")
sig = sig[sig.direction.isin(["long", "short"]) & (sig.tf == "4h")].copy()
rows = list(sig.itertuples())

for off in (1, 2):
    print(f"-- offset={off}（{'立即入场' if off == 1 else '等一根后入场'}）")
    for sl, tp in ((1.5, 2.0), (1.5, 3.0), (2.0, 2.0)):
        ex, holds = [], []
        for r in rows:
            ret, hh = atr_trade(r, off, sl, tp, 6)
            if ret is None:
                continue
            s = series(r.symbol, r.tf)
            i = s.index[int(r.ts)]
            sign = 1 if r.direction == "long" else -1
            ex.append(ret - s.drift(sign, off, int(hh)))
            holds.append(hh)
        arr = np.array(ex)
        m = arr.mean() * 1e4
        print(f"   SL{sl}ATR/TP{tp}R: {len(arr):>5d} 笔 / 超额 {m:+6.1f}bp / 净 {m-8:+6.1f}bp / 均持 {np.mean(holds):.1f} 根 / 胜率 {(arr>0).mean()*100:.1f}%")

print("\n-- 固定持有 + 时间止损对照（offset=2, h=3 / h=4）")
for h in (3, 4):
    ex, _ = [], []
    for r in rows:
        s = series(r.symbol, r.tf); i = s.index.get(int(r.ts))
        if i is None or i + 2 + h >= len(s.close):
            continue
        sign = 1 if r.direction == "long" else -1
        ret = sign * (s.close[i + 2 + h] / s.open[i + 2] - 1)
        ex.append(ret - s.drift(sign, 2, h))
    arr = np.array(ex); m = arr.mean() * 1e4
    print(f"   h={h}: {len(arr)} 笔 / 超额 {m:+.1f}bp / 净 {m-8:+.1f}bp / 胜率 {(arr>0).mean()*100:.1f}%")
