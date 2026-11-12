"""候选方案的**样本外验证**：前半段找出来的「更优」，后半段还在不在。

对每个候选同时给：全样本、前半（内）、后半（外）、按月、按币、t 值、出场分布。
判定标准（写进结论前必须全部满足）：
1. 后半段净收益 > 0；
2. 后半段 t > 1；
3. 按月胜率 > 50%，不是靠单月；
4. 按币胜率 > 50%，不是靠单币。
"""
import numpy as np
import pandas as pd

from exit_modes import COST_BP, collect, load_signals
from exit_pnl import curve
from final_bt import BASE, atr_cfg, pct_cfg, cap_concurrency

S4 = None


def stats(df):
    if df is None or len(df) < 10:
        return None
    net = df.ret.to_numpy() - COST_BP / 1e4
    ex = df.ex.to_numpy()
    sd = net.std(ddof=1)
    t = net.mean() / (sd / np.sqrt(len(net))) if sd else 0.0
    _, m = curve(df)
    d = df.copy()
    d['month'] = pd.to_datetime(d.exit_ts, unit='ms').dt.strftime('%m')
    d['net_px'] = d.ret - COST_BP / 1e4
    bm = d.groupby('month').net_px.agg(['count', 'sum'])
    bs = d.groupby('symbol').net_px.agg(['count', 'sum'])
    return {
        'n': len(net), 'net_bp': net.mean() * 1e4, 'ex_bp': ex.mean() * 1e4, 't': t,
        'total': m['total'], 'ann': m['ann'], 'mdd': m['mdd'], 'sharpe': m['sharpe'], 'pf': m['pf'],
        'win': (net > 0).mean(), 'bars': df.bars.mean(),
        'month_win': (bm['sum'] > 0).mean(), 'sym_win': (bs['sum'] > 0).mean(),
        'reasons': df.reason.value_counts().to_dict(),
    }


def row(name, df):
    a = stats(df)
    if not a:
        print(f'{name:<26} 样本不足')
        return
    cut = df.entry_ts.median()
    h1, h2 = stats(df[df.entry_ts <= cut]), stats(df[df.entry_ts > cut])
    r = a['reasons']
    print(f"{name:<26} {a['n']:>4}笔 净{a['net_bp']:>+6.1f}bp t{a['t']:>5.1f} "
          f"总{a['total']*100:>+6.1f}% MDD{a['mdd']*100:>5.0f}% Sh{a['sharpe']:>5.2f} "
          f"胜{a['win']*100:>4.1f}% 损{r.get('stop', 0):>4}盈{r.get('target', 0):>4}时{r.get('time', 0):>4}")
    if h1 and h2:
        print(f"{'  前半 / 后半':<26} 前 {h1['net_bp']:>+6.1f}bp t{h1['t']:>5.1f} 总{h1['total']*100:>+6.1f}% Sh{h1['sharpe']:>5.2f}"
              f"  |  后 {h2['net_bp']:>+6.1f}bp t{h2['t']:>5.1f} 总{h2['total']*100:>+6.1f}% Sh{h2['sharpe']:>5.2f}"
              f"  |  月胜率 {a['month_win']*100:>3.0f}% 币胜率 {a['sym_win']*100:>3.0f}%")


def main():
    global S4
    sig = load_signals()
    S4 = sig[sig.tf == '4h']
    print(f'4h 信号 {len(S4)} 条，偏移2，最多6根（除注明），成本 {COST_BP:.0f}bp\n')

    print('=' * 130)
    print('候选 A：atr 止损 + TP=1R（上轮网格里唯一成片为正的区域）')
    print('=' * 130)
    for sl in (1.5, 2.0, 2.5, 3.0, 4.0):
        row(f'atr {sl}/{1}R', collect(S4, '4h', 2, 6, atr_cfg(sl, 1.0)))

    print()
    print('=' * 130)
    print('候选 B：percent 宽止损（不挂止盈）')
    print('=' * 130)
    for dist in (8, 10, 15):
        row(f'percent -{dist}% 无TP', collect(S4, '4h', 2, 6, pct_cfg(dist, 0)))
    row('纯超时（对照）', collect(S4, '4h', 2, 6, {'enable_long_sl_tp': False, 'enable_short_sl_tp': False}))

    print()
    print('=' * 130)
    print('候选 C：波动率分层（基准 = 纯超时 6 根，看 ATR/价格 高的那一档）')
    print('=' * 130)
    base = collect(S4, '4h', 2, 6, {'enable_long_sl_tp': False, 'enable_short_sl_tp': False})
    row('基准', base)
    for lo in (0.015, 0.020, 0.025, 0.030):
        row(f'仅 ATR% > {lo*100:.1f}%', base[base.atr_pct > lo])
    for hi in (0.012, 0.015):
        print(f'  （反向对照）仅 ATR% < {hi*100:.1f}%: ', end='')
        sub = base[base.atr_pct < hi]
        a = stats(sub)
        print('样本不足' if not a else f"{a['n']}笔 净{a['net_bp']:+.1f}bp t{a['t']:.1f} 总{a['total']*100:+.1f}%")

    print()
    print('=' * 130)
    print('候选 D：策略过滤（基准 = 纯超时 6 根）')
    print('=' * 130)
    for strat in sorted(base.strategy.unique()):
        row(f'仅 {strat}', base[base.strategy == strat])
    keep = base[base.strategy.isin(['level_breakout', 'rsi_divergence', 'ma_breakout'])]
    row('剔除 trend_channel_breakout', keep)
    keep2 = base[base.strategy.isin(['level_breakout', 'rsi_divergence'])]
    row('仅 level+rsi（样本小）', keep2)

    print()
    print('=' * 130)
    print('候选 E：并发上限 + 组合')
    print('=' * 130)
    for limit in (2, 3, 4, 6):
        row(f'并发 <= {limit}', cap_concurrency(base, limit))
    q4 = base[base.atr_pct > 0.020]
    row('ATR% > 2.0% + 并发4', cap_concurrency(q4, 4))
    row('ATR% > 2.0% + 并发2', cap_concurrency(q4, 2))
    row('ATR% > 2.0% + 并发4 + 剔通道突破',
        cap_concurrency(q4[q4.strategy != 'trend_channel_breakout'], 4))

    print()
    print('=' * 130)
    print('候选 F：ATR 1.5/1R 与波动率过滤叠加（看是不是同一批交易）')
    print('=' * 130)
    a = collect(S4, '4h', 2, 6, atr_cfg(1.5, 1.0))
    row('atr1.5/1R', a)
    row('atr1.5/1R 且 ATR%>2%', a[a.atr_pct > 0.020])
    row('atr1.5/1R 且 ATR%<1.2%', a[a.atr_pct < 0.012])

    print()
    print('=' * 130)
    print('候选 G：持有根数敏感性（检验 6 根是不是峰值拟合）')
    print('=' * 130)
    for bars in (4, 5, 6, 7, 8, 10):
        row(f'纯超时 {bars} 根', collect(S4, '4h', 2, bars,
                                       {'enable_long_sl_tp': False, 'enable_short_sl_tp': False}))

    print()
    print('=' * 130)
    print('候选 H：月度逐月净收益（看 edge 是不是集中在某几个月）')
    print('=' * 130)
    for name, df in (('纯超时6根', base), ('atr1.5/1R', a), ('ATR%>2%', q4)):
        d = df.copy()
        d['net'] = d.ret - COST_BP / 1e4
        d['month'] = pd.to_datetime(d.exit_ts, unit='ms').dt.strftime('%Y-%m')
        bm = d.groupby('month').net.agg(['count', 'sum']).sort_index()
        print(f'{name:<12} ' + '  '.join(f"{m}:{int(r['count'])}笔{r['sum']*100:+.1f}%" for m, r in bm.iterrows()))


if __name__ == '__main__':
    main()
