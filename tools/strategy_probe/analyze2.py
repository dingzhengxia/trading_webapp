import json, math
import pandas as pd, numpy as np
df = pd.read_csv('res_base.csv')
base = json.load(open('res_base_baselines.json'))

df = df[df['direction'] != 'neutral'].copy()
df['base_s'] = [base[f'{v}|{t}|{s}'][str(int(h))] * (1 if d == 'long' else -1)
                for v, t, s, h, d in zip(df.variant, df.tf, df.symbol, df.h, df.direction)]
df['ex'] = df['ret'] - df['base_s']

# 趋势对齐：信号发生时的收盘价 vs 同周期 EMA200
align = {}
for tf in ('1h', '4h'):
    for sym in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'):
        d = pd.DataFrame(json.load(open(f'data/{sym}_{tf}.json')),
                         columns=['timestamp','open','high','low','close','volume'])
        ema = d['close'].ewm(span=200, adjust=False).mean()
        for ts, c, e in zip(d['timestamp'], d['close'], ema):
            align[(tf, sym, int(ts))] = 1 if c > e else -1

df['trend'] = [align.get((t, s, int(x)), 0) for t, s, x in zip(df.tf, df.symbol, df.ts)]
df['aligned'] = ((df['direction'] == 'long') & (df['trend'] == 1)) | ((df['direction'] == 'short') & (df['trend'] == -1))

def agg(g):
    n = len(g)
    if n < 3: return pd.Series({'N': n, 'hit%': np.nan, 'ret_bp': np.nan, 'ex_bp': np.nan, 't': np.nan})
    m, sd = g['ret'].mean(), g['ret'].std(ddof=1)
    return pd.Series({'N': n, 'hit%': round((g['ret'] > 0).mean()*100, 1), 'ret_bp': round(m*1e4, 1),
                      'ex_bp': round(g['ex'].mean()*1e4, 1),
                      't': round(m/(sd/math.sqrt(n)), 1) if sd else np.nan})

print('=== 趋势对齐 vs 逆势（全策略合并，按方向与持有期）===')
print(df.groupby(['tf', 'direction', 'aligned', 'h']).apply(agg, include_groups=False).reset_index().to_string(index=False))

print('\n=== 策略汇总（base 变体，合并多空，按 h）===')
b = df[df.variant == 'base']
print(b.groupby(['tf', 'strategy', 'h']).apply(agg, include_groups=False).reset_index().to_string(index=False))

print('\n=== 信号密度（每条=币种日均信号数，base）===')
for tf, hours in (('1h', 1), ('4h', 4)):
    d = b[b.tf == tf]
    days = 1500 * hours / 24 if tf == '1h' else 1000 * hours / 24
    cnt = d.groupby(['strategy', 'symbol']).size().groupby('strategy').mean() / days
    print(tf, cnt.round(2).to_dict())

print('\n=== 累计信号收益（等权、可重叠，base，1h/h=4 与 4h/h=3）===')
for tf, h in (('1h', 4), ('4h', 3)):
    d = b[(b.tf == tf) & (b.h == h)]
    for s, g in d.groupby('strategy'):
        print(f'{tf} {s:26s} N={len(g):4d} cum={g.ret.sum()*100:6.1f}% mean={g.ret.mean()*1e4:6.1f}bp')
