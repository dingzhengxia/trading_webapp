"""最新统一出场层（core/exit_rules + signals/outcomes）的**收益回测 + 优化扫描**。

与前面几轮的区别：
1. 完全按合并后的语义跑：`signal_exit_mode` 决定 percent / atr，实盘与纸面同一份 `exit_prices`；
2. 所有口径都做组合视角（同币持仓期不重复开仓、按实现时间累计净值），不是单笔统计；
3. 加样本内/外分割：前半段调参、后半段验证，用来区分「优化」和「拟合」；
4. 除了出场参数，还测三个真正的优化轴：方向过滤、策略过滤、波动率分层、并发上限。

运行：cd tools/strategy_probe && python final_bt.py
"""
import numpy as np
import pandas as pd

from exit_modes import COST_BP, collect, load_signals
from exit_pnl import curve, lever

LEV = 20
BASE = {
    'signal_exit_mode': 'percent',
    'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
    'leverage': LEV,
    'long_stop_loss_percentage': 300, 'long_take_profit_percentage': 600,
    'short_stop_loss_percentage': 200, 'short_take_profit_percentage': 300,
}


def pct_cfg(dist_pct, tp_r=0.0, lev=LEV):
    """价格止损距离 -> 保证金百分比配置（与设置页字段同义）。"""
    margin_pct = dist_pct * lev
    return dict(BASE, leverage=lev,
                long_stop_loss_percentage=margin_pct,
                short_stop_loss_percentage=margin_pct,
                long_take_profit_percentage=margin_pct * tp_r if tp_r else 0,
                short_take_profit_percentage=margin_pct * tp_r if tp_r else 0)


def atr_cfg(sl_atr, tp_r):
    return {'signal_exit_mode': 'atr', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
            'signal_paper_sl_atr': sl_atr, 'signal_paper_tp_r': tp_r}


def metrics(df):
    if df is None or len(df) < 10:
        return None
    _, m = curve(df)
    r = df.reason.value_counts().to_dict()
    m['net_bp'] = (df.ret.mean() - COST_BP / 1e4) * 1e4
    m['ex_bp'] = df.ex.mean() * 1e4
    m['bars'] = df.bars.mean()
    m['stops'] = r.get('stop', 0)
    m['targets'] = r.get('target', 0)
    m['times'] = r.get('time', 0)
    return m


def line(name, m, width=22):
    if not m:
        return f'{name:<{width}} 样本不足'
    return (f"{name:<{width}} {m['n']:>4}笔 净{m['net_bp']:>+6.1f}bp 总{m['total']*100:>+7.1f}% "
            f"年化{m['ann']*100:>+7.1f}% MDD{m['mdd']*100:>6.1f}% Sh{m['sharpe']:>5.2f} "
            f"PF{m['pf']:>4.2f} 胜{m['win']*100:>4.1f}% 持{m['bars']:>4.1f} "
            f"[损{m['stops']} 盈{m['targets']} 时{m['times']}]")


def cap_concurrency(df, limit):
    """全局并发上限：按入场顺序贪心，同时在场的仓位数不超过 limit。"""
    if df is None or len(df) == 0:
        return df
    d = df.sort_values('entry_ts').reset_index(drop=True)
    active, keep = [], []
    for idx, rec in zip(d.index, d.itertuples()):
        active = [x for x in active if x > rec.entry_ts]
        if len(active) >= limit:
            continue
        active.append(rec.exit_ts)
        keep.append(idx)
    return d.loc[keep].sort_values('entry_ts').reset_index(drop=True)


def split_halves(df):
    """前半 / 后半（按入场时间中位数切），用于样本内外对照。"""
    cut = df.entry_ts.median()
    return df[df.entry_ts <= cut], df[df.entry_ts > cut]


def main():
    sig = load_signals()
    s4 = sig[sig.tf == '4h']
    s1 = sig[sig.tf == '1h']
    print(f"样本：4h {len(s4)} 条 / 1h {len(s1)} 条方向性信号；"
          f"成本 {COST_BP:.0f}bp；每笔名义 10% 净值；同币不重复开仓\n")

    # ---------------------------------------------------------------- 1 现行 vs 候选
    print('=' * 118)
    print('1. 现行配置 vs 候选（组合收益口径）')
    print('=' * 118)
    cands = {
        'A 现行 percent(-15%/+30%)': BASE,
        'B 纯超时(不挂价单)': {'enable_long_sl_tp': False, 'enable_short_sl_tp': False},
        'C atr 1.5/2R': atr_cfg(1.5, 2.0),
        'D percent(-8%,无止盈)': pct_cfg(8, 0),
    }
    for tf, bars, src in (('4h', 6, s4), ('1h', 12, s1)):
        for offset in (1, 2):
            print(f'-- {tf} 偏移{offset} 最多{bars}根')
            for name, cfg in cands.items():
                print('   ' + line(name, metrics(collect(src, tf, offset, bars, cfg))))
            print()

    # ---------------------------------------------------------------- 2 percent 网格
    print('=' * 118)
    print('2. percent 口径网格：价格止损距离 × 止盈(止损的倍数) —— 4h 偏移2')
    print('=' * 118)
    print(f"{'止损距离':<10}" + ''.join(f'{f"TP={t}":>44}' for t in ('关', '1.5x', '2x', '3x')))
    for dist in (2, 3, 4, 6, 8, 10, 15):
        cells = []
        for tp_r in (0, 1.5, 2.0, 3.0):
            m = metrics(collect(s4, '4h', 2, 6, pct_cfg(dist, tp_r)))
            cells.append('—'.rjust(44) if not m else
                         f"{m['total']*100:>+7.1f}% MDD{m['mdd']*100:>5.0f}% 损{m['stops']:>3}".rjust(44))
        print(f'{f"-{dist}%":<10}' + ''.join(cells))
    print()

    # ---------------------------------------------------------------- 3 atr 网格
    print('=' * 118)
    print('3. atr 口径网格：SL 倍数 × TP R 倍数 —— 4h 偏移2 最多6根')
    print('=' * 118)
    print(f"{'SL':<8}" + ''.join(f'{f"TP={t}R":>44}' for t in ('关', 1, 2, 3, 4)))
    for sl in (1.5, 2.0, 2.5, 3.0, 4.0):
        cells = []
        for tp_r in (0, 1.0, 2.0, 3.0, 4.0):
            m = metrics(collect(s4, '4h', 2, 6, atr_cfg(sl, tp_r)))
            cells.append('—'.rjust(44) if not m else
                         f"{m['total']*100:>+7.1f}% MDD{m['mdd']*100:>5.0f}% 损{m['stops']:>3}".rjust(44))
        print(f'{str(sl) + "ATR":<8}' + ''.join(cells))
    print()

    # ---------------------------------------------------------------- 4 持有根数 + 样本内外
    print('=' * 118)
    print('4. 最大持有根数 × 样本内/外（前半调参、后半验证）—— 4h 偏移2')
    print('=' * 118)
    print(f"{'配置':<20}{'根数':>4}  {'全样本':>34}{'前半':>30}{'后半':>30}")
    for name, cfg in (('纯超时', cands['B 纯超时(不挂价单)']), ('percent -8%', pct_cfg(8, 0)),
                      ('atr 2/2R', atr_cfg(2.0, 2.0))):
        for bars in (4, 5, 6, 7, 8):
            df = collect(s4, '4h', 2, bars, cfg)
            a, b = split_halves(df) if len(df) else (None, None)
            m, m1, m2 = metrics(df), metrics(a), metrics(b)
            if not m:
                continue
            f = lambda x: (f"{x['total']*100:>+7.1f}%/MDD{x['mdd']*100:>4.0f}%/Sh{x['sharpe']:>4.2f}"
                           if x else '样本不足'.rjust(28))
            print(f'{name:<20}{bars:>4}  {f(m):>34}{f(m1):>30}{f(m2):>30}')
        print()

    # ---------------------------------------------------------------- 5 出场之外的优化轴
    print('=' * 118)
    print('5. 出场参数之外的优化轴（基准：4h 偏移2 纯超时 6 根）')
    print('=' * 118)
    base_df = collect(s4, '4h', 2, 6, cands['B 纯超时(不挂价单)'])
    print('   ' + line('基准', metrics(base_df)))

    for name, sub in (('只看多', base_df[base_df.direction == 'long']),
                      ('只看空', base_df[base_df.direction == 'short'])):
        print('   ' + line(name, metrics(sub)))

    print()
    print('   -- 按策略（同样 6 根纯超时）')
    for strat in sorted(base_df.strategy.unique()):
        print('   ' + line(strat, metrics(base_df[base_df.strategy == strat])))

    print()
    print('   -- 按信号 bar 的波动率分层（ATR/价格）')
    q = base_df.atr_pct.quantile([0.25, 0.5, 0.75]).to_numpy()
    labels = [f'Q1 <{q[0]*100:.2f}%', f'Q2 {q[0]*100:.2f}-{q[1]*100:.2f}%',
              f'Q3 {q[1]*100:.2f}-{q[2]*100:.2f}%', f'Q4 >{q[2]*100:.2f}%']
    edges = [-np.inf, q[0], q[1], q[2], np.inf]
    for lab, lo, hi in zip(labels, edges[:-1], edges[1:]):
        print('   ' + line(lab, metrics(base_df[(base_df.atr_pct > lo) & (base_df.atr_pct <= hi)])))

    print()
    print('   -- 全局并发上限（同时持仓数）')
    for limit in (2, 3, 4, 6, 8):
        print('   ' + line(f'最多 {limit} 个并发', metrics(cap_concurrency(base_df, limit))))

    print()
    print('   -- 组合：只做多 + 波动率过滤 + 并发上限')
    for lab, lo, hi in zip(labels, edges[:-1], edges[1:]):
        sub = base_df[(base_df.direction == 'long') &
                      (base_df.atr_pct > lo) & (base_df.atr_pct <= hi)]
        print('   ' + line(f'多 · {lab}', metrics(cap_concurrency(sub, 4))))

    # ---------------------------------------------------------------- 6 杠杆
    print()
    print('=' * 118)
    print('6. 实盘杠杆口径（每笔 10% 保证金，单笔亏损封顶于保证金，线性累加）')
    print('=' * 118)
    print(f"{'配置':<24}" + ''.join(f'{f"{L}x":>22}' for L in (1, 3, 5, 10, 20)))
    for name, df in (('A 现行 percent', collect(s4, '4h', 2, 6, BASE)),
                     ('B 纯超时', base_df),
                     ('D percent -8%', collect(s4, '4h', 2, 6, pct_cfg(8, 0)))):
        cells = []
        for L in (1, 3, 5, 10, 20):
            v = lever(df, 0.10, L)
            cells.append(f"{v['total']*100:>+7.0f}%/{v['mdd']*100:>5.0f}%/{v['liq']:>2}爆".rjust(22))
        print(f'{name:<24}' + ''.join(cells))
    print('（格式：总收益 / 最大回撤 / 单笔爆仓次数）')


if __name__ == '__main__':
    main()
