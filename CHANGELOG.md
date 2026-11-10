# GFIC 版本存档 / CHANGELOG

> 全球金融情报中心（Global Financial Intelligence Center）· 端口 6789 · 单容器零依赖

## V2.1 全面升级 — 投资决策驾驶舱 + AI 机会雷达 + 全站翻译 + 全量测试（2026-11-11）

**新增（全部基于现有项目扩展，未删除任何 V2.0 模块）**
- 后端新增 `gfic_research.py`（真实日线 / SEC XBRL / 可解释评分 / 领先榜 / 优质公司榜 / 成绩单 / 股票详情）与 `gfic_i18n.py`（五语言词典 / 23 条术语 / P1-P3 等级规则 / 单条与批量翻译 / 数字保护 / 磁盘缓存）。
- 新增 API：`/api/daily/summary`、`/api/research/{opportunities,leaders,quality,stock,track}`、`/api/detail`、`/api/i18n/{dict,glossary,priority,terms,stats,translate,translate_batch}`；SPA fallback 支持 `/stocks/AAPL`、`/news/<id>` 与单段视图直达。
- 前端用**独立扩展层** `static/v21.js` + `v21.css` 实现，原 97KB `app.js` **一行未改**：投资决策驾驶舱（机会 / 风险 / 依据 / 数据口径）、AI 全球投资机会雷达、全球表现领先榜、优质公司观察榜、小白易懂模式、术语解释、P1/P2/P3 等级说明、全站五语言切换、原文/译文/双语对照、24 个导航视图、详情路由与返回按钮。
- `tests/browser_test.py`：纯标准库实现的 Edge CDP 客户端，真实浏览器上做点击 / 前进后退 / 刷新 / 五档分辨率 / 截图 / 控制台异常捕获，并输出 `tests/browser_report.json`。
- `scripts/snapshot.py`：可复用版本快照（源码 / 凭据隔离 / 数据卷独立备份 + 恢复演练 SHA256 / 容器与路由清单 / 全文件哈希 / 一键回滚脚本）。
- `TEST_REPORT_V2.1.md` 全量测试报告；`AUDIT_V2.0.md` 功能审计与 Bug 清单。

**关键修复与数据质量**
- 修复扩展层 `window.esc/num/S` 取不到顶层 `const` 导致全模块失效、残留调试语句、详情页首次跳转不 mount、旧驾驶舱异步渲染覆盖新页等 4 个前端缺陷。
- **把已缓存的 SEC 官方财务真正接入机会评分**：服务端 `with_fin=True` + `financials(cached_only=True)` + 后台 `_warm_research` 预热；机会等级由「全部 D / 置信度 0.15」变为真实 S/A/B/C/D、置信度 0.5–0.75，SEC 净利率 / ROE 进入「为什么值得关注」。
- 修复领先榜免责声明残留 `**`、手机 390px 横向溢出 54px、易懂模式在词典 / 详情页无内容、`/glossary` 与 `/opportunities` 直达 404、V2.0 快照目录权限 000。
- 修复 **≤980px 侧栏脱离网格流导致主内容 0 宽塌陷**（平板/手机竖排文字）；修复 SEC companyfacts 偶发降级结果被缓存 1h/24h 导致 AAPL 长期 0 财务。

**实测口径**
- 本地接口冒烟 **97/97**、真实浏览器 **88/88**；NAS 接口 **97/97**、浏览器 **88/88**；0 条 JS 运行时异常。
- 机会雷达 12 项 / 真实抓取 29 / 失败 0；综合分口径逐项复核 0 异常；资讯 790 条去重 / 77 条 P1；行情 36 项；FRED 10 组；BTC/ETH 各 4 所。
- 五档分辨率（1920/1536/1366/768/390）无横向溢出；深浅主题、前进后退、刷新、直达 URL 全部通过。

**版本存档与回滚**
- 升级前已创建 `GFIC_V2.0_升级前完整快照`（18/18 校验通过、37 文件 / 444,355 B、数据备份恢复演练逐文件 SHA256 一致）与 Git Tag `v2.0.0-pre-gfic-v21`。
- 升级完成创建 `GFIC_V2.1_升级完成版本` 快照：`/vol1/1000/docker/GFIC/backups/snapshots/GFIC_V2.1/`；快照生成时自动执行源码 / 凭据 / 数据卷 / 容器 / 路由 / 版本多项校验并做恢复演练，逐项结果见快照内 `manifest.json`。
- 一键回滚：`sudo bash /vol1/1000/docker/GFIC/backups/rollback_to_v2.0.sh`（回 V2.0）、`sudo bash /vol1/1000/docker/GFIC/backups/rollback_to_v2_1.sh`（回 V2.1）；脚本先把当前现场另存 `pre-rollback-<时间戳>/` 再停服还原，不破坏历史。
- 快照目录含 `secrets/config.json`（600），**绝不入库**；`source_backup.tar.gz` 不含任何明文凭据。

**限制**：内网 `freellmapi` 当前 429 限流，动态内容翻译按设计诚实回退原文（固定文案走本地词典不受影响）；估值 / 行业景气 / A股港股财务仍如实标注「未接入」。

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
