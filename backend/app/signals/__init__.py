# backend/app/signals/__init__.py
"""信号引擎包（Phase 2：monitor 合并）。

模块组成：
- runtime:       冷却状态持久化（SQLite signal_state 表）、热门币种缓存、信号发射队列、时间工具
- signal_store:  线程安全信号环形缓冲 + 扫描统计
- market_data:   行情层（tickers/ohlcv/funding 缓存 + RestGuardian + TopN 选择）
- scanner:       异步扫描循环 + 手动触发
- auto_trader:   信号过滤器 + 自动开仓调度
- analysis/:     从 monitor 复制的纯技术分析模块（策略判定逻辑未改动）
"""
