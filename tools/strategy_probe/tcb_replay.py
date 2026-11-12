"""只回放 trend_channel_breakout 的两组参数，产出 tcb_signals.csv。

为什么单独重跑：
1. res_wide.csv 没存 strategy_index，TCB 的两组参数（短期 std1.5 / 长期 std1.8）
   被混在一起算平均，无法判断哪一组贡献了 +11.3bp；
2. 需要 volume_ratio（信号 bar 的量能倍数）做二次筛选实验；
3. 只启用 TCB，回放速度远快于全策略。

口径与 bt.replay 完全一致：逐 bar 截断（无未来数据）、入场取次根开盘、warmup 420。
"""
import json
import multiprocessing as mp
import time
from pathlib import Path

import pandas as pd

import bt

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
           "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")
PLAN = {"1h": (4000, 24), "4h": (1500, 6)}  # 两者持有上限都对齐到 24 小时

RECS = []


def make_sink(store):
    def sink(config, symbol, timeframe, df, info):
        if df is None:
            return
        ratio = None
        if info.get('volume_must_confirm'):
            from app.signals.analysis.indicators import is_realtime_volume_over
            from app.signals.analysis.trend import timeframe_to_minutes
            from app.signals.analysis.indicators import get_dynamic_volume_multiplier
            mult = get_dynamic_volume_multiplier(symbol, config, info.get('fallback_multiplier', 1.5))
            _, _, ratio = is_realtime_volume_over(df, timeframe_to_minutes(timeframe), 20, mult)
        atr = None
        if 'ATRr_14' in df.columns:
            atr = float(df['ATRr_14'].iloc[-1])
        store.append({
            'symbol': symbol, 'tf': timeframe, 'ts': int(df.iloc[-1]['timestamp']),
            'strategy_index': int(info.get('strategy_index', 0)),
            'direction': info.get('direction'),
            'close': float(df.iloc[-1]['close']),
            'volume_ratio': ratio,
            'atr': atr,
        })
    return sink


def tcb_only_config():
    cfg = json.loads(json.dumps(bt.CONFIG))
    for name in list(cfg['strategy_params'].keys()):
        if name != 'trend_channel_breakout':
            raw = cfg['strategy_params'][name]
            for item in (raw if isinstance(raw, list) else [raw]):
                if isinstance(item, dict):
                    item['enabled'] = False
    return cfg


def task(args):
    sym, tf, bars, _ = args
    store = []
    bt._sink = make_sink(store)
    out, _ = bt.replay(sym, tf, bars, tcb_only_config(), horizons=(1,))
    return pd.DataFrame(store)


if __name__ == '__main__':
    tasks = [(s, tf, bars, hz) for tf, (bars, hz) in PLAN.items() for s in SYMBOLS]
    t0 = time.time()
    with mp.Pool(4) as pool:
        frames = pool.map(task, tasks)
    df = pd.concat(frames, ignore_index=True)
    df.to_csv('tcb_signals.csv', index=False)
    print('rows', len(df), f'{time.time() - t0:.0f}s')
    print(df.groupby(['tf', 'strategy_index', 'direction']).size())
