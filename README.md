# GFIC 全球金融情报中心 V2.1

> Global Financial Intelligence Center · 免费优先 · 全球市场 · 可持续升级
> 本地 / 飞牛 NAS Docker 部署，端口固定 **6789**。
> **V2.1**：投资决策驾驶舱 + AI 全球投资机会雷达 + 全站翻译 + 易懂模式 + 详情路由（在 V2.0 基础上扩展，未删除任何既有模块）。

**核心原则：数据真实、来源可追溯、架构可扩展、界面专业、AI 有依据、运行稳定、成本可控。**
没有数据的地方一律显示「暂无数据 / 未接入」，绝不用模拟行情、随机数或虚构新闻填充。

---

## 1. 快速开始

### 本机（Windows / macOS / Linux）
```bash
# 零第三方依赖，Python 3.9+ 即可
python server.py
# 浏览器打开 http://127.0.0.1:6789
```
不自动开浏览器：`FR_NO_BROWSER=1 python server.py`

### NAS / Docker
```bash
cd /vol1/1000/docker/finance-radar
sudo docker compose up -d --build
```
或从工作区一键部署：
```bash
NAS_PASS=<SSH密码> python deploy_nas.py
```
访问：`http://<NAS_IP>:6789`

**前置条件**：境外数据需经代理 `<NAS_IP>:7893`；AI 网关 `http://<NAS_IP>:3001/v1` 可达。

---

## 2. 目录结构

```
finance-radar/
├── docker-compose.yml          # 单容器 + 可写数据卷 + 健康检查
├── Dockerfile                  # python:3.12-alpine（零依赖）
├── .env.example                # 服务端环境变量模板（密钥不入库、不下发前端）
├── config.json                # 端口/代理/AI/刷新周期/资讯源/行情标的
├── sources_catalog.json        # 100+ 权威信息源导航（P1/P2/P3）
├── server.py                   # HTTP 服务 + 资讯/行情/AI/V2.1 研究与国际化 API
├── gfic_sources.py             # ★ 统一数据源适配层（注册表/采集/状态/持久化/降级）
├── gfic_research.py            # ★ V2.1 真实日线 / SEC 财务 / 可解释评分 / 榜单 / 成绩单
├── gfic_i18n.py                # ★ V2.1 五语言词典 / 术语 / 等级规则 / 翻译与数字保护
├── static/                     # 专业金融终端前端（零外部 CDN 依赖）
│   ├── index.html
│   ├── style.css
│   ├── app.js                  # V2.0 主体（V2.1 未改动一行）
│   ├── v21.css                 # V2.1 视觉扩展层
│   └── v21.js                  # V2.1 驾驶舱 / 机会雷达 / 详情路由 / 易懂模式 / 翻译
├── data/                       # 可写卷：自选股、预警、数据源状态、成功数据落盘缓存
├── scripts/backup.sh           # 备份
├── scripts/restore.sh          # 恢复（自动先做 pre-restore 备份）
├── scripts/snapshot.py         # ★ 可复用版本快照 + 一键回滚脚本生成
├── tests/smoke_test.py         # 接口实机冒烟 / 验收测试
├── tests/browser_test.py       # ★ 真实 Edge CDP 浏览器全站验收（纯标准库）
├── CHANGELOG.md                # 版本存档
├── AUDIT_V2.0.md               # V2.0 功能审计与 Bug 清单
├── TEST_REPORT_V2.1.md         # V2.1 全量测试报告
└── deploy_nas.py               # 一键上传 + 构建 + 启动
```

---

## 3. 架构说明与取舍

V2.0 建议 React + FastAPI + PostgreSQL + Redis + 5 容器。本项目**第一阶段采用单容器零依赖架构**，理由：

| 目标 | 本实现 |
|---|---|
| 前后端分离、业务解耦 | 静态前端 + JSON API，完全分离 |
| 采集与业务解耦、可插拔供应商 | `gfic_sources.py` 适配层：33 源注册表，每源独立 adapter / 启停 / 状态 / 降级 |
| 统一数据标准 | 所有数据带 `source / updated / latency / frequency / license / coverage` |
| 缓存与持久化 | 内存缓存 + `data/` 落盘；容器重启自动恢复上次成功数据并标 `stale` |
| 实时推送 | SSE `/api/events` |
| 健康检查 / 自动重启 / 日志轮转 | compose 内已配置 |
| 不增加不必要的容器 | 单容器，内存限制 512MB，免维护 |

**为什么没上 5 容器**：V2.0 同时要求「不需要为了架构复杂而增加容器数量」「优先保证稳定性」「不允许把未实现的按钮伪装成已完成」。先把真实数据源、状态可观测、降级与持久化做扎实，比先搭一堆空服务更有价值。后续如需多实例、登录、全文检索，可在**不改动前端**的前提下把适配层输出写入 PostgreSQL。

---

## 4. 数据源清单（全部免费，实测可用）

| 等级 | 数据源 | 覆盖 / 口径 |
|---|---|---|
| **A 官方** | FRED | 美国 CPI、核心 CPI、失业率、非农、联邦基金利率、GDP、M2、2Y/10Y 国债、人民币汇率（10 组序列，日/月/季频） |
| **A 官方** | 美国财政部 | 1M–30Y 每日国债收益率曲线、10Y-2Y 利差、FiscalData 平均利率 |
| **A 官方** | World Bank | 美/中/日/德/印/英 GDP 与通胀（**年度数据，有滞后**） |
| **A 官方** | Eurostat | 欧元区 HICP 调和通胀（月频） |
| **A 官方** | ECB | 29 币种**官方参考汇率**（日更） |
| **A 官方** | SEC EDGAR | 10,414 家在美申报公司、10-K/10-Q/8-K、XBRL 原始财务事实 |
| **A 官方** | 美联储 / EIA / WTO / BOJ | 官方新闻稿 RSS |
| **A 交易所** | Binance / Coinbase / Kraken / OKX | BTC、ETH 现货实时 ticker，多所交叉验证 |
| **B** | Frankfurter | 基于 ECB 参考汇率的 USD 基准汇率（日更） |
| **C 非官方** | Yahoo Finance v8 | 36 标的全球行情，**约 15–20 分钟延迟** |
| **C 媒体** | Google News RSS（中英 17 主题）+ 19 个直连 RSS | CNBC / MarketWatch / BBC / Guardian / Fortune / Investing / Reuters 聚合等 |
| **D 社区** | Reddit r/stocks | 社交情绪，偶发限流，**不得单独作投资结论** |

**实测不可用 / 未接入（如实标注）**：CFTC COT（代理 TLS SNI 不可达）、BLS RSS（403，改由 FRED 收录同源序列）、IMF SDMX（502）、Twelve Data / Finnhub / Alpha Vantage / AKShare（需 Key 或引入依赖）、期权链、ETF 持仓、资金净流入、X / Telegram / YouTube。

每个源在「数据源管理」页可查看：等级、覆盖范围、延迟、刷新周期、授权许可、费用、请求成功/失败次数、成功率、最近成功/失败时间、上次耗时、错误原因，并支持**独立启停**与**真实连接探测**。

---

## 5. 界面模块（24 个独立视图）

情报中枢：全球金融驾驶舱（V2.1 决策驾驶舱）/ 全球实时资讯 / AI 全球事件分析 / 全球地缘政治 / 产业链与行业 / 社交与市场情绪
市场监控：全球行情 / 市场热力图 / 全球宏观经济 / 外汇与利率 / 商品与期货 / 数字资产 / 全球资金流向\* / 全球基金与 ETF\*
研究工作台：公司研究 SEC / AI 股票评分\* / **AI 投资机会（V2.1 机会雷达）** / AI 金融工作台 / AI 预测成绩单\*
资产与系统：自选股与模拟组合 / 全球风险预警 / 数据源管理 / **金融术语词典（V2.1）** / 系统说明与清单

\* 标记为**未接入数据源**的模块：页面明确列出缺失数据源与接入路径，不提供假按钮、不显示虚构数字。

---

## 6. 升级 / 备份 / 恢复

```bash
# 升级（从工作区）
NAS_PASS=<密码> python deploy_nas.py

# 仅重启
cd /vol1/1000/docker/finance-radar && sudo docker compose restart

# 备份（自动保留最近 14 份）
sudo bash scripts/backup.sh

# 恢复（会先自动另存 pre-restore 备份）
sudo bash scripts/restore.sh gfic-YYYYMMDD-HHMMSS.tgz

# 日志
sudo docker logs -f finance-radar

# 版本快照（在 NAS 上以 root 执行，源码/凭据/数据卷/容器配置/路由全量 + 恢复演练）
sudo GFIC_SNAPSHOT_NAME=GFIC_V2.1 GFIC_GIT_TAG=<tag> \
  python3 scripts/snapshot.py

# 一键回滚（脚本会先把当前现场另存 pre-rollback-<时间戳>）
sudo bash /vol1/1000/docker/GFIC/backups/rollback_to_v2.0.sh   # 回到 V2.0
sudo bash /vol1/1000/docker/GFIC/backups/rollback_to_v2_1.sh   # 回到 V2.1
```

快照目录：`/vol1/1000/docker/GFIC/backups/snapshots/<name>/`，含 `source_backup.tar.gz`（不含凭据）、`secrets/config.json`（600）、`database_backup.tar.gz`（已做恢复演练 + SHA256 逐文件校验）、`inspect/`（脱敏的容器 / 端口 / 路由 / API / 版本信息）、`manifest.json` 与 `README.md`。**快照目录含凭据，绝不入库。**

`data/` 为可写卷，包含：自选股、模拟组合、预警规则、通知记录、数据源启停状态，以及**各官方数据源上次成功抓取的真实快照**。容器重启后自动恢复，抓取失败时展示上次数据并标注「数据陈旧」，绝不补假值。

---

## 7. 测试

```bash
python tests/smoke_test.py --base http://<NAS_IP>:6789
python tests/smoke_test.py --base http://<NAS_IP>:6789 --full   # 含 AI 简报/问答
python tests/browser_test.py --base http://<NAS_IP>:6789         # 真实浏览器全站验收
```
`smoke_test.py` 覆盖：健康检查、静态资源 404 回归、资讯去重与时间戳、行情字段、官方宏观真实性、加密多所交叉、SEC 申报、数据源启停与连接探测、持久化写后回读与 1:1 还原、**V2.1 今日总结 / 机会雷达 / 评分口径逐项复核 / 领先榜 / 优质公司榜 / 股票详情 / 成绩单 / 详情接口 / SPA 直达路由 / 五语言词典 / 术语 / 等级定义 / 翻译与批量翻译 / 数据真实性总检**。`--full` 额外回归 AI 简报质量闸门。

`browser_test.py` 用纯标准库实现的 Edge DevTools Protocol 客户端（不依赖 selenium / playwright / puppeteer），在**真实浏览器**上验证：驾驶舱、机会雷达筛选器、术语弹窗、易懂模式、P1/P2/P3 弹窗、股票与资讯详情、`/stocks/AAPL` 与 `/news/<id>` 直达 URL、前进后退与刷新、五语言切换、双语对照与原文切换、深浅主题、1920/1536/1366/768/390 五档分辨率、V2.0 视图回归、JS 运行时异常与失败请求。结果写入 `tests/browser_report.json`，截图落在 `--shots` 指定目录。

> 为什么不用 `--headless --dump-dom`：该模式会被页面挂起中的网络请求卡死，也拿不到 JS 异常、无法模拟点击与改视口；CDP 才能做真实验收。

**V2.1 实测**：本地接口 97/97、浏览器 77/77；详见 `TEST_REPORT_V2.1.md`。

---

## 7.5 V2.1 新增功能一览

| 功能 | 入口 | 数据依据 |
|---|---|---|
| 投资决策驾驶舱 | 首页 `#dashboard` | 站内真实资讯 / 行情 / 官方宏观；机会、风险、依据、数据口径同屏 |
| AI 全球投资机会雷达 | 侧栏「AI 投资机会」或 `/opportunities` | Yahoo 真实 1 年日线 + SEC 官方 XBRL；8 维可解释评分、缺失不补分、置信度 <0.35 暂停排名 |
| 全球表现领先榜 / 优质公司观察榜 | 机会雷达内第 2 / 3 屏 | 真实历史涨跌 / SEC 申报利润率、ROE、负债率；明确「历史表现 ≠ 未来」 |
| 历史研究成绩单 | 机会雷达内第 4 屏 | 推荐时点价格快照，仅评估已满期记录，避免未来函数 |
| 详情页 | 点任意重要卡片、或 `/stocks/AAPL`、`/news/<id>` | 多空逻辑、风险、结论失效条件、公司新闻与监管公告、相关报道 |
| 小白易懂模式 | 顶栏「易」 | 在驾驶舱 / 机会雷达 / 词典 / 详情页注入大白话解释 |
| 金融术语词典 | 顶栏「?」或 `/glossary` | 23 条术语：通俗解释 / 作用 / 高低含义 / 市场影响 |
| P1/P2/P3 等级说明 | 任意等级徽标 | 规则模型和本条判定原因弹窗 |
| 全站翻译 | 顶栏语言下拉 + 「文/A」 | 五语言本地词典（各 75 键）+ 动态内容内网 AI 翻译与缓存；失败诚实回退原文；数字/代码/币种保护 |

**AI 推荐评分口径**：综合分 = Σ(可得维度权重 × 得分) / Σ(可得维度权重)；置信度 = 可得权重 / 100；估值、行业景气、非美股财务等无免费真实数据源的维度一律标「数据缺失」，不猜、不补分。每条推荐都带依据、风险、反向观点与结论失效条件。

---

## 8. 安全

- AI API Key 只在服务端 `config.json`（受保护，已被 `.gitignore` 排除）或环境变量 `FR_LLM_KEY`，**绝不下发浏览器**。
- `.env.example` 不含真实密钥；`.dockerignore` 排除 `data/`、临时文件与 `.git/`。
- 不开放数据库 / Redis 端口（本架构未使用）；不修改 Emby、MediaTidy 等现有容器与 NAS 系统网络。
- 局域网内部使用；登录认证与 HTTPS 反向代理为后续可选项。

---

## 9. 数据授权与使用限制

| 类别 | 限制 |
|---|---|
| 官方宏观 / 监管数据 | 个人内部展示；宏观为统计发布值，**不是实时行情**；World Bank 为 CC BY 4.0；Eurostat 需注明来源 |
| 交易所行情 | 遵守交易所接口条款与所在地适用规则，个人内部展示 |
| Yahoo Finance | **非官方接口**、延迟 15–20 分钟，仅供方向判断，不可用于下单 |
| 新闻 RSS | 仅存标题 / 摘要 / 发布时间 / 原文链接，**不复制全文、不绕过付费墙** |
| Reddit 等 D 级 | 未经验证，不得单独作为重大投资结论依据 |
| AI 输出 | 简报每句带编号可点回原文；问答区分站内事实、常识解释与观点，不得伪造数字或新闻 |

**风险声明**：本平台仅供个人研究，不构成投资建议。社交讨论量 ≠ 资金流；成交额 ≠ 资金净流入；COT 为周频报告而非实时持仓。AI 输出可能有误，重要结论请点开官方原文核验。

---

## 10. 已完成 / 未完成清单

**已完成（V2.0）**：22 视图专业终端（暗/浅主题、响应式）、统一适配层与真实状态、7 类官方宏观、ECB 汇率、SEC 财务、4 所加密实时交叉、资讯去重与多链接富化、AI 溯源简报与站内数据问答、成功数据落盘与陈旧降级、自选股/组合/预警真实持久化、SSE、健康检查、备份恢复脚本、冒烟测试。

**已完成（V2.1）**：投资决策驾驶舱、AI 全球投资机会雷达（真实日线 + SEC 财务 + 可解释 100 分制评分）、全球表现领先榜、优质公司观察榜、历史研究成绩单、股票/资讯/宏观/资产等详情路由与直达 URL、小白易懂模式、23 条术语词典、P1/P2/P3 等级说明、五语言固定文案词典、动态内容翻译 / 双语对照 / 原文切换、24 视图导航、真实浏览器 CDP 全站自动化测试、可复用版本快照与一键回滚。

**未完成**：实时交易所授权行情（当前为延迟）、PostgreSQL/Redis/FastAPI/React 多容器、登录与 HTTPS、期权链与隐含波动率、ETF 持仓与净值、资金净流入与 COT、A股/港股财务全量与龙虎榜、X/TG/YouTube 社交源、估值（PE/PB/PS）与行业景气指数、全市场筛选器、Telegram 推送、经济日历。

> 这些缺口都在界面「数据源管理」「系统说明」中明确标注了原因与替代方案；系统不会自动订阅、自动扣费或伪造成功。
