"""出场规则回测的**逐笔数据层**：用生产代码（core.exit_rules + signals.outcomes）跑出场。

口径（可被 exit_pnl.py 直接复用，不重复实现）：
1. 入场 = 信号 bar 之后第 `offset` 根的开盘价（offset=1 即"信号后立即"）；
2. 止损/止盈由生产代码 `exit_rules.exit_prices()` 算出，与实盘挂单同一份逻辑；
3. 出场由生产代码 `outcomes.simulate_exit()` 逐根判定（同根同触止损优先、跳空按开盘价）；
4. `dedupe=True` 时模拟实盘约束：**同一币在持仓期间不重复开新仓**（auto_trader 的真实规则）。

四种口径：
A. percent-live ：当前实盘设置（leverage 20，long 300%/600%，short 200%/300%）
B. percent-tight：同机制收紧（long 50%/100%，short 80%/150%）
C. atr          ：1.5 ATR 止损 / 2R 止盈
D. time-only    ：不挂价格单，只按 max_bars 超时平仓
"""
import json
import math
import sys

import numpy as np
import pandas as pd

from logic_test import series

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'backend'))
from app.core import exit_rules           # noqa: E402
from app.signals import outcomes          # noqa: E402

COST_BP = 8.0
LEVERAGE = 20

MODES = {
    'A percent-live': {'signal_exit_mode': 'percent', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
                       'leverage': LEVERAGE, 'long_stop_loss_percentage': 300, 'long_take_profit_percentage': 600,
                       'short_stop_loss_percentage': 200, 'short_take_profit_percentage': 300},
    'B percent-tight': {'signal_exit_mode': 'percent', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
                        'leverage': LEVERAGE, 'long_stop_loss_percentage': 50, 'long_take_profit_percentage': 100,
                        'short_stop_loss_percentage': 80, 'short_take_profit_percentage': 150},
    'C atr 1.5/2R': {'signal_exit_mode': 'atr', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
                     'signal_paper_sl_atr': 1.5, 'signal_paper_tp_r': 2.0},
    'D time-only': {'enable_long_sl_tp': False, 'enable_short_sl_tp': False},
}

FRAMES = {}


def frame(symbol, tf):
    key = (symbol, tf)
    if key not in FRAMES:
        FRAMES[key] = outcomes.to_frame(json.load(open(f'data/{symbol}_{tf}.json')))
    return FRAMES[key]


def load_signals(path='res_wide.csv'):
    sig = pd.read_csv(path)
    return sig[sig.direction.isin(['long', 'short'])].sort_values('ts').reset_index(drop=True)


def collect(sig, tf, offset, max_bars, config, dedupe=True):
    """跑出逐笔明细 DataFrame。

    列：symbol/tf/strategy/direction/entry_ts/exit_ts/entry/exit_price/bars/reason/ret/drift/ex
    `ret` 为方向性价格收益（未扣成本），`ex` = ret − 无条件漂移（超额，未扣成本）。
    """
    rows = []
    for r in sig.itertuples():
        s = series(r.symbol, r.tf)
        i = s.index.get(int(r.ts))
        if i is None or i + offset >= len(s.close):
            continue
        entry = float(s.open[i + offset])
        if entry <= 0:
            continue
        prices = exit_rules.exit_prices(entry, r.direction, config, atr=_atr(s, i))
        result = outcomes.simulate_exit(
            frame(r.symbol, r.tf), i + offset - 1, r.direction, entry,
            prices['stop_loss'] if prices else None,
            prices['take_profit'] if prices else None,
            max_bars)
        if result is None:
            continue
        sign = 1 if r.direction == 'long' else -1
        ret = sign * (float(result['exit_price']) / entry - 1)
        atr = _atr(s, i)
        rows.append({
            'symbol': r.symbol, 'tf': r.tf, 'strategy': r.strategy, 'direction': r.direction,
            'entry_ts': int(s.ts[i + offset]), 'exit_ts': int(result['exit_ts']),
            'entry': entry, 'exit_price': float(result['exit_price']),
            'bars': int(result['bars_held']), 'reason': result['reason'],
            'ret': ret, 'drift': s.drift(sign, offset, int(result['bars_held'])),
            'ex': ret - s.drift(sign, offset, int(result['bars_held'])),
            # 信号 bar 的波动率（占价格比例），用于「按波动率分层」这类优化实验
            'atr_pct': (atr / entry) if atr else np.nan,
        })
    df = pd.DataFrame(rows, columns=['symbol', 'tf', 'strategy', 'direction', 'entry_ts', 'exit_ts',
                                     'entry', 'exit_price', 'bars', 'reason', 'ret', 'drift', 'ex',
                                     'atr_pct'])
    if dedupe and len(df):
        df = df.sort_values('entry_ts')
        occupied, keep = {}, []
        for idx, rec in zip(df.index, df.itertuples()):
            if rec.entry_ts < occupied.get(rec.symbol, -1):
                continue
            occupied[rec.symbol] = rec.exit_ts
            keep.append(idx)
        df = df.loc[keep]
    return df.sort_values('entry_ts').reset_index(drop=True)


def _atr(s, i):
    value = float(s.atr[i])
    return None if math.isnan(value) or value <= 0 else value


def summary(df):
    """单笔层面的统计（超额 bp / t / 胜率 / 均持 / 出场分布）。"""
    if df is None or len(df) < 10:
        return None
    arr = df.ex.to_numpy()
    m = arr.mean() * 1e4
    sd = arr.std(ddof=1)
    return {
        'n': len(arr), 'ex_bp': m, 'net_bp': m - COST_BP,
        't': m / (sd * 1e4 / math.sqrt(len(arr))) if sd else 0.0,
        'hit': (df.ret > 0).mean() * 100,
        'bars': float(df.bars.mean()),
        'reasons': df.reason.value_counts().to_dict(),
    }


def main():
    sig_all = load_signals()
    for tf, max_bars in (('4h', 6), ('1h', 12)):
        sig = sig_all[sig_all.tf == tf]
        print(f"\n===== {tf}（最大持有 {max_bars} 根，信号 {len(sig)} 条，同币不重复开仓）=====")
        for offset in (1, 2):
            print(f"-- 入场偏移 {offset}（{'信号后立即' if offset == 1 else '等一根后'}）")
            print(f"{'口径':<18} {'样本':>5} {'超额':>8} {'净':>8} {'t':>6} {'胜率':>6} {'均持':>5}  出场分布")
            for name, config in MODES.items():
                r = summary(collect(sig, tf, offset, max_bars, config))
                if r is None:
                    print(f'{name:<18} 样本不足')
                    continue
                mix = ' '.join(f'{k}:{v}' for k, v in sorted(r['reasons'].items()))
                print(f"{name:<18} {r['n']:>5} {r['ex_bp']:>+8.1f} {r['net_bp']:>+8.1f} "
                      f"{r['t']:>+6.1f} {r['hit']:>5.1f}% {r['bars']:>5.1f}  {mix}")


if __name__ == '__main__':
    main()
