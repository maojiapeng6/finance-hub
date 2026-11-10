# GFIC V2.1 全量功能测试报告

> 生成时间：2026-11-11 · 项目：`finance-hub` / NAS 容器 `finance-radar` · 端口 6789
> 原则：**不虚构测试数量**，所有数字来自真实执行结果；所有断言都打在真实接口 / 真实浏览器上。
> 两套测试脚本：`tests/smoke_test.py`（接口层）、`tests/browser_test.py`（真实 Edge CDP 浏览器层）。

---

## 1. 测试环境与方法

| 项 | 说明 |
|---|---|
| 后端 | Python 3.12 标准库单文件 `server.py` + `gfic_sources.py` / `gfic_research.py` / `gfic_i18n.py` |
| 前端 | 原生 JS：`static/app.js`（V2.0 未改动一行）+ `static/v21.js` / `v21.css` 扩展层 |
| 接口测试 | `python tests/smoke_test.py --base <url>`，逐项真实 HTTP 断言，写入项 1:1 还原 |
| 浏览器测试 | `python tests/browser_test.py --base <url>`，纯标准库实现 CDP WebSocket 客户端，直连无头 Edge |
| 为什么不用 `--dump-dom` | 该模式会被页面挂起中的网络请求卡死，且拿不到 JS 异常、无法点击 / 前进后退 / 改视口；CDP 才能做真实验收 |

---

## 2. 本地 `127.0.0.1:6789` 结果

| 测试集 | 通过 | 失败 | 报告文件 |
|---|---|---|---|
| 接口冒烟 `tests/smoke_test.py` | **97** | **0** | 控制台输出 |
| 真实浏览器 `tests/browser_test.py` | **88** | **0** | `tests/browser_report.json` |

### 2.1 接口测试覆盖（97 项）

| 分组 | 主要断言 |
|---|---|
| 服务 / 静态资源 | `/api/status` = GFIC 2.1、7 项能力标记；8 个静态资源 200 且非空（含 `v21.css` / `v21.js`） |
| 资讯 / 行情 | 790 条去重、0 未来时间戳、77 条 P1 官方原文；36 项行情无空价 / NaN |
| 官方宏观 | FRED 10 组带截止期与来源链接、美债曲线 2026-11-09、ECB 29 币种、World Bank 带 lastupdated |
| 加密 / SEC | BTC / ETH 各 4 所交叉；AAPL 10 项 XBRL 财务；非美股代码返回诚实错误 |
| 数据源 / 持久化 | 33 源状态完整、启停真实生效并 1:1 还原；自选股与预警写后回读且无测试残留 |
| **V2.1 今日总结** | 一句话 / 三个事件 / 机会 / 风险 / 温度 / 口径免责；每条事件带 what / why / 来源 |
| **V2.1 机会雷达** | 12 项 / 抓取 29 / 失败 0；等级 S,A,B,C,D 有区分度；**综合分逐项复核 = Σ(可得权重×得分)/Σ(可得权重)**，0 异常；缺失维度带原因；未接入能力带替代方案 |
| **V2.1 财务依据** | SEC 官方财务已进入评分（非全部维度标「未接入」）；最高置信度 0.75，最低可排名 ≥0.35 |
| 领先榜 / 优质公司 / 股票详情 / 成绩单 | 29 项真实区间涨跌且明确「历史表现 ≠ 未来」；12 家 SEC 真实财务；股票详情保留反向观点与结论失效条件；成绩单标注不使用未来数据 |
| 详情接口 / SPA 直达 | `/api/detail` 含等级依据、小白解释、相关报道；未知类型返回 400 + supported；`/stocks/AAPL`、`/news/<真实id>`、`/glossary`、`/opportunities` 均回 SPA 入口 |
| 国际化 | 五语言词典各 75 键；术语 PE 含通俗解释 / 高低 / 市场影响；23 条术语；P1/P2/P3 判定规则；单条与批量翻译按契约返回并保护数字 |
| 数据真实性总检 | 无 NaN / undefined / 模拟占位词；每条带来源与时间戳；价格为正；逐条免责声明 |

### 2.2 真实浏览器测试覆盖（88 项）

| 分组 | 主要断言 |
|---|---|
| 驾驶舱首屏 | 6,499 字、9 张卡片、含机会 / 风险 / 依据 / 数据口径；右侧 AI 今日总结 1,328 字 |
| 导航完整性 | 24 项（原 22 + AI 投资机会 + 术语词典），原有 dashboard/news/macro/sources/about 全部保留 |
| 机会雷达 | 7,725 字、8 张机会卡、等级 S,A,B,B,C,C,C,D、SEC 依据可见；**周期切换 / 市场筛选按钮真的重算** |
| 词典 / 易懂模式 / 等级 | 23 个术语链接；弹窗 307 字通俗解释含偏高 / 影响；搜索框可过滤；P1/P2/P3 弹窗 442 字；易懂模式注入大白话 |
| 详情路由 | `detail/stocks/AAPL`、直达 `/stocks/AAPL`、`/news/<id>` 全通过；含多头 / 空头 / 风险 / 来源 |
| 前进后退 / 刷新 | `history.back()` → dashboard、`forward()` → glossary、刷新保持路由且正常渲染 |
| 翻译 | 日/中切换、localStorage 持久化、固定文案走本地词典；资讯详情双语对照 333 字、原文可切换；翻译 API 数字保护 |
| 主题 / 响应式 | 深浅主题；1920 / 1536 / 1366 / 平板 768 / 手机 390 五档视口生效、主内容区可见宽度、顶栏铺满、无横向溢出、内容仍可见；**截图人工复核** |
| V2.0 回归 | news / macro / sources / quotes 四视图正常渲染且含真实数据标记 |
| JS 运行时 | **0 条异常 / 控制台错误**；失败请求逐 URL 记录并即时复验；外链新闻缩略图因代理不可达而失败的，单独记录不算缺陷 |

---

## 3. 本轮发现并修复的真实 Bug

| # | 问题 | 根因 | 修复 | 验证 |
|---|---|---|---|---|
| 1 | V2.1 扩展层全部函数失效 | `v21.js` 用 `window.esc/num/S` 取全局，但 `app.js` 里这些是顶层 `const`，只在全局词法环境、不挂 `window` | 改为裸标识符；`cardHead` / `lineSVG` 同步改回 | 浏览器 0 JS 异常、驾驶舱正常渲染 |
| 2 | 残留调试语句 | `if (m) $('pageTitle妨') && 0;` | 删除 | `node --check` 通过 |
| 3 | 详情页首次跳转空白 | hash 变化时 `hashchange` 里 `h===S.view` 被跳过，不会触发 `mount()` | detail 分支显式调用 `mount()` | hash / 直达 URL 均通过 |
| 4 | 旧驾驶舱异步渲染可能覆盖新驾驶舱 | `app.js` 的 `init()` 在 `v21.js` 之前就启动了旧 `V.dashboard` | `freshHost()` 换掉 `#viewHost` 节点，旧异步渲染写入已脱离文档的节点 | 首屏稳定为 V2.1 驾驶舱 |
| 5 | 机会雷达全部 D 级、置信度 0.15 | `opportunities()` 默认 `with_fin=False`，SEC 财务明明已缓存却没进评分 | 服务端启用 `with_fin=True`；`financials(cached_only=True)` 只读缓存避免首屏阻塞；`_warm_research` 后台预热 SEC 并让缓存失效重算 | S/A/B/C/D 分级、置信度 0.5–0.75、0 抓取失败 |
| 6 | SEC 财务依据被挤出「为什么值得关注」 | `_reasons()` 把 SEC 事实排在行情条目之后，`why[:4]` 截断 | 官方申报事实提到前排，展示上限放宽到 6 条 | 机会卡可见 SEC 净利率 / ROE |
| 7 | 领先榜免责声明显示 `**` 星号 | 后端字符串含 Markdown | 去掉 `**` | 接口断言「无 Markdown 星号」通过 |
| 8 | 手机 390px 横向溢出 54px | `.top-actions` 宽 401px 且 `flex:none`，撑破整页 | ≤420px 改为可横向滚动条带，按钮全部保留 | `scrollWidth=390 = clientWidth` |
| 9 | 易懂模式在词典 / 详情页无任何变化 | 这些视图未注入 `easyBlock` | 词典 / 股票详情 / 资讯详情补大白话解释 | 易懂模式注入 ≥1 处 |
| 10 | `/glossary`、`/opportunities` 直达 404 | 后端 SPA fallback 只覆盖两段以上路径 | 后端加视图白名单；前端 `normalizePath()` 支持单段视图 | 两条直达路由 200 HTML |
| 11 | 批量翻译测试用错契约 | `translate_batch` 接受 `title/summary` 字段而非 `text` | 测试按真实契约断言 `title_translated` | 通过 |
| 12 | V2.0 快照目录权限 000 | NAS root umask 导致目录不可遍历 | `chmod 755` 目录 / 700 secrets / 600 敏感文件；新快照脚本显式 chmod | 目录可正常访问 |
| 13 | **平板 / 手机主内容被挤成一条竖排文字窄列** | `@media(max-width:980px)` 把 `.app-shell` 设为两列 `0 minmax(0,1fr)`，但侧栏同时 `position:fixed` 脱离网格流，`.main-col` 落到 0 宽的第一列 | `v21.css` 在 ≤980px 覆盖为单列 `minmax(0,1fr)`；自动化测试新增「主内容区可见宽度 ≥ 阈值」「顶栏铺满」断言 | 768/390 主区 725px / 372px，截图人工复核正常 |
| 14 | NAS 上 AAPL `/api/sec` 返回 0 项财务 | SEC companyfacts 偶发截断/抖动产生「有公司名/公告但 0 财务」的降级结果，被缓存 1 小时（内存）+ 24 小时（磁盘） | `fetch_sec` 解析失败立即重试、降级结果标 `partial` 且内存只缓存 60s；`financials` 只缓存含真实 `facts` 的结果、失败结果不落 24h；`quality` 加 5 分钟 TTL | NAS AAPL / MSFT / NVDA 各 10 项财务，优质公司榜 12 家含 AAPL |
| 15 | V2.1 快照 `manifest.json` 缺 `verified` 字段 | 脚本先写 manifest、后计算 `REPORT["verified"] = ok`，磁盘清单是浅拷贝，字段没落盘 | 把全部 `check` 与 `verified` 计算提前到写盘前，`checks` / `errors` / `verified` 同步写入 | 独立复核 `verified=true`、19/19、0 错误 |
| 16 | 回滚脚本命名与交付文档不一致 | `suffix` 直接由 `GFIC_V2.1` 生成 `gfic_v2_1`，且 V2.0 回滚引用误写成 `rollback_to_v2_0.sh`（NAS 实际为 `rollback_to_v2.0.sh`） | `suffix` 规范化为 `v2_1`；V2.0 引用改回实际文件名 | `rollback_to_v2_1.sh` / `rollback_to_v2.0.sh` 均存在、755、`bash -n` 通过，且各自指向正确快照目录 |

---

## 4. 数据真实性 / AI 推荐质量审计

- **无虚构**：机会数据全量 JSON 扫描无 `NaN` / `undefined` / 模拟 / 示例 / 占位词；每条带 `source` 与 `data_updated`；价格为正；逐条「不构成投资建议」。
- **可解释评分**：100 分制 8 维（趋势 10 / 量能 5 / 财务健康 10 / 盈利 15 / 基本面 20 / 成长 15 / 估值 15 / 行业 10），**缺失维度不补分**，综合分只在可得权重上归一，置信度 = 可得权重 / 100；<0.35 暂停排名。已逐条复核 12 个标的的 composite，0 异常。
- **风险与反向观点**：每条含 `why`（依据）、`risks`（风险）、`bull`（多头）、`bear`（空头）、`conclusion`（结论）与 `plan.invalidation`（结论失效条件）；股票详情保留反向观点。
- **仍诚实标注的缺口**：估值（PE/PB/PS/EV-EBITDA 与市值无免费 Key 接口）、行业景气指数、A股/港股/欧股财务（SEC 不覆盖）、全市场筛选器、实时授权行情。这些在界面「未接入的机会类型」中列出原因与替代方案，**不凑数**。
- **翻译上游限制**：内网 `freellmapi` 当前返回 `HTTP 429 Too Many Requests`，动态内容翻译按设计**诚实回退原文**并标注 `fallback=true` / 原因；固定 UI 文案走本地五语言词典（各 75 键）不依赖 AI；简繁转换为本地字典。这是上游限流，不是代码缺陷，限流解除后自动恢复（结果磁盘缓存）。

---

## 5. NAS `192.168.10.110:6789` 部署验收

| 测试集 | 通过 | 失败 |
|---|---|---|
| 接口冒烟 `tests/smoke_test.py` | **97** | **0** |
| 真实浏览器 `tests/browser_test.py` | **88** | **0** |

- 容器：`finance-radar` · `Up (healthy)` · `0.0.0.0:6789->6789/tcp`；镜像 `finance-radar:latest`（`python:3.12-alpine`，Dockerfile 已 COPY 四个后端模块）。
- `/api/status` 返回 `GFIC 2.1` + 7 项能力标记；资讯 739–769 条去重、行情 36 项。
- 静态资源 `/static/v21.css` / `/static/v21.js`、`/glossary`、`/opportunities`、`/stocks/AAPL` 均 200；SPA fallback 正常。
- 机会雷达：12 项 / 抓取 29 / 失败 0；SEC 官方财务已进入评分；优质公司榜 12 家（含 AAPL）；AAPL / MSFT / NVDA 各 10 项 XBRL 财务。
- 浏览器：9 张截图（驾驶舱 / 机会雷达 / 词典 / 股票详情 / 资讯详情 / 浅色主题 / 1920 / 平板768 / 手机390 / 翻译双语），人工复核无纯文本、无遮挡、无空白、无竖排窄列；0 条 JS 异常。
- 仅有的失败请求是外链新闻缩略图 `images.mktw.net`（代理不可达），已如实记录，不影响站内功能与数据；站内接口复验全部 200。
- 部署前已比对本地与 NAS 的 `config.json`，SHA256 完全一致，未覆盖任何线上配置；`data/` 卷未清空、未重建。

---

## 6. 快照与回滚

| 项 | 路径 |
|---|---|
| V2.0 升级前快照 | `/vol1/1000/docker/GFIC/backups/snapshots/GFIC_V2.0/`（18/18 校验通过、37 文件 / 444,355 B、数据备份恢复演练 SHA256 一致） |
| 一键回滚到 V2.0 | `sudo bash /vol1/1000/docker/GFIC/backups/rollback_to_v2.0.sh` |
| V2.1 升级完成快照 | `/vol1/1000/docker/GFIC/backups/snapshots/GFIC_V2.1/`（**19/19 校验通过、`verified=true`、0 错误**；数据备份恢复演练逐文件 SHA256 一致；文件数与全文件哈希见 `manifest.json`） |
| 一键回滚到 V2.1 | `sudo bash /vol1/1000/docker/GFIC/backups/rollback_to_v2_1.sh` |

回滚脚本会先把当前现场另存 `backups/pre-rollback-<时间戳>/`，再停服 → 还原代码 → 还原凭据 → 还原数据 → 重建容器 → 健康检查。

**V2.1 快照生成方式**（在 NAS 上以 root 执行，只读采集，不修改运行目录）：

```bash
sudo GFIC_SNAPSHOT_NAME=GFIC_V2.1 \
     GFIC_SNAPSHOT_LABEL=GFIC_V2.1_升级完成版本 \
     GFIC_EXPECT_VERSION="GFIC 2.1" \
     GFIC_GIT_COMMIT=<commit> GFIC_GIT_TAG=<tag> \
     python3 /vol1/1000/docker/finance-radar/scripts/snapshot.py
```

快照生成时自动校验：后端四模块与前端五件套齐全、凭据隔离且 600、环境变量脱敏、`docker inspect` 与端口 6789、路由与 API 清单、线上版本为 `GFIC 2.1`、数据文件逐个复制、独立 `database_backup.tar.gz` 可读、恢复演练逐文件 SHA256 一致且 JSON 可解析、源码整包不含 `config.json`、一键回滚脚本已生成、`manifest.json` 无明文密钥。逐项 `ok` 与 `verified` 结果写入快照内 `manifest.json`；**未通过的项会标 FAIL 并使快照校验失败**，不会静默当成成功。
