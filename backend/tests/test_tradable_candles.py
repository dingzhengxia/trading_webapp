"""静默 K 线剔除：ATR / 均量只许用「有真实交易」的 K 线计算。

背景：股票代币（AAPL/TQQQ/NVDA…）在美股休市时段仍 24/7 报价，产出「量极小 +
振幅极小」的 K 线。若把它们算进 ATR，ATR 会被压到真实值的 1/4~1/6，而 ATR 决定
档位缓冲、最小间距与灾难线——2026-11-13 TQQQ 的档位线因此挤在 -1.5%~-1.9%、
灾难线只在 -2.5%，一次 1.8% 的正常回落就逐档触发直至市价全平。

约定（双条件同时满足才算静默，缺一不可）：
· 只看量会误删「缩量插针」——量小但振幅大是有效信息；
· 只看振幅会误删「低波动整理期」——振幅小但量正常也是有效信息。
"""
from __future__ import annotations

import pytest

from app.protection.market_data import _atr_from_df, _tradable_df

COLS = ["timestamp", "open", "high", "low", "close", "volume"]

CONF = {
    'tradable_volume_ratio': 0.10,
    'tradable_range_ratio': 0.25,
    'tradable_min_bars': 16,
}

# 2h K 线。振幅 = high - low
ACTIVE = (100.0, 100.8, 99.2, 100.2, 1000.0)     # 盘中：振幅 1.6、量正常
IDLE = (100.0, 100.0, 100.0, 100.0, 0.0)         # 休市：振幅 0、零成交
QUIET = (100.0, 100.02, 99.98, 100.0, 900.0)     # 低波动整理：振幅 0.04、量 90%
THIN = (100.0, 103.0, 97.0, 100.5, 60.0)         # 缩量插针：振幅 6、量 6%
PRE = (100.0, 100.05, 99.95, 100.0, 5.0)         # 盘前微成交：振幅 0.1、量 5


def _df(spec):
    import pandas as pd
    return pd.DataFrame(
        [(i, *b) for i, b in enumerate(spec)], columns=COLS
    )


def _stock_spec(days=12):
    """美股节奏：每天 3 根盘中 2h + 7 根休市 2h。"""
    spec = []
    for _ in range(days):
        spec += [ACTIVE] * 3 + [IDLE] * 7
    return spec


def test_stock_idle_candles_are_dropped_and_atr_recovers():
    """股票代币：休市 K 线被剔除，ATR 从被压低的 0.36% 恢复到真实的 1.6%。"""
    df = _df(_stock_spec())
    kept = _tradable_df(df, CONF, 14)

    assert len(kept) == 36, f'应只保留 30% 的盘中 K 线，实际 {len(kept)}'
    assert (kept["volume"] > 0).all()

    raw = _atr_from_df(df, 14)
    fixed = _atr_from_df(kept, 14)
    assert fixed > raw * 3.0, f'ATR 未被修正: 旧={raw:.4f} 新={fixed:.4f}'
    assert fixed == pytest.approx(1.6, rel=1e-9), f'剔除后 ATR 应等于盘中真实振幅，实际 {fixed}'


def test_crypto_continuous_market_is_untouched():
    """加密 24h 连续交易：一根都不该被剔除，ATR 必须完全不变。"""
    df = _df([ACTIVE] * 120)
    kept = _tradable_df(df, CONF, 14)

    assert len(kept) == len(df)
    assert _atr_from_df(kept, 14) == _atr_from_df(df, 14)


def test_low_volatility_range_keeps_normal_volume():
    """低波动整理期：振幅极小但量正常，属真实行情，不得剔除。

    这是「只按振幅过滤」会犯的错：把整理期剔掉，ATR 只由高波动段构成，
    波动率被人为放大，保护线整体外移。
    """
    spec = [ACTIVE] * 30 + [QUIET] * 60 + [ACTIVE] * 30
    kept = _tradable_df(_df(spec), CONF, 14)

    assert len(kept) == len(spec)
    assert _atr_from_df(kept, 14) == _atr_from_df(_df(spec), 14)


def test_thin_volume_wick_is_kept():
    """缩量插针：量只有 6% 但振幅 6%，是有效信息，不得剔除。

    这是「只按量过滤」会犯的错：把插针剔掉，ATR 会低估真实风险。
    """
    spec = [ACTIVE] * 114 + [THIN] * 6
    kept = _tradable_df(_df(spec), CONF, 14)

    assert len(kept) == len(spec)


def test_all_idle_market_yields_no_usable_bars():
    """长期停牌/长休市：全部静默时返回空序列，调用方据此不判定。

    绝不能退回原序列——那等于用污染数据算 ATR，然后照常开枪。
    """
    df = _df([IDLE] * 120)
    kept = _tradable_df(df, CONF, 14)

    assert len(kept) == 0


def test_reference_uses_active_bars_not_median():
    """静默 K 线占多数时，基准仍必须由有成交的 K 线决定。

    59 根里 50 根零成交：若直接用全体 75 分位，基准会被算成 0，过滤整体失效。
    """
    spec = [IDLE] * 50 + [PRE] * 9
    kept = _tradable_df(_df(spec), CONF, 14)

    # 盘前微成交相对「有成交集合」并不算静默，9 根应全部保留
    assert len(kept) == 9


def test_short_history_is_not_filtered():
    """样本不足 2×min_bars 时分位数不可靠，原样返回。"""
    df = _df([ACTIVE] * 20 + [IDLE] * 10)
    kept = _tradable_df(df, CONF, 14)

    assert len(kept) == len(df)
