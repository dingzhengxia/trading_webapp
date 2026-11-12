"""出场口径的**收益回测**（组合视角，不是单笔统计）。

在 exit_modes.collect() 的逐笔明细上做资金曲线：
- 同一币持仓期间不重复开仓（实盘 auto_trader 的真实约束）；
- 每笔名义仓位 = 账户净值的 `weight`（默认 10%，8 币并发最多占 80%）；
- 收益按**实现时间（出场时间）**逐笔复利；
- 同时给「绝对收益」与「超额收益」两条曲线：后者每笔减掉同币同周期同持有期的无条件漂移，
  用于区分「策略 alpha」和「样本期行情 beta」。

输出：总收益 / 年化 / 最大回撤 / Calmar / Sharpe / 盈亏比 / 最大连亏 / 月度与币种拆分。
"""
import math
import sys

import numpy as np
import pandas as pd

import exit_modes
from exit_modes import COST_BP, MODES, collect, load_signals

COST = COST_BP / 1e4
WEIGHT = 0.10


def curve(df, weight=WEIGHT, excess=False):
    """按出场时间复利累计净值。返回 (net_curve_df, metrics)。"""
    if df is None or len(df) < 10:
        return None, None
    d = df.copy()
    d['net'] = d.ret - COST
    d['net_ex'] = d.ex - COST
    col = 'net_ex' if excess else 'net'
    d = d.sort_values('exit_ts').reset_index(drop=True)
    d['equity'] = (1 + weight * d[col]).cumprod()

    eq = d.equity.to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    days = (d.exit_ts.max() - d.entry_ts.min()) / 86400000
    years = max(days / 365, 1 / 365)
    total = eq[-1] - 1
    ann = (eq[-1]) ** (1 / years) - 1 if eq[-1] > 0 else -1.0
    per_trade = d[col].to_numpy()
    sd = per_trade.std(ddof=1)
    sharpe = (per_trade.mean() / sd * math.sqrt(len(per_trade) / years)) if sd else 0.0

    win = per_trade[per_trade > 0]
    loss = per_trade[per_trade < 0]
    pf = win.sum() / abs(loss.sum()) if len(loss) and loss.sum() != 0 else float('inf')
    payoff = (win.mean() / abs(loss.mean())) if len(loss) and len(win) else 0.0

    streak = worst = 0
    for x in per_trade:
        streak = streak + 1 if x < 0 else 0
        worst = max(worst, streak)

    # 并发占用：按 entry/exit 扫描
    events = sorted([(r.entry_ts, 1) for r in d.itertuples()] + [(r.exit_ts, -1) for r in d.itertuples()])
    cur = peak_conc = 0
    for _, delta in events:
        cur += delta
        peak_conc = max(peak_conc, cur)

    metrics = {
        'n': len(d), 'days': days, 'total': total, 'ann': ann,
        'mdd': float(dd.min()), 'calmar': ann / abs(float(dd.min())) if dd.min() < 0 else float('nan'),
        'sharpe': sharpe, 'win': float((per_trade > 0).mean()),
        'pf': pf, 'payoff': payoff, 'max_loss_streak': worst,
        'avg_win_bp': win.mean() * 1e4 if len(win) else 0.0,
        'avg_loss_bp': loss.mean() * 1e4 if len(loss) else 0.0,
        'peak_concurrent': peak_conc,
        'exposure': float((d.bars * d.tf.map({'1h': 1 / 24, '4h': 1 / 6})).sum() / max(days, 1) / 8),
    }
    return d, metrics


def fmt(m):
    if not m:
        return '样本不足'
    return (f"{m['n']:>4}笔 {m['total']*100:>+7.1f}% 年化{m['ann']*100:>+7.1f}% "
            f"MDD{m['mdd']*100:>6.1f}% Sh{m['sharpe']:>5.2f} PF{m['pf']:>4.2f} "
            f"连亏{m['max_loss_streak']:>2}")


def lever(df, margin=0.10, lev=20):
    """实盘杠杆口径：每笔投入 `margin` 比例保证金的固定金额，价格反向超过
    100% 保证金即视为爆仓（单笔亏损封顶 = margin），收益线性累加（不滚仓，
    因为爆仓后账户事实归零，复利没有意义）。
    """
    if df is None or len(df) < 10:
        return None
    d = df.sort_values('exit_ts').reset_index(drop=True)
    net = d.ret.to_numpy() - COST
    pnl = np.clip(margin * lev * net, -margin, None)
    equity = 1 + np.cumsum(pnl)
    dd = (equity / np.maximum.accumulate(equity) - 1).min()
    years = max((d.exit_ts.max() - d.entry_ts.min()) / 86400000 / 365, 1 / 365)
    return {'total': equity[-1] - 1, 'ann': (equity[-1] - 1) / years, 'mdd': dd,
            'liq': int((margin * lev * net <= -margin + 1e-12).sum())}


def main():
    sig_all = load_signals()
    out = []
    print(f"每笔名义 {WEIGHT*100:.0f}% 净值，往返成本 {COST_BP:.0f}bp，同币不重复开仓\n")

    for tf, max_bars in (('4h', 6), ('1h', 12)):
        sig = sig_all[sig_all.tf == tf]
        for offset in (1, 2):
            print(f"===== {tf} · 入场偏移 {offset} · 最大持有 {max_bars} 根 =====")
            for name, config in MODES.items():
                df = collect(sig, tf, offset, max_bars, config)
                d_abs, m_abs = curve(df, excess=False)
                _, m_ex = curve(df, excess=True)
                if m_abs:
                    print(f"  {name:<16} 绝对 {fmt(m_abs)}")
                    print(f"  {'':<16} 超额 {fmt(m_ex)}")
                    reasons = df.reason.value_counts().to_dict()
                    out.append({'tf': tf, 'offset': offset, 'mode': name,
                                'abs_total': m_abs['total'], 'abs_ann': m_abs['ann'], 'abs_mdd': m_abs['mdd'],
                                'ex_total': m_ex['total'], 'ex_ann': m_ex['ann'], 'ex_mdd': m_ex['mdd'],
                                'sharpe': m_abs['sharpe'], 'pf': m_abs['pf'], 'n': m_abs['n'],
                                'peak_concurrent': m_abs['peak_concurrent'],
                                'stops': reasons.get('stop', 0), 'targets': reasons.get('target', 0),
                                'times': reasons.get('time', 0)})
            print()
    pd.DataFrame(out).to_csv('pnl_summary.csv', index=False)

    # ---- 实盘杠杆口径：每笔 10% 保证金 × L 倍，爆仓按 100% 保证金计 ----
    for tf, max_bars in (('4h', 6), ('1h', 12)):
        sig = sig_all[sig_all.tf == tf]
        print(f"===== {tf} · 偏移2 · 实盘杠杆口径（每笔 10% 保证金，线性累加）=====")
        print(f"{'口径':<16}" + ''.join(f'{f"{L}x":>20}' for L in (1, 5, 10, 20)))
        for name, config in MODES.items():
            df = collect(sig, tf, 2, max_bars, config)
            if df is None or len(df) < 10:
                continue
            cells = []
            for L in (1, 5, 10, 20):
                m = lever(df, 0.10, L)
                cells.append(f"{m['total']*100:>+7.0f}%/{m['mdd']*100:>5.0f}%/{m['liq']:>2}爆")
            print(f'{name:<16}' + ''.join(c.rjust(20) for c in cells))
        print('  （格式：总收益 / 最大回撤 / 单笔爆仓次数）\n')

    # ---- 名义仓位对收益与回撤的放大（4h 偏移2） ----
    sig4 = sig_all[sig_all.tf == '4h']
    print('===== 4h · 偏移2 · 名义仓位敏感性（现货口径，总收益 / MDD）=====')
    print(f"{'口径':<16}" + ''.join(f'{f"{int(w*100)}%名义":>20}' for w in (0.1, 0.25, 0.5, 1.0)))
    for name, config in MODES.items():
        df = collect(sig4, '4h', 2, 6, config)
        if df is None or len(df) < 10:
            continue
        cells = []
        for w in (0.1, 0.25, 0.5, 1.0):
            _, m = curve(df, weight=w)
            cells.append(f"{m['total']*100:>+7.0f}%/{m['mdd']*100:>6.0f}%")
        print(f'{name:<16}' + ''.join(c.rjust(20) for c in cells))
    print()

    # ---- 4h / offset=2 的四口径净值曲线（用户最关心的一组） ----
    sig4 = sig_all[sig_all.tf == '4h']
    print('===== 4h · 偏移2 净值曲线（每 10% 时间采样，起点 1.000）=====')
    curves = {}
    for name, config in MODES.items():
        d, _ = curve(collect(sig4, '4h', 2, 6, config), excess=True)
        if d is not None:
            curves[name] = d
    if curves:
        marks = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        print(f"{'进度':>5} " + ' '.join(f'{k:>16}' for k in curves))
        for mk in marks:
            cells = []
            for name, d in curves.items():
                pos = min(int(mk * (len(d) - 1)), len(d) - 1)
                cells.append(f"{d.equity.iloc[pos]:>16.3f}")
            print(f"{mk*100:>4.0f}% " + ' '.join(cells))

    # ---- 稳定性拆分：4h / 偏移2 / 四口径 ----
    for name, config in MODES.items():
        df = collect(sig4, '4h', 2, 6, config)
        if df is None or len(df) < 10:
            continue
        df = df.copy()
        df['net'] = df.ret - COST
        df['month'] = pd.to_datetime(df.exit_ts, unit='ms').dt.strftime('%m月')
        print(f"\n===== 稳定性：4h·偏移2·{name} =====")
        by_month = df.groupby('month').net.agg(['count', 'sum']).sort_index()
        print('按月  ' + '  '.join(f"{m}:{int(r['count'])}笔{r['sum']*100:+.1f}%" for m, r in by_month.iterrows()))
        by_sym = df.groupby('symbol').net.agg(['count', 'sum', 'mean'])
        print('按币  ' + '  '.join(f"{s}:{r['sum']*100:+.1f}%" for s, r in by_sym.iterrows()))
        by_dir = df.groupby('direction').net.agg(['count', 'sum'])
        print('按方向 ' + '  '.join(f"{k}:{int(r['count'])}笔{r['sum']*100:+.1f}%" for k, r in by_dir.iterrows()))
        print(f"月胜率 {(by_month['sum'] > 0).mean()*100:.0f}%  币胜率 {(by_sym['sum'] > 0).mean()*100:.0f}%")


if __name__ == '__main__':
    main()
