"""用生产策略代码回放历史K线，统计信号的前视收益（离线、无未来函数）。"""
import json, sys, math, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 仓库根（本文件在 tools/strategy_probe/）
sys.path.insert(0, str(ROOT / 'backend'))
import pandas as pd
from loguru import logger
logger.remove()

from app.signals.analysis import strategies
from app.signals.analysis.indicators import is_realtime_volume_over, get_dynamic_volume_multiplier
from app.signals.analysis.trend import timeframe_to_minutes

CONFIG = json.load(open(ROOT / 'signal_config.json', encoding='utf-8'))
LIMITS = {'ema_cross': 170, 'ma_breakout': 150, 'kdj_cross': 170, 'volatility_breakout': 170,
          'level_breakout': 400, 'rsi_divergence': 170, 'trend_channel_breakout': 350,
          'consecutive_candles': 50, 'ob_luxalgo': 250, 'ob_fluxcharts': 250}
FUNCS = {'ema_cross': strategies.check_ema_signals, 'ma_breakout': strategies.check_ma_breakout,
         'level_breakout': strategies.check_level_breakout, 'rsi_divergence': strategies.check_rsi_divergence,
         'trend_channel_breakout': strategies.check_trend_channel_breakout,
         'consecutive_candles': strategies.check_consecutive_candles,
         'ob_luxalgo': strategies.check_ob_luxalgo, 'ob_fluxcharts': strategies.check_ob_fluxcharts,
         'kdj_cross': strategies.check_kdj_cross}

RECORDS = []


def _sink(config, symbol, timeframe, df, info):
    if df is None:
        return
    if info.get('volume_must_confirm'):
        mult = get_dynamic_volume_multiplier(symbol, config, info.get('fallback_multiplier', 1.5))
        ok, _, _ = is_realtime_volume_over(df, timeframe_to_minutes(timeframe), 20, mult)
        if not ok:
            return
    RECORDS.append({'symbol': symbol, 'tf': timeframe, 'ts': int(df.iloc[-1]['timestamp']),
                    'strategy': info.get('strategy_name'), 'direction': info.get('direction'),
                    'price': float(df.iloc[-1]['close'])})


def enabled_sets(config, tf):
    out = []
    for name, func in FUNCS.items():
        raw = config['strategy_params'].get(name, {})
        for idx, base in enumerate(raw if isinstance(raw, list) else [raw]):
            if not isinstance(base, dict) or not base.get('enabled'):
                continue
            params = base.copy()
            params.update(base.get('overrides_by_timeframe', {}).get(tf, {}))
            if tf in params.get('exclude_timeframes', []):
                continue
            out.append((name, func, params, idx, LIMITS[name]))
    return out


def replay(symbol, tf, bars, config, warmup=420, horizons=(1, 4, 12)):
    df = pd.DataFrame(json.load(open(f'data/{symbol}_{tf}.json')), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df = df.iloc[-bars:].reset_index(drop=True)
    strategies._prepare_and_send_notification = _sink
    sets = enabled_sets(config, tf)
    last = len(df) - max(horizons) - 1
    for t in range(min(warmup, len(df) // 2), last):
        for name, func, params, idx, limit in sets:
            sub = df.iloc[max(0, t + 1 - limit):t + 1].reset_index(drop=True)
            try:
                func(symbol, tf, config, sub, params, idx)
            except Exception as e:
                pass
    # 前视收益
    rows = []
    for r in RECORDS:
        i = int(r['ts'] // (df.timestamp.iloc[1] - df.timestamp.iloc[0]) * 0 + 0) if False else None
    ts_index = {int(v): i for i, v in enumerate(df['timestamp'])}
    for r in RECORDS:
        i = ts_index.get(r['ts'])
        if i is None or i + 1 >= len(df):
            continue
        entry = float(df['open'].iloc[i + 1])
        for h in horizons:
            if i + h >= len(df):
                continue
            exit_px = float(df['close'].iloc[i + h])
            ret = (exit_px - entry) / entry
            rows.append({'symbol': r['symbol'], 'tf': tf, 'ts': r['ts'], 'strategy': r['strategy'], 'direction': r['direction'],
                         'h': h, 'ret': ret if r['direction'] == 'long' else (-ret if r['direction'] == 'short' else 0.0),
                         'neutral': r['direction'] == 'neutral'})
    return pd.DataFrame(rows), df


def baseline(df, horizons):
    out = {}
    for h in horizons:
        rets = (df['close'].shift(-h) - df['open'].shift(-1)) / df['open'].shift(-1)
        out[h] = float(rets.dropna().mean())
    return out


def variant_config(name):
    cfg = json.loads(json.dumps(CONFIG))
    if name == 'voloff':
        for v in cfg['strategy_params'].values():
            for item in (v if isinstance(v, list) else [v]):
                if isinstance(item, dict):
                    item['volume_confirm'] = False
    elif name == 'ma7':
        cfg['strategy_params']['ma_breakout']['ma_periods'] = [7, 25, 99]
    elif name == 'ema05':
        cfg['strategy_params']['ema_cross']['atr_multiplier'] = 0.5
    elif name == 'levelvol':
        cfg['strategy_params']['level_breakout']['volume_confirm'] = True
        cfg['strategy_params']['level_breakout']['volume_multiplier'] = 1.5
    return cfg


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='1h')
    ap.add_argument('--bars', type=int, default=1500)
    ap.add_argument('--symbols', default='BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT')
    ap.add_argument('--variant', default='base')
    ap.add_argument('--dump', default='')
    a = ap.parse_args()
    cfg = variant_config(a.variant)
    frames, bases = [], {}
    for sym in a.symbols.split(','):
        rec = RECORDS
        rec.clear()
        hz = (1, 4, 12) if a.tf == '1h' else (1, 3, 6)
        out, df = replay(f'{sym}USDT' if not sym.endswith('USDT') else sym, a.tf, a.bars, cfg, horizons=hz)
        frames.append(out)
        bases[sym] = baseline(df, hz)
        print(f'{sym} raw signals: {len(rec)}', file=sys.stderr)
    allr = pd.concat(frames, ignore_index=True)
    out_csv = a.dump or f'res_{a.tf}_{a.variant}_{a.symbols.replace(",", "-")}.csv'
    allr.to_csv(out_csv, index=False)
    json.dump(bases, open(out_csv.replace('.csv', '_base.json'), 'w'))
    print(out_csv, len(allr))
