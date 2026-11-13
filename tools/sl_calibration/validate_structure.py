# -*- coding: utf-8 -*-
"""结构位有效性验证：现行 7/26/83 回看 vs 候选回看 vs 随机价位对照组。

口径与引擎对齐：2h K 线、ATR14、结构位 = 最近 N 根（不含当前根）的 rolling min/max。
事件定义（以支撑位为例，阻力位对称）：
  进入：某 2h 根 low 首次落入 [level - 0.5ATR, level + 1ATR] 且收盘在 level 上方
  结果窗口：之后 12 根 2h（24h）
  反弹成功：窗口内价格自进入根收盘价回升 >= 1 ATR，且此前未收破 level - 1 ATR
  跌破失败：先收破 level - 1 ATR（反弹按后续是否回升不追究，保守计失败）
对照：同一时刻取 level + uniform(0.5, 2.5)*ATR 的随机价位，同样规则计算反弹率。
用法：python3 validate_structure.py
输出：structure_report.json + 控制台摘要
"""
import glob
import io
import json
import zipfile

import numpy as np
import pandas as pd

RAW_DIR = "raw"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
LOOKBACK_SETS = {
    "current_7_26_83": (7, 26, 83),
    "short_5_13_34": (5, 13, 34),
    "long_12_48_120": (12, 48, 120),
}
ATR_PERIOD = 14
APPROACH_LO, APPROACH_HI = 0.5, 1.0  # 进入带：[level - 0.5ATR, level + 1ATR]
BREAK_ATR = 1.0
BOUNCE_ATR = 1.0
WINDOW_BARS = 12  # 2h 根数 = 24h


def load_symbol(symbol: str) -> pd.DataFrame:
    frames = []
    for path in sorted(glob.glob(f"{RAW_DIR}/{symbol}-1m-*.zip")):
        with zipfile.ZipFile(path) as zf:
            with zf.open(zf.namelist()[0]) as f:
                frames.append(pd.read_csv(io.BytesIO(f.read()), usecols=[0, 1, 2, 3, 4]))
    df = pd.concat(frames, ignore_index=True)
    df.columns = ["ts", "open", "high", "low", "close"]
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("dt").sort_index()
    ohlc = df.resample("2h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return ohlc


def atr14(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()


def support_levels(df: pd.DataFrame, lookback: int) -> pd.Series:
    return df["low"].rolling(lookback).min().shift(1)


def resistance_levels(df: pd.DataFrame, lookback: int) -> pd.Series:
    return df["high"].rolling(lookback).max().shift(1)


def evaluate_events(df: pd.DataFrame, levels: pd.Series, atr: pd.Series, rng: np.random.RandomState):
    """返回 (结构位事件反弹率, 对照随机价位反弹率, 事件数)。"""
    highs, lows, closes = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    stats = {"struct_bounce": 0, "struct_events": 0, "rand_bounce": 0, "rand_events": 0}
    last_event_bar = -999
    for i in range(ATR_PERIOD + 90, n - WINDOW_BARS):
        level, a = levels.iloc[i], atr.iloc[i]
        if not np.isfinite(level) or not np.isfinite(a) or a <= 0:
            continue
        # 事件间隔至少 6 根（同一波下探不重复计数）
        if i - last_event_bar < 6:
            continue
        # 进入条件：low 在带内、收盘未破位（首次逼近）
        if not (level - APPROACH_LO * a <= lows[i] <= level + APPROACH_HI * a and closes[i] > level):
            continue
        last_event_bar = i
        entry = closes[i]
        win_h, win_l = highs[i + 1:i + 1 + WINDOW_BARS], lows[i + 1:i + 1 + WINDOW_BARS]
        win_c = closes[i + 1:i + 1 + WINDOW_BARS]
        bounce_bar = np.argmax(win_h >= entry + BOUNCE_ATR * a) if (win_h >= entry + BOUNCE_ATR * a).any() else -1
        break_bar = np.argmax(win_c < level - BREAK_ATR * a) if (win_c < level - BREAK_ATR * a).any() else -1
        if bounce_bar >= 0 and (break_bar < 0 or bounce_bar < break_bar):
            stats["struct_bounce"] += 1
        stats["struct_events"] += 1
        # 随机对照：同根换一个随机价位（距现价同样位于下方 0.5~2.5 ATR）
        rlevel = closes[i] - rng.uniform(APPROACH_LO, 2.5) * a
        rentry = closes[i]
        rbounce = (win_h >= rentry + BOUNCE_ATR * a).any()
        rbreak = (win_c < rlevel - BREAK_ATR * a).any()
        if rbounce and not rbreak:
            stats["rand_bounce"] += 1
        stats["rand_events"] += 1
    return stats


def main():
    rng = np.random.RandomState(42)
    report = {}
    for name, (l1, l2, l3) in LOOKBACK_SETS.items():
        agg = {k: 0 for k in ["struct_bounce", "struct_events", "rand_bounce", "rand_events"]}
        per_tier = {f"T{i+1}": {"b": 0, "e": 0} for i in range(3)}
        for sym in SYMBOLS:
            df = load_symbol(sym)
            atr = atr14(df)
            for tier, lookback in enumerate((l1, l2, l3)):
                levels = support_levels(df, lookback)
                s = evaluate_events(df, levels, atr, rng)
                agg["struct_bounce"] += s["struct_bounce"]
                agg["struct_events"] += s["struct_events"]
                per_tier[f"T{tier+1}"]["b"] += s["struct_bounce"]
                per_tier[f"T{tier+1}"]["e"] += s["struct_events"]
                if tier == 0:
                    agg["rand_bounce"] += s["rand_bounce"]
                    agg["rand_events"] += s["rand_events"]
        sr = agg["struct_bounce"] / agg["struct_events"] if agg["struct_events"] else 0
        rr = agg["rand_bounce"] / agg["rand_events"] if agg["rand_events"] else 0
        report[name] = {
            "events": agg["struct_events"],
            "bounce_rate": round(sr, 4),
            "random_bounce_rate": round(rr, 4),
            "edge": round(sr - rr, 4),
            "per_tier": {k: round(v["b"] / v["e"], 4) if v["e"] else None for k, v in per_tier.items()},
        }
        print(f"[{name}] events={agg['struct_events']} bounce={sr:.1%} random={rr:.1%} edge={sr-rr:+.1%}")
    with open("structure_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("saved -> structure_report.json")


if __name__ == "__main__":
    main()
