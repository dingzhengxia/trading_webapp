import json
import pandas as pd

def load(csv, base_json, tag):
    df = pd.read_csv(csv); base = json.load(open(base_json))
    df = df[df['direction'] != 'neutral'].copy()
    df['base_s'] = [base[f"{v}|{t}|{s}"][str(int(h))] * (1 if d == 'long' else -1)
                    for v, t, s, h, d in zip(df.variant, df.tf, df.symbol, df.h, df.direction)]
    df['ex'] = df['ret'] - df['base_s']
    df['tag'] = tag
    return df

old = load('res_v2.csv', 'res_v2_baselines.json', 'v2')
new = load('res_base.csv', 'res_base_baselines.json', 'v3')
both = pd.concat([old, new], ignore_index=True)

for tf, h in (('1h', 4), ('4h', 3)):
    d = both[(both.tf == tf) & (both.h == h)]
    print(f'\n### {tf} h={h}  信号数 / 超额bp（扣8bp成本后）')
    print('| 策略 | v2 N / 超额 / 净 | v3 N / 超额 / 净 |')
    print('|---|---|---|')
    for s in sorted(both.strategy.unique()):
        cells = []
        for tag in ('v2', 'v3'):
            g = d[(d.strategy == s) & (d.tag == tag)]
            if len(g) == 0:
                cells.append('0 笔 / —')
            else:
                m = g['ex'].mean() * 1e4
                cells.append(f'{len(g)} 笔 / {m:+.0f}bp / {m-8:+.0f}bp')
        print(f'| {s} | {cells[0]} | {cells[1]} |')
    for tag in ('v2', 'v3'):
        g = d[d.tag == tag]
        print(f'合计 {tag}: {len(g)} 笔, 超额 {g.ex.mean()*1e4:+.0f}bp')
