import multiprocessing as mp, json, time
import bt
TASKS = [(s, tf, 1500 if tf == '1h' else 1000, 'base', (1, 4, 12) if tf == '1h' else (1, 3, 6))
         for tf in ('1h', '4h') for s in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT')]

def task(a):
    sym, tf, bars, variant, hz = a
    bt.RECORDS.clear()
    out, df = bt.replay(sym, tf, bars, bt.variant_config(variant), horizons=hz)
    out['variant'] = variant
    return out, bt.baseline(df, hz), f'{variant}|{tf}|{sym}'

if __name__ == '__main__':
    t0 = time.time()
    with mp.Pool(4) as pool:
        res = pool.map(task, TASKS)
    import pandas as pd
    frames, bases = [], {}
    for out, b, k in res:
        frames.append(out); bases[k] = b
    pd.concat(frames, ignore_index=True).to_csv('res_base.csv', index=False)
    json.dump(bases, open('res_base_baselines.json', 'w'))
    print('done', f'{time.time()-t0:.0f}s')
