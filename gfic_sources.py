#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GFIC 2.0 — 统一数据源适配层 (Data Source Adapter Layer)
=========================================================
职责：把「供应商」与「业务/前端」解耦。所有第三方数据只经本层进入系统。

设计原则（对应 V2.0 强制要求）：
  1. 每个数据源 = 注册表元数据 + 独立 adapter + 真实运行时状态。
  2. 状态只由真实网络请求更新，绝不伪造成功率/时间/条数。
  3. 每个源可独立启停；失败时保留上次成功数据并标记 stale，页面不崩。
  4. 所有返回值带 source / updated / frequency / latency / license / coverage。
  5. 只使用免费、公开、允许个人内部展示的数据；未接入的源如实标注原因与替代方案。
  6. 不产生任何虚构行情、随机数或模拟新闻。

安全说明：部分欧洲官方站点经本机代理时证书链不被 Python 信任，对这些
「公开只读 GET」使用 noverify；AI 密钥走内网直连 HTTP，从不使用该选项。
"""
import os, re, json, time, ssl, threading
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

PROXY = ""
# 实测：FRED 与 SEC 要求 User-Agent 中含可识别联系方式，否则请求被挂起直至超时。
# 该地址仅用于满足官方 UA 规范（个人内部研究），不代表对外服务。
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36 GFIC/2.0 "
      "(personal research; contact: research@example.com)")
_NV_CTX = ssl.create_default_context()
_NV_CTX.check_hostname = False
_NV_CTX.verify_mode = ssl.CERT_NONE

LOCK = threading.RLock()
CACHE = {}          # sid -> {"data":..., "ts":..., "ttl":...}
STATE = {}          # sid -> 真实运行时状态
_TICKERS = {"ts": 0, "map": {}}


# ---------------------------------------------------------------- 注册表
# grade: A=官方(交易所/政府/央行/监管) B=成熟专业供应商 C=公开媒体/聚合 D=社区
# status: live(已实测可用) / blocked(实测不可用) / planned(未接入，需授权或密钥)
def _src(**kw):
    d = dict(enabled=True, status="live", needs_key=False, official=True,
             free=True, cost="¥0", latency="", license="", coverage="",
             refresh=1800, note="", noverify=False, adapter="")
    d.update(kw)
    return d


REGISTRY = [
    # ===== A 级：官方原始数据源（已实测真实可用）=====
    _src(id="fred", name="FRED 美联储经济数据", grade="A", kind="宏观",
         provider="Federal Reserve Bank of St. Louis", coverage="美国 CPI/核心CPI/失业率/非农/联邦基金利率/GDP/M2/国债收益率/汇率",
         latency="日/月/季频，统计发布后更新，非实时", refresh=1800,
         license="FRED 公开数据，个人内部展示允许", home="https://fred.stlouisfed.org/",
         adapter="fred", note="无需 API Key，使用 fredgraph.csv 官方导出"),
    _src(id="treasury", name="美国财政部 国债收益率曲线", grade="A", kind="利率",
         provider="U.S. Department of the Treasury", coverage="1M~30Y 美债每日收益率曲线",
         latency="每日收盘后更新（约 T+0 晚间）", refresh=3600,
         license="美国政府公开数据", home="https://home.treasury.gov/",
         adapter="treasury", note="官方 Atom XML，实测最新 2026-11-09"),
    _src(id="fiscaldata", name="美国财政部 Fiscal Data", grade="A", kind="宏观",
         provider="U.S. Treasury Fiscal Service", coverage="国债平均利率/财政收支/债务",
         latency="月度", refresh=21600, license="美国政府公开数据",
         home="https://fiscaldata.treasury.gov/", adapter="fiscaldata", noverify=True),
    _src(id="worldbank", name="World Bank 世界银行", grade="A", kind="宏观",
         provider="World Bank", coverage="全球 GDP / 通胀 / 多国年度指标",
         latency="年度数据，发布有滞后（实测 lastupdated 2026-10-08）", refresh=21600,
         license="World Bank 开放数据 CC BY 4.0", home="https://data.worldbank.org/",
         adapter="worldbank", note="年度指标，禁止当作实时数据"),
    _src(id="eurostat", name="Eurostat 欧盟统计局", grade="A", kind="宏观",
         provider="Eurostat / European Commission", coverage="欧元区 HICP 调和通胀（月频）",
         latency="月频，数据截止期以官方返回为准", refresh=21600,
         license="Eurostat 公开数据可自由使用（需注明来源）",
         home="https://ec.europa.eu/eurostat", adapter="eurostat", noverify=True),
    _src(id="ecb_fx", name="ECB 欧洲央行参考汇率", grade="A", kind="外汇",
         provider="European Central Bank", coverage="欧元基准 29 种货币官方参考汇率",
         latency="每个工作日约 16:00 CET 发布，日更", refresh=3600,
         license="ECB 公开参考汇率", home="https://www.ecb.europa.eu/",
         adapter="ecb_fx", noverify=True, note="官方参考汇率，非银行间/零售/CFD 报价"),
    _src(id="sec_edgar", name="SEC EDGAR", grade="A", kind="监管披露",
         provider="U.S. SEC", coverage="美股 10414 家 10-K/10-Q/8-K 申报 + XBRL 财务事实",
         latency="申报披露即更新", refresh=3600,
         license="SEC 公开披露数据", home="https://www.sec.gov/edgar",
         adapter="sec_edgar", note="仅覆盖在美申报公司，不含 A股/港股；需合规 User-Agent"),
    _src(id="fed", name="美联储 新闻稿", grade="A", kind="官方公告",
         provider="Federal Reserve", coverage="FOMC / 货币政策 / 监管公告 RSS",
         latency="发布即推送", refresh=480, license="美联储公开信息",
         home="https://www.federalreserve.gov/", adapter="rss"),
    _src(id="sec_press", name="SEC 新闻稿", grade="A", kind="官方公告",
         provider="U.S. SEC", coverage="执法/监管新闻稿 RSS", latency="发布即推送",
         refresh=480, license="SEC 公开信息", home="https://www.sec.gov/news", adapter="rss"),
    _src(id="eia", name="EIA 美国能源署", grade="A", kind="官方公告",
         provider="U.S. Energy Information Administration", coverage="今日能源 / 原油天然气库存评论 RSS",
         latency="发布即推送", refresh=480, license="美国政府公开信息",
         home="https://www.eia.gov/", adapter="rss"),
    _src(id="wto", name="WTO 世贸组织", grade="A", kind="官方公告",
         provider="World Trade Organization", coverage="全球贸易 / 争端 / 政策 RSS",
         latency="发布即推送", refresh=480, license="WTO 公开信息",
         home="https://www.wto.org/", adapter="rss"),
    _src(id="boj", name="日本央行 BOJ", grade="A", kind="官方公告",
         provider="Bank of Japan", coverage="日本货币政策 / 统计 RSS",
         latency="发布即推送", refresh=480, license="BOJ 公开信息",
         home="https://www.boj.or.jp/en/", adapter="rss"),

    # ===== A 级：交易所官方公开行情接口 =====
    _src(id="binance", name="Binance 现货行情", grade="A", kind="数字资产",
         provider="Binance", coverage="BTC/ETH 现货 24h ticker", latency="实时（秒级）",
         refresh=60, license="交易所公开行情接口，个人内部展示",
         home="https://www.binance.com/", adapter="crypto", official=True),
    _src(id="coinbase", name="Coinbase Exchange", grade="A", kind="数字资产",
         provider="Coinbase", coverage="BTC-USD/ETH-USD 现货 ticker", latency="实时（秒级）",
         refresh=60, license="交易所公开行情接口", home="https://www.coinbase.com/", adapter="crypto"),
    _src(id="kraken", name="Kraken", grade="A", kind="数字资产",
         provider="Kraken", coverage="XBT/ETH-USD 现货 ticker", latency="实时（秒级）",
         refresh=60, license="交易所公开行情接口", home="https://www.kraken.com/", adapter="crypto"),
    _src(id="okx", name="OKX", grade="A", kind="数字资产",
         provider="OKX", coverage="BTC/ETH-USDT 现货 ticker", latency="实时（秒级）",
         refresh=60, license="交易所公开行情接口", home="https://www.okx.com/", adapter="crypto"),

    # ===== B 级：成熟公开接口 =====
    _src(id="frankfurter", name="Frankfurter 汇率 API", grade="B", kind="外汇",
         provider="Frankfurter (基于 ECB 参考汇率)", coverage="USD 基准多币种日度参考汇率",
         latency="每日一次（跟随 ECB）", refresh=3600,
         license="开源公开 API，数据源为 ECB", official=False,
         home="https://frankfurter.dev/", adapter="frankfurter",
         note="ECB 参考汇率的开放封装，口径不同于银行间即期报价"),

    # ===== C 级：公开媒体 / 非官方行情 =====
    _src(id="yahoo", name="Yahoo Finance (非官方接口)", grade="C", kind="行情",
         provider="Yahoo", coverage="全球指数/A股/港股/外汇/商品/加密/利率/美股龙头，36 标的",
         latency="约 15–20 分钟延迟，仅供方向判断，不可用于下单", refresh=60,
         license="非官方公开接口，官方=否；仅供个人研究", official=False,
         home="https://finance.yahoo.com/", adapter="yahoo",
         note="明确标注为非官方、延迟数据；故障时该分组显示暂无数据"),
    _src(id="gnews", name="Google News RSS", grade="C", kind="资讯",
         provider="Google News", coverage="中英 17 主题聚合（全球局势/宏观/股市/商品/加密/科技/中国）",
         latency="分钟级（取决于源站）", refresh=480, license="仅标题/摘要/链接，不复制全文",
         official=False, home="https://news.google.com/", adapter="rss",
         note="只存标题、摘要、来源、时间、原文链接；不绕过付费墙"),
    _src(id="cnbc", name="CNBC 多频道 RSS", grade="C", kind="资讯",
         provider="CNBC", coverage="Markets / World / Economy / Technology", latency="分钟级",
         refresh=480, license="公开 RSS，仅标题与摘要", official=False,
         home="https://www.cnbc.com/", adapter="rss"),
    _src(id="marketwatch", name="MarketWatch", grade="C", kind="资讯",
         provider="Dow Jones / MarketWatch", coverage="头条 + 快讯", latency="分钟级",
         refresh=480, license="公开 RSS", official=False,
         home="https://www.marketwatch.com/", adapter="rss"),
    _src(id="bbc_guardian", name="BBC / Guardian", grade="C", kind="资讯",
         provider="BBC / The Guardian", coverage="商业与全球局势", latency="分钟级",
         refresh=480, license="公开 RSS", official=False,
         home="https://www.bbc.com/news/business", adapter="rss"),
    _src(id="misc_rss", name="其他 P2 媒体 RSS", grade="C", kind="资讯",
         provider="Seeking Alpha / FXStreet / Investing / Fortune / Al Jazeera",
         coverage="美股观点 / 外汇 / 商品 / 全球", latency="分钟级", refresh=480,
         license="公开 RSS", official=False, home="", adapter="rss"),

    # ===== D 级：社区 / 非官方，不能单独作投资结论 =====
    _src(id="reddit", name="Reddit r/stocks", grade="D", kind="社交情绪",
         provider="Reddit", coverage="美股散户讨论（偶发限流）", latency="分钟级",
         refresh=480, license="公开 RSS，平台条款约束", official=False,
         home="https://www.reddit.com/r/stocks/", adapter="rss",
         note="社交讨论量 ≠ 真实资金流；不得单独作为重大结论依据"),

    # ===== 实测不可用 / 未接入：如实标注，不伪装成功 =====
    _src(id="cftc_cot", name="CFTC COT 持仓报告", grade="A", kind="期货持仓",
         provider="U.S. CFTC", coverage="期货商业/非商业持仓（周频）",
         status="blocked", enabled=False, latency="周频，非实时资金流",
         license="美国政府公开数据", home="https://www.cftc.gov/MarketReports/CommitmentsofTraders/",
         note="实测 Socrata 域名经当前代理 TLS SNI 不可达；替代：CFTC 官网公开报表文件，后续接入"),
    _src(id="bls", name="BLS 劳工统计局 RSS", grade="A", kind="宏观",
         provider="U.S. BLS", coverage="CPI/PPI/就业薪资", status="blocked", enabled=False,
         home="https://www.bls.gov/", note="实测返回 403；替代：FRED 已收录同源 BLS 序列（CPIAUCSL/PAYEMS/UNRATE）"),
    _src(id="imf", name="IMF Data API", grade="A", kind="宏观",
         provider="IMF", coverage="IFS 全球宏观", status="blocked", enabled=False,
         home="https://www.imf.org/en/Data", note="实测 SDMX 端点 502；替代：World Bank 已提供全球 GDP/通胀"),
    _src(id="twelvedata", name="Twelve Data 免费档", grade="B", kind="行情",
         provider="Twelve Data", coverage="多市场股票/ETF/外汇（需 Key 验证覆盖范围）",
         status="planned", enabled=False, needs_key=True, official=False,
         home="https://twelvedata.com/", note="未接入：需用户提供免费 API Key 并实测配额/市场范围"),
    _src(id="finnhub", name="Finnhub 免费档", grade="B", kind="行情",
         provider="Finnhub", coverage="股票行情/公司信息/新闻", status="planned",
         enabled=False, needs_key=True, official=False, home="https://finnhub.io/",
         note="未接入：需用户提供免费 API Key"),
    _src(id="alphavantage", name="Alpha Vantage", grade="B", kind="行情",
         provider="Alpha Vantage", coverage="股票/外汇/宏观低频备用", status="planned",
         enabled=False, needs_key=True, official=False, home="https://www.alphavantage.co/",
         note="未接入：需用户提供免费 API Key"),
    _src(id="akshare", name="AKShare A股数据", grade="C", kind="行情",
         provider="AKShare 开源社区", coverage="A股行情/财务/资金流", status="planned",
         enabled=False, official=False, home="https://akshare.akfamily.xyz/",
         note="未接入：需引入 Python 依赖并逐接口验证，当前零依赖架构暂不引入"),
    _src(id="options", name="期权链 / 隐含波动率", grade="B", kind="衍生品",
         provider="待评估", coverage="期权链/IV/Put-Call/持仓量", status="planned",
         enabled=False, official=False, home="",
         note="未接入：免费源无可靠期权链数据，页面明确显示『未接入』，不虚构"),
    _src(id="etf_holdings", name="ETF 持仓与净值", grade="B", kind="基金",
         provider="待评估", coverage="ETF 前十大持仓/行业分布/费率/规模", status="planned",
         enabled=False, official=False, home="",
         note="未接入：需基金公司或供应商授权数据，页面明确显示『暂无数据』"),
]

BY_ID = {s["id"]: s for s in REGISTRY}

# FRED 官方序列定义（真实 series_id，不含任何模拟值）
FRED_SERIES = [
    ("CPIAUCSL", "美国 CPI 消费者价格指数", "指数", "月", "BLS via FRED"),
    ("CPILFESL", "美国核心 CPI（剔除食品能源）", "指数", "月", "BLS via FRED"),
    ("UNRATE", "美国失业率", "%", "月", "BLS via FRED"),
    ("PAYEMS", "美国非农就业人数", "千人", "月", "BLS via FRED"),
    ("FEDFUNDS", "联邦基金有效利率", "%", "月", "Federal Reserve via FRED"),
    ("GDP", "美国名义 GDP", "十亿美元", "季", "BEA via FRED"),
    ("M2SL", "美国 M2 货币供应", "十亿美元", "月", "Federal Reserve via FRED"),
    ("DGS2", "美国 2 年期国债收益率", "%", "日", "Treasury via FRED"),
    ("DGS10", "美国 10 年期国债收益率", "%", "日", "Treasury via FRED"),
    ("DEXCHUS", "人民币/美元 官方汇率", "CNY/USD", "日", "H.10 via FRED"),
]

WB_COUNTRIES = [("USA", "美国"), ("CHN", "中国"), ("JPN", "日本"),
                ("DEU", "德国"), ("IND", "印度"), ("GBR", "英国")]
WB_INDICATORS = [("NY.GDP.MKTP.CD", "GDP 现价美元", "USD"),
                 ("FP.CPI.TOTL.ZG", "通胀率 年同比", "%")]

CRYPTO_EXCHANGES = {
    "binance": {
        "BTC": "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",
        "ETH": "https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT",
    },
    "coinbase": {
        "BTC": "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        "ETH": "https://api.exchange.coinbase.com/products/ETH-USD/ticker",
    },
    "kraken": {
        "BTC": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
        "ETH": "https://api.kraken.com/0/public/Ticker?pair=ETHUSD",
    },
    "okx": {
        "BTC": "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
        "ETH": "https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT",
    },
}


# ---------------------------------------------------------------- 状态持久化
def _state_file():
    return os.path.join(DATA, "source_state.json")


def _default_state():
    return {"enabled": True, "calls": 0, "ok": 0, "fail": 0,
            "last_ok": 0, "last_fail": 0, "last_error": "",
            "last_ms": 0, "last_count": 0, "stale": False}


def load_state():
    global STATE
    with LOCK:
        try:
            with open(_state_file(), "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = {}
        for s in REGISTRY:
            st = _default_state()
            st.update(saved.get(s["id"], {}) or {})
            # 注册表里的默认启停优先（除非用户显式改过）
            if "user_enabled" not in (saved.get(s["id"], {}) or {}):
                st["enabled"] = s["enabled"]
            STATE[s["id"]] = st


def save_state():
    with LOCK:
        try:
            tmp = _state_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(STATE, f, ensure_ascii=False, indent=1)
            os.replace(tmp, _state_file())
        except Exception:
            pass


def _record(sid, ok, ms=0, count=0, err=""):
    with LOCK:
        st = STATE.setdefault(sid, _default_state())
        st["calls"] += 1
        if ok:
            st["ok"] += 1
            st["last_ok"] = int(time.time())
            st["last_error"] = ""
            st["stale"] = False
        else:
            st["fail"] += 1
            st["last_fail"] = int(time.time())
            st["last_error"] = str(err)[:180]
            st["stale"] = True
        st["last_ms"] = int(ms)
        st["last_count"] = int(count)


def enabled(sid):
    s = BY_ID.get(sid)
    if not s or s.get("status") != "live":
        return False
    return bool(STATE.get(sid, {}).get("enabled", s.get("enabled", True)))


def set_enabled(sid, on):
    if sid not in BY_ID:
        return None, "未知数据源"
    s = BY_ID[sid]
    if s.get("status") != "live":
        return None, "该数据源当前不可用或未接入（%s），不能启用" % s.get("note", "")
    with LOCK:
        st = STATE.setdefault(sid, _default_state())
        st["enabled"] = bool(on)
        st["user_enabled"] = True
    save_state()
    CACHE.pop(sid, None)
    # 与 /api/sources/status 保持同一种结构，前端可直接复用
    return {"sources": sources_status(), "summary": status_summary()}, None


# ---------------------------------------------------------------- 网络层
def _opener(proxy, noverify=False):
    handlers = [urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy} if proxy else {})]
    if noverify:
        handlers.append(urllib.request.HTTPSHandler(context=_NV_CTX))
    return urllib.request.build_opener(*handlers)


def _get(sid, url, timeout=28, headers=None, expecting=None, tries=2, limit=3000000):
    """统一 GET：代理优先 + 直连兜底 + 真实状态记录 + 内容校验。"""
    s = BY_ID.get(sid, {})
    nv = bool(s.get("noverify"))
    hdr = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if headers:
        hdr.update(headers)
    t0 = time.time()
    last = ""
    attempts = ([PROXY, None] if PROXY else [None]) * 1
    for px in attempts:
        for _ in range(tries if px == PROXY else 1):
            try:
                req = urllib.request.Request(url, headers=hdr)
                with _opener(px, nv).open(req, timeout=timeout) as r:
                    text = r.read(limit).decode("utf-8", "ignore")
                if expecting and not expecting(text):
                    raise ValueError("返回内容不符合预期（可能被拦截或格式变更）")
                _record(sid, True, (time.time() - t0) * 1000, 1)
                return text
            except Exception as e:
                last = "%s: %s" % (type(e).__name__, str(e)[:110])
                continue
    _record(sid, False, (time.time() - t0) * 1000, 0, last)
    return None


def _disk_path(sid):
    return os.path.join(DATA, "cache_" + sid + ".json")


def _disk_read(sid):
    try:
        with open(_disk_path(sid), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _disk_write(sid, data):
    try:
        p = _disk_path(sid)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"data": data, "ts": time.time()}, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
    except Exception:
        pass


def _preload_caches():
    """容器重启后先恢复上次成功数据；同时强制过期以便后台真实刷新。"""
    for sid in ("fred", "worldbank", "eurostat", "ecb_fx", "frankfurter",
                "treasury", "fiscaldata", "crypto"):
        d = _disk_read(sid)
        if d and d.get("data"):
            CACHE[sid] = {"data": d["data"], "ts": 0, "ttl": 1}


def _cached(sid, ttl, producer):
    """内存缓存 + 磁盘持久化 + 陈旧数据降级。
    刷新失败时保留上次成功数据并明确标记 stale / stale_note，绝不补假值。"""
    with LOCK:
        c = CACHE.get(sid)
        if c and time.time() - c["ts"] < ttl:
            return c["data"]
    data = producer()
    with LOCK:
        if data is not None and not data.get("disabled"):
            CACHE[sid] = {"data": data, "ts": time.time(), "ttl": ttl}
            _disk_write(sid, data)
            return data
        # 失败：内存历史 → 磁盘历史，均标记陈旧
        old = (CACHE.get(sid) or {}).get("data") or (_disk_read(sid) or {}).get("data")
        if old:
            err = STATE.get(sid, {}).get("last_error", "") or "本次刷新失败，展示上次成功数据"
            return dict(old, stale=True, stale_note=err, stale_since=int(time.time()))
    return data


def _j(s):
    return s.strip().startswith(("{", "["))


def _x(s):
    return any(k in s[:600] for k in ("<rss", "<feed", "<?xml", "<item", "<entry"))


# ---------------------------------------------------------------- 适配器：FRED
def _parse_fred_csv(text, sid):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    pts = []
    for l in lines[1:]:
        parts = l.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d) or not v or v == ".":
            continue
        try:
            pts.append([d, float(v)])
        except ValueError:
            continue
    return pts


def fetch_fred():
    def produce():
        if not enabled("fred"):
            return {"series": [], "disabled": True, "updated": 0}
        out = []

        def one(spec):
            code, name, unit, freq, origin = spec
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=%s" % (
                code, "2024-01-01" if freq in ("月", "季") else "2026-08-01")
            txt = _get("fred", url, timeout=30, expecting=lambda t: t.startswith("observation_date"))
            if not txt:
                return None
            pts = _parse_fred_csv(txt, code)
            if not pts:
                return None
            last_d, last_v = pts[-1]
            prev_v = pts[-2][1] if len(pts) > 1 else None
            chg = round(last_v - prev_v, 4) if prev_v is not None else None
            return {"id": code, "name": name, "unit": unit, "frequency": freq,
                    "origin": origin, "as_of": last_d, "value": last_v, "change": chg,
                    "points": pts[-24:], "source": "FRED", "license": "FRED 公开数据",
                    "url": "https://fred.stlouisfed.org/series/" + code,
                    "latency": "统计发布后更新（%s频），非实时" % freq}

        # 并发压到 3：实测 FRED 对高并发会限流挂起
        with ThreadPoolExecutor(max_workers=3) as ex:
            for r in ex.map(one, FRED_SERIES):
                if r:
                    out.append(r)
        if not out:
            return None
        return {"series": out, "updated": int(time.time()), "source": "FRED",
                "coverage": "美国宏观（CPI/就业/利率/GDP/M2/国债）", "stale": False}
    return _cached("fred", 1800, produce)


# ---------------------------------------------------------------- 适配器：World Bank
def fetch_worldbank():
    def produce():
        if not enabled("worldbank"):
            return {"countries": [], "disabled": True, "updated": 0}
        jobs = [(c, n, ind, label, unit)
                for c, n in WB_COUNTRIES for ind, label, unit in WB_INDICATORS]

        def one(job):
            c, n, ind, label, unit = job
            url = ("https://api.worldbank.org/v2/country/%s/indicator/%s"
                   "?format=json&date=2021:2024&per_page=8" % (c, ind))
            txt = _get("worldbank", url, timeout=32, expecting=_j)
            if not txt:
                return None
            try:
                d = json.loads(txt)
                rows = (d[1] or []) if isinstance(d, list) and len(d) > 1 else []
                vals = [(r["date"], r["value"]) for r in rows if r.get("value") is not None]
                if not vals:
                    return None
                vals.sort()
                return {"country": n, "code": c, "indicator": label, "unit": unit,
                        "points": vals, "last_date": vals[-1][0], "last_value": vals[-1][1],
                        "lastupdated": (d[0] or {}).get("lastupdated", ""),
                        "source": "World Bank", "license": "CC BY 4.0",
                        "url": "https://data.worldbank.org/indicator/" + ind,
                        "latency": "年度数据，发布有滞后（不可当实时）"}
            except Exception:
                return None

        out = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            for r in ex.map(one, jobs):
                if r:
                    out.append(r)
        if not out:
            return None
        return {"countries": out, "updated": int(time.time()),
                "source": "World Bank", "coverage": "全球 GDP / 通胀年度指标", "stale": False}
    return _cached("worldbank", 21600, produce)


# ---------------------------------------------------------------- 适配器：Eurostat
def fetch_eurostat():
    def produce():
        if not enabled("eurostat"):
            return {"points": [], "disabled": True, "updated": 0}
        url = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
               "prc_hicp_manr?lang=en&geo=EA&sinceTimePeriod=2025-01")
        txt = _get("eurostat", url, timeout=32, expecting=_j)
        if not txt:
            return None
        try:
            d = json.loads(txt)
            tidx = d.get("dimension", {}).get("time", {}).get("category", {}).get("index", {}) or {}
            order = sorted(tidx.items(), key=lambda kv: kv[1])
            values = d.get("value", {}) or {}
            pts = []
            for period, idx in order:
                v = values.get(str(idx))
                if v is not None:
                    pts.append([period, round(float(v), 3)])
            if not pts:
                return None
            return {"label": "欧元区 HICP 调和消费者物价指数 年同比", "unit": "%",
                    "frequency": "月", "points": pts[-24:], "as_of": pts[-1][0],
                    "value": pts[-1][1], "source": "Eurostat",
                    "license": "Eurostat 公开数据（需注明来源）",
                    "url": "https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_manr",
                    "latency": "月频，官方数据集截止期为准（非实时）",
                    "updated": int(time.time()), "stale": False}
        except Exception:
            return None
    return _cached("eurostat", 21600, produce)


# ---------------------------------------------------------------- 适配器：ECB 参考汇率
def fetch_ecb_fx():
    def produce():
        if not enabled("ecb_fx"):
            return {"rates": [], "disabled": True, "updated": 0}
        txt = _get("ecb_fx", "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
                   timeout=25, expecting=_x)
        if not txt:
            return None
        try:
            root = ET.fromstring(txt)
            date = ""
            for c in root.iter():
                if c.tag.endswith("}Cube") and c.get("time"):
                    date = c.get("time"); break
            rates = [(c.get("currency"), float(c.get("rate"))) for c in root.iter()
                     if c.tag.endswith("}Cube") and c.get("currency") and c.get("rate")]
            if not rates:
                return None
            return {"base": "EUR", "date": date, "rates": rates, "updated": int(time.time()),
                    "source": "ECB 欧洲央行", "kind": "官方参考汇率",
                    "license": "ECB 公开参考汇率", "latency": "工作日约 16:00 CET 日更",
                    "url": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
                    "note": "不同于银行间即期、零售换汇或 CFD 报价，不可混用", "stale": False}
        except Exception:
            return None
    return _cached("ecb_fx", 3600, produce)


# ---------------------------------------------------------------- 适配器：Frankfurter
def fetch_frankfurter():
    def produce():
        if not enabled("frankfurter"):
            return {"rates": [], "disabled": True, "updated": 0}
        txt = _get("frankfurter",
                   "https://api.frankfurter.app/latest?from=USD&to=EUR,JPY,GBP,CNY,HKD,CHF,AUD,CAD,SGD",
                   timeout=22, expecting=_j)
        if not txt:
            return None
        try:
            d = json.loads(txt)
            if not d.get("rates"):
                return None
            return {"base": d.get("base", "USD"), "date": d.get("date", ""),
                    "rates": sorted(d["rates"].items()), "updated": int(time.time()),
                    "source": "Frankfurter (ECB 参考汇率)", "license": "开源公开 API",
                    "latency": "日更（跟随 ECB）", "url": "https://frankfurter.dev/",
                    "note": "官方参考汇率口径，非实时", "stale": False}
        except Exception:
            return None
    return _cached("frankfurter", 3600, produce)


# ---------------------------------------------------------------- 适配器：美国财政部收益率曲线
def fetch_treasury():
    def produce():
        if not enabled("treasury"):
            return {"curve": [], "disabled": True, "updated": 0}
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
               "pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=%d" % time.localtime().tm_year)
        txt = _get("treasury", url, timeout=35, expecting=_x)
        if not txt:
            return None
        try:
            root = ET.fromstring(txt)
            entries = root.findall(".//{*}entry")
            rows = []
            for e in entries:
                p = e.find(".//{*}properties")
                if p is None:
                    continue
                kv = {c.tag.split("}")[-1]: (c.text or "").strip() for c in p}
                d = kv.get("NEW_DATE", "")[:10]
                if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                    rows.append((d, kv))
            if not rows:
                return None
            rows.sort(key=lambda x: x[0])
            last_d, kv = rows[-1]
            fields = [("BC_1MONTH", "1月"), ("BC_3MONTH", "3月"), ("BC_6MONTH", "6月"),
                      ("BC_1YEAR", "1年"), ("BC_2YEAR", "2年"), ("BC_3YEAR", "3年"),
                      ("BC_5YEAR", "5年"), ("BC_7YEAR", "7年"), ("BC_10YEAR", "10年"),
                      ("BC_20YEAR", "20年"), ("BC_30YEAR", "30年")]
            curve = []
            for key, label in fields:
                try:
                    curve.append({"tenor": label, "yield": float(kv[key]), "key": key})
                except (ValueError, KeyError):
                    pass
            hist = []
            for d, k in rows[-30:]:
                try:
                    hist.append([d, float(k["BC_10YEAR"]), float(k["BC_2YEAR"])])
                except (ValueError, KeyError):
                    pass
            if not curve:
                return None
            spread = None
            m = {c["tenor"]: c["yield"] for c in curve}
            if "10年" in m and "2年" in m:
                spread = round(m["10年"] - m["2年"], 3)
            return {"date": last_d, "curve": curve, "spread_10y_2y": spread,
                    "history": hist, "updated": int(time.time()),
                    "source": "U.S. Department of the Treasury", "license": "美国政府公开数据",
                    "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve",
                    "latency": "每日收盘后更新", "stale": False}
        except Exception:
            return None
    return _cached("treasury", 3600, produce)


# ---------------------------------------------------------------- 适配器：FiscalData
def fetch_fiscaldata():
    def produce():
        if not enabled("fiscaldata"):
            return {"rows": [], "disabled": True, "updated": 0}
        url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/"
               "accounting/od/avg_interest_rates?page[size]=6&sort=-record_date")
        txt = _get("fiscaldata", url, timeout=25, expecting=_j)
        if not txt:
            return None
        try:
            d = json.loads(txt)
            rows = d.get("data", []) or []
            if not rows:
                return None
            return {"rows": rows, "updated": int(time.time()),
                    "source": "U.S. Treasury Fiscal Data", "license": "美国政府公开数据",
                    "url": "https://fiscaldata.treasury.gov/datasets/average-interest-rates-treasury-securities/",
                    "latency": "月度", "stale": False}
        except Exception:
            return None
    return _cached("fiscaldata", 21600, produce)


# ---------------------------------------------------------------- 适配器：加密交易所（多源交叉）
def _crypto_one(ex, coin):
    sid, url = ex, CRYPTO_EXCHANGES[ex][coin]
    txt = _get(sid, url, timeout=18, expecting=_j)
    if not txt:
        return None
    try:
        d = json.loads(txt)
        if ex == "binance":
            return {"price": float(d["lastPrice"]), "pct": float(d["priceChangePercent"]),
                    "volume": float(d.get("quoteVolume") or 0), "pair": d["symbol"]}
        if ex == "coinbase":
            return {"price": float(d["price"]), "pct": None,
                    "volume": float(d.get("volume") or 0), "pair": "USD"}
        if ex == "kraken":
            k = list(d["result"].keys())[0]
            r = d["result"][k]
            last, op = float(r["c"][0]), float(r["o"])
            return {"price": last, "pct": round((last - op) / op * 100, 3) if op else None,
                    "volume": float(r["v"][1]) if len(r.get("v", [])) > 1 else 0, "pair": "USD"}
        if ex == "okx":
            r = d["data"][0]
            last, op = float(r["last"]), float(r["open24h"])
            return {"price": last, "pct": round((last - op) / op * 100, 3) if op else None,
                    "volume": float(r.get("vol24h") or 0), "pair": "USDT"}
    except Exception:
        return None
    return None


def fetch_crypto():
    def produce():
        coins, out = ["BTC", "ETH"], {}
        jobs = [(ex, c) for ex in CRYPTO_EXCHANGES for c in coins if enabled(ex)]
        if not jobs:
            return {"coins": {}, "disabled": True, "updated": 0}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(_crypto_one, e, c): (e, c) for e, c in jobs}
            for fu in as_completed(futs):
                e, c = futs[fu]
                try:
                    r = fu.result()
                    if r:
                        out.setdefault(c, []).append(dict(exchange=e, **r))
                except Exception:
                    pass
        if not out:
            return None
        result = {}
        for c, rows in out.items():
            rows.sort(key=lambda x: x["exchange"])
            ps = [r["price"] for r in rows]
            avgp = [r["pct"] for r in rows if r.get("pct") is not None]
            result[c] = {"rows": rows, "exchanges": len(rows),
                         "median": round(sorted(ps)[len(ps) // 2], 4),
                         "spread_pct": round((max(ps) - min(ps)) / min(ps) * 100, 4) if ps else None,
                         "avg_pct": round(sum(avgp) / len(avgp), 3) if avgp else None,
                         "quote": "USDT 计价（Binance/OKX）与 USD 计价（Coinbase/Kraken）存在正常价差"}
        return {"coins": result, "updated": int(time.time()),
                "source": "交易所官方公开接口（Binance / Coinbase / Kraken / OKX）",
                "latency": "实时（秒级请求）", "license": "交易所公开行情，个人内部展示",
                "note": "多所交叉验证：价差反映计价币种与市场差异，不是错误数据", "stale": False}
    return _cached("crypto", 60, produce)


# ---------------------------------------------------------------- 适配器：SEC EDGAR
def _sec_tickers():
    if _TICKERS["map"] and time.time() - _TICKERS["ts"] < 86400:
        return _TICKERS["map"]
    txt = _get("sec_edgar", "https://www.sec.gov/files/company_tickers.json",
               timeout=35, expecting=_j)
    if not txt:
        return _TICKERS["map"]
    try:
        d = json.loads(txt)
        m = {v["ticker"].upper(): {"cik": v["cik_str"], "title": v["title"]} for v in d.values()}
        _TICKERS.update({"ts": time.time(), "map": m})
    except Exception:
        pass
    return _TICKERS["map"]


def fetch_sec(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol or not enabled("sec_edgar"):
        return {"error": "SEC EDGAR 未启用或代码为空", "symbol": symbol}
    key = "sec:" + symbol
    with LOCK:
        c = CACHE.get(key)
        if c and time.time() - c["ts"] < 3600:
            return c["data"]
    m = _sec_tickers()
    info = m.get(symbol)
    if not info:
        return {"error": "未在 SEC EDGAR 找到该代码（仅覆盖在美申报公司，不含 A股/港股）",
                "symbol": symbol, "universe": len(m)}
    cik = str(info["cik"]).zfill(10)
    out = {"symbol": symbol, "company": info["title"], "cik": cik,
           "source": "SEC EDGAR", "license": "SEC 公开披露", "coverage": "美股申报公司",
           "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" + symbol,
           "updated": int(time.time())}
    txt = _get("sec_edgar", "https://data.sec.gov/submissions/CIK%s.json" % cik,
               timeout=28, expecting=_j)
    if txt:
        try:
            d = json.loads(txt)
            recent = d.get("filings", {}).get("recent", {}) or {}
            forms = recent.get("form", []) or []
            dates = recent.get("filingDate", []) or []
            acc = recent.get("accessionNumber", []) or []
            docs = recent.get("primaryDocument", []) or []
            filings = []
            for i, f in enumerate(forms):
                if f in ("10-K", "10-Q", "8-K", "20-F", "6-K", "4", "S-1", "DEF 14A"):
                    an = (acc[i] or "").replace("-", "") if i < len(acc) else ""
                    link = ("https://www.sec.gov/Archives/edgar/data/%d/%s/%s"
                            % (int(info["cik"]), an, docs[i] if i < len(docs) else "")) if an else ""
                    filings.append({"form": f, "date": dates[i] if i < len(dates) else "", "link": link})
                if len(filings) >= 12:
                    break
            out["filings"] = filings
            out["sic"] = d.get("sicDescription", "")
        except Exception:
            pass
    # companyfacts 单文件可达数十 MB（Apple 实测 >3MB），必须放宽读取上限，否则 JSON 被截断
    txt2 = _get("sec_edgar", "https://data.sec.gov/api/xbrl/companyfacts/CIK%s.json" % cik,
                timeout=60, expecting=_j, limit=60000000)
    if txt2:
        try:
            d = json.loads(txt2)
            us = (d.get("facts", {}) or {}).get("us-gaap", {}) or {}
            keys = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "NetIncomeLoss", "Assets", "Liabilities", "StockholdersEquity",
                    "EarningsPerShareDiluted", "GrossProfit", "OperatingIncomeLoss",
                    "CashAndCashEquivalentsAtCarryingValue", "LongTermDebtNoncurrent"]
            facts = []
            for k in keys:
                node = us.get(k)
                if not node:
                    continue
                units = node.get("units", {}) or {}
                arr = units.get("USD") or units.get("USD/shares") or []
                arr = [x for x in arr if x.get("val") is not None and x.get("form") in ("10-K", "10-Q")]
                if not arr:
                    continue
                arr.sort(key=lambda x: x.get("end", ""))
                last = arr[-1]
                facts.append({"key": k, "label": node.get("label", k),
                              "value": last["val"], "end": last.get("end", ""),
                              "form": last.get("form", ""), "fy": last.get("fy", ""),
                              "fp": last.get("fp", ""), "unit": list(units.keys())[0]})
            # 同一公司换过 XBRL 标签时旧标签会停在多年前；只保留与最新申报期同代的数据，
            # 避免把 2018 年的旧值当成当前财务展示。
            years = [int(f["end"][:4]) for f in facts if re.match(r"^\d{4}", f["end"])]
            if years:
                cutoff = max(years) - 2
                facts = [f for f in facts if re.match(r"^\d{4}", f["end"]) and int(f["end"][:4]) >= cutoff]
            out["facts"] = facts
            out["facts_as_of"] = max((f["end"] for f in facts), default="")
            out["facts_note"] = ("来自 SEC XBRL 公司事实（原始申报值，未经复权/调整；"
                                 "仅保留与最新申报期同代的数据；不同公司口径可能不同）")
        except Exception:
            pass
    with LOCK:
        CACHE[key] = {"data": out, "ts": time.time()}
    return out


# ---------------------------------------------------------------- 汇总 API
def macro():
    """全球宏观：只返回真实接入的数据；失败的分项明确标注，不补假值。"""
    parts, errors = {}, {}
    jobs = [("fred", fetch_fred), ("worldbank", fetch_worldbank),
            ("eurostat", fetch_eurostat), ("ecb_fx", fetch_ecb_fx),
            ("frankfurter", fetch_frankfurter), ("treasury", fetch_treasury),
            ("fiscaldata", fetch_fiscaldata)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fn): k for k, fn in jobs}
        for fu in as_completed(futs):
            k = futs[fu]
            try:
                r = fu.result()
                if r and not r.get("disabled"):
                    parts[k] = r
                elif r and r.get("disabled"):
                    errors[k] = "数据源已停用"
                else:
                    errors[k] = "本次抓取失败且无历史数据（页面显示暂无数据）"
            except Exception as e:
                errors[k] = "%s: %s" % (type(e).__name__, str(e)[:80])
    return {"parts": parts, "errors": errors, "updated": int(time.time()),
            "note": "宏观数据均为统计发布值（日/月/季/年频），不是实时行情；每条数据带来源与统计截止期"}


def status_summary():
    """数据源真实状态汇总：按等级 / 类型 / 可用性统计。"""
    st = sources_status()
    live = [x for x in st if x["status"] == "live"]
    ok = [x for x in live if x["last_ok"] and (not x["last_fail"] or x["last_ok"] >= x["last_fail"])]
    return {"total": len(st), "live": len(live), "enabled": sum(1 for x in live if x["enabled"]),
            "healthy": len(ok), "blocked": sum(1 for x in st if x["status"] == "blocked"),
            "planned": sum(1 for x in st if x["status"] == "planned"),
            "grade_a": sum(1 for x in st if x["grade"] == "A" and x["status"] == "live"),
            "cost": "¥0（全部免费公开源）", "updated": int(time.time())}


def sources_status(news_errors=None, quote_errors=None):
    """每个源的真实连接状态（成功率/最近成功/失败/耗时/条数/覆盖/延迟/授权/费用）。"""
    news_errors = news_errors or {}
    quote_errors = quote_errors or {}
    out = []
    with LOCK:
        snap = {k: dict(v) for k, v in STATE.items()}
    for s in REGISTRY:
        st = snap.get(s["id"], _default_state())
        d = dict(s)
        d.update({"enabled": st.get("enabled", s["enabled"]), "calls": st.get("calls", 0),
                  "ok": st.get("ok", 0), "fail": st.get("fail", 0),
                  "last_ok": st.get("last_ok", 0), "last_fail": st.get("last_fail", 0),
                  "last_error": st.get("last_error", ""), "last_ms": st.get("last_ms", 0),
                  "last_count": st.get("last_count", 0), "stale": st.get("stale", False)})
        d["success_rate"] = round(d["ok"] / d["calls"] * 100) if d["calls"] else None
        # 新闻/行情类源的状态由 server 的真实抓取结果回填
        if s["adapter"] == "rss":
            hit = [k for k in news_errors if s["id"] in k.lower() or
                   (s["name"][:6].lower() in k.lower())]
            if hit:
                d["last_error"] = "最近一次抓取失败：" + ", ".join(hit[:2])
                d["stale"] = True
        if s["id"] == "yahoo" and quote_errors:
            d["last_error"] = "%d 个标的暂无数据" % len(quote_errors)
            d["stale"] = True
        out.append(d)
    return out


def probe(sid):
    """手动测试单个数据源连接（真实请求，即时反馈）。"""
    if sid not in BY_ID:
        return {"ok": False, "error": "未知数据源"}
    s = BY_ID[sid]
    if s.get("status") != "live":
        return {"ok": False, "error": "该源当前标记为 %s：%s" % (s["status"], s.get("note", ""))}
    tests = {
        "fred": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE&cosd=2026-01-01", lambda t: t.startswith("observation_date")),
        "worldbank": ("https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD?format=json&date=2023:2024&per_page=5", _j),
        "eurostat": ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?lang=en&geo=EA&sinceTimePeriod=2025-01", _j),
        "ecb_fx": ("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml", _x),
        "frankfurter": ("https://api.frankfurter.app/latest?from=USD&to=EUR,CNY", _j),
        "treasury": ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026", _x),
        "fiscaldata": ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates?page[size]=2", _j),
        "sec_edgar": ("https://www.sec.gov/files/company_tickers.json", _j),
        "binance": ("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", _j),
        "coinbase": ("https://api.exchange.coinbase.com/products/BTC-USD/ticker", _j),
        "kraken": ("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", _j),
        "okx": ("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", _j),
        "yahoo": ("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1m&range=1d", _j),
        "gnews": ("https://news.google.com/rss/search?q=markets&hl=en-US&gl=US&ceid=US:en", _x),
        "boj": ("https://www.boj.or.jp/en/rss/whatsnew.xml", _x),
    }
    if sid not in tests:
        return {"ok": False, "error": "该源由新闻聚合链路统一检测，请用『刷新全部』验证"}
    url, chk = tests[sid]
    t0 = time.time()
    txt = _get(sid, url, timeout=25, expecting=chk, tries=1)
    save_state()
    return {"ok": bool(txt), "ms": int((time.time() - t0) * 1000),
            "bytes": len(txt or ""), "error": "" if txt else STATE.get(sid, {}).get("last_error", ""),
            "sample": (txt or "")[:110]}


# ---------------------------------------------------------------- 业务数据：自选股 / 预警
def _store_path(name):
    return os.path.join(DATA, name + ".json")


def _read(name, default):
    try:
        with open(_store_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(name, val):
    try:
        p = _store_path(name)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(val, f, ensure_ascii=False, indent=1)
        os.replace(p + ".tmp", p)
        return True
    except Exception:
        return False


def watchlist():
    return _read("watchlist", {"items": [], "portfolio": []})


def watchlist_save(data):
    ok = _write("watchlist", data)
    return {"ok": ok, "data": watchlist()}


def alerts():
    return _read("alerts", {"rules": [], "notifications": []})


def alerts_save(data):
    ok = _write("alerts", data)
    return {"ok": ok, "data": alerts()}


def check_alerts(quotes):
    """基于真实行情判定预警；不产生任何模拟价格。"""
    a = alerts()
    qmap = {x["symbol"]: x for x in (quotes or [])}
    fired, now = [], int(time.time())
    for r in a.get("rules", []):
        if not r.get("enabled", True):
            continue
        q = qmap.get(r.get("symbol"))
        if not q or q.get("price") is None:
            continue
        hit, msg = False, ""
        typ, th, price, pct = r.get("type"), float(r.get("threshold") or 0), q["price"], q.get("pct")
        if typ == "above" and price >= th:
            hit, msg = True, "%s 现价 %s 已突破 %s" % (r["symbol"], price, th)
        elif typ == "below" and price <= th:
            hit, msg = True, "%s 现价 %s 已跌破 %s" % (r["symbol"], price, th)
        elif typ == "pct_up" and pct is not None and pct >= th:
            hit, msg = True, "%s 涨幅 %s%% 已达阈值 %s%%" % (r["symbol"], pct, th)
        elif typ == "pct_down" and pct is not None and pct <= -abs(th):
            hit, msg = True, "%s 跌幅 %s%% 已达阈值 -%s%%" % (r["symbol"], pct, th)
        if hit and now - int(r.get("last_fired") or 0) > 1800:
            r["last_fired"] = now
            fired.append({"symbol": r["symbol"], "message": msg, "time": now,
                          "source": "Yahoo Finance（延迟行情）", "price": price})
    if fired:
        a["notifications"] = (fired + a.get("notifications", []))[:50]
        _write("alerts", a)
    return {"fired": fired, "notifications": a.get("notifications", []),
            "rules": len(a.get("rules", [])),
            "note": "基于延迟行情触发，仅作站内提醒，不构成交易指令"}


# ---------------------------------------------------------------- 初始化
def init(cfg):
    global PROXY
    PROXY = cfg.get("proxy") or ""
    load_state()
    _preload_caches()
    return REGISTRY
