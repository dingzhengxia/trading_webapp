"""主配置的详细报告：月度收益、多空腿分解、资金费与成本、稳健性检验。

关注三个问题：
1. 收益是否集中在少数几个月（若如此，则是一次性行情而非可复利的能力）；
2. 收益来自「小币下跌」这个 beta，还是来自「小币相对主流币更弱」这个横截面 alpha；
3. 极端行情下的回撤与尾部。
"""
import numpy as np
import pandas as pd

from backtest import Cfg, load, run, stats, TRADING_DAYS

pd.set_option('display.width', 200)


def month_table(navs):
    m = navs.resample('ME').last()
    first = navs.iloc[0]
    rets = m.pct_change()
    rets.iloc[0] = m.iloc[0] / first - 1
    out = pd.DataFrame({'月收益': rets * 100})
    out.index = out.index.strftime('%Y-%m')
    return out


def yearly(navs):
    y = navs.resample('YE').last()
    firsts = pd.concat([pd.Series([navs.iloc[0]]), y.shift(1).dropna()])
    firsts.index = y.index
    return ((y / firsts - 1) * 100)


def main():
    close, volq, funding, first_fr = load()
    btc = close['BTCUSDT'].pct_change(fill_method=None)

    for n in (50, 100):
        for w in ('equal', 'invvol'):
            cfg = Cfg(mode='ls', n_short=n, gross=1.0, rebal='M', weight=w, cost_bp=5.0)
            navs, legs, extra = run(close, volq, funding, first_fr, cfg)
            s = stats(navs, legs, f'N={n} {w}', btc)
            print(f"\n{'=' * 92}")
            print(f"多 BTC/ETH(各半) · 空 {n} 小币等权 · 月度调仓 · 总名义 1x · 成本 5bp · 权重 {w}")
            print('=' * 92)
            print(f"总收益 {s['total']*100:+.1f}%  年化 {s['ann']*100:+.1f}%  "
                  f"波动 {s['vol']*100:.1f}%  Sharpe {s['sharpe']:.2f}  回撤 {s['mdd']*100:.1f}%")
            print(f"beta(BTC) {s['beta']:+.2f}  年化alpha {s['alpha_ann']*100:+.1f}%  "
                  f"相关系数 {s['corr']:+.2f}  日胜率 {s['win_d']*100:.1f}%")
            print(f"腿贡献：多头 {legs.long.sum()*100:+.1f}%  空头 {legs.short.sum()*100:+.1f}%  "
                  f"资金费 {legs.funding.sum()*100:+.1f}%  成本 {-legs.cost.sum()*100:+.1f}%")
            print(f"换手 {extra['turnover']:.1f}x（累计名义/净值，{extra['turnover']/(len(navs)/365):.1f}x/年）")
            print('\n月度收益 %:')
            print('  ' + '  '.join(f'{i}:{v:+.1f}' for i, v in month_table(navs)['月收益'].items()))
            print('分年 %: ' + '  '.join(f'{i.year}:{v:+.1f}' for i, v in yearly(navs).items()))

            if n == 50 and w == 'equal':
                navs.to_csv('nav_main.csv', header=['nav'])
                legs.to_csv('legs_main.csv')


if __name__ == '__main__':
    main()
