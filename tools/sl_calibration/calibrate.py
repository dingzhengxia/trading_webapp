# -*- coding: utf-8 -*-
"""止盈止损阈值标定（事件研究法）。

数据：Binance USDT-M 永续 1m K 线（data.binance.vision monthly zip，2026-08 ~ 2026-10）。
口径与引擎对齐（runner._structure_from_df / risk_model.build_plan）：
- 2h K 线聚合，ATR14(2h)；
- long 侧 T1 线 = 最近 7 根 2h 的 min(low)（T2/T3 同理 26/83 根）；
- R = |entry - t1|，TPk = entry + k*R（k=1,2,3）。

回答两个问题：
Q1（破位深度分级）：T1 破位事件发生后，30/60/120/300s 内价格继续深入多少 ATR？
    → 「深度 >= X ATR 跳过确认」的 X 怎么定，30s 确认窗口里最大额外损失是多少。
Q2（TP 防插针）：首次触及 TPk 的时刻，多少比例是「插针」（1m 收盘回到线内）？
    插针的后续走势 vs 真突破的后续走势差多少 → TP 确认用几根 1m 收盘合适。
"""
import glob
import io
import json
import zipfile
from collections import defaultdict

import numpy as np
import pandas as pd

RAW = r"E:/python/trading_webapp/tools/sl_calibration/raw"
LOOKBACKS = (7, 26, 83)
TP_MULTS = (1.0, 2.0, 3.0)


def load_1m(symbol: str) -> pd.DataFrame:
    frames = []
    for path in sorted(glob.glob(f"{RAW}/{symbol}-1m-*.zip")):
        with zipfile.ZipFile(path) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                df = pd.read_csv(io.BytesIO(f.read()))
                # Binance kline CSV 带表头：open_time,open,high,low,close,volume,...
                df = df.rename(columns={"open_time": "ts", "volume": "vol"})
                df = df[["ts", "open", "high", "low", "close", "vol"]]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def to_2h(df: pd.DataFrame) -> pd.DataFrame:
    g = df.set_index("ts").resample("2h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    return g.dropna().reset_index()


def atr14(h2: pd.DataFrame) -> pd.Series:
    tr = pd.concat([
        h2["high"] - h2["low"],
        (h2["high"] - h2["close"].shift()).abs(),
        (h2["low"] - h2["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False).mean()


def run_symbol(symbol: str) -> dict:
    m1 = load_1m(symbol)
    h2 = to_2h(m1)
    atr2h = atr14(h2).values
    lows2h = h2["low"].values
    highs2h = h2["high"].values
    close2h = h2["close"].values
    ts2h = h2["ts"].values

    # 1m 数组（numpy 化加速）
    m1_ts = m1["ts"].values.astype("datetime64[ns]")
    m1_low = m1["low"].values
    m1_high = m1["high"].values
    m1_close = m1["close"].values

    out = {"symbol": symbol,
           "breach_events": [],      # Q1
           "tp_events": defaultdict(list),  # Q2: k -> list of dicts
           "bars": len(h2)}

    n2h = len(h2)
    start_bar = max(LOOKBACKS) + 15  # 结构与 ATR 预热

    # 每个 2h bar 边界在 1m 序列中的起点索引
    import bisect
    m1_offsets = np.searchsorted(m1_ts, ts2h)

    # ---- Q1: T1/T2 破位事件（long 侧，镜像 short 对称，只测 long）----
    for lb_idx, lb in enumerate(LOOKBACKS[:2]):  # T1=7, T2=26
        level_name = f"T{lb_idx + 1}"
        for i in range(start_bar, n2h - 5):
            level = float(np.min(lows2h[i - lb:i]))
            atr = atr2h[i]
            if not np.isfinite(atr) or atr <= 0 or level <= 0:
                continue
            # 事件：本 2h bar 的 1m 收盘首次跌破 level（近似引擎实时价破线）
            s = m1_offsets[i]
            e = m1_offsets[i + 1] if i + 1 < n2h else len(m1)
            if e <= s:
                continue
            seg_close = m1_close[s:e]
            below = np.nonzero(seg_close < level)[0]
            if len(below) == 0:
                continue
            # 跨 2h bar 继续找后续深入（最多往后 5 个 2h bar ≈ 10h）
            end_all = m1_offsets[min(i + 5, n2h - 1) + 1]
            ev_start = s + int(below[0])
            # 防重复：与前一个事件太近则跳过（同一段下跌别反复计数）
            rec = {"level": level_name, "atr": float(atr)}
            for horizon_s, key in ((30, "d30"), (60, "d60"), (120, "d120"), (300, "d300")):
                idx_end = ev_start + horizon_s
                if idx_end >= end_all:
                    idx_end = end_all - 1
                if idx_end <= ev_start:
                    rec[key] = None
                    continue
                deepest = float(np.min(m1_low[ev_start:idx_end + 1]))
                rec[key] = round((level - deepest) / atr, 3)  # 深入多少 ATR（正=继续跌）
            out["breach_events"].append(rec)

    # ---- Q2: TP 防插针（long 侧）----
    for i in range(start_bar, n2h - 30):
        entry = float(close2h[i - 1]) if i > 0 else None
        t1 = float(np.min(lows2h[i - LOOKBACKS[0]:i]))
        atr = atr2h[i]
        if entry is None or not np.isfinite(atr) or atr <= 0:
            continue
        risk = entry - t1
        # risk 下限：引擎有 risk_min_pct=1.5%（剔除过近结构）
        if risk <= 0 or risk / entry < 0.015 or risk / entry > 0.08:
            continue
        s = m1_offsets[i]
        e = m1_offsets[min(i + 24, n2h - 1) + 1]  # 最多看 48h
        if e <= s + 1:
            continue
        seg_ts = m1_ts[s:e]
        seg_high = m1_high[s:e]
        seg_close = m1_close[s:e]
        for k, mult in enumerate(TP_MULTS):
            tp = entry + risk * mult
            hit = np.nonzero(seg_high >= tp)[0]
            if len(hit) == 0:
                continue
            h0 = int(hit[0])
            close_after = seg_close[h0]
            wick = close_after < tp  # 1m 收盘回到线下 = 插针（引擎 3s 轮询会立即触发）
            ev = {"wick": bool(wick),
                  "revisit_within_4h": bool(np.any(seg_high[h0 + 1:] >= tp)) if h0 + 1 < len(seg_high) else False,
                  "max_extra_r": None}
            if h0 + 1 < len(seg_high):
                maxhigh = float(np.max(seg_high[h0 + 1:]))
                ev["max_extra_r"] = round((maxhigh - tp) / risk, 3)
            out["tp_events"][k].append(ev)
    return out


def summarize(all_out: list) -> dict:
    report = {}

    # Q1 汇总
    for level in ("T1", "T2"):
        evs = [e for o in all_out for e in o["breach_events"] if e["level"] == level]
        if not evs:
            continue
        rep = {"n_events": len(evs)}
        for key in ("d30", "d60", "d120", "d300"):
            vals = np.array([e[key] for e in evs if e[key] is not None])
            if len(vals):
                rep[key] = {
                    "mean": round(float(vals.mean()), 3),
                    "p50": round(float(np.percentile(vals, 50)), 3),
                    "p75": round(float(np.percentile(vals, 75)), 3),
                    "p90": round(float(np.percentile(vals, 90)), 3),
                    "p_ge_0.5atr": round(float((vals >= 0.5).mean()), 3),
                    "p_ge_1.0atr": round(float((vals >= 1.0).mean()), 3),
                    "p_ge_1.5atr": round(float((vals >= 1.5).mean()), 3),
                }
        # 30s 确认窗口内的最大额外损失（原本 30s 确认会付出的代价）
        d30 = np.array([e["d30"] for e in evs if e["d30"] is not None])
        rep["cost_of_30s_confirm_p90"] = round(float(np.percentile(d30, 90)), 3)
        report[f"Q1_breach_{level}"] = rep

    # Q2 汇总
    for k in range(3):
        evs = [e for o in all_out for e in o["tp_events"].get(k, [])]
        if not evs:
            continue
        wick_n = sum(1 for e in evs if e["wick"])
        real = [e for e in evs if not e["wick"]]
        wicks = [e for e in evs if e["wick"]]
        rep = {
            "n_touches": len(evs),
            "wick_ratio": round(wick_n / len(evs), 3),
        }
        for name, group in (("real", real), ("wick", wicks)):
            extra = [e["max_extra_r"] for e in group if e["max_extra_r"] is not None]
            revisit = [e["revisit_within_4h"] for e in group]
            rep[name] = {
                "n": len(group),
                "mean_extra_r_after": round(float(np.mean(extra)), 3) if extra else None,
                "p50_extra_r_after": round(float(np.percentile(extra, 50)), 3) if extra else None,
                "revisit_ratio_4h": round(float(np.mean(revisit)), 3) if revisit else None,
            }
        report[f"Q2_TP{k + 1}"] = rep
    return report


def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
    all_out = []
    for s in symbols:
        try:
            r = run_symbol(s)
            all_out.append(r)
            print(f"{s}: 2h bars={r['bars']}, breach_events={len(r['breach_events'])}, "
                  f"tp_events={ {k: len(v) for k, v in r['tp_events'].items()} }")
        except Exception as exc:  # noqa: BLE001
            print(f"{s}: FAILED {exc}")
    report = summarize(all_out)
    out_path = r"E:/python/trading_webapp/tools/sl_calibration/calibration_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nsaved -> {out_path}")


if __name__ == "__main__":
    main()
