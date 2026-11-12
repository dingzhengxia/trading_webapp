"""「做多 BTC/ETH、做空 50~100 个小币」横截面策略回测。

与之前的信号策略完全不同：这里没有入场信号，是**持续持有的横截面组合**，
所以评估维度是日频净值、beta/alpha、多空两腿分解、资金费与换手成本。

三个必须做对的地方：
1. **币池动态、无前视**：每月末按「过去 30 天成交额中位数」重新排名取前 N，
   而不是用今天的排名回溯历史（那会把 2 年后还活着的币提前塞进池子）。
2. **权重随价格漂移**：不每日重置到目标权重，否则会白捡一份「波动率再平衡溢价」，
   在高波动小币上足以虚构出每年几个点的收益。
3. **资金费逐日累计**：每次结算按持仓市值 × 费率计，多头付、空头收，方向不能错。

对照实验（判断收益到底来自哪）：
  ls        目标策略：多 BTC/ETH，空小币
  long_maj  只多 BTC/ETH
  short_alt 只空小币
  reverse   多小币、空 BTC/ETH（符号应相反）
  rand_alt  空随机 N 个小币（检验选池规则有没有额外价值）
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PX, FR = ROOT / 'data/px', ROOT / 'data/fr'
MAJORS = ('BTCUSDT', 'ETHUSDT')
TRADING_DAYS = 365
# Binance 代币化股票（股票代码 + B + USDT），不是加密资产，剔除
STOCK_TOKENS = {'NVDABUSDT', 'TSMBUSDT', 'MUBUSDT', 'SNDKBUSDT', 'SOXLBUSDT',
                'AAPLBUSDT', 'MSFTBUSDT', 'TSLABUSDT', 'GOOGLBUSDT', 'AMZNBUSDT',
                'METABUSDT', 'COINBUSDT', 'MSTRBUSDT', 'SPYBUSDT', 'QQQBUSDT'}


# ---------------------------------------------------------------- 数据
def load():
    px, qv = {}, {}
    for f in sorted(PX.glob('*.csv')):
        df = pd.read_csv(f)
        df['date'] = pd.to_datetime(df['date'], unit='ms')
        df = df.set_index('date')
        df = df[~df.index.duplicated(keep='last')].sort_index()
        px[f.stem] = df['close'].astype(float)
        qv[f.stem] = df['quote_volume'].astype(float)
    close = pd.DataFrame(px).sort_index()
    volq = pd.DataFrame(qv).sort_index()
    close.index = close.index.normalize().tz_localize(None)
    volq.index = close.index
    close = close[~close.index.duplicated(keep='last')]
    volq = volq[~volq.index.duplicated(keep='last')]

    fr = {}
    for f in sorted(FR.glob('*.csv')):
        d = pd.read_csv(f)
        ts = pd.to_datetime(d['ts'], unit='ms').dt.normalize()
        fr[f.stem] = d.groupby(ts)['rate'].sum()
    raw = pd.DataFrame(fr).reindex(close.index)
    # 合约首日：早于这一天无法做空，选池必须排除（现货有币不等于能开空）
    first_fr = {s: raw[s].first_valid_index() for s in raw.columns}
    funding = raw.fillna(0.0)
    funding.index = close.index

    # 剔除稳定币（日波动 <0.4% 且几乎不涨跌）与代币化股票（非加密资产，做空无意义）
    drop = []
    for s in close.columns:
        r = close[s].pct_change(fill_method=None)
        if r.std() < 0.004 and abs(close[s].iloc[-1] / close[s].dropna().iloc[0] - 1) < 0.1:
            drop.append(s)
    drop += [s for s in close.columns if s in STOCK_TOKENS]
    if drop:
        close = close.drop(columns=drop)
        volq = volq.drop(columns=drop)
        funding = funding.drop(columns=[c for c in drop if c in funding.columns])
        first_fr = {k: v for k, v in first_fr.items() if k in funding.columns}
    return close, volq, funding, first_fr


# ---------------------------------------------------------------- 选池
def rank_pool(volq, t, n, first_fr, lookback=30, need=0.8):
    """t 位置（含）往前 lookback 天成交额中位数排名。返回按成交额降序的币列表。

    first_fr 保证「该币合约已上市」——现货有报价但没合约的币无法做空。
    """
    lo = max(0, t - lookback + 1)
    win = volq.iloc[lo:t + 1]
    med = win.median()
    cnt = win.notna().sum()
    asof = volq.index[t]
    far = asof + pd.Timedelta(days=3650)
    ok = [s for s in med.index
          if med[s] > 0 and cnt[s] >= lookback * need and s not in MAJORS
          and first_fr.get(s, far) is not None and first_fr.get(s, far) <= asof]
    return sorted(ok, key=lambda s: -med[s])[:n]


def build_target(close, volq, funding, first_fr, t, cfg, nav, rng):
    """返回目标持仓市值向量（相对 nav），t 为决策日（从 t+1 生效）。"""
    nsym = close.shape[1]
    idx = {s: i for i, s in enumerate(close.columns)}
    w = np.zeros(nsym)
    pool = rank_pool(volq, t, cfg.n_short, first_fr, cfg.lookback)

    if cfg.mode == 'rand_alt':
        # 从更大的候选池里随机抽，否则和前 N 名完全重合、对照失效
        wide = rank_pool(volq, t, cfg.n_short * 3, first_fr, cfg.lookback)
        if len(wide) > cfg.n_short:
            pool = list(rng.choice(wide, cfg.n_short, replace=False))

    def spread(names, side_total, sign):
        if not names:
            return
        if cfg.weight == 'invvol':
            lo = max(0, t - cfg.lookback + 1)
            ret = close.iloc[lo:t + 1].pct_change(fill_method=None)
            sd = ret[names].std().replace(0, np.nan)
            raw = 1 / sd
            raw = raw.fillna(raw.median())
            if raw.sum() <= 0:
                return
            wts = (raw / raw.sum()).to_numpy()
        else:
            wts = np.full(len(names), 1.0 / len(names))
        for s, k in zip(names, wts):
            w[idx[s]] = sign * side_total * k

    if cfg.alt_trend and pool:
        lo = max(0, t - cfg.alt_trend + 1)
        seg = close.iloc[lo:t + 1]
        alt = (seg[pool].iloc[-1] / seg[pool].iloc[0]).mean()
        maj = seg['BTCUSDT'].iloc[-1] / seg['BTCUSDT'].iloc[0]
        if alt / maj > 1:   # 小币跑赢主流 → 山寨季，不做空
            pool = []

    if cfg.mode == 'ls':
        if pool:            # 空头腿关闭时多头腿同时关闭，否则变成裸多
            spread(list(MAJORS), cfg.gross / 2, +1)
            spread(pool, cfg.gross / 2, -1)
    elif cfg.mode == 'reverse':
        spread(list(MAJORS), cfg.gross / 2, -1)
        spread(pool, cfg.gross / 2, +1)
    elif cfg.mode == 'long_maj':
        spread(list(MAJORS), cfg.gross, +1)
    elif cfg.mode in ('short_alt', 'rand_alt'):
        spread(pool, cfg.gross, -1)
    return w * nav


# ---------------------------------------------------------------- 回测
def run(close, volq, funding, first_fr, cfg, use_funding=True):
    dates = close.index
    R = close.pct_change(fill_method=None).fillna(0.0)
    F = funding.reindex(columns=close.columns).fillna(0.0)
    nsym = close.shape[1]

    if cfg.rebal == 'W':
        marks = pd.Series(dates, index=dates).groupby([dates.isocalendar().year,
                                                       dates.isocalendar().week]).max().values
    elif cfg.rebal == 'D':
        marks = dates.values
    else:
        marks = pd.Series(dates, index=dates).groupby([dates.year, dates.month]).max().values
    pos_of = {d: i for i, d in enumerate(dates)}
    rebal = {pos_of[pd.Timestamp(m)] for m in marks if pd.Timestamp(m) in pos_of}

    rng = np.random.default_rng(cfg.seed)

    # 统一建仓起点：第一个能选出非空池的交易日（需要 lookback 天历史）。
    # 否则月调仓要等到月末才建仓、周调仓等到周末，两个配置的起点不同，
    # 会各自错过不同的行情，导致配置之间不可比（曾造成 -32.7% vs -3.7% 的假差异）。
    start = None
    for t in range(cfg.lookback, len(dates) - 1):
        if rank_pool(volq, t, cfg.n_short, first_fr, cfg.lookback):
            start = t
            break
    if start is None:
        return pd.Series(dtype=float), pd.DataFrame(), dict(turnover=0, cost=0, funding=0)

    nav = 1.0
    hold = build_target(close, volq, funding, first_fr, start, cfg, nav, rng)
    rows, legs = [(dates[start], nav)], []
    turn_acc = cost_acc = fund_acc = 0.0

    for t in range(start + 1, len(dates)):
        cost = 0.0
        if (t - 1) in rebal:
            target = build_target(close, volq, funding, first_fr, t - 1, cfg, nav, rng)
            turnover = float(np.abs(target - hold).sum() / nav)
            cost = turnover * cfg.cost_bp / 1e4 * nav
            turn_acc += turnover
            cost_acc += cost
            hold = target
            nav -= cost

        r = R.iloc[t].to_numpy()
        f = F.iloc[t].to_numpy()
        base = nav          # 归因一律按净值归一化，否则复利下后段权重变大、腿贡献失真
        pnl_long = float(hold[hold > 0] @ r[hold > 0])
        pnl_short = float(hold[hold < 0] @ r[hold < 0])
        fund = -float(hold @ f) if use_funding else 0.0
        fund_acc += fund

        hold = hold * (1 + r)
        nav += pnl_long + pnl_short + fund
        legs.append((dates[t], pnl_long / base, pnl_short / base, fund / base, cost / base))
        rows.append((dates[t], nav))

    navs = pd.Series(dict(rows), name='nav')
    leg_df = pd.DataFrame(legs, columns=['date', 'long', 'short', 'funding', 'cost']).set_index('date')
    return navs, leg_df, dict(turnover=turn_acc, cost=cost_acc, funding=fund_acc)


# ---------------------------------------------------------------- 指标
def stats(navs, leg_df, name, btc=None):
    r = navs.pct_change(fill_method=None).dropna()
    if len(r) < 30:
        return None
    years = len(r) / TRADING_DAYS
    total = navs.iloc[-1] / navs.iloc[0] - 1
    ann = (1 + total) ** (1 / years) - 1 if total > -1 else -1.0
    vol = r.std(ddof=1) * np.sqrt(TRADING_DAYS)
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS) if r.std(ddof=1) else 0
    eq = navs / navs.cummax()
    mdd = float(eq.min() - 1)
    out = {
        'name': name, 'days': len(r), 'total': total, 'ann': ann, 'vol': vol,
        'sharpe': sharpe, 'mdd': mdd,
        'calmar': ann / abs(mdd) if mdd < 0 else float('nan'),
        'win_d': float((r > 0).mean()),
        'leg_long': float(leg_df.long.sum()), 'leg_short': float(leg_df.short.sum()),
        'funding': float(leg_df.funding.sum()), 'cost': float(leg_df.cost.sum()),
    }
    if btc is not None:
        b = btc.reindex(r.index).fillna(0)
        var = b.var()
        beta = float(r.cov(b) / var) if var else 0.0
        alpha = float((r.mean() - beta * b.mean()) * TRADING_DAYS)
        out['beta'] = beta
        out['alpha_ann'] = alpha
        out['corr'] = float(r.corr(b))
    return out


def fmt(s):
    if not s:
        return '样本不足'
    return (f"{s['name']:<12}{s['total']*100:>+8.1f}%{s['ann']*100:>+8.1f}%{s['vol']*100:>7.1f}%"
            f"{s['sharpe']:>7.2f}{s['mdd']*100:>8.1f}%{s.get('beta', float('nan')):>7.2f}"
            f"{s.get('alpha_ann', float('nan'))*100:>+8.1f}%")


class Cfg:
    def __init__(self, mode='ls', n_short=100, gross=1.0, rebal='M', weight='equal',
                 cost_bp=5.0, lookback=30, seed=7, alt_trend=0):
        self.mode, self.n_short, self.gross = mode, n_short, gross
        self.rebal, self.weight, self.cost_bp = rebal, weight, cost_bp
        self.lookback, self.seed = lookback, seed
        self.alt_trend = alt_trend   # >0 时启用「小币相对主流走强就空仓」的过滤


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', default='20,50,100')
    ap.add_argument('--rebal', default='M')
    ap.add_argument('--gross', type=float, default=1.0)
    ap.add_argument('--cost', type=float, default=5.0)
    ap.add_argument('--weight', default='equal')
    args = ap.parse_args()

    close, volq, funding, first_fr = load()
    print(f'数据：{close.shape[0]} 个交易日 × {close.shape[1]} 个币  '
          f'{close.index[0].date()} ~ {close.index[-1].date()}')
    print(f'有合约（可做空）的币：{funding.shape[1]} 个\n')
    btc = close['BTCUSDT'].pct_change(fill_method=None)

    hdr = f"{'策略':<12}{'总收益':>9}{'年化':>8}{'波动':>7}{'Sharpe':>7}{'回撤':>8}{'beta':>7}{'alpha':>8}"
    for n in [int(x) for x in args.n.split(',')]:
        print(f'=== 空头腿 {n} 个币 · {args.rebal} 调仓 · 总名义 {args.gross:g}x · 成本 {args.cost:g}bp ===')
        print(hdr)
        for mode, label in (('ls', '多主流/空小币'), ('long_maj', '只多BTC+ETH'),
                            ('short_alt', '只空小币'), ('reverse', '反向(多小/空主)'),
                            ('rand_alt', '随机N个做空')):
            cfg = Cfg(mode=mode, n_short=n, gross=args.gross, rebal=args.rebal,
                      weight=args.weight, cost_bp=args.cost)
            navs, legs, extra = run(close, volq, funding, first_fr, cfg)
            s = stats(navs, legs, label, btc)
            if s:
                s['cost_detail'] = extra
                print(fmt(s))
        print()


if __name__ == '__main__':
    main()
