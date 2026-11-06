# backend/app/signals/analysis/__init__.py
"""从 monitor/app/analysis 复制的纯技术分析模块。

仅做了导入改造（相对导入、移除 monitor app.* 顶层依赖与 notification_service），
策略判定逻辑未做任何改动（MERGE_PLAN §11）。
"""
