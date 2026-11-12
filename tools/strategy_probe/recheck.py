"""用修正后的去重口径，重做两件事：

1. 每个策略**独立**评估（各开各的仓，不互相抢），看信号层到底有没有 edge；
   旧口径把 6 个策略塞进同一条 dedupe 队列、先到先得，ma_breakout 信号量占 74%，
   其它策略只能在它没占用的时段捡剩，等于随机抽样，结论不可用。
2. 出场口径对比（percent vs atr）放到**每个策略内部**做，避免混合偏差。
"""
import math

import numpy as np
import pandas as pd

from exit_modes import COST_BP, collect, summary
from exit_pnl import curve
import exit_pnl

STRATS = ['ema_cross', 'ma_breakout', 'level_breakout', 'rsi_divergence',
          'trend_channel_breakout', 'consecutive_candles']
TF_BARS = {'4h': 6, '1h': 24}

MODES = {
    'P40@5': {'signal_exit_mode': 'percent', 'leverage': 5,
              'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
              'long_stop_loss_percentage': 40, 'long_take_profit_percentage': 40,
              'short_stop_loss_percentage': 40, 'short_take_profit_percentage': 40},
    'P40@20': {'signal_exit_mode': 'percent', 'leverage': 20,
               'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
               'long_stop_loss_percentage': 40, 'long_take_profit_percentage': 40,
               'short_stop_loss_percentage': 40, 'short_take_profit_percentage': 40},
    'ATR1.5/1R': {'signal_exit_mode': 'atr', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
                  'signal_paper_sl_atr': 1.5, 'signal_paper_tp_r': 1.0},
    'ATR1.5/2R': {'signal_exit_mode': 'atr', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
                  'signal_paper_sl_atr': 1.5, 'signal_paper_tp_r': 2.0},
    'TIME': {'signal_exit_mode': 'percent', 'enable_long_sl_tp': False, 'enable_short_sl_tp': False},
}


def load():
    s = pd.read_csv('res_wide.csv')
    return s[s.direction.isin(['long', 'short'])].sort_values('ts').reset_index(drop=True)


def cell(r):
    return f"{r['ex_bp']:>+7.1f}({r['n']:>4})" if r else f"{'-':>12}"


def main():
    sig = load()
    names = list(MODES)

    for tf in ('4h', '1h'):
        print(f"\n{'=' * 96}")
        print(f'{tf}  单策略独立评估（超额 bp，括号内笔数；成本 8bp 未扣）')
        print('=' * 96)
        print(f"{'策略':<24}" + ''.join(f'{n:>14}' for n in names) + f"{'t(ATR1.5/1R)':>13}")
        for st in STRATS:
            s = sig[(sig.tf == tf) & (sig.strategy == st)]
            if not len(s):
                continue
            cells, tval = [], 0.0
            for n in names:
                r = summary(collect(s, tf, 1, TF_BARS[tf], MODES[n]))
                cells.append(f'{cell(r):>14}')
                if n == 'ATR1.5/1R' and r:
                    tval = r['t']
            print(f'{st:<24}' + ''.join(cells) + f'{tval:>+13.1f}')

        # 全策略混合（旧口径，作为对照）
        s = sig[sig.tf == tf]
        cells = [f'{cell(summary(collect(s, tf, 1, TF_BARS[tf], MODES[n]))):>14}' for n in names]
        print(f"{'—— 混合(对照)':<24}" + ''.join(cells))

    # 组合曲线：单策略最优 vs 混合
    print(f"\n{'=' * 96}")
    print('组合资金曲线（每笔名义 10% 净值，实现时间复利，8bp 成本）')
    print('=' * 96)
    print(f"{'样本':<30}{'口径':<12}{'笔数':>5}{'总收益':>9}{'年化':>9}{'回撤':>8}{'Sharpe':>8}{'盈亏比':>7}")
    for tf in ('4h', '1h'):
        rows = []
        for st in STRATS:
            s = sig[(sig.tf == tf) & (sig.strategy == st)]
            if not len(s):
                continue
            df = collect(s, tf, 1, TF_BARS[tf], MODES['ATR1.5/1R'])
            _, m = curve(df, weight=0.10)
            if m:
                rows.append((m['ann'], st, m, len(df)))
        rows.sort(reverse=True)
        for _, st, m, n in rows:
            print(f"{tf + ' ' + st:<30}{'ATR1.5/1R':<12}{m['n']:>5}{m['total']*100:>+8.1f}%"
                  f"{m['ann']*100:>+8.1f}%{m['mdd']*100:>7.1f}%{m['sharpe']:>8.2f}{m['pf']:>7.2f}")
        s = sig[sig.tf == tf]
        df = collect(s, tf, 1, TF_BARS[tf], MODES['ATR1.5/1R'])
        _, m = curve(df, weight=0.10)
        if m:
            print(f"{tf + ' 混合(先到先得)':<30}{'ATR1.5/1R':<12}{m['n']:>5}{m['total']*100:>+8.1f}%"
                  f"{m['ann']*100:>+8.1f}%{m['mdd']*100:>7.1f}%{m['sharpe']:>8.2f}{m['pf']:>7.2f}")

    # 统计功效测算
    print(f"\n{'=' * 96}")
    print('统计功效：要在单笔标准差 σ 下检出 d bp 的 edge，需要多少笔（双尾 5%、80% 功效）')
    print('=' * 96)
    n_need = 7.85 * (300 / 10.0) ** 2
    print(f'  σ≈300bp、目标 +10bp/笔 → 需 ≈{n_need:.0f} 笔')
    print(f'  现状：4h 单策略最多 200~2000 笔，1h 更多但 edge 更差')
    for tf in ('4h', '1h'):
        s = sig[sig.tf == tf]
        df = collect(s, tf, 1, TF_BARS[tf], MODES['ATR1.5/1R'])
        if df is not None and len(df):
            sd = df.ex.std(ddof=1) * 1e4
            print(f'  {tf} 实际：n={len(df)}  σ={sd:.0f}bp  → 可检出的最小 edge ≈ '
                  f'{2.8 * sd / math.sqrt(len(df)):.1f}bp')


if __name__ == '__main__':
    main()
