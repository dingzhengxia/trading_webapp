"""为「多 BTC/ETH、空小币」策略抓数据。

来源：data.binance.vision 批量仓库（现货日线 + 合约资金费），无需 API key。

为什么用日线：这是横截面持仓策略，调仓频率按天/周计，日线足够，
且请求量比 4h 少 6 倍（200 币 × 24 月 × 2 类 ≈ 9600 个 ZIP）。

合约符号映射：现货 PEPEUSDT 的合约叫 1000PEPEUSDT，SHIB/BONK 等同理，
另有 1000000 前缀（MOG、BABYDOGE）。资金费率与代币面值无关，可直接套用。
不加映射会漏掉成交额最大的那批 meme 币 —— 恰恰是做空腿的主力。

输出：
  data/px/{SYM}.csv   date(ms),open,high,low,close,volume,quote_volume
  data/fr/{SYM}.csv   ts(ms),rate,interval_h    （无合约的币没有这个文件）
  data/pool.json      候选池
  data/fr_map.json    现货符号 -> 实际合约符号
"""
import io
import json
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

STABLE = {'USDCUSDT', 'FDUSDUSDT', 'TUSDUSDT', 'DAIUSDT', 'USDPUSDT', 'BUSDUSDT',
          'AEURUSDT', 'EURUSDT', 'USDDUSDT', 'XUSDUSDT', 'USDEUSDT', 'PYUSDUSDT',
          'USD1USDT', 'BFUSDUSDT', 'RLUSDUSDT'}
LEVER = ('UPUSDT', 'DOWNUSDT', 'BULLUSDT', 'BEARUSDT')

SPOT = 'https://data.binance.vision/data/spot/monthly/klines/{s}/1d/{s}-1d-{m}.zip'
FUND = 'https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{m}.zip'
MONTHS = [f'{y}-{m:02d}' for y in (2024, 2025, 2026) for m in range(1, 13)]
MONTHS = [m for m in MONTHS if '2024-11' <= m <= '2026-10']

ROOT = Path(__file__).resolve().parent
PX, FR = ROOT / 'data/px', ROOT / 'data/fr'
WORKERS = 12


def fetch(url, retry=2):
    for _ in range(retry + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
    return None


def unzip_csv(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    return z.read(z.namelist()[0]).decode().strip().split('\n')


def norm_ts(v):
    v = int(v)
    return v // 1000 if v > 1e14 else v


def do_px(sym):
    path = PX / f'{sym}.csv'
    if path.exists() and path.stat().st_size > 500:
        return sym, sum(1 for _ in path.open()) - 1, True
    out = []
    for m in MONTHS:
        blob = fetch(SPOT.format(s=sym, m=m))
        if not blob:
            continue
        for line in unzip_csv(blob):
            p = line.split(',')
            if len(p) < 8:
                continue
            out.append(f'{norm_ts(p[0])},{p[1]},{p[2]},{p[3]},{p[4]},{p[5]},{p[7]}')
    if not out:
        return sym, 0, True
    path.write_text('date,open,high,low,close,volume,quote_volume\n' + '\n'.join(out), encoding='utf-8')
    return sym, len(out), True


def do_fr(sym):
    path = FR / f'{sym}.csv'
    if path.exists() and path.stat().st_size > 200:
        return sym, None, True
    for cand in (sym, f'1000{sym}', f'1000000{sym}'):
        out = []
        for m in MONTHS:
            blob = fetch(FUND.format(s=cand, m=m))
            if not blob:
                continue
            for line in unzip_csv(blob):
                if line.startswith('calc_time'):
                    continue
                p = line.split(',')
                if len(p) < 3:
                    continue
                out.append(f'{int(p[0])},{p[2]},{p[1]}')
        if len(out) > 100:
            path.write_text('ts,rate,interval_h\n' + '\n'.join(out), encoding='utf-8')
            return sym, cand, False
    return sym, None, False


def main(limit=200):
    PX.mkdir(parents=True, exist_ok=True)
    FR.mkdir(parents=True, exist_ok=True)
    rank = json.load(open(ROOT.parent / 'strategy_probe/spot_rank.json'))
    pool = [s for s in rank if s not in STABLE and not s.endswith(LEVER)][:limit]
    json.dump(pool, open(ROOT / 'data/pool.json', 'w'))
    print(f'候选池 {len(pool)} 个', flush=True)

    ok_px = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for f in as_completed({ex.submit(do_px, s): s for s in pool}):
            _, n, _ = f.result()
            ok_px += 1 if n else 0
    print(f'价格完成 {ok_px}/{len(pool)}', flush=True)

    frmap, ok_fr, miss = {}, 0, []
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(do_fr, s): s for s in pool}
        done = 0
        for f in as_completed(futs):
            sym, cand, existed = f.result()
            done += 1
            if cand:
                ok_fr += 1
                if cand != sym:
                    frmap[sym] = cand
            else:
                miss.append(sym)
            if done % 50 == 0:
                print(f'  资金费 {done}/{len(pool)}  命中 {ok_fr}', flush=True)
    json.dump(frmap, open(ROOT / 'data/fr_map.json', 'w'))
    print(f'资金费完成 {ok_fr}/{len(pool)}；无合约 {len(miss)}: {miss[:12]}', flush=True)
    print(f'需改名映射 {len(frmap)}: {list(frmap.items())[:8]}', flush=True)


if __name__ == '__main__':
    main()
