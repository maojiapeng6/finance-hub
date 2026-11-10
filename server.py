#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GFIC 全球金融情报中心 (Global Financial Intelligence Center) — v2.0
端口 6789 | 零第三方依赖(仅 Python 标准库) | 本机 / Docker 容器均可运行

架构：供应商 → 数据源适配层(gfic_sources) → 清洗/标准化 → 缓存 → 业务 API → 前端
数据源（全部免费、真实、可溯源）：
  A 级官方  FRED / 美国财政部 / World Bank / Eurostat / ECB / SEC EDGAR / 美联储 / EIA / WTO / BOJ
             Binance / Coinbase / Kraken / OKX 交易所公开行情
  B 级      Frankfurter (ECB 参考汇率封装)
  C 级      Yahoo Finance (非官方·延迟) / Google News RSS / CNBC / MarketWatch / BBC / Guardian 等
  D 级      Reddit r/stocks (社交情绪，不作投资结论依据)
  AI        freellmapi (OpenAI 兼容 /v1/chat/completions)，密钥仅存服务端

原则：不虚构行情、不模拟新闻、不把延迟数据标为实时；无数据显示「暂无数据」。
"""
import json, os, re, time, html, threading, webbrowser
import urllib.request, urllib.error, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gfic_sources as gs

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
CATALOG_PATH = os.path.join(BASE, "sources_catalog.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

NEWS = {"items": [], "updated": 0, "errors": {}}
QUOTES = {"items": [], "updated": 0, "errors": {}}
BRIEF = {"text": "", "updated": 0, "status": "pending", "err": "", "refs": []}
CFG = {}
LOCK = threading.Lock()


def load_config():
    global CFG
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        CFG = json.load(f)
    # 容器/部署环境覆盖（不改动配置文件本身）
    if os.environ.get("FR_NO_BROWSER") == "1":
        CFG["open_browser"] = False
    if os.environ.get("FR_PROXY") is not None:
        CFG["proxy"] = os.environ.get("FR_PROXY") or ""
    if os.environ.get("FR_LLM_BASE"):
        CFG["llm"]["base_url"] = os.environ["FR_LLM_BASE"]
    # 密钥优先从服务端环境变量注入；config.json 为受保护的本地回退，绝不发送到浏览器
    if os.environ.get("FR_LLM_KEY"):
        CFG["llm"]["api_key"] = os.environ["FR_LLM_KEY"]
    gs.init(CFG)


# ---------------- 网络层：直连优先，失败回退代理 ----------------
def _build_opener(proxy):
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    # 显式禁用环境代理，保证"直连"确定可达内网服务(如 freellmapi)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url, timeout=20, as_json=False, validate=None):
    # 已确认本机/容器外网需经代理，故代理优先、直连兜底，避免每个源先等一次超时
    px = CFG.get("proxy")
    attempts = [px, None] if px else [None]
    for proxy in attempts:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with _build_opener(proxy).open(req, timeout=timeout) as r:
                text = r.read().decode("utf-8", "ignore")
            if validate and not validate(text):
                continue
            return json.loads(text) if as_json else text
        except Exception:
            continue
    return None


def fetch_json(url, timeout=20):
    return fetch(url, timeout, as_json=True,
                 validate=lambda t: t.strip().startswith("{"))


def fetch_rss(url, timeout=20):
    return fetch(url, timeout,
                 validate=lambda t: any(x in t for x in ("<rss", "<feed", "<item", "<entry")))


# ---------------- RSS 解析 ----------------
def _local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _find_text(parent, name):
    for child in parent.iter():
        if child is not parent and _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_rss(xml_text):
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    nodes = []
    chan = root.find("channel")
    if chan is not None:
        nodes = chan.findall("item")
    if not nodes:
        nodes = root.findall(".//item") + root.findall(".//{*}item")
    if not nodes:
        nodes = root.findall(".//entry") + root.findall(".//{*}entry")
    for idx, it in enumerate(nodes):
        title = _find_text(it, "title")
        if not title:
            continue
        img = ""
        for el in it.iter():
            tag = el.tag.split("}")[-1].lower()
            if tag in ("content", "thumbnail") and el.get("url"):
                img = el.get("url"); break
            if tag == "enclosure" and (el.get("type") or "").startswith("image") and el.get("url"):
                img = el.get("url"); break
        raw_sum = _strip_tags(_find_text(it, "description") or
                              _find_text(it, "summary") or
                              _find_text(it, "content"))
        # Google News 的 description 只是「标题 + 来源」的 HTML 链接，无信息量
        if raw_sum and (title[:24] in raw_sum or raw_sum.startswith(title[:18])):
            raw_sum = ""
        out.append({
            "image": img,
            "title": html.unescape(title),
            "link": _find_text(it, "link"),
            "summary": raw_sum[:260],
            "published": _parse_date(_find_text(it, "pubDate") or
                                     _find_text(it, "published") or
                                     _find_text(it, "updated")) or
                         (int(time.time()) - 3600 - idx * 60),
            "source": _find_text(it, "source"),
        })
    return out


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            continue
    return None


# ---------------- 资讯富化（通俗解读 / 关联标的 / 可点链接） ----------------
_HINT_RULES = [
    (r"降息|加息|利率|美联储|Fed|FOMC|鲍威尔|通胀|CPI|PPI|非农|就业|失业率|货币政策",
     "影响资金成本与估值锚，通常牵动美元、美债、黄金和成长股。"),
    (r"财报|营收|利润|业绩|指引|EPS|earnings|revenue|guidance|profit",
     "公司业绩信息，重点看是否超预期，以及管理层对下一季的指引。"),
    (r"收购|并购|merger|acquisition|buyout|takeover|私有化",
     "并购事件，通常影响双方股价、行业竞争格局与后续整合预期。"),
    (r"原油|油价|OPEC|天然气|EIA|能源库存|crude|oil",
     "能源供需消息，常影响原油、能源股与整体通胀预期。"),
    (r"黄金|白银|贵金属|gold|silver",
     "贵金属走势，往往反映避险情绪与实际利率的变化。"),
    (r"关税|贸易|制裁|出口管制|芯片限制|tariff|sanction|export control",
     "贸易与政策变化，可能影响供应链、进出口企业利润与相关行业。"),
    (r"AI|人工智能|芯片|半导体|英伟达|NVIDIA|GPU|算力|光刻|晶圆|数据中心",
     "科技产业链消息，关注算力需求、订单变化与上下游传导。"),
    (r"比特币|以太坊|加密|数字资产|BTC|ETH|crypto|ETF",
     "数字资产波动大，重点看资金流向、杠杆水平与监管口径。"),
    (r"央行|国务院|证监会|财政部|A股|港股|中国经济|政策|刺激|降准|LPR",
     "国内政策与宏观，关注对流动性、行业景气度与市场情绪的影响。"),
    (r"战争|冲突|地缘|中东|军事|导弹|停火|选举|大选|geopolitics|war",
     "地缘事件，常推升避险资产（黄金、美元），并扰动能源与风险偏好。"),
    (r"指数|美股|大盘|涨跌|抛售|反弹|rally|selloff|stocks|market",
     "市场整体表现，结合成交量与领涨板块判断是普涨还是结构性行情。"),
]
_SYMBOLS = [
    (r"英伟达|NVIDIA|NVDA", "NVDA", "英伟达"), (r"苹果|Apple|AAPL", "AAPL", "苹果"),
    (r"特斯拉|Tesla|TSLA", "TSLA", "特斯拉"), (r"微软|Microsoft|MSFT", "MSFT", "微软"),
    (r"谷歌|Google|Alphabet|GOOGL", "GOOGL", "谷歌"), (r"亚马逊|Amazon|AMZN", "AMZN", "亚马逊"),
    (r"Meta|脸书|META", "META", "Meta"), (r"台积电|TSMC", "TSM", "台积电"),
    (r"比特币|BTC|Bitcoin", "BTC-USD", "比特币"), (r"以太坊|ETH|Ethereum", "ETH-USD", "以太坊"),
    (r"黄金|Gold", "GC=F", "黄金期货"), (r"原油|Crude|Oil|WTI", "CL=F", "WTI原油"),
    (r"标普|S&P|SP500", "%5EGSPC", "标普500"), (r"纳斯达克|Nasdaq", "%5EIXIC", "纳指"),
    (r"恒生|Hang Seng", "%5EHSI", "恒生指数"), (r"日经|Nikkei", "%5EN225", "日经225"),
    (r"上证|A股|沪指", "000001.SS", "上证指数"),
]


def enrich(it):
    """给每条资讯附加：站点域名、通俗解读、可点的关联标的、话题标签、外链。"""
    title = it.get("title") or ""
    link = it.get("link") or ""
    try:
        u = urllib.parse.urlparse(link)
        domain = (u.netloc or "").lower().replace("www.", "")
        site = u.scheme + "://" + u.netloc if u.netloc else ""
    except Exception:
        domain, site = "", ""
    hint = ""
    for pat, txt in _HINT_RULES:
        if re.search(pat, title, re.I):
            hint = txt; break
    if not hint:
        hint = "点「打开原文」看全文；用「搜相关」可跨全部资讯比对同一话题的其他报道。"
    syms = []
    for pat, sym, name in _SYMBOLS:
        if re.search(pat, title, re.I):
            syms.append({"name": name, "url": "https://finance.yahoo.com/quote/" + sym})
        if len(syms) >= 3:
            break
    kws = []
    for w in ["美联储", "降息", "通胀", "英伟达", "AI", "财报", "黄金", "原油", "比特币",
              "A股", "港股", "关税", "半导体", "中国经济", "美债", "OPEC", "ETF"]:
        if w.lower() in title.lower():
            kws.append(w)
    it.update({
        "domain": domain, "site": site, "hint": hint, "symbols": syms, "tags": kws[:3],
        "search": "https://www.bing.com/news/search?q=" + urllib.parse.quote(title[:60]),
    })
    return it


# ---------------- 新闻聚合 ----------------
def _norm(t):
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", t.lower()).strip()


def _gnews_url(q):
    """构造 Google News RSS 地址（实测可用；支持搜索与 topic:BUSINESS 形式）"""
    zh = q.get("market") == "zh"
    hl, gl, ceid = ("zh-CN", "CN", "CN:zh-Hans") if zh else ("en-US", "US", "US:en")
    ceid_q = urllib.parse.quote(ceid, safe=":")
    query = q["query"]
    if query.startswith("topic:"):
        return ("https://news.google.com/rss/headlines/section/topic/%s?hl=%s&gl=%s&ceid=%s"
                % (query.split(":", 1)[1], hl, gl, ceid_q))
    return ("https://news.google.com/rss/search?q=%s&hl=%s&gl=%s&ceid=%s"
            % (urllib.parse.quote(query), hl, gl, ceid_q))


def collect_news(force=False):
    now = time.time()
    if not force and NEWS["items"] and now - NEWS["updated"] < CFG["refresh"]["news_minutes"] * 60:
        return NEWS

    jobs = []
    queries = CFG.get("news", {}).get("queries") or CFG.get("news", {}).get("bing_queries") or []
    for q in queries:
        url = _gnews_url(q)
        jobs.append((q["key"], url, q["category"], "Google News", q.get("market", "en"), "P2"))
    for f in CFG.get("news", {}).get("direct_feeds", []):
        jobs.append((f["name"], f["url"], f["category"], f["name"], f.get("market", "en"),
                     f.get("priority", "P2")))

    def work(job):
        key, url, cat, src, region, prio = job
        xmlt = fetch_rss(url)
        if not xmlt:
            return key, []
        res = []
        for it in parse_rss(xmlt)[:30]:   # 单一来源限量，避免一家刷屏
            it.update({"category": cat, "priority": prio, "region": region,
                       "source": it.get("source") or src})
            res.append(it)
        return key, res

    merged, errs = [], {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for fu in as_completed(futs):
            try:
                key, res = fu.result()
                if not res:
                    errs[key] = "unreachable"
                merged.extend(res)
            except Exception as e:
                errs[str(e)] = "error"

    # 按标题相似度去重（跨源同题合并，保留最权威/最新一条）
    seen, out = [], []
    for it in merged:
        k = _norm(it["title"])
        if not k or len(k) < 6:
            continue
        ka = set(k.split())
        dup = False
        for old in seen:
            oa = set(old.split())
            if k == old or (ka and oa and len(ka & oa) / min(len(ka), len(oa)) > 0.78):
                dup = True
                break
        if dup:
            continue
        seen.append(k)
        out.append(enrich(it))
    out.sort(key=lambda x: x.get("published", 0), reverse=True)

    with LOCK:
        NEWS["items"] = out
        NEWS["updated"] = int(now)
        NEWS["errors"] = errs
    return NEWS


# ---------------- 行情 ----------------
def _one_quote(group, sym):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1m&range=1d" % urllib.parse.quote(sym)
    d = fetch_json(url)
    if not d or not d.get("chart", {}).get("result"):
        return sym, None
    try:
        r = d["chart"]["result"][0]
        meta = r["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        closes = r["indicators"]["quote"][0]["close"]
        spark = [round(x, 3) for x in closes if x is not None][-32:]
        chg = (price - prev) if (price is not None and prev) else 0
        pct = (chg / prev * 100) if prev else 0
        return sym, {
            "group": group, "symbol": sym,
            "name": meta.get("shortName") or sym,
            "price": price, "prev": prev,
            "change": round(chg, 3), "pct": round(pct, 2),
            "time": int(meta.get("regularMarketTime", time.time())),
            "spark": spark, "currency": meta.get("currency", ""),
        }
    except Exception:
        return sym, None


def fetch_quotes():
    now = time.time()
    if QUOTES["items"] and now - QUOTES["updated"] < CFG["refresh"]["quotes_minutes"] * 60:
        return QUOTES
    jobs = [(g, s) for g, syms in CFG.get("quotes", {}).get("symbols", {}).items() for s in syms]
    out, errs = [], {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_one_quote, g, s) for g, s in jobs]
        for fu in as_completed(futs):
            try:
                sym, data = fu.result()
                if data:
                    out.append(data)
                else:
                    errs[sym] = "no-data"
            except Exception as e:
                errs[str(e)] = "error"
    out.sort(key=lambda x: (list(CFG["quotes"]["symbols"]).index(x["group"]) if x["group"] in CFG["quotes"]["symbols"] else 99,))
    with LOCK:
        QUOTES["items"] = out
        QUOTES["updated"] = int(now)
        QUOTES["errors"] = errs
    return QUOTES


# ---------------- 情绪 / 热点 ----------------
_POS = "涨 升 增长 利好 反弹 突破 盈利 超预期 复苏 宽松 大涨 新高 乐观 上涨 增益 强劲 回暖 提振 受益 扩产 创新高 飘红 走强 rally gain surge jump rise record boost optimism stimulus".split()
_NEG = "跌 暴跌 下跌 利空 衰退 危机 制裁 冲突 做空 亏损 不及预期 收紧 抛售 风险 警告 违约 崩盘 跌停 下滑 承压 重挫 杀跌 走低 疲软 降温 selloff slump plunge drop fall risk warning crisis tariff recession cut".split()


def sentiment(items, window=200):
    pos = neg = 0
    for it in items[:window]:
        t = it["title"].lower()
        p = sum(t.count(w.lower()) for w in _POS)
        n = sum(t.count(w.lower()) for w in _NEG)
        if p > n:
            pos += 1
        elif n > p:
            neg += 1
    tot = pos + neg
    return {"score": round((pos - neg) / tot * 100) if tot else 0,
            "pos": pos, "neg": neg, "total": tot}


_STOP = set("的 了 和 与 在 是 对 及 为 以 将 其 该 此 一 一个 市场 报道 消息 相关 表示 显示 目前 今日 最新 或 被 把 从 到 有 也 更 最 已 将 会 能 可 中 上 下 "
            "a an the of to in on for and with at by from is are be as stocks market news says said new over us after more than could would "
            "into about up down what why how not but its it this that their they has have will one two first last week year day shares stock "
            "reuters cnbc bloomberg com www https http".split())


def topics(items, top=14):
    cnt = {}
    for it in items[:300]:
        for w in _norm(it["title"]).split():
            if len(w) > 1 and w not in _STOP and not w.isdigit():
                cnt[w] = cnt.get(w, 0) + 1
    return [{"word": w, "count": c} for w, c in
            sorted(cnt.items(), key=lambda x: x[1], reverse=True)[:top]]


# ---------------- AI (freellmapi) ----------------
_COT = re.compile(r"(the user asks|we need to|here'?s (a )?thinking|means:|first,? i need|"
                  r"the user wants|let me think|analysis:|step 1:)", re.I)


# 上游模型偶发把「英文原文清单 + 自我核对草稿」一起吐出来，必须挡住
_LEAK = re.compile(
    r"(等等[，,]?\s*我|我需要检查|现在检查|让我核对|检查一下|对于第\s*\d+\s*条|"
    r"我应该|可以接受|为了严谨|不过为了|原文没有|标题说|翻译为|没有添加数字|"
    r"都在了|每个短句|按规则写|所有编号|"
    r"let me check|i need to check|as requested|note:)", re.I)


def _sanitize(t):
    """清洗上游推理模型可能泄漏的英文思维链、原始清单与代码块"""
    t = re.sub(r"<think>[\s\S]*?</think>", "", t or "", flags=re.I)
    t = re.sub(r"^```[a-zA-Z]*\s*$", "", t, flags=re.M).replace("```", "")
    # 统一在服务端去掉 Markdown 加粗标记，前端 / API / 日志都拿到纯文本
    t = t.replace("**", "")
    if "【" in t:                       # 简报正文从第一个小节标题开始
        t = t[t.index("【"):]
    # 简报规定以「今日关键词」收尾，其后一律是模型自检草稿，直接裁掉
    m = re.search(r"今日关键词：[^\n]*", t)
    if m:
        t = t[:m.end()]
    return t.strip()


def _good(t, min_len, max_len=3000):
    """输出质量校验：长度合适、中文占比够、无思维链/自检草稿/英文原始清单"""
    if not t or len(t) < min_len or len(t) > max_len:
        return False
    zh = len(re.findall(r"[\u4e00-\u9fff]", t))
    if zh / max(1, len(t)) < 0.40:
        return False
    if _COT.search(t[:220]) or _LEAK.search(t):
        return False
    # 上游把输入里已编号的英文标题原样抄回来（>2 行）视为未归纳
    if len(re.findall(r"^\s*\d+\.\s+[A-Za-z]", t, re.M)) > 2:
        return False
    return True


def _llm_chat(system, user, max_tokens=900, min_len=100, max_len=3000, accept=None):
    """freellmapi 调用：auto 优先 + 备选模型轮转 + 质量校验重试。
    实测 auto 偶发路由到 2.6B 推理模型吐英文 CoT 并被 length 截断，故必须校验。
    accept: 额外的业务校验回调（如简报必须带 [n] 溯源编号）。"""
    llm = CFG.get("llm", {})
    if not llm.get("enabled"):
        return None, "AI 未启用"
    url = llm["base_url"].rstrip("/") + "/chat/completions"
    models = llm.get("models") or [llm.get("model", "auto")]
    retries = llm.get("retries", 3)
    budget = llm.get("budget", 150)
    deadline = time.time() + budget
    last = "未知错误"
    for attempt in range(retries):
        for model in models:
            if time.time() > deadline:
                return None, "AI 上游响应超时（%ds 预算），请点「重生成」再试" % budget
            payload = {"model": model,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}],
                       "temperature": 0.3, "max_tokens": max_tokens}
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + llm.get("api_key", "")})
            try:
                # freellmapi 在内网，强制直连，不经过外网代理
                with _build_opener(None).open(req, timeout=llm.get("timeout", 40)) as r:
                    resp = json.loads(r.read().decode("utf-8", "ignore"))
                ch = resp["choices"][0]
                txt = _sanitize(ch["message"]["content"])
                if ch.get("finish_reason") == "length" and not _good(txt, min_len, max_len):
                    last = "上游输出被截断(%s)" % model
                    continue
                if not _good(txt, min_len, max_len) or (accept and not accept(txt)):
                    last = "输出质量不合格(%s, %d字)" % (model, len(txt))
                    continue
                return txt, None
            except Exception as e:
                last = "%s: %s" % (model, e)
                continue
    return None, "AI 上游不稳定，已重试 %d 轮（%s）。可点「重生成」再试" % (retries, last[:90])


def build_brief(force=False):
    now = time.time()
    if not force and BRIEF["text"] and now - BRIEF["updated"] < CFG["refresh"]["brief_minutes"] * 60:
        return BRIEF
    items = NEWS["items"] or collect_news()["items"]
    if not items:
        BRIEF["status"] = "waiting"
        BRIEF["err"] = "资讯尚未就绪"
        return BRIEF
    picked, seen = [], set()
    for cat in dict.fromkeys(i.get("category", "") for i in items):
        for it in [x for x in items if x.get("category", "") == cat][:7]:
            if it["title"] not in seen:
                seen.add(it["title"]); picked.append(it)
    for it in items[:15]:
        if it["title"] not in seen:
            seen.add(it["title"]); picked.append(it)
    picked = picked[:50]
    lines = "\n".join("%d. [%s][%s] %s" % (i + 1, it.get("category", ""),
                                            it.get("source", ""), it["title"])
                      for i, it in enumerate(picked))
    refs = [{"n": i + 1, "title": it["title"], "link": it.get("link", ""),
             "source": it.get("source", "")} for i, it in enumerate(picked)]
    # 严格归纳式提示词：禁止跨条拼接与编造，句末必须标注来源编号，保证可回溯
    system = ("你是严谨的财经资讯编辑，服务对象为中文散户。你的任务是把下面【已编号】的资讯标题"
              "归纳复述成一份简体中文『盘面与局势简报』，不是创作、不是预测。\n"
              "铁律（违反即算错误）：\n"
              "1. 只能复述标题里明确写了的事实。禁止推断、补充、延伸，禁止编造任何数字、时间、人物、"
              "公司、因果关系或『可能/据传』的猜测。\n"
              "2. 一条资讯写一句短句，句末标注其编号，如 [3]。严禁把不同编号的两条新闻拼成一句，"
              "更严禁把 A 公司的事安到 B 公司头上。\n"
              "3. 某小节没有对应资讯就写『暂无明确相关资讯』，不要硬凑、不要用旧知识填充。\n"
              "4. 不喊单、不预测点位、不给买卖建议。\n"
              "格式：仅以下五个小节，每节 1-3 句；最后单起一行『今日关键词：』列 3-5 个词（须来自标题）。"
              "不要 markdown 代码块或表格。\n"
              "【全球局势】\n【宏观与财经】\n【股市风向】\n【商品与加密】\n【风险提示】")
    user = "以下为近实时聚合资讯（已去重、已编号），请据此生成简报：\n%s" % lines
    txt, err = _llm_chat(system, user, CFG["llm"].get("brief_max_tokens", 2400),
                         min_len=200, max_len=1800,
                         accept=lambda x: len(re.findall(r"\[\d+\]", x)) >= 8)
    if err:
        BRIEF["status"] = "error"
        BRIEF["err"] = err
    else:
        BRIEF["text"] = txt
        BRIEF["refs"] = refs
        BRIEF["status"] = "ok"
        BRIEF["updated"] = int(now)
        BRIEF["err"] = ""
    return BRIEF


def _ai_context():
    """AI 工作台的站内真实数据上下文：只放 GFIC 已接入的数据，并标注来源/时间/口径。"""
    b = []
    b.append("【GFIC 站内数据 · 全部为真实接入数据，非模型自带知识】")
    if NEWS["items"]:
        b.append("· 最新资讯（来源已标注，时间 %s）：" % datetime.fromtimestamp(
            NEWS["updated"]).strftime("%Y-%m-%d %H:%M"))
        b += ["  - %s｜%s" % (it.get("source", ""), it["title"]) for it in NEWS["items"][:22]]
    if QUOTES["items"]:
        b.append("· 行情快照（Yahoo Finance 非官方接口，约 15-20 分钟延迟）：")
        b += ["  - %s %s %s %+.2f%%" % (x["symbol"], x["name"], x["price"], x["pct"])
              for x in QUOTES["items"][:20]]
    try:
        f = gs.fetch_fred() or {}
        rows = f.get("series", [])[:6]
        if rows:
            b.append("· 美国宏观（FRED 官方统计值，非实时，带统计截止期）：")
            b += ["  - %s %s %s（截至 %s，%s频）" %
                  (r["name"], r["value"], r["unit"], r["as_of"], r["frequency"]) for r in rows]
        t = gs.fetch_treasury() or {}
        if t.get("curve"):
            b.append("· 美债收益率曲线（美国财政部，%s，日更）：%s" %
                     (t["date"], "；".join("%s %s%%" % (c["tenor"], c["yield"]) for c in t["curve"][:6])))
            if t.get("spread_10y_2y") is not None:
                b.append("  - 10Y-2Y 期限利差：%s 个百分点" % t["spread_10y_2y"])
        c = gs.fetch_crypto() or {}
        for coin, d in (c.get("coins") or {}).items():
            b.append("· %s 多所交叉（%d 家交易所实时）：中位价 %s，所间价差 %s%%，平均涨跌 %s%%" %
                     (coin, d["exchanges"], d["median"], d["spread_pct"], d["avg_pct"]))
        e = gs.fetch_ecb_fx() or {}
        if e.get("date"):
            b.append("· ECB 官方参考汇率（%s，日更，非实时即期）：USD %s、JPY %s、CNY %s（每 1 EUR）" %
                     (e["date"], *[dict(e["rates"]).get(k, "—") for k in ("USD", "JPY", "CNY")]))
    except Exception:
        pass
    b.append("【数据口径】行情为延迟数据；宏观为统计发布值；加密为交易所实时接口。"
             "社交讨论量不等于资金流。以下未接入：期权链、ETF 持仓、A股财务全量、实时交易所行情。")
    return "\n".join(b)


def ai_ask(q):
    ctx = _ai_context()
    system = ("你是 GFIC 全球金融情报中心的 AI 金融助手，服务对象为中文个人投资者。"
              "作答必须优先引用下面给出的【GFIC 站内真实数据】，并注明来源与数据口径。\n"
              "铁律：\n"
              "1. 不得编造任何价格、财务指标、新闻、机构观点或数据来源；站内数据没有的内容，"
              "明确说明『当前接入数据中没有相关内容』或『该模块尚未接入数据源』。\n"
              "2. 明确区分【已验证事实】（站内数据）、【常识解释】与【个人观点】，不得混淆。"
              "延迟行情不得说成实时，年度宏观不得说成当前值。\n"
              "3. 不喊单、不给目标价、不承诺收益；涉及判断时同时给出风险与反面证据。\n"
              "4. 简洁、客观、分点、使用简体中文。")
    return _llm_chat(system, "站内数据：\n%s\n\n用户问题：%s" % (ctx, q),
                     CFG["llm"].get("ask_max_tokens", 1600), min_len=50)


# ---------------- 后台刷新 ----------------
def _bg_loop():
    while True:
        time.sleep(45)
        for fn in (collect_news, fetch_quotes, build_brief):
            try:
                fn()
            except Exception:
                pass
        try:
            gs.check_alerts(QUOTES["items"])
        except Exception:
            pass
        try:
            gs.save_state()
        except Exception:
            pass


def _warm_official():
    """启动时预热官方数据源（并发、失败不影响主服务）。"""
    for fn in (gs.fetch_fred, gs.fetch_treasury, gs.fetch_ecb_fx,
               gs.fetch_crypto, gs.fetch_eurostat, gs.fetch_worldbank,
               gs.fetch_frankfurter, gs.fetch_fiscaldata):
        try:
            fn()
        except Exception:
            pass
    try:
        gs.save_state()
    except Exception:
        pass


# ---------------- HTTP ----------------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        fp = os.path.normpath(os.path.join(BASE, path.lstrip("/")))
        if not fp.startswith(BASE) or not os.path.isfile(fp):
            return self._send(404, {"error": "not found"})
        ext = os.path.splitext(fp)[1].lstrip(".")
        ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript; charset=utf-8",
                 "css": "text/css; charset=utf-8", "json": "application/json; charset=utf-8",
                 "svg": "image/svg+xml", "ico": "image/x-icon"}.get(ext, "application/octet-stream")
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        route = p.path

        if route in ("/", "/index.html"):
            return self._static("/static/index.html")
        # 兼容 index.html 里的相对路径引用（曾导致 CSS/JS 全部 404、页面变纯文本）
        if route in ("/style.css", "/app.js", "/favicon.ico"):
            return self._static("/static" + route)
        if route.startswith("/static/"):
            return self._static(route)

        if route == "/api/events":
            # SSE：每 15s 推送一次状态，供前端感知"有新数据"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                for _ in range(80):
                    data = {"type": "tick", "news_updated": NEWS["updated"],
                            "quotes_updated": QUOTES["updated"],
                            "brief_updated": BRIEF["updated"],
                            "news_count": len(NEWS["items"]),
                            "time": int(time.time())}
                    self.wfile.write(("data: %s\n\n" % json.dumps(data)).encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(15)
            except Exception:
                pass
            return

        if route == "/api/status":
            return self._send(200, {
                "ok": True, "news_updated": NEWS["updated"], "quotes_updated": QUOTES["updated"],
                "brief_updated": BRIEF["updated"], "news_count": len(NEWS["items"]),
                "quotes_count": len(QUOTES["items"]), "news_errors": NEWS["errors"],
                "llm_enabled": CFG.get("llm", {}).get("enabled", False),
                "version": "GFIC 2.0", "sources": gs.status_summary(),
                "time": int(time.time()),
            })

        if route == "/api/news":
            collect_news()
            items = NEWS["items"]
            cat, prio = q.get("category", [""])[0], q.get("priority", [""])[0]
            src, kw = q.get("source", [""])[0], q.get("q", [""])[0].lower()
            if cat:
                items = [i for i in items if i.get("category") == cat]
            if prio:
                items = [i for i in items if i.get("priority") == prio]
            if src:
                items = [i for i in items if src.lower() in (i.get("source") or "").lower()]
            if kw:
                items = [i for i in items if kw in i["title"].lower() or
                         kw in (i.get("summary") or "").lower()]
            limit = int(q.get("limit", ["150"])[0])
            off = int(q.get("offset", ["0"])[0])
            return self._send(200, {"items": items[off:off + limit], "total": len(items),
                                   "updated": NEWS["updated"], "errors": NEWS["errors"]})

        if route == "/api/overview":
            items = NEWS["items"] or collect_news()["items"]
            qs = QUOTES["items"] or fetch_quotes()["items"]
            ranked = sorted([x for x in qs if x.get("pct") is not None],
                            key=lambda x: x["pct"], reverse=True)
            sen = sentiment(items)
            return self._send(200, {
                "total": len(items), "p1": sum(1 for x in items if x.get("priority") == "P1"),
                "latest": items[0]["published"] if items else 0,
                "sentiment": sen, "top": ranked[:3], "bottom": ranked[-3:][::-1],
                "quote_count": len(qs), "updated": int(time.time())})

        if route == "/api/quotes":
            fetch_quotes()
            return self._send(200, {"items": QUOTES["items"], "updated": QUOTES["updated"],
                                   "errors": QUOTES["errors"]})

        if route == "/api/markets":
            fetch_quotes()
            items = NEWS["items"] or collect_news()["items"]
            return self._send(200, {"quotes": QUOTES["items"], "sentiment": sentiment(items),
                                   "topics": topics(items), "updated": QUOTES["updated"]})

        if route == "/api/brief":
            return self._send(200, build_brief(force=q.get("regen", ["0"])[0] == "1"))

        if route == "/api/sources":
            try:
                with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                    return self._send(200, json.load(f))
            except Exception:
                return self._send(200, [])

        if route == "/api/search":
            kw = q.get("q", [""])[0].lower().strip()
            if not kw:
                return self._send(200, {"news": [], "sources": []})
            collect_news()
            news = [i for i in NEWS["items"] if kw in i["title"].lower() or
                    kw in (i.get("summary") or "").lower()][:40]
            try:
                with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                    cat = json.load(f)
            except Exception:
                cat = []
            src = [s for s in cat if kw in s.get("name", "").lower() or
                   kw in s.get("url", "").lower() or kw in s.get("cat", "").lower()][:40]
            return self._send(200, {"news": news, "sources": src})

        # ---------------- GFIC 2.0 新增业务 API ----------------
        if route == "/api/dashboard":
            items = NEWS["items"] or collect_news()["items"]
            qs = QUOTES["items"] or fetch_quotes()["items"]
            ranked = sorted([x for x in qs if x.get("pct") is not None],
                            key=lambda x: x["pct"], reverse=True)
            macro = {}
            try:
                m = gs.macro()
                macro = {k: {"updated": v.get("updated"), "stale": v.get("stale", False)}
                         for k, v in m["parts"].items()}
            except Exception:
                pass
            return self._send(200, {
                "total": len(items), "p1": sum(1 for x in items if x.get("priority") == "P1"),
                "latest": items[0]["published"] if items else 0,
                "sentiment": sentiment(items), "topics": topics(items, 12),
                "top": ranked[:5], "bottom": ranked[-5:][::-1],
                "quote_count": len(qs), "quote_groups": len(CFG["quotes"]["symbols"]),
                "macro": macro, "sources": gs.status_summary(),
                "alerts": gs.alerts().get("notifications", [])[:5],
                "data_policy": {"quotes": "Yahoo 非官方接口，约 15-20 分钟延迟",
                                "macro": "官方统计发布值，非实时",
                                "crypto": "交易所官方接口，实时",
                                "news": "仅标题/摘要/链接，不复制全文"},
                "updated": int(time.time())})

        if route == "/api/macro":
            return self._send(200, gs.macro())

        if route == "/api/crypto":
            return self._send(200, gs.fetch_crypto() or
                              {"coins": {}, "error": "数字资产数据源暂无数据", "stale": True})

        if route == "/api/sec":
            sym = q.get("symbol", [""])[0]
            return self._send(200, gs.fetch_sec(sym) if sym else
                              {"error": "请提供 symbol，例如 ?symbol=AAPL",
                               "universe": "SEC EDGAR 在美申报公司（约 1 万家）",
                               "source": "SEC EDGAR", "coverage": "不含 A股/港股"})

        if route == "/api/sources/status":
            return self._send(200, {"sources": gs.sources_status(NEWS["errors"], QUOTES["errors"]),
                                   "summary": gs.status_summary()})

        if route == "/api/sources/probe":
            return self._send(200, gs.probe(q.get("id", [""])[0]))

        if route == "/api/watchlist":
            return self._send(200, gs.watchlist())

        if route == "/api/alerts":
            return self._send(200, gs.alerts())

        if route == "/api/alerts/check":
            fetch_quotes()
            return self._send(200, gs.check_alerts(QUOTES["items"]))

        if route == "/api/heatmap":
            fetch_quotes()
            cells = [{"symbol": x["symbol"], "name": x["name"], "group": x["group"],
                      "pct": x["pct"], "price": x["price"], "pct_abs": abs(x["pct"])}
                     for x in QUOTES["items"] if x.get("pct") is not None]
            return self._send(200, {"cells": cells, "updated": QUOTES["updated"],
                                   "source": "Yahoo Finance（延迟行情）",
                                   "note": "涨红跌绿（中国市场习惯）；色深表示涨跌幅绝对值大小"})

        if route == "/api/refresh":
            what = q.get("what", ["all"])[0]
            if what in ("news", "all"):
                collect_news(force=True)
            if what in ("quotes", "all"):
                fetch_quotes()
            if what in ("brief", "all"):
                build_brief(force=True)
            if what in ("macro", "all"):
                with gs.LOCK:
                    for k in list(gs.CACHE):
                        if not k.startswith("sec:"):
                            gs.CACHE.pop(k, None)
            return self._send(200, {"ok": True, "what": what})

        self._send(404, {"error": "route not found"})

    def do_HEAD(self):
        p = urllib.parse.urlparse(self.path)
        fp = os.path.normpath(os.path.join(
            BASE, "static", p.path.lstrip("/")))
        if p.path in ("/", "/index.html"):
            fp = os.path.join(BASE, "static", "index.html")
        if not os.path.isfile(fp):
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8" if fp.endswith(".html") else "text/plain")
        self.send_header("Content-Length", str(os.path.getsize(fp)))
        self.end_headers()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        try:
            ln = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(ln).decode("utf-8", "ignore") or "{}") if ln else {}
        except Exception:
            data = {}
        if p.path == "/api/ask":
            q = (data.get("q") or "").strip()
            if not q:
                return self._send(400, {"error": "empty question"})
            ans, err = ai_ask(q)
            return self._send(502, {"error": err}) if err else self._send(200, {"answer": ans})
        if p.path == "/api/brief":
            return self._send(200, build_brief(force=True))

        # ---- GFIC 2.0：数据源管理 / 自选股 / 预警（均为真实持久化操作）----
        if p.path == "/api/sources/toggle":
            sid, on = (data.get("id") or "").strip(), bool(data.get("enabled"))
            res, err = gs.set_enabled(sid, on)
            return self._send(400, {"error": err}) if err else self._send(200, res)

        if p.path == "/api/sources/probe":
            return self._send(200, gs.probe((data.get("id") or "").strip()))

        if p.path == "/api/watchlist/save":
            payload = data.get("data")
            if not isinstance(payload, dict):
                return self._send(400, {"error": "data 必须是对象"})
            return self._send(200, gs.watchlist_save(payload))

        if p.path == "/api/alerts/save":
            payload = data.get("data")
            if not isinstance(payload, dict):
                return self._send(400, {"error": "data 必须是对象"})
            return self._send(200, gs.alerts_save(payload))

        self._send(404, {"error": "route not found"})


def main():
    load_config()
    port, host = CFG.get("port", 6789), CFG.get("host", "0.0.0.0")
    for fn in (collect_news, fetch_quotes, build_brief, _warm_official):
        threading.Thread(target=fn, daemon=True).start()
    threading.Thread(target=_bg_loop, daemon=True).start()
    url = "http://localhost:%d/" % port
    print("=" * 62)
    print("  GFIC 全球金融情报中心 v2.0  (Global Financial Intelligence Center)")
    print("  访问: %s" % url)
    print("  数据源: %d 个注册 / %d 个已实测可用 / A级官方 %d 个" % (
        len(gs.REGISTRY), sum(1 for s in gs.REGISTRY if s["status"] == "live"),
        sum(1 for s in gs.REGISTRY if s["grade"] == "A" and s["status"] == "live")))
    print("  端口: %d | 代理: %s | AI: %s | 成本: ¥0" % (
        port, CFG.get("proxy") or "直连", "启用" if CFG.get("llm", {}).get("enabled") else "关闭"))
    print("=" * 62, flush=True)
    if CFG.get("open_browser", True):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    srv = ThreadingHTTPServer((host, port), H)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
