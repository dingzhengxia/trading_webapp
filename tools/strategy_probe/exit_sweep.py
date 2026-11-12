"""出场参数扫描：在 4h/偏移2 这一有效组合上，找「既有风险兜底又不伤收益」的出场。
复用 exit_modes.collect()（生产代码路径），不重复实现任何出场逻辑。
"""
import pandas as pd

from exit_modes import collect, load_signals
from exit_pnl import curve, fmt

BASE = {'enable_long_sl_tp': True, 'enable_short_sl_tp': True, 'leverage': 20,
        'long_stop_loss_percentage': 300, 'long_take_profit_percentage': 600,
        'short_stop_loss_percentage': 200, 'short_take_profit_percentage': 300}

CONFIGS = {
    'D time-only': {},
    'E atr 2.0/2R': {'signal_exit_mode': 'atr', 'signal_paper_sl_atr': 2.0, 'signal_paper_tp_r': 2.0},
    'F atr 3.0/2R': {'signal_exit_mode': 'atr', 'signal_paper_sl_atr': 3.0, 'signal_paper_tp_r': 2.0},
    'G atr 3.0/3R': {'signal_exit_mode': 'atr', 'signal_paper_sl_atr': 3.0, 'signal_paper_tp_r': 3.0},
    'H atr 4.0/3R': {'signal_exit_mode': 'atr', 'signal_paper_sl_atr': 4.0, 'signal_paper_tp_r': 3.0},
}


def main():
    sig_all = load_signals()
    sig4 = sig_all[sig_all.tf == '4h']
    print('===== 4h · 偏移2 · 出场参数扫描（每笔 10% 净值，扣 8bp）=====')
    for bars in (4, 6, 8):
        print(f'-- 最大持有 {bars} 根')
        for name, cfg in CONFIGS.items():
            config = dict(BASE, **cfg) if cfg else {'enable_long_sl_tp': False, 'enable_short_sl_tp': False}
            df = collect(sig4, '4h', 2, bars, config)
            _, m = curve(df)
            if m is None:
                print(f'  {name:<14} 样本不足')
                continue
            r = df.reason.value_counts().to_dict()
            print(f"  {name:<14} {fmt(m)}  止损{r.get('stop',0):>3} 止盈{r.get('target',0):>3} 超时{r.get('time',0):>4}")

    # 最优候选的方向/月度稳定性
    for name, bars in (('F atr 3.0/2R', 6), ('D time-only', 6)):
        config = dict(BASE, **CONFIGS[name]) if CONFIGS[name] else {'enable_long_sl_tp': False,
                                                                    'enable_short_sl_tp': False}
        df = collect(sig4, '4h', 2, bars, config).copy()
        df['net'] = df.ret - 8e-4
        df['month'] = pd.to_datetime(df.exit_ts, unit='ms').dt.strftime('%m月')
        bm = df.groupby('month').net.agg(['count', 'sum']).sort_index()
        bs = df.groupby('symbol').net.agg(['count', 'sum'])
        bd = df.groupby('direction').net.agg(['count', 'sum'])
        print(f"\n== {name} ==  月胜率 {(bm['sum']>0).mean()*100:.0f}% 币胜率 {(bs['sum']>0).mean()*100:.0f}%")
        print('  按月 ' + ' '.join(f"{m}:{r['sum']*100:+.0f}%" for m, r in bm.iterrows()))
        print('  按币 ' + ' '.join(f"{s[:3]}:{r['sum']*100:+.0f}%" for s, r in bs.iterrows()))
        print('  方向 ' + ' '.join(f"{k}:{r['sum']*100:+.0f}%" for k, r in bd.iterrows()))


if __name__ == '__main__':
    main()
