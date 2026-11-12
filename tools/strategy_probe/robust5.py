"""atr 1.5ATR / 1R 的稳健性检验。

单笔 t 值会因「同时持仓、同涨同跌」而虚高，这里额外给**按月聚类**的 t 值：
把每个月当成一个独立观测，看 edge 是否跨月稳定，而不是靠 800 笔相关交易堆出显著性。
"""
import numpy as np
import pandas as pd

from exit_modes import COST_BP, collect, load_signals
from exit_pnl import curve, lever
from final_bt import atr_cfg

S4 = None


def month_t(df, cost=COST_BP / 1e4):
    d = df.copy()
    d['net'] = d.ret - cost
    d['m'] = pd.to_datetime(d.exit_ts, unit='ms').dt.strftime('%Y-%m')
    g = d.groupby('m').net.mean()
    if len(g) < 3:
        return 0.0, g
    return float(g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))), g


def brief(df, cost=COST_BP / 1e4):
    net = df.ret.to_numpy() - cost
    _, m = curve(df)
    mt, _ = month_t(df, cost)
    return (f"{len(df):>4}笔 净{net.mean()*1e4:>+6.1f}bp 总{m['total']*100:>+6.1f}% "
            f"MDD{m['mdd']*100:>5.0f}% Sh{m['sharpe']:>5.2f} 月t{mt:>5.1f}")


def halves(df, cost=COST_BP / 1e4):
    cut = df.entry_ts.median()
    out = []
    for part in (df[df.entry_ts <= cut], df[df.entry_ts > cut]):
        net = part.ret.to_numpy() - cost
        sd = net.std(ddof=1)
        t = net.mean() / (sd / np.sqrt(len(net))) if sd else 0
        out.append((net.mean() * 1e4, t))
    return out


def main():
    global S4
    sig = load_signals()
    S4 = sig[sig.tf == '4h']

    print('=' * 120)
    print('1. 参数平台：SL × TP（4h 偏移2 最多6根，成本 8bp）')
    print('=' * 120)
    print(f"{'':<8}" + ''.join(f'{f"TP={t}R":>26}' for t in (0.75, 1.0, 1.25, 1.5, 2.0)))
    for sl in (1.0, 1.25, 1.5, 1.75, 2.0):
        cells = []
        for tp in (0.75, 1.0, 1.25, 1.5, 2.0):
            df = collect(S4, '4h', 2, 6, atr_cfg(sl, tp))
            _, m = curve(df)
            net = df.ret.mean() - COST_BP / 1e4
            cells.append(f"{net*1e4:>+5.1f}bp {m['total']*100:>+5.0f}%".rjust(26))
        print(f'{f"SL={sl}":<8}' + ''.join(cells))

    print()
    print('=' * 120)
    print('2. 成本敏感性（atr 1.5/1R）')
    print('=' * 120)
    df = collect(S4, '4h', 2, 6, atr_cfg(1.5, 1.0))
    for cost in (8, 12, 16, 20, 30, 40):
        net = df.ret.to_numpy() - cost / 1e4
        sd = net.std(ddof=1)
        t = net.mean() / (sd / np.sqrt(len(net)))
        print(f'  往返 {cost:>2}bp：净 {net.mean()*1e4:>+6.1f}bp  t {t:>+5.1f}  '
              f'胜率 {(net>0).mean()*100:>4.1f}%')

    print()
    print('=' * 120)
    print('3. 入场偏移 × 最大持有（atr 1.5/1R）')
    print('=' * 120)
    for offset in (1, 2, 3):
        cells = []
        for bars in (4, 5, 6, 8, 10, 12):
            d = collect(S4, '4h', offset, bars, atr_cfg(1.5, 1.0))
            cells.append(f"{d.ret.mean()*1e4 - COST_BP:>+6.1f}".rjust(8))
        print(f'  偏移{offset}（净 bp）' + ''.join(cells) + '   ← 持有 4/5/6/8/10/12 根')
    print('  对照 纯超时：', end='')
    for bars in (4, 6, 8, 10):
        d = collect(S4, '4h', 2, bars, {'enable_long_sl_tp': False, 'enable_short_sl_tp': False})
        print(f'{bars}根 {d.ret.mean()*1e4 - COST_BP:+.1f}bp', end='  ')
    print()

    print()
    print('=' * 120)
    print('4. 逐币（atr 1.5/1R）')
    print('=' * 120)
    for sym, sub in df.groupby('symbol'):
        h = halves(sub)
        net = sub.ret.mean() - COST_BP / 1e4
        print(f"  {sym:<10} {len(sub):>4}笔 净{net*1e4:>+6.1f}bp  前{h[0][0]:>+6.1f}/后{h[1][0]:>+6.1f}bp  "
              f"胜{(sub.ret > COST_BP/1e4).mean()*100:>4.1f}%")

    print()
    print('=' * 120)
    print('5. 去重方式与并发（atr 1.5/1R）')
    print('=' * 120)
    raw = collect(S4, '4h', 2, 6, atr_cfg(1.5, 1.0), dedupe=False)
    print(f"  不去重（同币可重叠）      {brief(raw)}")
    print(f"  去重（实盘约束）          {brief(df)}")
    for limit in (2, 3, 4, 6):
        d = df.sort_values('entry_ts').reset_index(drop=True)
        active, keep = [], []
        for idx, rec in zip(d.index, d.itertuples()):
            active = [x for x in active if x > rec.entry_ts]
            if len(active) >= limit:
                continue
            active.append(rec.exit_ts)
            keep.append(idx)
        print(f"  并发 <= {limit}              {brief(d.loc[keep])}")

    print()
    print('=' * 120)
    print('6. 实盘杠杆口径（每笔 10% 保证金，atr 1.5/1R）')
    print('=' * 120)
    for L in (1, 2, 3, 5, 10, 20):
        v = lever(df, 0.10, L)
        print(f"  {L:>2}x  总{v['total']*100:>+7.0f}%  MDD{v['mdd']*100:>6.0f}%  单笔爆仓{v['liq']:>3}次")

    print()
    print('=' * 120)
    print('7. 按月明细（atr 1.5/1R vs 纯超时6根）')
    print('=' * 120)
    base = collect(S4, '4h', 2, 6, {'enable_long_sl_tp': False, 'enable_short_sl_tp': False})
    for name, d in (('atr1.5/1R', df), ('纯超时6根', base)):
        x = d.copy()
        x['net'] = x.ret - COST_BP / 1e4
        x['m'] = pd.to_datetime(x.exit_ts, unit='ms').dt.strftime('%Y-%m')
        g = x.groupby('m').net.agg(['count', 'mean', 'sum'])
        mt, _ = month_t(d)
        print(f'  {name:<10} 月t={mt:>5.2f}  ' + '  '.join(
            f"{m}:{int(r['count'])}笔{r['mean']*1e4:+.0f}bp" for m, r in g.iterrows()))


if __name__ == '__main__':
    main()
