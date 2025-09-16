# backend/app/logic/plan_calculator.py
from typing import List, Dict, Any, Tuple, Set

# --- 修改导入 ---
from ..config.config import ALL_AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
# --- 修改结束 ---

def calculate_trade_plan(config, custom_weights):
    long_plan, short_plan = {}, {}

    if config.get('enable_long_trades', True) and config.get('total_long_position_value', 0) > 0:
        # --- 修改：直接使用 config 中的 long_coin_list，不再回退 ---
        long_coin_list = config.get('long_coin_list', [])
        if not long_coin_list:
             print("警告: 多头币种列表为空！")
             # 如果用户清空了列表，那么这个列表就应该为空，不进行交易
        # --- 修改结束 ---

        if not long_coin_list: return {}, {}

        total_long_value = config['total_long_position_value']
        long_coin_list = [c.strip().upper() for c in long_coin_list if isinstance(c, str) and c.strip()]

        if not long_coin_list: return {}, {}

        if custom_weights:
            assigned_coins = {c: w for c, w in custom_weights.items() if c in long_coin_list and w > 0}
            unassigned_coins = [c for c in long_coin_list if c not in assigned_coins]
            assigned_weight_total = sum(assigned_coins.values())
            final_weights = {}

            if unassigned_coins and assigned_weight_total < 100:
                remaining_weight = 100.0 - assigned_weight_total
                weight_per_unassigned = remaining_weight / len(unassigned_coins)
                final_weights.update(assigned_coins)
                for coin in unassigned_coins:
                    final_weights[coin] = weight_per_unassigned
            else:
                final_weights = assigned_coins

            total_final_weight = sum(final_weights.values())
            if total_final_weight > 0:
                for coin, weight in final_weights.items():
                    long_plan[coin] = total_long_value * (weight / total_final_weight)
        else:
            btc_in_list = 'BTC' in long_coin_list
            eth_in_list = 'ETH' in long_coin_list
            satellite_coins = [c for c in long_coin_list if c not in ['BTC', 'ETH']]
            if (btc_in_list or eth_in_list) and satellite_coins:
                remaining_value = float(total_long_value)
                if btc_in_list: long_plan['BTC'] = total_long_value * 0.40; remaining_value -= long_plan['BTC']
                if eth_in_list: long_plan['ETH'] = total_long_value * 0.30; remaining_value -= long_plan['ETH']
                if satellite_coins and remaining_value > 0:
                    value_per_satellite = remaining_value / len(satellite_coins)
                    for coin in satellite_coins: long_plan[coin] = value_per_satellite
            elif btc_in_list and eth_in_list and not satellite_coins:
                long_plan['BTC'] = total_long_value * 0.60
                long_plan['ETH'] = total_long_value * 0.40
            else:
                value_per_coin = total_long_value / len(long_coin_list)
                for coin in long_coin_list: long_plan[coin] = value_per_coin


    if config.get('enable_short_trades', True) and config.get('total_short_position_value', 0) > 0:
        # --- 修改：直接使用 config 中的 short_coin_list，不再回退 ---
        short_coin_list = config.get('short_coin_list', [])
        if not short_coin_list:
            print("用户未选择任何做空币种。")
            # short_coin_list = [] # 保持为空
        # --- 修改结束 ---

        if not short_coin_list:
            return long_plan, {}

        short_coin_list = [c.strip().upper() for c in short_coin_list if isinstance(c, str) and c.strip()]
        if short_coin_list:
            value_per_short = config['total_short_position_value'] / len(short_coin_list)
            for coin in short_coin_list:
                short_plan[coin] = value_per_short

    return long_plan, short_plan