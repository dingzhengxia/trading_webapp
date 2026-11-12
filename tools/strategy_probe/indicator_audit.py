"""指标实用性审计：用 res_wide.csv（生产策略代码逐根回放的真实信号）按指标口径重算。

不重新抓数据、不改生产代码，只做四件事：
1. 每个策略/周期的信号密度与占比（谁在淹没信息流）；
2. 前视超额（ret − 同币同周期同持有期的无条件漂移），t 值 + 按币 bootstrap（8 币重采样）；
3. 扣 8bp 往返成本后的净期望；
4. 同根共振冗余：同一 (symbol, tf, ts, direction) 上是否还有别的策略，比较「独占」与「共现」的超额。

输出：docs/indicator-audit-2026-11-12.json + 控制台表格。
用法：cd tools/strategy_probe && python indicator_audit.py
"""
import csv
import hashlib
import json
import math
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / 'tools' / 'strategy_probe' / 'res_wide.csv'
BASE = ROOT / 'tools' / 'strategy_probe' / 'res_wide_baselines.json'
OUT = ROOT / 'docs' / 'indicator-audit-2026-11-12.json'
COST_BP = 8.0
BOOT = 2000
MAIN_H = {'1h': 4, '4h': 6}   # 与生产 paper 跟踪/默认持有期一致的评估口径


def sha256(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def load():
    base = json.load(open(BASE, encoding='utf-8'))
    rows = []
    with open(CSV, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            r['ret'] = float(r['ret'])
            r['h'] = int(r['h'])
            r['ts'] = int(r['ts'])
            r['drift'] = base[f"v3|{r['tf']}|{r['symbol']}"][str(r['h'])]
            r['ex'] = r['ret'] - r['drift']
            rows.append(r)
    return rows


def tstat(xs):
    n = len(xs)
    if n < 3:
        return 0.0
    sd = st.stdev(xs)
    return 0.0 if sd == 0 else st.mean(xs) / (sd / math.sqrt(n))


def coin_bootstrap(rows, by_coin=True, iters=BOOT, seed=7):
    """按币重采样：衡量「换个币池结论还成立吗」，顺便抵消同币信号的自相关。"""
    key = 'symbol' if by_coin else 'ts'
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r['ex'])
    coins = list(groups)
    if len(coins) < 3:
        return None
    agg = {c: (sum(groups[c]), len(groups[c])) for c in coins}
    rnd = random.Random(seed)
    means = []
    for _ in range(iters):
        tot = cnt = 0.0
        for _ in range(len(coins)):
            s, n = agg[rnd.choice(coins)]
            tot += s
            cnt += n
        means.append(tot / cnt)
    means.sort()
    lo, hi = means[int(0.025 * iters)], means[int(0.975 * iters)]
    return {'mean_bp': st.mean(means) * 1e4, 'lo_bp': lo * 1e4, 'hi_bp': hi * 1e4,
            'p_gt0': sum(1 for m in means if m > 0) / len(means)}


def main():
    rows = load()
    tfs = sorted({r['tf'] for r in rows})
    days = 180.0
    coins = len({r['symbol'] for r in rows})
    out = {'source': str(CSV.relative_to(ROOT)).replace('\\', '/'),
           'source_sha256': sha256(CSV),
           'baseline_sha256': sha256(BASE),
           'rows': len(rows), 'coins': coins, 'days': days, 'cost_bp': COST_BP,
           'window': '1h 3000 根 / 4h 1200 根，截止 2026-11-12（v3 配置回放）',
           'indicators': [], 'redundancy': {}, 'coverage_gaps': []}

    # h=1 行即「每条信号一行」，用于密度/占比/共振
    min_h = {}
    for r in rows:
        min_h[r['tf']] = min(min_h.get(r['tf'], 10 ** 9), r['h'])
    sig = [r for r in rows if r['h'] == min_h[r['tf']]]
    by_tf = defaultdict(list)
    for r in sig:
        by_tf[r['tf']].append(r)

    for tf in tfs:
        total = len(by_tf[tf])
        strats = sorted({r['strategy'] for r in by_tf[tf]})
        for s in strats:
            item = {'tf': tf, 'indicator': s, 'n_signals': sum(1 for r in by_tf[tf] if r['strategy'] == s)}
            item['share_pct'] = round(100 * item['n_signals'] / total, 1) if total else 0
            item['per_coin_day'] = round(item['n_signals'] / (coins * days), 3)
            item['neutral'] = sum(1 for r in by_tf[tf] if r['strategy'] == s and r['direction'] == 'neutral')
            for h in sorted({r['h'] for r in rows if r['tf'] == tf}):
                sub = [r for r in rows if r['tf'] == tf and r['strategy'] == s and r['h'] == h]
                if not sub:
                    continue
                ex = [r['ex'] for r in sub]
                item[f'h{h}_n'] = len(sub)
                item[f'h{h}_ex_bp'] = round(st.mean(ex) * 1e4, 1)
                item[f'h{h}_t'] = round(tstat(ex), 2)
            main_rows = [r for r in rows if r['tf'] == tf and r['strategy'] == s and r['h'] == MAIN_H[tf]]
            if main_rows:
                ex = [r['ex'] for r in main_rows]
                item['main_h'] = MAIN_H[tf]
                item['main_ex_bp'] = round(st.mean(ex) * 1e4, 1)
                item['main_net_bp'] = round(st.mean(ex) * 1e4 - COST_BP, 1)
                item['hit_pct'] = round(100 * sum(1 for x in ex if x > 0) / len(ex), 1)
                item['bootstrap'] = coin_bootstrap(main_rows)
                one = [r for r in sig if r['tf'] == tf and r['strategy'] == s]
                for d in ('long', 'short'):
                    ds = [r['ex'] for r in one if r['direction'] == d]
                    if ds:
                        item[f'{d}_n'] = len(ds)
                        item[f'{d}_ex_bp'] = round(st.mean(ds) * 1e4, 1)
            out['indicators'].append(item)

    # 共振冗余：同 (symbol, tf, ts, direction) 上的策略集合
    groups = defaultdict(set)
    for r in sig:
        if r['direction'] in ('long', 'short'):
            groups[(r['symbol'], r['tf'], r['ts'], r['direction'])].add(r['strategy'])
    ex_by_key = {(r['symbol'], r['tf'], r['ts'], r['direction']): r for r in sig
                 if r['direction'] in ('long', 'short')}
    for tf in tfs:
        alone, shared = [], []
        for k, names in groups.items():
            if k[1] != tf:
                continue
            rec = ex_by_key.get(k)
            if not rec:
                continue
            (alone if len(names) == 1 else shared).append(rec['ex'])
        out['redundancy'][tf] = {
            'alone': {'n': len(alone), 'ex_bp': round(st.mean(alone) * 1e4, 1) if alone else None},
            'shared': {'n': len(shared), 'ex_bp': round(st.mean(shared) * 1e4, 1) if shared else None},
            'multi_share_pct': round(100 * len(shared) / max(1, len(alone) + len(shared)), 1),
        }

    # 覆盖率缺口：配置里启用/存在但回放中零信号
    cfg = json.load(open(ROOT / 'signal_config.json', encoding='utf-8'))['strategy_params']
    seen = {(i['tf'], i['indicator']) for i in out['indicators']}
    for name, raw in cfg.items():
        if name in ('trend_ema', 'trend_ema_short', 'trend_ema_long',
                    'dynamic_volume_multipliers', 'dynamic_atr_multipliers'):
            continue
        entries = raw if isinstance(raw, list) else [raw]
        enabled = any(e.get('enabled') for e in entries if isinstance(e, dict))
        for tf in ('1h', '4h'):
            excluded = all(tf in (e.get('exclude_timeframes') or []) for e in entries if isinstance(e, dict))
            if enabled and not excluded and (tf, name) not in seen:
                out['coverage_gaps'].append({'indicator': name, 'tf': tf,
                                             'reason': '配置启用但 180 天回放零信号'})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"source={out['source']} sha256={out['source_sha256'][:16]}… rows={out['rows']}")
    print(f"{'tf':3} {'indicator':24} {'n':>5} {'占比%':>6} {'/币/日':>6} "
          f"{'h1bp':>7} {'hMidbp':>7} {'hLongbp':>8} {'净bp':>7} {'t':>6} {'胜率':>6}")
    for i in out['indicators']:
        hs = [k for k in i if k.startswith('h') and k.endswith('_ex_bp')]
        v = [str(i.get(k, '')) for k in sorted(hs, key=lambda k: int(k[1:k.index('_')]))]
        print(f"{i['tf']:3} {i['indicator']:24} {i['n_signals']:5d} {i['share_pct']:6.1f} "
              f"{i['per_coin_day']:6.2f} {v[0] if v else '':>7} {v[1] if len(v)>1 else '':>7} "
              f"{v[2] if len(v)>2 else '':>8} {i.get('main_net_bp',''):>7} {i.get('main_h') or ''}")
    print('\nredundancy:')
    for tf, v in out['redundancy'].items():
        print(f"  {tf}: 独占 {v['alone']['n']} 笔 {v['alone']['ex_bp']}bp | "
              f"共振 {v['shared']['n']} 笔 {v['shared']['ex_bp']}bp | 共振占比 {v['multi_share_pct']}%")
    print(f"\ncoverage_gaps: {out['coverage_gaps']}")
    print(f"written -> {OUT.relative_to(ROOT)}")


if __name__ == '__main__':
    main()
