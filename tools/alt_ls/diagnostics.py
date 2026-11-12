"""稳健性诊断：收益是不是只来自 2025 年那一段、资金费方向、成本敏感性与尾部。"""
import numpy as np
import pandas as pd

from backtest import Cfg, load, run, stats

HALVES = [('2024-11', '2025-04'), ('2025-05', '2025-10'),
          ('2025-11', '2026-04'), ('2026-05', '2026-10')]


def seg(navs, a, b):
    s = navs.loc[a:b]
    return float(s.iloc[-1] / s.iloc[0] - 1) * 100 if len(s) > 5 else np.nan


def main():
    close, volq, funding, first_fr = load()
    btc = close['BTCUSDT'].pct_change(fill_method=None)

    print('=' * 100)
    print('1) 分半年收益（%）：收益是否只集中在某一段')
    print('=' * 100)
    print(f"{'配置':<28}" + ''.join(f'{f"{a}~{b}":>18}' for a, b in HALVES))
    for mode, label in (('ls', '多主流/空小币'), ('long_maj', '只多主流'), ('short_alt', '只空小币')):
        for n in (50, 100):
            cfg = Cfg(mode=mode, n_short=n, gross=1.0, rebal='M', weight='equal', cost_bp=5.0)
            navs, legs, _ = run(close, volq, funding, first_fr, cfg)
            print(f'{label + f" N={n}":<28}' + ''.join(f'{seg(navs, a, b):>+18.1f}' for a, b in HALVES))

    print('\n' + '=' * 100)
    print('2) 资金费：做空小币到底是收钱还是付钱')
    print('=' * 100)
    fr = funding.copy()
    fr = fr.loc[:, [c for c in fr.columns if c not in ('BTCUSDT', 'ETHUSDT')]]
    tot = fr.replace(0, np.nan)
    print(f'小币资金费率（每次结算）：全样本均值 {tot.stack().mean()*100:+.4f}%  '
          f'年化 ≈ {tot.stack().mean()*3*365*100:+.1f}%')
    for y, g in fr.groupby(fr.index.year):
        v = g.replace(0, np.nan).stack()
        print(f'  {y}: 均值 {v.mean()*100:+.4f}%/次  ≈ {v.mean()*3*365*100:+.1f}%/年  '
              f'正费率占比 {(v > 0).mean()*100:.1f}%')
    per = tot.replace(0, np.nan).mean()
    print(f'  按币：正费率币 {int((per > 0).sum())} 个 / 负费率币 {int((per < 0).sum())} 个')
    print(f'  最负 5 个: ' + ', '.join(f'{s[:-4]} {v*3*365*100:+.1f}%' for s, v in per.nsmallest(5).items()))
    print(f'  最正 5 个: ' + ', '.join(f'{s[:-4]} {v*3*365*100:+.1f}%' for s, v in per.nlargest(5).items()))

    print('\n' + '=' * 100)
    print('3) 资金费开关与成本敏感性（N=50 等权，年化 %）')
    print('=' * 100)
    print(f"{'场景':<26}{'总收益':>10}{'年化':>9}{'波动':>8}{'Sharpe':>8}{'回撤':>9}")
    base = None
    for tag, cost, usefr in (('基准（5bp，含资金费）', 5.0, True), ('成本 10bp', 10.0, True),
                             ('成本 20bp', 20.0, True), ('不计资金费', 5.0, False)):
        cfg = Cfg(mode='ls', n_short=50, gross=1.0, rebal='M', weight='equal', cost_bp=cost)
        navs, legs, _ = run(close, volq, funding, first_fr, cfg, use_funding=usefr)
        s = stats(navs, legs, tag, btc)
        print(f"{tag:<26}{s['total']*100:>+9.1f}%{s['ann']*100:>+8.1f}%{s['vol']*100:>7.1f}%"
              f"{s['sharpe']:>8.2f}{s['mdd']*100:>8.1f}%")

    print('\n' + '=' * 100)
    print('4) 杠杆敏感性（总名义 / 净值）')
    print('=' * 100)
    print(f"{'总名义':<10}{'总收益':>10}{'年化':>9}{'波动':>8}{'Sharpe':>8}{'回撤':>9}{'最差5天之和':>13}")
    for g in (0.5, 1.0, 1.5, 2.0, 3.0):
        cfg = Cfg(mode='ls', n_short=50, gross=g, rebal='M', weight='equal', cost_bp=5.0)
        navs, legs, _ = run(close, volq, funding, first_fr, cfg)
        s = stats(navs, legs, f'{g:g}x', btc)
        r = navs.pct_change(fill_method=None).dropna()
        print(f"{g:<10.1f}{s['total']*100:>+9.1f}%{s['ann']*100:>+8.1f}%{s['vol']*100:>7.1f}%"
              f"{s['sharpe']:>8.2f}{s['mdd']*100:>8.1f}%{r.nsmallest(5).sum()*100:>12.1f}%")

    print('\n' + '=' * 100)
    print('5) 空头腿数量与调仓频率')
    print('=' * 100)
    print(f"{'空头币数/调仓':<16}{'总收益':>10}{'年化':>9}{'波动':>8}{'Sharpe':>8}{'回撤':>9}{'换手/年':>9}")
    for n in (20, 50, 100):
        for rb in ('M', 'W'):
            cfg = Cfg(mode='ls', n_short=n, gross=1.0, rebal=rb, weight='equal', cost_bp=5.0)
            navs, legs, extra = run(close, volq, funding, first_fr, cfg)
            s = stats(navs, legs, f'{n}/{rb}', btc)
            print(f"{f'{n} 币 / {rb}':<16}{s['total']*100:>+9.1f}%{s['ann']*100:>+8.1f}%{s['vol']*100:>7.1f}%"
                  f"{s['sharpe']:>8.2f}{s['mdd']*100:>8.1f}%{extra['turnover']/(len(navs)/365):>8.1f}x")


if __name__ == '__main__':
    main()
