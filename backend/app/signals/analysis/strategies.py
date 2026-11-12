# --- START OF FILE analysis/strategies.py ---
# 从 monitor/app/analysis/strategies.py 复制改造（MERGE_PLAN §3.1）：
# - 导入改为包内相对导入，删除 monitor 的 app.* 顶层依赖与 notification_service；
# - _prepare_and_send_notification 改为冷却/过滤后调用 runtime.emit_signal(...)；
# - 为每个策略补充结构化 strategy_name / direction 元数据（price 由统一出口从 df 提取）；
# - 所有策略判定逻辑未做任何改动。
from datetime import datetime, timezone
from loguru import logger
import pandas as pd
import pandas_ta as pta

from .order_blocks import find_lux_order_blocks, find_flux_order_blocks
from ..runtime import alerted_states, save_alert_states, emit_signal
from ..runtime import calculate_cooldown_time
from .trend import get_current_trend, timeframe_to_minutes
from .levels import find_market_structure_swings
from .channels import detect_regression_channel
from .indicators import (
    get_dynamic_volume_multiplier, get_dynamic_atr_multiplier, is_realtime_volume_over,
    get_dynamic_consecutive_candles
)


def _get_params_for_timeframe(base_params: dict, timeframe: str) -> dict:
    final_params = base_params.copy()
    overrides = base_params.get("overrides_by_timeframe", {})
    if timeframe in overrides:
        final_params.update(overrides[timeframe])
    return final_params


def _prepare_and_send_notification(config, symbol, timeframe, df, signal_info):
    """统一信号出口：冷却/成交量/趋势过滤后构造结构化信号并入队。

    结构化元数据（MERGE_PLAN §3.1）：
    - strategy_name / strategy_index / direction 由各策略调用前写入 signal_info；
    - price 统一从这里从 df 取当前收盘价（df 为 None 时为 None，如资金费率告警）。
    """
    now_utc = datetime.now(timezone.utc)
    tf_minutes = timeframe_to_minutes(timeframe)
    params = config['strategy_params']
    market_settings = config.get('market_settings', {})

    alert_key = signal_info['alert_key']
    if alerted_states.get(alert_key) and now_utc < alerted_states[alert_key]:
        return

    vol_text = ""
    volume_label = ""
    trend_status, trend_emoji = "趋势未知", "📊"

    price = None
    volume_ratio = None
    bar_ts = None
    if df is not None:
        static_bases = market_settings.get('static_symbols', [])
        symbol_base = symbol.split('/')[0].split(':')[0]
        is_static_symbol = symbol_base in static_bases

        exemption_enabled_for_this_strategy = signal_info.get('exempt_static_on_volume', False)
        original_volume_confirm = signal_info.get('volume_must_confirm', False)
        final_volume_confirm = False if (
                exemption_enabled_for_this_strategy and is_static_symbol) else original_volume_confirm
        # volume_filter_mode='record'：量能只写进信号记录（volume_ratio），不再拦截信号。
        # 依据回测：量能门槛砍掉的多是后续赚钱的那批，作为闸门没有筛选价值（docs/strategy-validation）。
        volume_filter_mode = str((config.get('app_settings') or {}).get('volume_filter_mode', 'block')).lower()

        dynamic_multiplier = get_dynamic_volume_multiplier(symbol, config, signal_info.get('fallback_multiplier', 1.5))

        # 为了兼容不同的策略，获取成交量周期参数
        vol_ma_period = 20
        if 'level_breakout' in params:
            raw_lb = params['level_breakout'][0] if isinstance(params['level_breakout'], list) else params[
                'level_breakout']
            vol_ma_period = raw_lb.get('volume_ma_period', 20)

        is_vol_over, v_text, actual_vol_ratio = is_realtime_volume_over(
            df, tf_minutes, vol_ma_period, dynamic_multiplier
        )
        volume_ratio = actual_vol_ratio

        if final_volume_confirm and not is_vol_over and volume_filter_mode != 'record':
            logger.debug(f"[{symbol}|{timeframe}] 信号 '{signal_info.get('log_name', 'N/A')}' 因成交量不足被过滤。")
            return

        # 标题只在放量时带标签；量能不足的倍数放在正文「成交量分析」里，避免「缩量(2.7x)强势突破」这类自相矛盾文案
        volume_label = f"放量({actual_vol_ratio:.1f}x) " if is_vol_over else ""
        if v_text and signal_info.get('always_show_volume', True):
            vol_text = f"\n---\n{v_text}"

        trend_status, trend_emoji = get_current_trend(df.copy(), timeframe, params)

        # 结构化价格：当前收盘价；bar_ts 供结果跟踪对齐 K 线
        try:
            price = float(df.iloc[-1]['close'])
            bar_ts = int(df.iloc[-1]['timestamp'])
        except (KeyError, IndexError, TypeError, ValueError):
            price = None

    title = signal_info['title_template'].format(vol_label=volume_label).replace("  ", " ").strip()

    message_data = signal_info.get('template_data', {})
    message_data['trend_message'] = f"**当前趋势**: {trend_emoji} {trend_status}\n\n"
    message_data['vol_text'] = vol_text

    message = signal_info['message_template'].format(**message_data)

    # 发射结构化信号（线程安全入队，由 SignalStore 异步消费落库并触发自动开仓）
    emit_signal(
        symbol=symbol,
        full_symbol=symbol,
        timeframe=timeframe,
        strategy=signal_info.get('strategy_name', 'unknown'),
        strategy_index=signal_info.get('strategy_index', 0),
        direction=signal_info.get('direction', 'neutral'),
        price=price,
        volume_ratio=volume_ratio,
        title=title,
        message=message,
        dedupe_key=alert_key,
        bar_ts=bar_ts,
    )

    if signal_info.get('cooldown_logic') == 'align_to_period_end':
        alerted_states[alert_key] = calculate_cooldown_time(tf_minutes, align_to_period_end=True)
    else:
        cooldown_minutes = tf_minutes * signal_info.get('cooldown_mult', 1)
        alerted_states[alert_key] = calculate_cooldown_time(cooldown_minutes)

    save_alert_states()


def check_level_breakout(symbol, timeframe, config, df, breakout_params, config_index=0):
    """
    实战波段前高/前低 (Swing Pivots) 结构破坏判断
    """
    try:
        level_conf = breakout_params.get('level_detection', {})
        df.ta.atr(length=breakout_params.get('atr_period', 14), append=True)
        df_cleaned = df.dropna().reset_index(drop=True)
        if len(df_cleaned) < 3: return
        current = df_cleaned.iloc[-1]
        prev = df_cleaned.iloc[-2]
        all_levels = []

        # 1. 寻找实战波段前高前低
        if level_conf.get('swing_pivots', {}).get('enabled', True):
            left_bars = level_conf.get('swing_pivots', {}).get('left_bars', 7)
            right_bars = level_conf.get('swing_pivots', {}).get('right_bars', 7)
            swings = find_market_structure_swings(df.copy(), left_bars, right_bars)
            all_levels.extend(swings)

        # 2. 寻找近期震荡箱体边界
        if level_conf.get('rolling_pivots', {}).get('enabled', True):
            period = breakout_params.get('breakout_period', 120)
            if len(df_cleaned) > period:
                lookback_df = df_cleaned.iloc[-period - 2:-2]
                if not lookback_df.empty:
                    all_levels.append({'level': lookback_df['high'].max(), 'type': f'箱体顶部(近{period}根K线)'})
                    all_levels.append({'level': lookback_df['low'].min(), 'type': f'箱体底部(近{period}根K线)'})

        if not all_levels: return
        prev_price = prev['close']

        # V=== 核心逻辑修复：强制符合人类视觉习惯 ===V
        # 阻力位：只允许“前高”或“箱体顶部”充当阻力。如果上方出现“前低”，直接无视。
        resistances = sorted([lvl for lvl in all_levels if
                              lvl['level'] > prev_price and '前低' not in lvl.get('type', '') and '底部' not in lvl.get(
                                  'type', '')], key=lambda x: x['level'])

        # 支撑位：只允许“前低”或“箱体底部”充当支撑。如果下方出现“前高”，直接无视。
        supports = sorted([lvl for lvl in all_levels if
                           lvl['level'] < prev_price and '前高' not in lvl.get('type', '') and '顶部' not in lvl.get(
                               'type', '')], key=lambda x: x['level'], reverse=True)
        # ^========================================^

        if resistances or supports:
            res_str = ", ".join([f"{r['level']:.2f}({r.get('type', 'N/A')})" for r in resistances[:2]])
            sup_str = ", ".join([f"{s['level']:.2f}({s.get('type', 'N/A')})" for s in supports[:2]])
            logger.debug(
                f"[{symbol}|{timeframe}] 🎯 实战支撑阻力 -> 当前价: {current['close']:.2f} | 阻力: [{res_str}] | 支撑: [{sup_str}]")

        atr_val = current.get(f"ATRr_{breakout_params.get('atr_period', 14)}", 0.0)
        if atr_val == 0: return
        atr_break_buffer = atr_val * breakout_params.get('atr_multiplier_breakout', 0.1)

        # --- 阻力位逻辑 (向上突破) ---
        if resistances:
            closest_res = resistances[0]
            cond_below_res = prev['close'] < closest_res['level']
            is_breakout = cond_below_res and current['close'] > closest_res['level'] + atr_break_buffer
            is_testing_res = cond_below_res and current['high'] >= closest_res['level'] and not is_breakout
            original_type = closest_res.get('type', '阻力位')

            if original_type == '近期前高(Swing High)':
                action_desc, structure_desc, signal_title, test_title = "强势突破近期前高", "构成多头市场结构破坏 (Bullish BOS)，趋势可能延续", f"🚨 {{vol_label}}多头结构破坏(BOS): {symbol} ({timeframe})", f"⚠️ 测试上方前高: {symbol} ({timeframe})"
            else:
                action_desc, structure_desc, signal_title, test_title = f"强势突破了关键压力 ({original_type})", "多头动能转强", f"🚨 {{vol_label}}突破关键压力: {symbol} ({timeframe})", f"⚠️ 测试上方压力: {symbol} ({timeframe})"

            if is_breakout:
                signal_info = {
                    'log_name': 'Level Breakout BOS',
                    'strategy_name': 'level_breakout', 'strategy_index': config_index,
                    'direction': 'long',  # BOS 向上 / 突破阻力 -> long
                    'alert_key': f"{symbol}_{timeframe}_BOS_UP_{config_index}_{current['timestamp']}",
                    'volume_must_confirm': breakout_params.get('volume_confirm', True),
                    'fallback_multiplier': breakout_params.get('volume_multiplier', 1.5),
                    'title_template': signal_title,
                    'message_template': (
                            "{trend_message}**信号**: **" + action_desc + "！**\n\n**形态学**: 价格突破了 `{original_type}`，{structure_desc}。\n> **阻力价位**: `{closest_res[level]:.4f}`\n> **突破价格**: `{current[close]:.4f}`\n\n这是典型的右侧看涨信号。\n\n{vol_text}"),
                    # 原 monitor 版本 template_data 为空但模板引用了这些键，
                    # format 抛 KeyError 导致该分支信号永远无法发出（通知路径潜在 bug 修复）
                    'template_data': {'original_type': original_type, 'structure_desc': structure_desc,
                                      'closest_res': closest_res, 'current': current},
                    'cooldown_mult': 1
                }
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
            elif is_testing_res and breakout_params.get('alert_on_test', True):
                signal_info = {
                    'log_name': 'Level Testing Res',
                    'strategy_name': 'level_breakout', 'strategy_index': config_index,
                    'direction': 'neutral',  # 测试阻力 -> neutral
                    'alert_key': f"{symbol}_{timeframe}_testing_res_{config_index}_{current['timestamp']}",
                    'volume_must_confirm': breakout_params.get('volume_confirm', True), 'title_template': test_title,
                    'message_template': (
                        "{trend_message}**信号**: **价格正在摸顶/插针试探上方阻力**。\n\n**形态学**: 价格最高点触及了 `{original_type}`。\n> **阻力价位**: `{closest_res[level]:.4f}`\n> **当前最高价**: `{current[high]:.4f}`\n请留意是否形成受阻回落，或蓄力完成突破。\n\n{vol_text}"),
                    'template_data': {'original_type': original_type, 'closest_res': closest_res,
                                      'current': current},
                    'cooldown_mult': 1, 'always_show_volume': True
                }
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)

        # --- 支撑位逻辑 (向下砸穿) ---
        if supports:
            closest_sup = supports[0]
            cond_above_sup = prev['close'] > closest_sup['level']
            is_breakdown = cond_above_sup and current['close'] < closest_sup['level'] - atr_break_buffer
            is_testing_sup = cond_above_sup and current['low'] <= closest_sup['level'] and not is_breakdown
            original_type = closest_sup.get('type', '支撑位')

            if original_type == '近期前低(Swing Low)':
                action_desc, structure_desc, signal_title, test_title = "有效跌破近期前低", "构成空头市场结构破坏 (Bearish BOS)，趋势可能反转/延续", f"📉 {{vol_label}}空头结构破坏(BOS): {symbol} ({timeframe})", f"💡 测试下方前低: {symbol} ({timeframe})"
            else:
                action_desc, structure_desc, signal_title, test_title = f"有效跌破了关键支撑 ({original_type})", "空头动能转强", f"📉 {{vol_label}}跌破关键支撑: {symbol} ({timeframe})", f"💡 测试下方支撑: {symbol} ({timeframe})"

            if is_breakdown:
                signal_info = {
                    'log_name': 'Level Breakdown BOS',
                    'strategy_name': 'level_breakout', 'strategy_index': config_index,
                    'direction': 'short',  # BOS 向下 / 跌破支撑 -> short
                    'alert_key': f"{symbol}_{timeframe}_BOS_DOWN_{config_index}_{current['timestamp']}",
                    'volume_must_confirm': breakout_params.get('volume_confirm', True),
                    'fallback_multiplier': breakout_params.get('volume_multiplier', 1.5),
                    'title_template': signal_title,
                    'message_template': (
                            "{trend_message}**信号**: **" + action_desc + "！**\n\n**形态学**: 价格跌破了 `{original_type}`，{structure_desc}。\n> **支撑价位**: `{closest_sup[level]:.4f}`\n> **跌破价格**: `{current[close]:.4f}`\n\n这是典型的右侧看跌/破位离场信号。\n\n{vol_text}"),
                    # 同上：补齐模板所需的键（原 monitor 版本 template_data 为空）
                    'template_data': {'original_type': original_type, 'structure_desc': structure_desc,
                                      'closest_sup': closest_sup, 'current': current},
                    'cooldown_mult': 1
                }
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
            elif is_testing_sup and breakout_params.get('alert_on_test', True):
                signal_info = {
                    'log_name': 'Level Testing Sup',
                    'strategy_name': 'level_breakout', 'strategy_index': config_index,
                    'direction': 'neutral',  # 测试支撑 -> neutral
                    'alert_key': f"{symbol}_{timeframe}_testing_sup_{config_index}_{current['timestamp']}",
                    'volume_must_confirm': breakout_params.get('volume_confirm', True), 'title_template': test_title,
                    'message_template': (
                        "{trend_message}**信号**: **价格插针/试探关键支撑**。\n\n**形态学**: 价格最低点触及了 `{original_type}`。\n> **支撑价位**: `{closest_sup[level]:.4f}`\n> **当前最低价**: `{current[low]:.4f}`\n请留意是否企稳反弹，或无力防守破位下行。\n\n{vol_text}"),
                    'template_data': {'original_type': original_type, 'closest_sup': closest_sup,
                                      'current': current},
                    'cooldown_mult': 1, 'always_show_volume': True
                }
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ 在 {symbol} {timeframe} (关键位突破) 中出错: {e}", exc_info=True)


def _check_ob_base(symbol, timeframe, config, df, ob_params, config_index, algo_name, bull_ob, bear_ob,
                   algo_prefix, strategy_key):
    """
    OB 核心判断逻辑 (双引擎共用此大脑，带阻力支撑互换逻辑)
    """
    try:
        all_obs = [ob for ob in [bear_ob, bull_ob] if ob]
        if not all_obs: return
        current, prev = df.iloc[-1], df.iloc[-2]

        ob_logs = [f"{'熊市OB' if ob['type'] == 'bearish' else '牛市OB'}: [{ob['bottom']:.4f}-{ob['top']:.4f}]" for ob
                   in all_obs]
        logger.debug(f"[{symbol}|{timeframe}] 🧱 {algo_name} 计算完毕 -> {', '.join(ob_logs)}")

        for ob in all_obs:
            top, bottom = ob['top'], ob['bottom']

            if prev['close'] < bottom:  # OB 在价格上方，充当【阻力】
                if ob['type'] == 'bearish':
                    ob_name, action_test, action_break = f"熊市订单块 ({algo_name} 供应区)", "向上触及上方的", "强势突破了上方的"
                else:
                    ob_name, action_test, action_break = f"看跌转换块 ({algo_name} 阻力转换区)", "反抽测试前期跌破的", "向上强势收复了前期跌破的"

                if ob_params.get('alert_on_rejection', True) and bottom <= current['close'] <= top:
                    signal_info = {
                        'log_name': f'OB Testing Res ({algo_prefix})',
                        'strategy_name': strategy_key, 'strategy_index': config_index,
                        'direction': 'neutral',  # 测试区间 -> neutral
                        'alert_key': f"{symbol}_{timeframe}_OB_TEST_RES_{algo_prefix}_{ob['timestamp']}",
                        'volume_must_confirm': False, 'title_template': f"⚠️ {symbol} ({timeframe}) 测试关键阻力区",
                        'message_template': (
                                "{trend_message}**信号**: 价格**" + action_test + "** " + ob_name + "。\n\n> **阻力区间**: `{bottom:.4f} - {top:.4f}`\n> **当前价格**: `{current_close:.4f}`\n\n请关注此处是否受阻回落，或蓄力突破。\n\n{vol_text}"),
                        'template_data': {"bottom": bottom, "top": top, "current_close": current['close']},
                        'cooldown_mult': 2, 'always_show_volume': True
                    }
                    _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)

                elif ob_params.get('alert_on_breakout', False) and current['close'] > top:
                    signal_info = {
                        'log_name': f'OB Breakout Up ({algo_prefix})',
                        'strategy_name': strategy_key, 'strategy_index': config_index,
                        'direction': 'long',  # 向上突破阻力区 -> long
                        'alert_key': f"{symbol}_{timeframe}_OB_BREAK_UP_{algo_prefix}_{ob['timestamp']}",
                        'volume_must_confirm': True, 'fallback_multiplier': 1.8,
                        'title_template': f"🚀 {{vol_label}}强势突破阻力区: {symbol} ({timeframe})",
                        'message_template': (
                                "{trend_message}**信号**: 价格已**" + action_break + "** " + ob_name + "！\n\n> **原阻力区间**: `{bottom:.4f} - {top:.4f}`\n> **突破价格**: `{current_close:.4f}`\n\n阻力现已转化为支撑，多头结构确认。\n\n{vol_text}"),
                        'template_data': {"bottom": bottom, "top": top, "current_close": current['close']},
                        'cooldown_mult': 4
                    }
                    _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)

            elif prev['close'] > top:  # OB 在价格下方，充当【支撑】
                if ob['type'] == 'bullish':
                    ob_name, action_test, action_break = f"牛市订单块 ({algo_name} 需求区)", "向下回踩下方的", "有效跌破了下方的"
                else:
                    ob_name, action_test, action_break = f"看涨转换块 ({algo_name} 支撑转换区)", "向下回踩前期突破的", "向下砸穿了前期突破的"

                if ob_params.get('alert_on_rejection', True) and bottom <= current['close'] <= top:
                    signal_info = {
                        'log_name': f'OB Testing Sup ({algo_prefix})',
                        'strategy_name': strategy_key, 'strategy_index': config_index,
                        'direction': 'neutral',  # 测试区间 -> neutral
                        'alert_key': f"{symbol}_{timeframe}_OB_TEST_SUP_{algo_prefix}_{ob['timestamp']}",
                        'volume_must_confirm': False, 'title_template': f"💡 {symbol} ({timeframe}) 测试关键支撑区",
                        'message_template': (
                                "{trend_message}**信号**: 价格**" + action_test + "** " + ob_name + "。\n\n> **支撑区间**: `{bottom:.4f} - {top:.4f}`\n> **当前价格**: `{current_close:.4f}`\n\n请关注此处是否获得支撑企稳，或无力跌破。\n\n{vol_text}"),
                        'template_data': {"bottom": bottom, "top": top, "current_close": current['close']},
                        'cooldown_mult': 2, 'always_show_volume': True
                    }
                    _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)

                elif ob_params.get('alert_on_breakout', False) and current['close'] < bottom:
                    signal_info = {
                        'log_name': f'OB Breakout Down ({algo_prefix})',
                        'strategy_name': strategy_key, 'strategy_index': config_index,
                        'direction': 'short',  # 跌破支撑区 -> short
                        'alert_key': f"{symbol}_{timeframe}_OB_BREAK_DOWN_{algo_prefix}_{ob['timestamp']}",
                        'volume_must_confirm': True, 'fallback_multiplier': 1.8,
                        'title_template': f"📉 {{vol_label}}有效跌破支撑区: {symbol} ({timeframe})",
                        'message_template': (
                                "{trend_message}**信号**: 价格已**" + action_break + "** " + ob_name + "！\n\n> **原支撑区间**: `{bottom:.4f} - {top:.4f}`\n> **跌破价格**: `{current_close:.4f}`\n\n支撑现已转化为强阻力，空头结构确认。\n\n{vol_text}"),
                        'template_data': {"bottom": bottom, "top": top, "current_close": current['close']},
                        'cooldown_mult': 4
                    }
                    _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ OB判断出错: {e}", exc_info=True)


def check_ob_luxalgo(symbol, timeframe, config, df, ob_params, config_index=0):
    bull_ob, bear_ob = find_lux_order_blocks(df.copy(), ob_params.get('swing_length', 5))
    _check_ob_base(symbol, timeframe, config, df, ob_params, config_index, "爆量OB(Lux)", bull_ob, bear_ob,
                   "LUX", 'ob_luxalgo')


def check_ob_fluxcharts(symbol, timeframe, config, df, ob_params, config_index=0):
    bull_ob, bear_ob = find_flux_order_blocks(df.copy(), ob_params.get('swing_length', 10),
                                              ob_params.get('atr_multiplier', 3.5))
    _check_ob_base(symbol, timeframe, config, df, ob_params, config_index, "结构OB(Flux)", bull_ob, bear_ob,
                   "FLUX", 'ob_fluxcharts')


# --- 保留策略区 ---
def check_ma_breakout(symbol, timeframe, config, df, ma_params, config_index=0):
    try:
        ma_periods = ma_params.get('ma_periods', [7, 25, 99])
        ma_type = ma_params.get('ma_type', 'sma').lower()
        for period in ma_periods:
            col_name = f"{ma_type}_{period}"
            if ma_type == 'ema':
                df[col_name] = pta.ema(df['close'], length=period)
            else:
                df[col_name] = pta.sma(df['close'], length=period)
        df_cleaned = df.dropna().reset_index(drop=True)
        if len(df_cleaned) < 2: return
        current, prev = df_cleaned.iloc[-1], df_cleaned.iloc[-2]

        ma_log_list = []
        for period in ma_periods:
            col_name = f"{ma_type}_{period}"
            if col_name in current: ma_log_list.append(f"{ma_type.upper()}{period}: {current[col_name]:.4f}")
        if ma_log_list: logger.debug(
            f"[{symbol}|{timeframe}] 📈 均线计算完毕 -> 当前价: {current['close']:.4f} | 均线: {', '.join(ma_log_list)}")

        for period in ma_periods:
            col_name = f"{ma_type}_{period}"
            if col_name not in current: continue
            ma_val = current[col_name]
            prev_ma_val = prev[col_name]

            bullish = prev['close'] < prev_ma_val and current['close'] > ma_val
            bearish = prev['close'] > prev_ma_val and current['close'] < ma_val

            if bullish or bearish:
                action, emoji = ("突破", "🚀") if bullish else ("跌破", "📉")
                signal_info = {
                    'log_name': f'MA Breakout ({period})',
                    'strategy_name': 'ma_breakout', 'strategy_index': config_index,
                    'direction': 'long' if bullish else 'short',  # 向上突破 -> long；向下跌破 -> short
                    'alert_key': f"{symbol}_{timeframe}_MA_{action}_{period}_{config_index}",
                    'volume_must_confirm': ma_params.get('volume_confirm', True),
                    'fallback_multiplier': ma_params.get('volume_multiplier', 1.5),
                    'title_template': f"{emoji} {{vol_label}}{action} {ma_type.upper()}{period}: {symbol} ({timeframe})",
                    # 注意：template_data 传入的 ma_type 已是大写；原 monitor 模板误写为
                    # {ma_type.upper()}，str.format 不支持方法调用会导致信号永远无法发出
                    # （通知路径的潜在 bug，修复不改变策略判定逻辑）。
                    'message_template': (
                        "{trend_message}**信号**: 价格实时 **{action}** {ma_type}({period}) 均线。\n\n> **当前价**: `{current_close:.4f}`\n> **均线值**: `{ma_value:.4f}`\n\n{vol_text}"),
                    'template_data': {"action": action, "period": period, "ma_type": ma_type.upper(),
                                      "current_close": current['close'], "ma_value": ma_val},
                    'cooldown_mult': 1
                }
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ MA突破出错: {e}")


def check_ema_signals(symbol, timeframe, config, df, ema_params, config_index=0):
    try:
        atr_period = ema_params.get('atr_period', 14)
        atr_multiplier = ema_params.get('atr_multiplier', 0.3)
        df.ta.atr(length=atr_period, append=True)
        ema_period = ema_params.get('period', 120)
        indicator_result = df.ta.ema(length=ema_period, append=True)
        if indicator_result is None or indicator_result.empty: return
        ema_col = indicator_result.columns[0] if isinstance(indicator_result, pd.DataFrame) else indicator_result.name
        df_cleaned = df.dropna(subset=[ema_col]).reset_index(drop=True)
        if len(df_cleaned) < 2: return
        current, prev = df_cleaned.iloc[-1], df_cleaned.iloc[-2]
        atr_col = f"ATRr_{atr_period}"
        if pd.isna(current.get(atr_col)) or current.get(atr_col, 0) == 0: return
        atr_val = current[atr_col]
        atr_buffer = atr_val * atr_multiplier
        bullish = (current['close'] > current[ema_col] + atr_buffer) and (prev['close'] < prev[ema_col])
        bearish = (current['close'] < current[ema_col] - atr_buffer) and (prev['low'] > prev[ema_col])
        if bullish or bearish:
            action = "有效突破" if bullish else "有效跌破"
            breakout_distance = abs(current['close'] - current[ema_col])
            breakout_atr_ratio = (breakout_distance / atr_val) if atr_val > 0 else float('inf')
            signal_info = {
                'log_name': 'EMA Cross',
                'strategy_name': 'ema_cross', 'strategy_index': config_index,
                'direction': 'long' if bullish else 'short',  # 向上突破 -> long；向下跌破 -> short
                # 冷却键必须带方向：否则多头信号占掉同币同周期的冷却，反向（做空）突破会被吞掉
                'alert_key': f"{symbol}_{timeframe}_EMACROSS_{'UP' if bullish else 'DOWN'}_{config_index}",
                'volume_must_confirm': ema_params.get('volume_confirm', False),
                'fallback_multiplier': ema_params.get('volume_multiplier', 1.5),
                'title_template': f"🚀 EMA {{vol_label}}{action}: {symbol} ({timeframe})",
                'message_template': (
                    "{trend_message}**信号**: 价格 **实时{action}** EMA({period})。\n\n> **当前价**: {current_close:.4f}\n> **EMA值**: {ema_value:.4f}\n> **突破力度**: **{breakout_atr_ratio:.1f} 倍 ATR**\n\n{vol_text}"),
                'template_data': {"action": action, "period": ema_period, "current_close": current['close'],
                                  "ema_value": current[ema_col], "breakout_atr_ratio": breakout_atr_ratio},
                'cooldown_mult': 1
            }
            _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ EMA信号错: {e}")


def check_kdj_cross(symbol, timeframe, config, df, kdj_params, config_index=0):
    try:
        indicator_result = df.ta.kdj(fast=kdj_params.get('fast_k', 9), slow=kdj_params.get('slow_k', 3),
                                     signal=kdj_params.get('slow_d', 3), append=True)
        if indicator_result is None or indicator_result.empty: return
        k_col, d_col = indicator_result.columns[0], indicator_result.columns[1]
        df_cleaned = df.dropna(subset=[k_col, d_col]).reset_index(drop=True)
        if len(df_cleaned) < 2: return
        current, prev = df_cleaned.iloc[-1], df_cleaned.iloc[-2]
        golden = current[k_col] > current[d_col] and prev[k_col] <= prev[d_col]
        death = current[k_col] < current[d_col] and prev[k_col] >= prev[d_col]
        if not (golden or death): return
        direction = 'long' if golden else 'short'  # 金叉/看涨 -> long；死叉/看跌 -> short
        trend_status, trend_emoji = get_current_trend(df.copy(), timeframe, config['strategy_params'])
        signal_type_desc = ""
        if "多头" in trend_status:
            signal_type_desc = "顺势看涨 (入场机会)" if golden else "回调警示 (减仓风险)"
        elif "空头" in trend_status:
            signal_type_desc = "顺势看跌 (入场机会)" if death else "反弹警示 (空单止盈)"
        else:
            signal_type_desc = "震荡金叉 (反弹机会)" if golden else "震荡死叉 (下跌机会)"
        if not signal_type_desc: return
        emoji = {"看涨": "📈", "看跌": "📉", "警示": "⚠️", "金叉": "📈", "死叉": "📉", "机会": "💡"}.get(
            signal_type_desc.split(' ')[0].replace("顺势", "").replace("震荡", ""), "⚙️")
        signal_info = {
            'log_name': 'KDJ Cross',
            'strategy_name': 'kdj_cross', 'strategy_index': config_index,
            'direction': direction,
            'alert_key': f"{symbol}_{timeframe}_KDJ_{config_index}",
            'volume_must_confirm': kdj_params.get('volume_confirm', True),
            'fallback_multiplier': kdj_params.get('volume_multiplier', 1.5),
            'title_template': f"{emoji} KDJ {{vol_label}}信号: {signal_type_desc} ({symbol} {timeframe})",
            'message_template': (
                "{trend_message}**信号解读**: {signal_type_desc}信号出现。\n\n**当前K/D值**: {k_val:.2f} / {d_val:.2f}\n**当前价**: {price:.4f}\n\n{vol_text}"),
            'template_data': {"signal_type_desc": signal_type_desc, "k_val": current[k_col], "d_val": current[d_col],
                              "price": current['close']},
            'cooldown_mult': 0.5
        }
        _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ KDJ信号错: {e}")


def check_volatility_breakout(symbol, timeframe, config, df, vol_params, config_index=0):
    try:
        atr_period = vol_params.get('atr_period', 14)
        dynamic_atr_multiplier = get_dynamic_atr_multiplier(symbol, config, vol_params.get('atr_multiplier', 2.5))
        df.ta.atr(length=atr_period, append=True)
        atr_col = f"ATRr_{atr_period}"
        if atr_col not in df.columns: return
        df_cleaned = df.dropna(subset=[atr_col]).reset_index(drop=True)
        if len(df_cleaned) < 2: return
        current, prev = df_cleaned.iloc[-1], df_cleaned.iloc[-2]
        if pd.isna(prev.get(atr_col)) or prev.get(atr_col, 0) == 0: return
        current_volatility = current['high'] - current['low']
        reference_atr = prev[atr_col]
        if current_volatility > reference_atr * dynamic_atr_multiplier:
            actual_atr_ratio = current_volatility / reference_atr
            signal_info = {
                'log_name': 'Volatility Breakout',
                'strategy_name': 'volatility_breakout', 'strategy_index': config_index,
                'direction': 'neutral',  # 波动异常警示 -> neutral（不自动开仓）
                'alert_key': f"{symbol}_{timeframe}_VOLATILITY_{config_index}",
                'volume_must_confirm': vol_params.get('volume_confirm', True),
                'fallback_multiplier': vol_params.get('volume_multiplier', 2.0),
                'title_template': f"💥 {{vol_label}}盘中波动异常: {symbol} ({timeframe})",
                'message_template': (
                    "{trend_message}**波动分析**:\n> **当前波幅**: `{current_volatility:.4f}` **({actual_atr_ratio:.1f}倍)**\n> **参考ATR**: `{reference_atr:.4f}`\n\n{vol_text}"),
                'template_data': {"current_volatility": current_volatility, "actual_atr_ratio": actual_atr_ratio,
                                  "reference_atr": reference_atr},
                'cooldown_mult': 1
            }
            _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ 波动率信号错: {e}")


def detect_rsi_divergence(df, lookback=60, pivot_window=5, min_rsi_gap=5.0):
    """真背离判定：当前收盘 vs「最近一个已确认摆动点」。

    - 顶背离：收盘价创该摆动高点之上的新高，但 RSI 比该点低至少 min_rsi_gap；
    - 底背离：对称。
    要求摆动点已被右侧 pivot_window 根 K 线确认，避免把正在形成的 K 线当枢轴。
    :param df: 含 high/low/close/rsi 列且已 reset_index 的 DataFrame
    :return: 'top' / 'bottom' / None
    """
    n = len(df)
    span = pivot_window * 2 + 1
    if n < span + 2:
        return None

    high, low, rsi = df['high'], df['low'], df['rsi']
    win_high = high.rolling(span, center=True).max()
    win_low = low.rolling(span, center=True).min()
    start = max(0, n - 1 - lookback)
    end = n - 1 - pivot_window  # 右侧未确认的 K 线不能当枢轴

    prev_high_idx = prev_low_idx = None
    for i in range(end - 1, start - 1, -1):
        if prev_high_idx is None and high.iloc[i] == win_high.iloc[i]:
            prev_high_idx = i
        if prev_low_idx is None and low.iloc[i] == win_low.iloc[i]:
            prev_low_idx = i
        if prev_high_idx is not None and prev_low_idx is not None:
            break

    current = df.iloc[-1]
    if prev_high_idx is not None:
        if current['close'] > high.iloc[prev_high_idx] and \
                current['rsi'] <= rsi.iloc[prev_high_idx] - min_rsi_gap:
            return 'top'
    if prev_low_idx is not None:
        if current['close'] < low.iloc[prev_low_idx] and \
                current['rsi'] >= rsi.iloc[prev_low_idx] + min_rsi_gap:
            return 'bottom'
    return None


def check_rsi_divergence(symbol, timeframe, config, df, rsi_params, config_index=0):
    try:
        indicator_result = pta.rsi(df['close'], length=rsi_params.get('rsi_period', 14))
        if indicator_result is None or indicator_result.empty: return
        df['rsi'] = indicator_result
        df_cleaned = df.dropna(subset=['rsi']).reset_index(drop=True)
        divergence = detect_rsi_divergence(
            df_cleaned,
            lookback=int(rsi_params.get('lookback_period', 60)),
            pivot_window=int(rsi_params.get('pivot_window', 5)),
            min_rsi_gap=float(rsi_params.get('min_rsi_gap', 5.0)),
        )
        if divergence == 'top':
            signal_info = {'log_name': 'RSI Top Div',
                           'strategy_name': 'rsi_divergence', 'strategy_index': config_index,
                           'direction': 'short',  # 顶背离 -> short
                           'alert_key': f"{symbol}_{timeframe}_DIV_TOP_{config_index}",
                           'volume_must_confirm': False, 'title_template': f"🚩 RSI顶背离风险: {symbol} ({timeframe})",
                           'message_template': "{trend_message}**信号**: 价格创近期新高，但RSI指标衰弱。\n\n{vol_text}",
                           'template_data': {}, 'cooldown_mult': 2, 'always_show_volume': True}
            _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
        elif divergence == 'bottom':
            signal_info = {'log_name': 'RSI Bottom Div',
                           'strategy_name': 'rsi_divergence', 'strategy_index': config_index,
                           'direction': 'long',  # 底背离 -> long
                           'alert_key': f"{symbol}_{timeframe}_DIV_BOT_{config_index}",
                           'volume_must_confirm': False, 'title_template': f"⛳️ RSI底背离机会: {symbol} ({timeframe})",
                           'message_template': "{trend_message}**信号**: 价格创近期新低，但RSI指标企稳。\n\n{vol_text}",
                           'template_data': {}, 'cooldown_mult': 2, 'always_show_volume': True}
            _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ RSI背离错: {e}")


def check_trend_channel_breakout(symbol, timeframe, config, df, channel_params, config_index=0):
    try:
        if 'lookback_period' not in channel_params: return
        df.ta.atr(length=14, append=True)
        atr_col = "ATRr_14"
        if atr_col not in df.columns: return

        df_for_channel = df.copy()
        df_for_channel['symbol'] = symbol
        df_for_channel['timeframe'] = timeframe
        channel_info = detect_regression_channel(df_for_channel, lookback_period=channel_params.get('lookback_period'),
                                                 min_trend_length=channel_params.get('min_trend_length', 20),
                                                 std_dev_multiplier=channel_params.get('std_dev_multiplier', 2.0))

        if not channel_info or len(df) < 3: return
        current, prev = df.iloc[-1], df.iloc[-2]
        current_upper_band = channel_info['upper_band'].iloc[-1]
        prev_upper_band = channel_info['upper_band'].iloc[-2]
        current_lower_band = channel_info['lower_band'].iloc[-1]
        prev_lower_band = channel_info['lower_band'].iloc[-2]
        confirmation_buffer = current.get(atr_col, 0) * channel_params.get('breakout_confirmation_atr', 0.0)

        trend_dir = "↘️下降趋势" if channel_info['slope'] < 0 else "↗️上升趋势"
        logger.debug(
            f"[{symbol}|{timeframe}] 🛤️ 通道计算完毕 -> {trend_dir} (已持续 {channel_info['trend_length']} 根K线) | 当前价: {current['close']:.2f} | 通道上轨: {current_upper_band:.2f} | 通道下轨: {current_lower_band:.2f}")

        if channel_info['slope'] < 0:
            if prev['close'] < prev_upper_band and current['close'] > current_upper_band + confirmation_buffer:
                signal_info = {'log_name': "Channel Up",
                               'strategy_name': 'trend_channel_breakout', 'strategy_index': config_index,
                               'direction': 'long',  # 突破下降通道 -> long
                               'alert_key': f"{symbol}_{timeframe}_CHAN_UP_{config_index}",
                               'volume_must_confirm': channel_params.get('volume_confirm', True),
                               'fallback_multiplier': channel_params.get('volume_multiplier', 1.8),
                               'title_template': f"📈 {{vol_label}}突破回归通道: {symbol} ({timeframe})",
                               'message_template': (
                                   "{trend_message}**信号**: **确认突破下降回归通道**。\n\n> **突破价格**: `{current_close:.4f}`\n\n{vol_text}"),
                               'template_data': {"current_close": current['close']}, 'cooldown_mult': 4}
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
        elif channel_info['slope'] > 0:
            if prev['close'] > prev_lower_band and current['close'] < current_lower_band - confirmation_buffer:
                signal_info = {'log_name': "Channel Down",
                               'strategy_name': 'trend_channel_breakout', 'strategy_index': config_index,
                               'direction': 'short',  # 跌破上升通道 -> short
                               'alert_key': f"{symbol}_{timeframe}_CHAN_DOWN_{config_index}",
                               'volume_must_confirm': channel_params.get('volume_confirm', True),
                               'fallback_multiplier': channel_params.get('volume_multiplier', 1.8),
                               'title_template': f"📉 {{vol_label}}跌破回归通道: {symbol} ({timeframe})",
                               'message_template': (
                                   "{trend_message}**信号**: **确认跌破上升回归通道**。\n\n> **跌破价格**: `{current_close:.4f}`\n\n{vol_text}"),
                               'template_data': {"current_close": current['close']}, 'cooldown_mult': 4}
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ 通道突破错: {e}")


def check_consecutive_candles(symbol, timeframe, config, df, consecutive_params, config_index=0):
    try:
        min_n_to_alert = get_dynamic_consecutive_candles(symbol, config,
                                                         consecutive_params.get('min_consecutive_candles', 4))
        if len(df) < min_n_to_alert + 2: return

        def count_backwards(start_index, direction):
            count = 0
            for i in range(start_index, -1, -1):
                candle = df.iloc[i]
                current_direction = 'up' if candle['close'] > candle['open'] else (
                    'down' if candle['close'] < candle['open'] else 'none')
                if current_direction == direction:
                    count += 1
                else:
                    break
            return count

        last_candle, prev_candle = df.iloc[-2], df.iloc[-3]
        is_last_up, is_last_down = last_candle['close'] > last_candle['open'], last_candle['close'] < last_candle[
            'open']
        is_prev_up, is_prev_down = prev_candle['close'] > prev_candle['open'], prev_candle['close'] < prev_candle[
            'open']

        if is_last_up and is_prev_down:
            if (c := count_backwards(len(df) - 3, 'down')) >= min_n_to_alert:
                signal_info = {'alert_key': f"{symbol}_{timeframe}_REV_UP_{config_index}_{last_candle['timestamp']}",
                               'strategy_name': 'consecutive_candles', 'strategy_index': config_index,
                               'direction': 'neutral',  # 连续K线警示 -> neutral（不自动开仓）
                               'title_template': f"🔄 动能衰竭: {symbol} ({timeframe})", 'message_template': (
                        "{trend_message}**空头动能衰竭 (反弹警示)**!\n\n> 连续下跌 **{c}** 根K线后，首现收涨K线。\n> **当前价**: {p:.4f}\n\n请留意止跌企稳迹象。\n\n{vol_text}"),
                               'template_data': {'c': c, 'p': last_candle['close']},
                               'cooldown_logic': 'align_to_period_end', 'always_show_volume': True}
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
        elif is_last_down and is_prev_up:
            if (c := count_backwards(len(df) - 3, 'up')) >= min_n_to_alert:
                signal_info = {'alert_key': f"{symbol}_{timeframe}_REV_DOWN_{config_index}_{last_candle['timestamp']}",
                               'strategy_name': 'consecutive_candles', 'strategy_index': config_index,
                               'direction': 'neutral',  # 连续K线警示 -> neutral（不自动开仓）
                               'title_template': f"🔄 动能衰竭: {symbol} ({timeframe})", 'message_template': (
                        "{trend_message}**多头动能衰竭 (回调警示)**!\n\n> 连续上涨 **{c}** 根K线后，首现收跌K线。\n> **当前价**: {p:.4f}\n\n请留意滞涨回调风险。\n\n{vol_text}"),
                               'template_data': {'c': c, 'p': last_candle['close']},
                               'cooldown_logic': 'align_to_period_end', 'always_show_volume': True}
                _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)

        current_trend_count = count_backwards(len(df) - 2, 'up' if is_last_up else 'down')
        if current_trend_count >= min_n_to_alert:
            d_text, emoji = ("收涨", "📈") if is_last_up else ("收跌", "📉")
            signal_info = {
                'alert_key': f"{symbol}_{timeframe}_CONT_{'UP' if is_last_up else 'DOWN'}_{config_index}_{last_candle['timestamp']}",
                'strategy_name': 'consecutive_candles', 'strategy_index': config_index,
                'direction': 'neutral',  # 单边动能提示 -> neutral（不自动开仓）
                'title_template': f"{emoji} 极度强势: {{vol_label}}{symbol} ({timeframe})", 'message_template': (
                    "{trend_message}**单边动能极强**：\n\n> 价格已连续 **{c}** 个周期{d_text}。\n> **当前价**: {p:.4f}\n\n{vol_text}"),
                'template_data': {'c': current_trend_count, 'd_text': d_text, 'p': last_candle['close']},
                'cooldown_logic': 'align_to_period_end', 'always_show_volume': True,
                'fallback_multiplier': consecutive_params.get('volume_multiplier', 1.5),
                'volume_must_confirm': consecutive_params.get('volume_confirm', False)}
            _prepare_and_send_notification(config, symbol, timeframe, df, signal_info)
    except Exception as e:
        logger.error(f"❌ 连K错: {e}")
# --- END OF FILE analysis/strategies.py ---
