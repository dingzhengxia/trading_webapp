"""深挖 trend_channel_breakout：唯一正 edge 的候选，逐层拆解。

检验顺序（先证伪，再谈优化）：
0. 概览：两组参数（std 1.5 短周期 / 1.8 长周期）各多少信号
1. 固定持有、不挂止损：原始 edge 是否存在（排除「出场规则碰巧救活」）
2. 生产出场（ATR n× / mR + 超时）：与固定持有对比
3. 分币：是不是 1~2 个币撑着
4. 分月：前后半段是否一致（180 天样本，按月切）
5. 多空对称性
6. 反向检验：把方向翻转，若反向收益接近正向 → 纯噪音
7. 参数网格：sl_atr × tp_r × max_bars
8. leave-one-symbol-out + 按币 bootstrap
"""
import math

import numpy as np
import pandas as pd

from exit_modes import COST_BP, collect, summary
from logic_test import series

TF_BARS = {'4h': 6, '1h': 24}      # 持有上限统一 24 小时
GRID_BARS = {'4h': (3, 6, 12), '1h': (6, 12, 24)}

OFF = 1


def load():
    df = pd.read_csv('tcb_signals.csv')
    df = df[df.direction.isin(['long', 'short'])].copy()
    df['strategy'] = 'trend_channel_breakout'
    return df.sort_values('ts').reset_index(drop=True)


def atr_cfg(sl_atr, tp_r, max_bars):
    return {'signal_exit_mode': 'atr', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
            'signal_paper_sl_atr': sl_atr, 'signal_paper_tp_r': tp_r}


def hold_cfg():
    return {'signal_exit_mode': 'percent', 'enable_long_sl_tp': False, 'enable_short_sl_tp': False}


def line(r, label, width=26):
    if r is None:
        return f'{label:<{width}} 样本不足'
    return (f"{label:<{width}} {r['n']:>5} {r['ex_bp']:>+7.1f} {r['net_bp']:>+7.1f} "
            f"{r['t']:>+6.1f} {r['hit']:>5.1f}% {r['bars']:>5.1f}")


HEAD_HOLD = f"{'口径':<26} {'样本':>5} {'超额':>7} {'净':>7} {'t':>6} {'胜率':>6} {'均持':>5}"


def sec(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main():
    sig = load()
    sec('0. 概览（信号条数，未去重）')
    print(sig.groupby(['tf', 'strategy_index', 'direction']).size().unstack(fill_value=0))

    # ---------- 1. 固定持有 ----------
    sec('1. 固定持有（不挂止损止盈，只按时间平）—— 检验原始 edge')
    for tf in ('4h', '1h'):
        print(f"\n-- {tf}")
        print(HEAD_HOLD)
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            s = sub[sub.strategy_index == idx]
            for h in (1, 3, 6, 12, 24):
                if h * (4 if tf == '4h' else 1) > 96:
                    continue
                r = summary(collect(s, tf, OFF, h, hold_cfg()))
                print(line(r, f'idx{idx} 持有{h}根'))

    # ---------- 2. 生产出场 ----------
    sec('2. 生产出场（ATR 1.5 / 1R，超时平仓）')
    for tf in ('4h', '1h'):
        print(f"\n-- {tf}（max_bars={TF_BARS[tf]}）")
        print(HEAD_HOLD + '  出场分布')
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            s = sub[sub.strategy_index == idx]
            df = collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf]))
            r = summary(df)
            mix = ' '.join(f'{k}:{v}' for k, v in sorted(r['reasons'].items())) if r else ''
            print(line(r, f'idx{idx} ATR1.5/1R') + f'  {mix}')

    # ---------- 3. 分币 ----------
    sec('3. 分币（ATR 1.5/1R，去重后）')
    for tf in ('4h', '1h'):
        print(f"\n-- {tf}")
        print(HEAD_HOLD)
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            for sym in sorted(sub.symbol.unique()):
                s = sub[(sub.strategy_index == idx) & (sub.symbol == sym)]
                r = summary(collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf])))
                print(line(r, f'idx{idx} {sym[:-4]}'))

    # ---------- 4. 分月 ----------
    sec('4. 分月（ATR 1.5/1R，去重后）')
    for tf in ('4h', '1h'):
        print(f"\n-- {tf}")
        print(HEAD_HOLD)
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            s = sub[sub.strategy_index == idx]
            df = collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf]))
            if df is None or not len(df):
                continue
            df['month'] = pd.to_datetime(df.entry_ts, unit='ms').dt.strftime('%Y-%m')
            for m, g in df.groupby('month'):
                r = summary(g.reset_index(drop=True))
                print(line(r, f'idx{idx} {m}'))

    # ---------- 5. 多空 ----------
    sec('5. 多空对称性（ATR 1.5/1R）')
    for tf in ('4h', '1h'):
        print(f"\n-- {tf}")
        print(HEAD_HOLD)
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            for d in ('long', 'short'):
                s = sub[(sub.strategy_index == idx) & (sub.direction == d)]
                r = summary(collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf])))
                print(line(r, f'idx{idx} {d}'))

    # ---------- 6. 反向 ----------
    sec('6. 反向检验（方向翻转；若 |反向| ≈ |正向| 则为噪音）')
    print(HEAD_HOLD)
    for tf in ('4h', '1h'):
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            s = sub[sub.strategy_index == idx].copy()
            fwd = summary(collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf])))
            s['direction'] = s.direction.map({'long': 'short', 'short': 'long'})
            rev = summary(collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf])))
            print(line(fwd, f'{tf} idx{idx} 正向'))
            print(line(rev, f'{tf} idx{idx} 反向'))

    # ---------- 7. 参数网格 ----------
    sec('7. 参数网格（超额 bp；括号内为笔数）')
    for tf in ('4h', '1h'):
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            s = sub[sub.strategy_index == idx]
            print(f"\n-- {tf} idx{idx}")
            header = 'sl_atr\\tp_r ' + ''.join(f'{f"{t}R":>14}' for t in (0.5, 1.0, 1.5, 2.0)) + '     time-only'
            print(header)
            for sl in (1.0, 1.5, 2.0, 2.5):
                cells = []
                for tp in (0.5, 1.0, 1.5, 2.0):
                    r = summary(collect(s, tf, OFF, TF_BARS[tf], atr_cfg(sl, tp, TF_BARS[tf])))
                    cells.append(f"{r['ex_bp']:>+8.1f}({r['n']:>3})" if r else f"{'-':>14}")
                print(f'{sl:>9.1f}   ' + ''.join(f'{c:>14}' for c in cells), end='')
                if sl == 1.5:
                    r = summary(collect(s, tf, OFF, TF_BARS[tf], hold_cfg()))
                    print(f"   {r['ex_bp']:>+8.1f}({r['n']:>3})" if r else '   -')
                else:
                    print()

    # ---------- 8. leave-one-out + bootstrap ----------
    sec('8. 稳健性：leave-one-symbol-out 与按币 bootstrap（ATR 1.5/1R）')
    rng = np.random.default_rng(7)
    for tf in ('4h', '1h'):
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            s = sub[sub.strategy_index == idx]
            df = collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf]))
            if df is None or not len(df):
                continue
            print(f"\n-- {tf} idx{idx}  全样本 {df.ex.mean()*1e4:+.1f}bp / {len(df)} 笔")
            loo = []
            for sym in sorted(df.symbol.unique()):
                g = df[df.symbol != sym]
                loo.append((sym, g.ex.mean() * 1e4, len(g)))
            print('  LOO: ' + '  '.join(f"-{s[:-4]} {b:+.1f}" for s, b, _ in loo))
            # 按币重采样
            groups = [g.ex.to_numpy() for _, g in df.groupby('symbol')]
            means = []
            for _ in range(2000):
                pick = rng.integers(0, len(groups), len(groups))
                arr = np.concatenate([groups[i] for i in pick])
                means.append(arr.mean() * 1e4)
            means = np.array(means)
            print(f"  bootstrap(按币, 2000 次): 均值 {means.mean():+.1f}bp  "
                  f"2.5%~97.5% [{np.percentile(means, 2.5):+.1f}, {np.percentile(means, 97.5):+.1f}]  "
                  f"P(>0)={float((means > 0).mean())*100:.1f}%")

    # ---------- 9. 量能分层 ----------
    sec('9. 量能倍率分层（信号 bar 的 volume_ratio，仅参考）')
    for tf in ('4h', '1h'):
        sub = sig[sig.tf == tf]
        for idx in sorted(sub.strategy_index.unique()):
            s = sub[sub.strategy_index == idx]
            df = collect(s, tf, OFF, TF_BARS[tf], atr_cfg(1.5, 1.0, TF_BARS[tf]))
            if df is None or not len(df):
                continue
            key = s.set_index(['symbol', 'ts'])['volume_ratio']
            df['vr'] = [key.get((r.symbol, r.entry_ts), np.nan) for r in df.itertuples()]
            ok = df.dropna(subset=['vr'])
            if len(ok) < 30:
                print(f'\n-- {tf} idx{idx} 无量能数据')
                continue
            print(f"\n-- {tf} idx{idx}")
            print(HEAD_HOLD)
            for lo, hi in ((0, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 99)):
                g = ok[(ok.vr >= lo) & (ok.vr < hi)]
                r = summary(g.reset_index(drop=True))
                print(line(r, f'vr [{lo:g},{hi:g})'))


if __name__ == '__main__':
    main()
