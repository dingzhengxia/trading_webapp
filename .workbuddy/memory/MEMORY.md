# 项目长期备忘

## 用户偏好
- 信号方向配色：**红跌绿涨**（做多🟢绿、做空🔴红），不是中国传统的红涨绿跌。前端 directionColor 和钉钉推送 _DIRECTION_LABEL 都要用这套。
- 钉钉推送策略：静态币（BTC/ETH/BNB）实时全推；其它币成交量达到量能倍数（signal_push_volume_multiplier）才推送。
- 信号扫描范围 Top 30（signal_scan_top_n=30），用户说 Top 多少无所谓。

## 项目结构要点
- 信号链路统一入口：backend/app/signals/dispatcher.py（展示 → 钉钉推送独立task → 自动开仓）。
- 前端部署：frontend/dist 被 gitignore，Docker 构建时重新打包；改动需服务器重跑 ./deploy.sh。
- 服务器 43.167.206.29:8000，API Key 见用户提供的密码。
- 测试：pytest 全量在 backend/ 下运行，不用 pytest-asyncio（async 测试用 asyncio.run）。
