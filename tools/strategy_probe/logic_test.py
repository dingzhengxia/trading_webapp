"""信号「逻辑层」实验：入场延迟 / 固定持有 / 反向跟随 / ATR 止损止盈。

输入：run_wide.py 产出的 res_wide.csv（symbol/tf/ts/strategy/direction）
      data/*.json（同一批 K 线）
输出：控制台表格，结论写进 docs。

超额 = 单笔收益 - 同期同方向「无条件漂移」（对该币该周期全部 bar 取相同入场偏移与持有期求均值），
这样既不奖励「牛市里做多」，也不因样本期方向偏置而虚高。
"""
import json
import math
import sys

import numpy as np
import pandas as pd

COST_BP = 8.0  # 往返成本


class Series:
    def __init__(self, symbol, tf):
        df = pd.DataFrame(json.load(open(f"data/{symbol}_{tf}.json")),
                          columns=["timestamp", "open", "high", "low", "close", "volume"])
        prev_close = df["close"].shift(1)
        tr = pd.concat([df["high"] - df["low"],
                        (df["high"] - prev_close).abs(),
                        (df["low"] - prev_close).abs()], axis=1).max(axis=1)
        self.ts = df["timestamp"].to_numpy()
        self.open = df["open"].to_numpy()
        self.high = df["high"].to_numpy()
        self.low = df["low"].to_numpy()
        self.close = df["close"].to_numpy()
        self.atr = tr.rolling(14).mean().to_numpy()
        self.index = {int(t): i for i, t in enumerate(df["timestamp"])}
        self._drift = {}

    def drift(self, sign, offset, hold):
        """无条件漂移：从任意 bar 起 offset 后入场、持有 hold 根的均值收益（同方向）。"""
        key = (sign, offset, hold)
        if key not in self._drift:
            n = len(self.close)
            starts = np.arange(0, n - offset - hold)
            if len(starts) < 30:
                self._drift[key] = 0.0
            else:
                e = starts + offset
                ret = sign * (self.close[e + hold] / self.open[e] - 1)
                self._drift[key] = float(np.mean(ret))
        return self._drift[key]


SERIES = {}


def series(symbol, tf):
    key = (symbol, tf)
    if key not in SERIES:
        SERIES[key] = Series(symbol, tf)
    return SERIES[key]


def fixed_hold(rows, offset, hold):
    """固定持有：返回 (超额列表, 绝对收益列表)。"""
    ex, raw = [], []
    for r in rows:
        s = series(r.symbol, r.tf)
        i = s.index.get(int(r.ts))
        if i is None or i + offset + hold >= len(s.close):
            continue
        sign = 1 if r.direction == "long" else -1
        entry = s.open[i + offset]
        if entry <= 0:
            continue
        ret = sign * (s.close[i + offset + hold] / entry - 1)
        raw.append(ret)
        ex.append(ret - s.drift(sign, offset, hold))
    return ex, raw


def atr_trade(r, offset, sl_atr, tp_r, max_hold):
    """ATR 止损 + R 倍数止盈；同根同时触发按止损优先（保守）。"""
    s = series(r.symbol, r.tf)
    i = s.index.get(int(r.ts))
    if i is None or i + offset >= len(s.close) or math.isnan(s.atr[i]):
        return None, None
    entry = s.open[i + offset]
    atr = s.atr[i]
    if entry <= 0 or atr <= 0:
        return None, None
    sign = 1 if r.direction == "long" else -1
    stop = entry - sign * sl_atr * atr
    target = entry + sign * tp_r * sl_atr * atr

    for j in range(i + offset, min(i + offset + max_hold, len(s.close))):
        hi, lo, op = s.high[j], s.low[j], s.open[j]
        if sign > 0:
            if lo <= stop:
                return (min(stop, op) / entry - 1), j - i - offset + 1
            if hi >= target:
                return (max(target, op) / entry - 1), j - i - offset + 1
        else:
            if hi >= stop:
                return -((max(stop, op) / entry - 1)), j - i - offset + 1
            if lo <= target:
                return -((min(target, op) / entry - 1)), j - i - offset + 1
    j = min(i + offset + max_hold, len(s.close)) - 1
    return sign * (s.close[j] / entry - 1), j - i - offset + 1


def stats(ex, label=""):
    arr = np.asarray(ex, dtype=float)
    n = len(arr)
    if n < 10:
        return f"{label}{n} 笔 / 样本不足"
    m = arr.mean() * 1e4
    sd = arr.std(ddof=1)
    t = m / (sd * 1e4 / math.sqrt(n)) if sd else 0.0
    hit = (arr > 0).mean() * 100
    return f"{label}{n:>5d} 笔 / 超额 {m:+6.1f}bp / 净 {m - COST_BP:+6.1f}bp / 胜率 {hit:4.1f}% / t={t:+5.1f}"


def main():
    sig = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "res_wide.csv")
    sig = sig[sig["direction"].isin(["long", "short"])].reset_index(drop=True)
    rows = list(sig.itertuples())
    print(f"信号 {len(rows)} 条（已剔除 neutral），"
          f"{sig.symbol.nunique()} 币 × {sig.tf.nunique()} 周期\n")

    print("=== A. 入场延迟（超额，扣 8bp 后为净值）===")
    for tf, hold in (("1h", 4), ("4h", 3)):
        sub = [r for r in rows if r.tf == tf]
        for offset in (1, 2, 3):
            ex, raw = fixed_hold(sub, offset, hold)
            print(stats(ex, f"{tf} hold={hold} 延迟{offset - 1}根: "))

    print("\n=== B. 固定持有期（offset=1，超额）===")
    for tf, holds in (("1h", (1, 2, 4, 8, 12)), ("4h", (1, 2, 3, 4, 6))):
        sub = [r for r in rows if r.tf == tf]
        for h in holds:
            ex, _ = fixed_hold(sub, 1, h)
            print(stats(ex, f"{tf} h={h:>2d}: "))

    print("\n=== C. 反向跟随（fade，offset=1）===")
    for tf, hold in (("1h", 4), ("4h", 3)):
        sub = [r for r in rows if r.tf == tf]
        flipped = [r._replace(direction="short" if r.direction == "long" else "long") for r in sub]
        ex, _ = fixed_hold(flipped, 1, hold)
        print(stats(ex, f"{tf} fade h={hold}: "))

    print("\n=== D. ATR 止损 + R 倍数止盈（offset=1，扣 8bp）===")
    for tf, max_hold in (("1h", 12), ("4h", 6)):
        sub = [r for r in rows if r.tf == tf]
        print(f"-- {tf}，最大持有 {max_hold} 根")
        print(f"{'SL\\TP':>10} | " + " | ".join(f"{tp:.0f}R".rjust(26) for tp in (1.0, 2.0, 3.0)))
        for sl in (1.0, 1.5, 2.0):
            cells = []
            for tp in (1.0, 2.0, 3.0):
                ex, holds = [], []
                for r in sub:
                    ret, hh = atr_trade(r, 1, sl, tp, max_hold)
                    if ret is None:
                        continue
                    s = series(r.symbol, r.tf)
                    sign = 1 if r.direction == "long" else -1
                    i = s.index[int(r.ts)]
                    ex.append(ret - s.drift(sign, 1, int(hh)))
                    holds.append(hh)
                if len(ex) < 10:
                    cells.append("样本不足".rjust(26))
                    continue
                arr = np.array(ex)
                m = arr.mean() * 1e4
                cells.append(f"{m:+6.1f}/净{m - COST_BP:+6.1f} 持{np.mean(holds):4.1f}".rjust(26))
            print(f"SL={sl:.1f}ATR | " + " | ".join(cells))

    print("\n=== E. 按策略（最佳固定持有：1h h=4 / 4h h=3，offset=1）===")
    for tf, hold in (("1h", 4), ("4h", 3)):
        sub = [r for r in rows if r.tf == tf]
        for name in sorted({r.strategy for r in sub}):
            part = [r for r in sub if r.strategy == name]
            ex, _ = fixed_hold(part, 1, hold)
            print(stats(ex, f"{tf} {name:<24} h={hold}: "))


if __name__ == "__main__":
    main()
