import json, math
import pandas as pd, numpy as np
df = pd.read_csv('res_base.csv'); base = json.load(open('res_base_baselines.json'))
df = df[df['direction'] != 'neutral'].copy()
df['base_s'] = [base[f"{v}|{t}|{s}"][str(int(h))] * (1 if d == 'long' else -1)
                for v, t, s, h, d in zip(df.variant, df.tf, df.symbol, df.h, df.direction)]
df['ex'] = df['ret'] - df['base_s']

def cell(g):
    n = len(g)
    if n < 3: return f"{n} 笔 / —"
    m = g['ex'].mean()*1e4
    return f"{n} 笔 / {m:+.0f}bp"

for tf, h in (('1h', 4), ('4h', 3)):
    d = df[(df.tf == tf) & (df.h == h)]
    print(f'\n#### {tf} · 持有 {h} 根（超额 bp，已扣 8bp 往返成本后 = 括号内）')
    print('| 策略 | 做多 N/超额 | 做空 N/超额 | 合计超额 | 扣成本后 |')
    print('|---|---|---|---|---|')
    for s in sorted(d.strategy.unique()):
        g = d[d.strategy == s]
        lg, sh = g[g.direction == 'long'], g[g.direction == 'short']
        tot = g['ex'].mean()*1e4
        print(f'| {s} | {cell(lg)} | {cell(sh)} | {tot:+.0f}bp | {tot-8:+.0f}bp |')
