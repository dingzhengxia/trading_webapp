#!/usr/bin/env python3
"""只读诊断：某个币的市价平仓到底是谁下的、为什么。

背景
----
全后端只有 `app/protection/exits.py::_market_reduce_and_confirm` 会下「普通市价单」
（币安 App 里显示为「市价委托」+「只减仓：是」）。它的调用方只有三类：

  1. 灾难线击穿   reason = "击穿灾难线 {price}"        （risk_model.decide → type=exit）
  2. 黑天鹅/放量  reason = "{原因} 紧急市价全平"        （engine 紧急止损）
  3. 抄底专属线   reason = "... 紧急市价全平"           （t3_waived + bottom_fish_sl）
  4. 减仓保底     reason = "{原因}(保底市价)"           （限价+吃单价都未成交后兜底）

每次执行都会写一条 `protection_events`（kind=exit/reduce），成功全平后还会删掉
`protection_positions` 里该仓的 plan —— 所以本脚本优先打印事件轨迹，plan 只作旁证。

用法
----
    # 服务器上（宿主机路径，不需要进容器）
    python tools/diagnose_exit.py --db /root/config/data/app.db --symbol TQQQ

    # 指定要复盘的时间点，会额外标出 ±10 分钟内的事件
    python tools/diagnose_exit.py --symbol TQQQ --at "2026-11-13 22:44"

    # 容器内
    docker exec my-trading-container python /app/../tools/diagnose_exit.py ...  # 或直接挂载

脚本只 SELECT，不写库、不下单。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

CANDIDATE_DBS = (
    '/root/config/data/app.db',   # 生产（宿主机挂载目录）
    '/app/data/app.db',           # 容器内
    'data/app.db',                # 仓库内本地副本
)

EXIT_REASONS = {
    '击穿灾难线': '灾难线（结构 T3 再往下 disaster_atr_buffer 倍 ATR）被实时价击穿，'
                 '规则是「不确认、不等收盘，直接全平」',
    '紧急市价全平': '黑天鹅/放量加速/抄底专属线触发，属于紧急止损通道',
    '保底市价': '减仓单（maker 挂单 → 吃单价）都没成交，最后一级市价兜底',
}


def _resolve_db(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            sys.exit(f'找不到数据库：{path}')
        return path
    for cand in CANDIDATE_DBS:
        if os.path.exists(cand):
            return Path(cand)
    sys.exit('未自动找到 app.db，请用 --db 指定（生产一般是 /root/config/data/app.db）')


def _rows(conn: sqlite3.Connection, table: str) -> list[tuple[str, dict]]:
    try:
        raw = conn.execute(f'SELECT key, value FROM {table}').fetchall()
    except sqlite3.Error as exc:
        print(f'  (读取 {table} 失败：{exc})')
        return []
    out = []
    for key, value in raw:
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            out.append((key, parsed))
    return out


def _fmt_ts(ts: float) -> str:
    try:
        return dt.datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError, OSError):
        return '??'


def _parse_at(text: str | None) -> float | None:
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%m-%d %H:%M:%S', '%m-%d %H:%M'):
        try:
            parsed = dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.year == 1900:
            parsed = parsed.replace(year=dt.date.today().year)
        return parsed.timestamp()
    sys.exit(f'--at 时间格式不认识：{text}（示例："2026-11-13 22:44"）')


def main() -> None:
    ap = argparse.ArgumentParser(description='只读诊断市价平仓的决策依据')
    ap.add_argument('--db', help='app.db 路径（默认自动探测生产/容器/本地）')
    ap.add_argument('--symbol', required=True, help='币种，支持部分匹配，如 TQQQ')
    ap.add_argument('--at', help='复盘时间点，如 "2026-11-13 22:44"（本地时区）')
    ap.add_argument('--window', type=int, default=10, help='--at 前后多少分钟内高亮（默认 10）')
    ap.add_argument('--limit', type=int, default=25, help='事件最多打印多少条（默认 25）')
    args = ap.parse_args()

    db = _resolve_db(args.db)
    needle = args.symbol.upper()
    at_ts = _parse_at(args.at)

    print(f'数据库：{db}')
    print(f'币种匹配：*{needle}*')
    if at_ts:
        print(f'复盘时间点：{_fmt_ts(at_ts)}（前后 {args.window} 分钟高亮）')
    print()

    conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        # ---------------- 1. 保护事件轨迹 ----------------
        events = [e for _, e in _rows(conn, 'protection_events')
                  if needle in str(e.get('symbol', '')).upper()]
        events.sort(key=lambda e: float(e.get('ts') or 0))

        print(f'== 保护事件（{len(events)} 条，最新在后） ==')
        if not events:
            print('  （没有该币的保护事件：说明这次平仓不是仓位保护引擎干的，往下看 open_history）')
        for e in events[-args.limit:]:
            ts = float(e.get('ts') or 0)
            mark = ''
            if at_ts and abs(ts - at_ts) <= args.window * 60:
                mark = '  <<< 复盘窗口内'
            print(f"  {_fmt_ts(ts)}  {e.get('side','?'):5s} {e.get('kind','?'):6s} "
                  f"{e.get('level','?'):7s} {e.get('message','')}{mark}")
            for key, label in (('ratio', '减仓比例'), ('after', '剩余张数'), ('tiers', '档位'),
                               ('tps', '止盈档')):
                if key in e:
                    print(f'      {label}: {e[key]}')
        print()

        # ---------------- 2. 当前保护计划（已平仓会被删） ----------------
        plans = [p for _, p in _rows(conn, 'protection_positions')
                 if needle in str(p.get('symbol', '')).upper()
                 or needle in str(p.get('full_symbol', '')).upper()]
        print('== 当前保护计划 ==')
        if not plans:
            print('  （没有记录：仓位已平，账本按设计已删除该行；看事件轨迹即可）')
        for p in plans:
            plan = p.get('plan') or {}
            print(f"  方向={p.get('side')} 基准张数={p.get('base_contracts')} "
                  f"周期={p.get('risk_cycle_id')}")
            if plan:
                print(f"    开仓价={plan.get('entry')} 风险R={plan.get('risk')} "
                      f"ATR={plan.get('atr_at_plan')}")
                print(f"    四档线={plan.get('levels')} 灾难线={plan.get('disaster_stop')}")
                print(f"    已执行档={p.get('tiers_done')} 已止盈={p.get('tp_done')} "
                      f"重估次数={plan.get('replan_count')}")
        print()

        # ---------------- 3. 开仓台账（谁开的、开了多少） ----------------
        history = []
        for _, h in _rows(conn, 'open_history'):
            blob = json.dumps(h, ensure_ascii=False)
            if needle in blob.upper():
                history.append(h)
        history.sort(key=lambda h: float(h.get('ts') or h.get('timestamp') or 0))
        print(f'== 开仓记录（匹配 {len(history)} 条，最新在后） ==')
        if not history:
            print('  （无匹配）')
        for h in history[-10:]:
            print('  ' + json.dumps(h, ensure_ascii=False)[:400])
        print()

        # ---------------- 4. 结论：命中的是哪条规则 ----------------
        print('== 结论 ==')
        if not events:
            print('  该币无保护事件。市价单只可能来自保护引擎，若确实无事件，'
                  '请把容器日志（下面命令）发我。')
        else:
            hit = [e for e in events if at_ts and abs(float(e.get('ts') or 0) - at_ts)
                   <= args.window * 60 and e.get('kind') in ('exit', 'reduce')]
            if hit:
                for e in hit:
                    msg = str(e.get('message', ''))
                    print(f"  {_fmt_ts(float(e.get('ts') or 0))} → {msg}")
                    for token, explain in EXIT_REASONS.items():
                        if token in msg:
                            print(f'    规则：{explain}')
            else:
                print('  复盘窗口内没有 exit/reduce 事件，请核对 --at 时区或加大 --window。')
    finally:
        conn.close()

    print()
    print('补充证据（在服务器执行，二选一）：')
    print('  docker logs my-trading-container --since 2026-11-13T14:40:00 '
          '--until 2026-11-13T14:50:00 2>&1 | grep -i TQQQ')
    print('  # 容器一般跑 UTC，上面的时间是北京时间 22:44 减 8 小时')


if __name__ == '__main__':
    main()
