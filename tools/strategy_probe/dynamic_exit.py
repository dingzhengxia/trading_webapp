"""动态出场回测：移动止损 / 保本止损 / 分批止盈 vs 静态 1.5ATR/1R。

上一轮确定的「atr 1.5 / 1R」是**静态**出场。实盘还支持 TRAILING_STOP_MARKET
（回调率%），超时执行器可以补保本与分批。这轮逐一回测动态出场能不能再挤出收益。

模拟语义（与 outcomes.simulate_exit 一致，保守）：
- 逐根**先判触达**（用本根开始前的止损价），**再更新止损**（移动/保本）——杜绝根内前视；
- 跳空按开盘价成交；同根止损优先于止盈；
- 分批止盈的先出场那半仓多付一次出场成本（+2bp，占半仓 → 组合 +1bp）；
- ATR 缺失的交易按纯超时处理（与生产代码 exit_prices 返回 None 的行为一致）。
"""
import math

import numpy as np
import pandas as pd

from exit_modes import COST_BP, load_signals, frame, _atr
from exit_pnl import curve, fmt
from logic_test import series

SL_ATR, TP_R, MAX_BARS = 1.5, 1.0, 6


# ---------------------------------------------------------------------- 模拟器
def sim_exit(df, entry_idx, is_long, entry, sl0, tp, max_bars,
             trail_dist=None, trail_after=1, be_px=None):
    """单腿出场：静态 SL/TP + 可选移动止损 + 可选保本。

    trail_dist：移动止损距离（价格绝对值）；trail_after：入场后第几根开始跟踪。
    be_px：价格到达后把止损抬到 entry（保本）。
    """
    stop = sl0
    last_idx = min(entry_idx + int(max_bars), len(df) - 1)
    window_complete = entry_idx + int(max_bars) <= len(df) - 1

    def out(j, reason, px):
        return {'exit_price': px, 'exit_ts': int(df['timestamp'].iloc[j]),
                'bars_held': j - entry_idx + 1, 'reason': reason}

    for j in range(entry_idx, last_idx + 1):
        high = float(df['high'].iloc[j])
        low = float(df['low'].iloc[j])
        open_px = float(df['open'].iloc[j])
        if is_long:
            if stop is not None and low <= stop:
                return out(j, 'stop', min(stop, open_px))
            if tp is not None and high >= tp:
                return out(j, 'target', max(tp, open_px))
        else:
            if stop is not None and high >= stop:
                return out(j, 'stop', max(stop, open_px))
            if tp is not None and low <= tp:
                return out(j, 'target', min(tp, open_px))
        # ---- 根收盘后更新止损（本根的高/低只影响下一根的判定） ----
        if trail_dist is not None and (j - entry_idx + 1) >= trail_after:
            if is_long:
                moved = high - trail_dist
                stop = max(stop, moved) if stop is not None else moved
            else:
                moved = low + trail_dist
                stop = min(stop, moved) if stop is not None else moved
        if be_px is not None:
            if is_long and high >= be_px:
                stop = max(stop, entry) if stop is not None else entry
            if not is_long and low <= be_px:
                stop = min(stop, entry) if stop is not None else entry

    if not window_complete:
        return None
    return out(last_idx, 'time', float(df['close'].iloc[last_idx]))


def sim_partial(df, entry_idx, is_long, entry, sl0, risk, w1, tp1_r, tp2_r, max_bars,
                extra_cost=0.0):
    """分批止盈：w1 仓位在 tp1_r 出场，其余拿到 tp2_r（或 None=超时）。"""
    sign = 1 if is_long else -1
    tp1 = entry + sign * tp1_r * risk
    tp2 = entry + sign * tp2_r * risk if tp2_r else None
    ret_a = None
    last_idx = min(entry_idx + int(max_bars), len(df) - 1)
    window_complete = entry_idx + int(max_bars) <= len(df) - 1

    for j in range(entry_idx, last_idx + 1):
        high = float(df['high'].iloc[j])
        low = float(df['low'].iloc[j])
        open_px = float(df['open'].iloc[j])

        def stop_hit():
            return low <= sl0 if is_long else high >= sl0

        def fill_stop():
            return min(sl0, open_px) if is_long else max(sl0, open_px)

        if stop_hit():
            px = fill_stop()
            ra = ret_a if ret_a is not None else (px / entry - 1) * sign
            ret = w1 * ra + (1 - w1) * sign * (px / entry - 1)
            return {'exit_price': px, 'exit_ts': int(df['timestamp'].iloc[j]),
                    'bars_held': j - entry_idx + 1, 'reason': 'stop',
                    'ret': ret - extra_cost}
        if ret_a is None:
            if is_long and high >= tp1:
                ret_a = (max(tp1, open_px) / entry - 1)
            if not is_long and low <= tp1:
                ret_a = sign * (min(tp1, open_px) / entry - 1)
        if tp2 is not None:
            hit2 = high >= tp2 if is_long else low <= tp2
            if hit2:
                px = max(tp2, open_px) if is_long else min(tp2, open_px)
                rb = sign * (px / entry - 1)
                ra = ret_a if ret_a is not None else rb
                ret = w1 * ra + (1 - w1) * rb
                return {'exit_price': px, 'exit_ts': int(df['timestamp'].iloc[j]),
                        'bars_held': j - entry_idx + 1, 'reason': 'target',
                        'ret': ret - extra_cost}

    if not window_complete:
        return None
    px = float(df['close'].iloc[last_idx])
    ra = ret_a if ret_a is not None else sign * (px / entry - 1)
    ret = w1 * ra + (1 - w1) * sign * (px / entry - 1)
    return {'exit_price': px, 'exit_ts': int(df['timestamp'].iloc[last_idx]),
            'bars_held': last_idx - entry_idx + 1, 'reason': 'time',
            'ret': ret - extra_cost}


# ---------------------------------------------------------------------- 收集
def collect_dyn(sig, tf, offset, max_bars, variant, dedupe=True):
    rows = []
    for r in sig.itertuples():
        s = series(r.symbol, r.tf)
        i = s.index.get(int(r.ts))
        if i is None or i + offset >= len(s.close):
            continue
        entry = float(s.open[i + offset])
        if entry <= 0:
            continue
        atr = _atr(s, i)
        is_long = r.direction == 'long'
        sign = 1 if is_long else -1
        df = frame(r.symbol, r.tf)
        entry_idx = i + offset
        risk = sign * SL_ATR * atr if atr else None          # 1R = 1.5ATR 的价格距离
        sl0 = entry - risk if risk else None
        tp = entry + sign * variant.get('tp_r', TP_R) * abs(risk) if (variant.get('tp_r', TP_R) and risk) else None
        trail_dist = None
        if variant.get('trail_atr') and atr:
            trail_dist = variant['trail_atr'] * atr
        be_px = None
        if variant.get('be_r') and risk:
            be_px = entry + sign * variant['be_r'] * abs(risk)

        if variant.get('partial'):
            w1, tp1_r, tp2_r = variant['partial']
            if risk is None:
                continue
            res = sim_partial(df, entry_idx, is_long, entry, sl0, abs(risk),
                              w1, tp1_r, tp2_r, max_bars, extra_cost=0.0002)
        else:
            base = sim_exit(df, entry_idx, is_long, entry, sl0, tp, max_bars,
                            trail_dist=trail_dist, trail_after=variant.get('trail_after', 1),
                            be_px=be_px)
            if base is not None:
                res = dict(base, ret=sign * (base['exit_price'] / entry - 1))
            else:
                res = None
        if res is None:
            continue
        bars = int(res['bars_held'])
        rows.append({
            'symbol': r.symbol, 'tf': r.tf, 'strategy': r.strategy, 'direction': r.direction,
            'entry_ts': int(s.ts[entry_idx]), 'exit_ts': int(res['exit_ts']),
            'bars': bars, 'reason': res['reason'], 'ret': res['ret'],
            'drift': s.drift(sign, offset, bars),
            'ex': res['ret'] - s.drift(sign, offset, bars),
        })
    df_out = pd.DataFrame(rows, columns=['symbol', 'tf', 'strategy', 'direction', 'entry_ts', 'exit_ts',
                                         'bars', 'reason', 'ret', 'drift', 'ex'])
    if dedupe and len(df_out):
        df_out = df_out.sort_values('entry_ts')
        occupied, keep = {}, []
        for idx, rec in zip(df_out.index, df_out.itertuples()):
            if rec.entry_ts < occupied.get(rec.symbol, -1):
                continue
            occupied[rec.symbol] = rec.exit_ts
            keep.append(idx)
        df_out = df_out.loc[keep]
    return df_out.sort_values('entry_ts').reset_index(drop=True)


# ---------------------------------------------------------------------- 变体
def variants():
    v = {}
    v['静态 1.5/1R（现行）'] = {}
    v['静态 1.5 无TP'] = {'tp_r': None}
    v['移动 1.0ATR 延迟1根'] = {'trail_atr': 1.0, 'trail_after': 1, 'tp_r': None}
    v['移动 1.0ATR 延迟2根'] = {'trail_atr': 1.0, 'trail_after': 2, 'tp_r': None}
    v['移动 1.5ATR 延迟2根'] = {'trail_atr': 1.5, 'trail_after': 2, 'tp_r': None}
    v['移动 2.0ATR 延迟1根'] = {'trail_atr': 2.0, 'trail_after': 1, 'tp_r': None}
    v['移动1.0ATR + TP1R'] = {'trail_atr': 1.0, 'trail_after': 1}
    v['回调率1%（实盘TRAILING）'] = {'cb_pct': 0.01, 'tp_r': None}
    v['回调率2%'] = {'cb_pct': 0.02, 'tp_r': None}
    v['回调率3%'] = {'cb_pct': 0.03, 'tp_r': None}
    v['保本@1R + 无TP'] = {'be_r': 1.0, 'tp_r': None}
    v['保本@0.75R + 无TP'] = {'be_r': 0.75, 'tp_r': None}
    v['分批 50%@1R + 余仓拿满'] = {'partial': (0.5, 1.0, None)}
    v['分批 50%@1R + 余仓TP2R'] = {'partial': (0.5, 1.0, 2.0)}
    v['分批 30%@1R + 余仓TP2R'] = {'partial': (0.3, 1.0, 2.0)}
    return v


def apply_cb(sig, tf, offset, max_bars, variant, dedupe=True):
    """百分比回调率（实盘 TRAILING_STOP_MARKET 口径）：止损 = 极值价 × (1∓cb)。"""
    rows = []
    cb = variant['cb_pct']
    for r in sig.itertuples():
        s = series(r.symbol, r.tf)
        i = s.index.get(int(r.ts))
        if i is None or i + offset >= len(s.close):
            continue
        entry = float(s.open[i + offset])
        if entry <= 0:
            continue
        atr = _atr(s, i)
        is_long = r.direction == 'long'
        sign = 1 if is_long else -1
        df = frame(r.symbol, r.tf)
        entry_idx = i + offset
        risk = sign * SL_ATR * atr if atr else None
        sl0 = entry - risk if risk else None
        tp = entry + sign * variant.get('tp_r', TP_R) * abs(risk) if (variant.get('tp_r', TP_R) and risk) else None
        hwm = entry
        lwm = entry
        stop = sl0
        last_idx = min(entry_idx + int(max_bars), len(df) - 1)
        window_complete = entry_idx + int(max_bars) <= len(df) - 1
        result = None
        for j in range(entry_idx, last_idx + 1):
            high = float(df['high'].iloc[j])
            low = float(df['low'].iloc[j])
            open_px = float(df['open'].iloc[j])
            if is_long:
                if stop is not None and low <= stop:
                    result = (j, 'stop', min(stop, open_px))
                    break
                if tp is not None and high >= tp:
                    result = (j, 'target', max(tp, open_px))
                    break
            else:
                if stop is not None and high >= stop:
                    result = (j, 'stop', max(stop, open_px))
                    break
                if tp is not None and low <= tp:
                    result = (j, 'target', min(tp, open_px))
                    break
            # 根收盘后更新极值与移动止损
            if is_long:
                hwm = max(hwm, high)
                moved = hwm * (1 - cb)
                stop = max(stop, moved) if stop is not None else moved
            else:
                lwm = min(lwm, low)
                moved = lwm * (1 + cb)
                stop = min(stop, moved) if stop is not None else moved
        if result is None:
            if not window_complete:
                continue
            j = last_idx
            result = (j, 'time', float(df['close'].iloc[j]))
        j, reason, px = result
        bars = j - entry_idx + 1
        rows.append({
            'symbol': r.symbol, 'tf': r.tf, 'strategy': r.strategy, 'direction': r.direction,
            'entry_ts': int(s.ts[entry_idx]), 'exit_ts': int(df['timestamp'].iloc[j]),
            'bars': bars, 'reason': reason, 'ret': sign * (px / entry - 1),
            'drift': s.drift(sign, offset, bars),
            'ex': sign * (px / entry - 1) - s.drift(sign, offset, bars),
        })
    df_out = pd.DataFrame(rows, columns=['symbol', 'tf', 'strategy', 'direction', 'entry_ts', 'exit_ts',
                                         'bars', 'reason', 'ret', 'drift', 'ex'])
    if dedupe and len(df_out):
        df_out = df_out.sort_values('entry_ts')
        occupied, keep = {}, []
        for idx, rec in zip(df_out.index, df_out.itertuples()):
            if rec.entry_ts < occupied.get(rec.symbol, -1):
                continue
            occupied[rec.symbol] = rec.exit_ts
            keep.append(idx)
        df_out = df_out.loc[keep]
    return df_out.sort_values('entry_ts').reset_index(drop=True)


# ---------------------------------------------------------------------- 主流程
def run(tf, offset, max_bars=MAX_BARS, verbose_reason=True):
    sig = load_signals()
    sig = sig[sig.tf == tf]
    print(f"===== {tf} · 偏移{offset} · 最大持有 {max_bars} 根（每笔 10% 净值，{COST_BP:.0f}bp 成本）=====")
    print(f"{'变体':<24}{'笔数':>5}{'净bp':>8}{'总收益':>9}{'MDD':>8}{'Sharpe':>8}{'PF':>6}  出场分布")
    results = {}
    for name, v in variants().items():
        if v.get('cb_pct'):
            df = apply_cb(sig, tf, offset, max_bars, v)
        else:
            df = collect_dyn(sig, tf, offset, max_bars, v)
        _, m = curve(df)
        if m is None:
            print(f"{name:<24}  样本不足")
            continue
        mix = ' '.join(f'{k}:{n}' for k, n in sorted(df.reason.value_counts().items()))
        print(f"{name:<24}{m['n']:>5}{(df.ret.mean()-COST_BP/1e4)*1e4:>+8.1f}"
              f"{m['total']*100:>+8.1f}%{m['mdd']*100:>7.1f}%{m['sharpe']:>8.2f}{m['pf']:>6.2f}  {mix}")
        results[name] = df
    return results


def split_check(results, keys, tf, offset):
    """赢家做前半/后半与逐币稳定性。"""
    for name in keys:
        df = results.get(name)
        if df is None or len(df) < 20:
            continue
        cut = df.entry_ts.median()
        h, t = df[df.entry_ts <= cut], df[df.entry_ts > cut]
        print(f"\n-- {name}（{tf} 偏移{offset}）")
        print(f"   前半 {len(h)}笔 {(h.ret.mean()-COST_BP/1e4)*1e4:>+7.1f}bp | "
              f"后半 {len(t)}笔 {(t.ret.mean()-COST_BP/1e4)*1e4:>+7.1f}bp")
        by = df.groupby('symbol').ret.mean().sort_values(ascending=False)
        print('   按币 ' + '  '.join(f"{s}:{v*1e4:+.0f}bp" for s, v in by.items()))


if __name__ == '__main__':
    res = run('4h', 2)
    print()
    winners = ['移动 1.0ATR 延迟1根', '移动 2.0ATR 延迟1根', '回调率2%', '回调率3%',
               '保本@1R + 无TP', '分批 50%@1R + 余仓拿满']
    split_check(res, winners, '4h', 2)
    print()
    run('4h', 1)
