"""只读诊断：某标的的成交量是否呈「交易时段」潮汐，以及剔除低流动 K 线后 ATR 怎么变。

回答两个问题：
1. 币安股票代币在美股休市时是「没有 K 线」还是「有 K 线但量很小」？
   —— 如果夜间仍有成交，那就不存在「排除无数据」，只能「排除低流动性时段」。
2. 只取盘中 K 线算 ATR / 均线，与全天混算差多少？

无第三方依赖（只用标准库），宿主机直接跑，不需要进容器、不需要重建镜像：
    cd /root/trading_webapp
    python3 tools/inspect_symbol_profile.py --symbol AAPLUSDT
    python3 tools/inspect_symbol_profile.py --symbol BTCUSDT

不写库、不下单、不改任何配置。
"""
from __future__ import annotations

import argparse
import json
import statistics
import urllib.request
from datetime import datetime, timedelta, timezone

ETF = timezone(timedelta(hours=-5))     # 美东（冬令时 EST）
CST = timezone(timedelta(hours=8))
HOSTS = ('https://fapi.binance.com', 'https://fapi1.binance.com', 'https://fapi2.binance.com')


def _get(path: str, params: dict):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    last = None
    for host in HOSTS:
        url = f'{host}{path}' + (f'?{query}' if query else '')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001 - 换下一个镜像域名重试
            last = exc
    raise RuntimeError(f'全部域名均失败: {last}')


def _norm(symbol: str) -> str:
    """AAPL/USDT:USDT -> AAPLUSDT"""
    return symbol.replace('/', '').split(':')[0].upper()


def _et_hour(ms: int) -> int:
    return datetime.fromtimestamp(ms / 1000, ETF).hour


def _fmt(ms: int, tz) -> str:
    return datetime.fromtimestamp(ms / 1000, tz).strftime('%m-%d %H:%M')


def _atr(rows, period: int = 14):
    """与后端 _atr_from_df 同口径：TR 的 period 简单均值。"""
    if len(rows) < period + 1:
        return None
    trs = []
    for i in range(1, len(rows)):
        _ts, _o, h, l, c, _v = rows[i]
        prev_c = rows[i - 1][4]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', default='AAPLUSDT', help='币安原始 symbol，如 AAPLUSDT / BTCUSDT')
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--low-vol-ratio', type=float, default=0.15,
                    help='量低于该标的中位量这个比例视为低流动性 K 线（默认 15%%）')
    args = ap.parse_args()
    sym = _norm(args.symbol)

    print(f'=== {sym} 市场元数据（exchangeInfo） ===')
    try:
        info = _get('/fapi/v1/exchangeInfo', {})
        hit = next((s for s in info.get('symbols', []) if s['symbol'] == sym), None)
        if not hit:
            print(f'  exchangeInfo 里没有 {sym}')
        else:
            for key in ('contractType', 'status', 'underlyingType', 'underlyingSubType',
                        'quoteAsset', 'marginAsset', 'deliveryDate', 'onboardDate'):
                if key in hit:
                    print(f'  {key:<16}: {hit[key]}')
            print(f'  全部字段         : {sorted(hit.keys())}')
    except Exception as exc:  # noqa: BLE001
        print(f'  exchangeInfo 获取失败: {exc}')

    rows = _get('/fapi/v1/klines', {'symbol': sym, 'interval': '15m', 'limit': args.days * 96})
    if not rows:
        print('无 K 线数据')
        return
    print(f'\n=== K 线 {len(rows)} 根：{_fmt(rows[0][0], CST)} ~ {_fmt(rows[-1][0], CST)}（北京时间） ===')

    zero = sum(1 for r in rows if r[5] == 0)
    vols = [r[5] for r in rows]
    med = statistics.median(vols)
    print(f'  零成交 K 线    : {zero} / {len(rows)} ({zero / len(rows):.1%})')
    print(f'  成交量中位数   : {med:.2f}   最小: {min(vols):.2f}   最大: {max(vols):.2f}')

    by_hour: dict[int, list[float]] = {}
    for r in rows:
        by_hour.setdefault(_et_hour(r[0]), []).append(r[5])
    print('\n=== 按美东小时的中位成交量（★ = 美股常规时段 09:30-16:00 ET） ===')
    for h in range(24):
        vs = by_hour.get(h) or []
        if not vs:
            print(f'  {h:02d}:00  —')
            continue
        m = statistics.median(vs)
        bar = '#' * min(40, int(m / max(med, 1e-9) * 20))
        mark = ' ★' if 9 <= h < 16 else '  '
        print(f'  {h:02d}:00  {m:14.2f}  {bar}{mark}')

    full_atr = _atr(rows)
    liquid = [r for r in rows if r[5] >= med * args.low_vol_ratio]
    liq_atr = _atr(liquid)
    eth = [r for r in rows if 9 <= _et_hour(r[0]) < 16]
    eth_atr = _atr(eth)

    price = float(rows[-1][4])
    print('\n=== ATR(14) 对比 ===')
    print(f'  当前价  : {price:.4f}')
    for label, val, n in (
        ('全天混算（现状）        ', full_atr, len(rows)),
        (f'仅量>中位×{args.low_vol_ratio:<5.2f}      ', liq_atr, len(liquid)),
        ('仅美股时段 09-16 ET    ', eth_atr, len(eth)),
    ):
        if val:
            print(f'  {label}: {val:.4f}  ({val / price:.3%} of price)  n={n}')
        else:
            print(f'  {label}: 样本不足')

    downs = sorted(((r[1] - r[4]) / r[4]) for r in rows if r[4] < r[1])
    if downs:
        print('\n=== 单根 15m 下跌幅度分位（占价格） ===')
        for q in (0.5, 0.9, 0.95, 0.99, 0.995, 1.0):
            idx = min(len(downs) - 1, int(q * (len(downs) - 1)))
            print(f'  {q * 100:5.1f}% : {downs[idx]:.3%}  → {downs[idx] * price:.4f}')


if __name__ == '__main__':
    main()
