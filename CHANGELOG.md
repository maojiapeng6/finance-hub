# GFIC 版本存档 / CHANGELOG

> 全球金融情报中心（Global Financial Intelligence Center）· 端口 6789 · 单容器零依赖

## v2.1.0 — 官方数据源适配层 + 专业金融终端 + 交付体系（2026-11-10）

**新增**
- `gfic_sources.py` 统一数据源适配层：33 源注册表（A/B/C/D 分级）、每源独立启停 / 连接探测 / 成功率 / 最近成功失败 / 延迟 / 授权 / 费用。
- 接入 7 类官方免费宏观：FRED（10 组序列）、美国财政部收益率曲线与 FiscalData、World Bank、Eurostat、ECB 参考汇率、Frankfurter；SEC EDGAR 公司研究；Binance / Coinbase / Kraken / OKX 四所加密实时交叉。
- 业务 API：`/api/dashboard`、`/api/macro`、`/api/crypto`、`/api/sec`、`/api/sources/*`、`/api/watchlist*`、`/api/alerts*`、`/api/heatmap`。
- 成功数据落盘 `data/cache_*.json` + `source_state.json`，容器重启恢复；抓取失败标 `stale` 降级，绝不补假值。
- 前端重写为 22 视图专业金融终端：驾驶舱 / 资讯流 / 行情 / 宏观 / 数据源 / 自选股 / 预警 / AI 工作台，暗浅主题、涨红跌绿、响应式。
- 交付物：`.env.example`、`README.md`、`scripts/backup.sh`、`scripts/restore.sh`、`tests/smoke_test.py`；Dockerfile / compose / deploy 链路补齐可写卷与变量模板。
- 冒烟测试 44 项（本地 + NAS 各 44/44），`--full` 追加 AI 简报与问答回归。

**修复**
- 静态资源 `/style.css`、`/app.js` 404 导致页面退化为纯文本（后端补路由映射 + `do_HEAD`）。
- 右侧抽屉常驻遮挡（`[hidden]{display:none !important}`）。
- SSE 长连接导致无头浏览器不退出（`?nosse=1`）。
- `/api/sources/toggle` 返回数组但前端按对象读取 → 改为 `{sources, summary}`。
- AI 输出残留 Markdown `**` 星号：前端清洗 + 服务端 `_sanitize` 统一清洗，API / 页面 / 日志都拿到纯文本。
- **AI 简报质量闸门（v2.1 收尾修复）**：上游模型偶发把「英文原始标题清单 + 中文翻译 + 自我核对草稿」一起输出，中文占比 0.269 恰好绕过旧 0.25 阈值。现加入 `_LEAK` 自检草稿识别、「今日关键词」后内容截断、中文占比 ≥ 0.40、长度 200–1800 字、`[n]` 溯源 ≥ 8 条、英文编号清单 ≤ 2 行等校验，不合格自动轮换模型重试。
- `.gitignore` 补 `data/`，避免运行时缓存与状态入库。

**实测口径**
- 本地 `http://127.0.0.1:6789`：44/44 通过；NAS `http://192.168.10.110:6789`：44/44 通过。
- 资讯 813 条（0 重复、77 条 P1 官方原文）、行情 36 项、FRED 10 组、ECB 29 币种、SEC AAPL 10 项财务、BTC/ETH 各 4 所报价。
- 真实浏览器渲染验证：驾驶舱 / 数据源 / 宏观 / 资讯四视图截图，无纯文本、无遮挡、无空白。

**已知缺口**：实时授权行情（当前延迟 15–20 分钟）、多容器架构、登录与 HTTPS、期权链 / ETF 持仓 / 资金净流入 / COT、A股港股财务全量、X/TG/YouTube 社交源、AI 评分与回测成绩单、Telegram 推送、经济日历。界面「数据源管理」「系统说明」中均如实标注。

## v2.0.0-ui — 界面重做与静态资源修复（2026-11-10）

- 修复 `/style.css` `/app.js` 404 导致的纯文本页面；重做 Hero / KPI 可视化与卡片式资讯流。
- 资讯富化：摘要、大白话解读、关联标的、原文链接、搜相关、站点链接。
- AI 简报编号溯源 `[n]`，收紧提示词禁止推断与跨条拼接。
- 修复右侧抽屉常驻遮挡。
- tag：`v2.0.0-ui`。
