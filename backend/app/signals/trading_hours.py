# backend/app/signals/trading_hours.py
"""币股（TradFi 代币化标的）交易时段判定 + K 线会话过滤。

背景：Binance USDⓈ-M 上的代币化标的（美股/韩股/港股/A股/贵金属能源等）7x24
都有 K 线，但标的本身只在所属市场常规时段有真实成交——非交易时段的 K 线是
「死线」，指标计算失真、信号全是噪音（设置页反馈：夜间刷屏）。

市场识别（全自动，无需手工名单）：Binance exchangeInfo 的 underlyingType
（COIN=加密币、EQUITY=美股、KR_EQUITY=韩股、HK_EQUITY=港股、CN_EQUITY=A股、
PREMARKET=Pre-IPO、COMMODITY=贵金属/能源、INDEX/FX=指数外汇）。ccxt 的
market['info'] 保留原始字段，直接读取。商品/指数/外汇的价格发现集中在美国
时段，统一映射到 US 会话（周末同样不开盘）。

三层闸门（按 user_settings 的 signal_tradfi_session_* 热更新）：
1. 扫描闸门 scan_allowed：非交易时段、周末、以及开盘后 warmup 分钟内
   （「开盘一小时以后才开始计算」）→ 不拉 K 线、不计算、不产生/推送信号；
2. K 线会话过滤 filter_session_candles：计算指标前剔除非交易时段的 K 线
   （按 K 线开盘时间判定，等价 TradingView 的 session 过滤）；
3. 时段时间用 IANA 时区（America/New_York 等），自动处理夏令时；
   节假日不另外排除（近似为周末+常规时段）。
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from zoneinfo import ZoneInfo

# Binance underlyingType -> 市场键
MARKET_BY_UNDERLYING_TYPE = {
    'EQUITY': 'US',
    'PREMARKET': 'US',
    'KR_EQUITY': 'KR',
    'HK_EQUITY': 'HK',
    'CN_EQUITY': 'CN',
    # 商品/指数/外汇按美股时段处理（价格发现集中在美国时段，周末休市）
    'COMMODITY': 'US',
    'INDEX': 'US',
    'FX': 'US',
}

# 标准常规交易时段：windows 为当地「日内分钟」的半开区间 [start, end)，
# weekday 0=周一……4=周五；周六周日一律休市。
DEFAULT_SESSIONS: Dict[str, Dict[str, Any]] = {
    'US': {'label': '美股', 'tz': ZoneInfo('America/New_York'),
           'windows': ((570, 960),)},                              # 09:30-16:00
    'KR': {'label': '韩股', 'tz': ZoneInfo('Asia/Seoul'),
           'windows': ((540, 930),)},                              # 09:00-15:30
    'HK': {'label': '港股', 'tz': ZoneInfo('Asia/Hong_Kong'),
           'windows': ((570, 720), (780, 960))},                   # 09:30-12:00, 13:00-16:00
    'CN': {'label': 'A股', 'tz': ZoneInfo('Asia/Shanghai'),
           'windows': ((570, 690), (780, 900))},                   # 09:30-11:30, 13:00-15:00
}


def _merged_sessions(overrides: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """内置时段 + settings 覆盖（signal_tradfi_session_windows）合并。"""
    sessions = {key: {**conf, 'windows': tuple(tuple(w) for w in conf['windows'])}
                for key, conf in DEFAULT_SESSIONS.items()}
    for key, windows in (overrides or {}).items():
        conf = sessions.get(str(key).upper())
        if not conf or not windows:
            continue
        try:
            conf['windows'] = tuple((int(w[0]), int(w[1])) for w in windows)
        except (TypeError, ValueError, IndexError):
            continue  # 非法覆盖值：安全回退内置默认
    return sessions


def tradfi_market(full_symbol: str, markets: Optional[Mapping[str, Any]]) -> Optional[str]:
    """识别代币化标的市场（'US'/'KR'/...）；加密币或元数据缺失返回 None。

    ccxt market dict 的 info 保留 exchangeInfo 原始字段（underlyingType/
    underlyingSubType）；老缓存没有 info 时退回统一形态判断，绝不误伤加密币。
    """
    market = (markets or {}).get(full_symbol)
    if not isinstance(market, dict):
        return None
    info = market.get('info') if isinstance(market.get('info'), dict) else {}
    underlying = str(info.get('underlyingType') or market.get('underlyingType') or '').upper()
    mapped = MARKET_BY_UNDERLYING_TYPE.get(underlying)
    if mapped:
        return mapped
    sub_types = info.get('underlyingSubType') or []
    if any(str(x).upper() == 'TRADFI' for x in sub_types):
        return 'US'  # 兜底：TradFi 标的统一按美股时段
    return None


def _in_windows(conf: Mapping[str, Any], local: datetime) -> bool:
    if local.weekday() >= 5:
        return False
    minute_of_day = local.hour * 60 + local.minute
    return any(start <= minute_of_day < end for start, end in conf['windows'])


def _localize(market_key: str, dt: Optional[datetime],
              overrides: Optional[Mapping[str, Any]]):
    """解析出 (时段配置, 当地时间)；未知市场返回 (None, None)（按不过滤处理）。"""
    conf = _merged_sessions(overrides).get(market_key)
    if not conf:
        return None, None
    return conf, (dt or datetime.now(timezone.utc)).astimezone(conf['tz'])


def in_session(market_key: str, dt: Optional[datetime] = None,
               overrides: Optional[Mapping[str, Any]] = None) -> bool:
    """某市场在给定时刻是否处于常规交易时段（dt 缺省取当前 UTC 时间）。"""
    conf, local = _localize(market_key, dt, overrides)
    return True if conf is None else _in_windows(conf, local)


def _since_open(conf: Mapping[str, Any], local: datetime) -> Optional[int]:
    """距当日开盘的分钟数；休市日/未开盘返回 None。"""
    if local.weekday() >= 5:
        return None
    open_start = conf['windows'][0][0]
    open_dt = local.replace(hour=open_start // 60, minute=open_start % 60,
                            second=0, microsecond=0)
    if local < open_dt:
        return None
    return int((local - open_dt).total_seconds() // 60)


def minutes_since_open(market_key: str, dt: Optional[datetime] = None,
                       overrides: Optional[Mapping[str, Any]] = None) -> Optional[int]:
    """距当日开盘的分钟数；休市日/未开盘/未知市场返回 None。"""
    conf, local = _localize(market_key, dt, overrides)
    return None if conf is None else _since_open(conf, local)


def scan_allowed(market_key: str, warmup_minutes: int = 60,
                 overrides: Optional[Mapping[str, Any]] = None,
                 dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """扫描闸门：交易时段内且已过开盘预热期才允许计算/推送。

    返回 (是否允许, 原因说明)；原因用于扫描日志。未知市场不过滤
    （宁可多扫也不误杀，与 in_session 口径一致）。
    """
    conf, local = _localize(market_key, dt, overrides)
    if conf is None:
        return True, ''
    if not _in_windows(conf, local):
        return False, '非交易时段'
    since_open = _since_open(conf, local)
    if since_open is None:
        return False, '非交易时段'
    warmup = max(0, int(warmup_minutes or 0))
    if since_open < warmup:
        return False, f'开盘预热中（{since_open}/{warmup} 分钟）'
    return True, ''


def filter_session_candles(rows: Sequence[Sequence[Any]], market_key: str,
                           overrides: Optional[Mapping[str, Any]] = None) -> List[Sequence[Any]]:
    """剔除非交易时段的 K 线（按开盘时间判定），返回保留的行。

    - rows 为 ohlcv 行 [timestamp_ms, open, high, low, close, volume]；
    - 非交易时段整段剔除后，指标看到的就是「连续交易时段」K 线，
      MA/ATR 等不再被夜间死线稀释；
    - 未知市场或空输入原样返回。
    """
    conf = _merged_sessions(overrides).get(market_key)
    if not rows or not conf:
        return list(rows or [])
    kept: List[Sequence[Any]] = []
    for row in rows:
        try:
            ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError, IndexError):
            kept.append(row)  # 时间异常的行保留，交给下游策略自行处理
            continue
        if _in_windows(conf, ts.astimezone(conf['tz'])):
            kept.append(row)
    return kept
