"""LightGBM 信号二次筛选：能否在 ATR 1.5/1R 的 +21.4bp 基线上再挤出收益。

口径与 final_bt.py 完全一致（走生产代码，不重写逻辑）：
- 入场 = 信号 bar 后第 2 根开盘价；
- 出场 = `exit_rules.exit_prices` 算价 + `outcomes.simulate_exit` 逐根判定（ATR 1.5 / 1R / 最多 6 根）；
- 成本 8bp 往返；
- **特征只用信号 bar 及之前的数据**（严格避免前视）。

验证方式：按时间切 70/30，中间留 6 根 K 线 embargo（标签窗口重叠会污染切分），
早停只用训练集内部的验证段，测试集一次都不用碰。

输出：过滤曲线（保留比例 vs 每笔净收益）、五分组单调性、特征重要性。
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend'))

from app.core import exit_rules        # noqa: E402
from app.signals import outcomes       # noqa: E402

COST = 8e-4
OFFSET = 2
BARS = 6
CFG = {'signal_exit_mode': 'atr', 'enable_long_sl_tp': True, 'enable_short_sl_tp': True,
       'signal_paper_sl_atr': 1.5, 'signal_paper_tp_r': 1.0}
TF_MS = {'1h': 3_600_000, '4h': 14_400_000}


# --------------------------------------------------------------------- 特征
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """在整个 K 线序列上预计算指标，后续按信号 bar 下标取行。全部是向后看的。"""
    c, h, l, v = df['close'], df['high'], df['low'], df['volume']
    ma20, ma60 = c.rolling(20).mean(), c.rolling(60).mean()
    f = pd.DataFrame(index=df.index)
    f['atr_pct'] = df['atr'] / c
    f['atr_ratio'] = df['atr'] / df['atr'].rolling(60).mean()
    for n in (1, 3, 6, 12, 24):
        f[f'ret{n}'] = c.pct_change(n)
    f['dist_ma20'] = c / ma20 - 1
    f['dist_ma60'] = c / ma60 - 1
    f['ma20_slope'] = ma20 / ma20.shift(5) - 1
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    f['rsi14'] = 100 - 100 / (1 + up / (dn + 1e-12))
    f['vol_ratio'] = v / v.rolling(20).mean()
    f['bb_width'] = 4 * c.rolling(20).std() / ma20
    f['range_pct'] = (h - l) / c
    f['close_pos'] = (c - l) / (h - l + 1e-12)
    lo20, hi20 = l.rolling(20).min(), h.rolling(20).max()
    f['range_pos20'] = (c - lo20) / (hi20 - lo20 + 1e-12)
    sign = np.sign(c.diff()).fillna(0)
    grp = (sign != sign.shift()).cumsum()
    f['consec'] = sign * (sign.groupby(grp).cumcount() + 1)
    f['vol_z'] = (v - v.rolling(20).mean()) / (v.rolling(20).std() + 1e-12)
    f['ma20_gt_ma60'] = (ma20 > ma60).astype(int)
    return f


def build(tf: str = '4h') -> pd.DataFrame:
    raw = pd.read_csv(HERE / 'res_wide.csv')
    sig = (raw[(raw.tf == tf) & raw.direction.isin(['long', 'short'])]
           .drop_duplicates(['symbol', 'tf', 'ts', 'strategy', 'direction'])
           .sort_values('ts').reset_index(drop=True))
    syms = sorted(sig.symbol.unique())

    # 多策略共振：同一 (币, 信号 bar) 下同向策略数 / 是否多空并存。
    # 这是实盘也能实时算出来的信息，不是未来函数。
    cnt = sig.groupby(['symbol', 'ts', 'direction']).size().unstack(fill_value=0)
    for c in ('long', 'short'):
        if c not in cnt:
            cnt[c] = 0
    conf = pd.DataFrame({'same': cnt[['long', 'short']].max(axis=1),
                         'both': ((cnt['long'] > 0) & (cnt['short'] > 0)).astype(int)})
    conf_map = conf.to_dict('index')

    cache, rows = {}, []
    for r in sig.itertuples():
        key = (r.symbol, r.tf)
        if key not in cache:
            df = outcomes.to_frame(json.load(open(HERE / f'data/{r.symbol}_{r.tf}.json')))
            cache[key] = (df, enrich(df), {int(t): i for i, t in enumerate(df['timestamp'].values)})
        df, feat, idxmap = cache[key]
        i = idxmap.get(int(r.ts))
        if i is None or i + OFFSET >= len(df):
            continue
        row = feat.iloc[i]
        if row.isna().any():
            continue

        entry = float(df['open'].iloc[i + OFFSET])
        prices = exit_rules.exit_prices(entry, r.direction, CFG, atr=outcomes.atr_at(df, i))
        if prices is None or entry <= 0:
            continue
        res = outcomes.simulate_exit(df, i + OFFSET - 1, r.direction, entry,
                                     prices.get('stop_loss'), prices.get('take_profit'), BARS)
        if res is None:
            continue

        sign = 1.0 if r.direction == 'long' else -1.0
        net = sign * (float(res['exit_price']) / entry - 1) - COST
        c = conf_map.get((r.symbol, int(r.ts)), {'same': 1, 'both': 0})
        rec = row.to_dict()
        rec.update({
            'symbol': r.symbol, 'strategy': r.strategy, 'dir': sign,
            'sig_ts': int(r.ts), 'entry_ts': int(df['timestamp'].iloc[i + OFFSET]),
            'exit_ts': int(res['exit_ts']), 'reason': res['reason'],
            'net': net, 'hour': (int(r.ts) % 86_400_000) // 3_600_000,
            'conf_same': int(c['same']), 'conf_both': int(c['both']),
        })
        rows.append(rec)

    ds = pd.DataFrame(rows).sort_values('entry_ts').reset_index(drop=True)

    # 跨币特征：同期相对 BTC 强弱 + 信号拥挤度
    # 注意：必须按 **BTC 的 K 线时间轴** 对齐（ffill），不能用 BTC 的信号时刻做映射，
    # 否则只有"和 BTC 同时出信号"的样本能匹配上，会把样本量砍掉一半并引入选择偏差。
    btc_df, btc_feat, _ = cache[('BTCUSDT', tf)]
    btc_s = pd.Series(btc_feat['ret12'].to_numpy(),
                      index=btc_df['timestamp'].to_numpy()).dropna()
    ds['btc_ret12'] = btc_s.reindex(ds['sig_ts'].to_numpy(), method='ffill').to_numpy()
    ds['rel_btc'] = ds['ret12'] - ds['btc_ret12']
    crowd = ds.groupby('sig_ts').size()
    ds['crowd'] = ds['sig_ts'].map(crowd)

    ds = pd.concat([ds, pd.get_dummies(ds.strategy, prefix='st').astype(int)], axis=1)
    ds = pd.concat([ds, pd.get_dummies(ds.symbol, prefix='sy').astype(int)], axis=1)
    # 只丢弃特征本身缺失的行（rel_btc 首根可能缺），不要整表 dropna
    need = [c for c in ds.columns if c not in
            ('symbol', 'strategy', 'dir', 'sig_ts', 'entry_ts', 'exit_ts', 'reason', 'net')]
    ds = ds.dropna(subset=need)

    # 实盘约束：同币持仓期内不重复开仓。
    # 必须用 `<=`：当上一笔在入场当根就出场时 exit_ts == entry_ts，
    # 用 `<` 会让同一根 K 线上的其它信号全部逃脱约束，把 1 次交易重复计成 3~6 次。
    ds = ds.sort_values('entry_ts').reset_index(drop=True)
    held, keep = {}, []
    for idx, r in zip(ds.index, ds.itertuples()):
        if r.entry_ts <= held.get(r.symbol, -1):
            continue
        held[r.symbol] = r.exit_ts
        keep.append(idx)
    return ds.loc[keep].sort_values('entry_ts').reset_index(drop=True)


# ------------------------------------------------------------------- 组合口径
def portfolio(d: pd.DataFrame, weight: float = 0.10) -> dict:
    """过滤后重算组合收益：同币持仓期不重复开仓，按出场时间线性累加。"""
    d = d.sort_values('entry_ts')
    held, keep = {}, []
    for r in d.itertuples():
        if r.entry_ts < held.get(r.symbol, -1):
            continue
        held[r.symbol] = r.exit_ts
        keep.append(r)
    if not keep:
        return {'n': 0, 'per_trade_bp': 0.0, 'total': 0.0, 'mdd': 0.0}
    k = pd.DataFrame([{'net': x.net, 'exit_ts': x.exit_ts, 'entry_ts': x.entry_ts} for x in keep])
    eq = 1 + np.cumsum(weight * k['net'].to_numpy())
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return {'n': len(k), 'per_trade_bp': k.net.mean() * 1e4,
            'total': eq[-1] - 1, 'mdd': dd,
            'win': (k.net > 0).mean()}


def filter_curve(d: pd.DataFrame, score: np.ndarray, label: str):
    order = np.argsort(-np.asarray(score))
    print(f'\n{label}：按模型分数从高到低保留')
    print(f"{'保留':>5}{'笔数':>7}{'每笔净bp':>11}{'胜率':>8}{'组合总收益':>12}{'MDD':>8}")
    for pct in (1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2):
        n = int(len(d) * pct)
        sub = d.iloc[order[:n]]
        p = portfolio(sub)
        print(f'{pct*100:>4.0f}%{n:>7}{sub.net.mean()*1e4:>+11.1f}'
              f'{p["win"]*100:>7.0f}%{p["total"]*100:>+11.1f}%{p["mdd"]*100:>7.1f}%')


def quintiles(d: pd.DataFrame, score: np.ndarray):
    d = d.copy()
    # 用位置数组赋值，避免 Series 索引与原表索引不对齐导致整列 NaN
    ranks = pd.Series(np.asarray(score)).rank(method='first').to_numpy()
    d['bucket'] = pd.qcut(ranks, 5, labels=['Q1 低', 'Q2', 'Q3', 'Q4', 'Q5 高'])
    g = d.groupby('bucket', observed=True)['net']
    print(f"\n{'分组':<8}{'笔数':>7}{'每笔净bp':>11}{'胜率':>8}")
    for name, s in g:
        print(f'{name:<8}{len(s):>7}{s.mean()*1e4:>+11.1f}{(s>0).mean()*100:>7.0f}%')


# ---------------------------------------------------------------------- 主流程
def main():
    import lightgbm as lgb

    ds = build('4h')
    feat_cols = [c for c in ds.columns if c not in
                 ('symbol', 'strategy', 'dir', 'sig_ts', 'entry_ts', 'exit_ts', 'reason', 'net')]
    print(f'样本 {len(ds)} 笔，特征 {len(feat_cols)} 个，'
          f'时间 {pd.to_datetime(ds.sig_ts.min(), unit="ms"):%Y-%m-%d} → '
          f'{pd.to_datetime(ds.sig_ts.max(), unit="ms"):%Y-%m-%d}')
    print(f'全样本基线：每笔 {ds.net.mean()*1e4:+.1f} bp，胜率 {(ds.net>0).mean()*100:.0f}%')

    print('\n按多策略共振强度分层（这是规则，不需要模型，实盘可实时计算）：')
    print(f"{'共振':<14}{'笔数':>7}{'每笔净bp':>11}{'胜率':>8}{'总收益':>9}")
    for lab, sel in (('单策略', ds.conf_same == 1), ('2 个同向', ds.conf_same == 2),
                     ('≥3 个同向', ds.conf_same >= 3), ('多空并存', ds.conf_both == 1)):
        x = ds[sel]
        if len(x) < 20:
            continue
        eq = 1 + np.cumsum(0.10 * x.net.to_numpy())
        print(f'{lab:<14}{len(x):>7}{x.net.mean()*1e4:>+11.1f}'
              f'{(x.net>0).mean()*100:>7.0f}%{(eq[-1]-1)*100:>+8.1f}%')

    # 按日期切分：训练 ≤ 8 月底，样本外 = 9 月起（与「现在还有没有效」直接对应）
    # 中间留 6 根 4h 的 embargo，避免测试集第一笔的标签窗口跨进训练集
    test_from = pd.Timestamp('2026-09-01').value // 10 ** 6
    embargo = BARS * TF_MS['4h']
    tr = ds[ds.sig_ts < test_from - embargo].copy()
    te = ds[ds.sig_ts >= test_from].copy()
    vcut = int(len(tr) * 0.8)
    fit, val = tr.iloc[:vcut], tr.iloc[vcut:]
    print(f'\n训练 {len(fit)} / 验证 {len(val)} / 样本外 {len(te)} 笔'
          f'（样本外 {pd.to_datetime(te.sig_ts.min(), unit="ms"):%m-%d} 起）')
    print(f'训练段基线 {fit.net.mean()*1e4:+.1f} bp / 样本外基线 {te.net.mean()*1e4:+.1f} bp')

    params = dict(n_estimators=600, learning_rate=0.03, num_leaves=8, max_depth=3,
                  min_child_samples=120, feature_fraction=0.7, bagging_fraction=0.8,
                  bagging_freq=5, lambda_l2=5.0, random_state=42, verbose=-1)
    reg = lgb.LGBMRegressor(objective='huber', **params)
    reg.fit(fit[feat_cols], fit.net, eval_set=[(val[feat_cols], val.net)],
            eval_metric='l2', callbacks=[lgb.early_stopping(80, verbose=False)])
    print(f'早停于第 {reg.best_iteration_} 棵树')

    te_pred = reg.predict(te[feat_cols])
    ic = np.corrcoef(te_pred, te.net)[0, 1]
    print(f'样本外 预测 vs 实际 相关系数 IC = {ic:.3f}')

    filter_curve(te, te_pred, '回归模型（预测净收益）')
    quintiles(te, te_pred)

    imp = pd.Series(reg.feature_importances_, index=feat_cols).sort_values(ascending=False)
    print('\n特征重要性 top 12：')
    for k, v in imp.head(12).items():
        print(f'  {k:<14}{v:>6.0f}')

    # 保守检查：模型分数在训练段是否也单调（防止只在测试段碰巧有效）
    print('\n训练段五分组（检查模型是否只是在测试段碰巧有效）：')
    quintiles(fit, reg.predict(fit[feat_cols]))

    reg.booster_.save_model(str(HERE / 'gbdt_4h.txt'))
    print(f'\n模型已存 gbdt_4h.txt（{len(feat_cols)} 个特征）')


if __name__ == '__main__':
    main()
