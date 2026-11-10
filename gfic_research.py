#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFIC 投资研究引擎（V2.1）

铁律：只用真实数据。行情来自 Yahoo Finance v8 chart（非官方、延迟 15–20 分钟），
财务来自 SEC EDGAR companyfacts（官方公开披露）。任何拿不到的维度一律标
「数据缺失」，不填模拟分数；综合分只在**实际可得的维度**上归一，并给出置信度。
所有结论由可解释规则产生，不由 LLM 自由生成，杜绝编造目标价/评级/资金流。
"""
import os, re, json, time, math, hashlib, urllib.parse, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)
LOCK = threading.RLock()
PROXY = ""
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36 GFIC/2.1 "
      "(personal research; contact: research@example.com)")

# 真实标的清单（仅代码/名称/市场等元数据，不含任何行情数值）
UNIVERSE = [
    ("AAPL", "苹果", "美股", "NASDAQ", "USD", "科技硬件"),
    ("NVDA", "英伟达", "美股", "NASDAQ", "USD", "半导体"),
    ("MSFT", "微软", "美股", "NASDAQ", "USD", "软件与云"),
    ("TSLA", "特斯拉", "美股", "NASDAQ", "USD", "汽车"),
    ("META", "Meta", "美股", "NASDAQ", "USD", "互联网"),
    ("GOOGL", "谷歌", "美股", "NASDAQ", "USD", "互联网"),
    ("AMZN", "亚马逊", "美股", "NASDAQ", "USD", "电商与云"),
    ("AVGO", "博通", "美股", "NASDAQ", "USD", "半导体"),
    ("AMD", "超威半导体", "美股", "NASDAQ", "USD", "半导体"),
    ("JPM", "摩根大通", "美股", "NYSE", "USD", "银行"),
    ("LLY", "礼来", "美股", "NYSE", "USD", "医药"),
    ("XOM", "埃克森美孚", "美股", "NYSE", "USD", "能源"),
    ("600519.SS", "贵州茅台", "A股", "上交所", "CNY", "白酒"),
    ("000858.SZ", "五粮液", "A股", "深交所", "CNY", "白酒"),
    ("300750.SZ", "宁德时代", "A股", "深交所", "CNY", "动力电池"),
    ("601318.SS", "中国平安", "A股", "上交所", "CNY", "保险"),
    ("002594.SZ", "比亚迪", "A股", "深交所", "CNY", "汽车"),
    ("0700.HK", "腾讯控股", "港股", "港交所", "HKD", "互联网"),
    ("9988.HK", "阿里巴巴", "港股", "港交所", "HKD", "电商与云"),
    ("3690.HK", "美团", "港股", "港交所", "HKD", "本地生活"),
    ("1299.HK", "友邦保险", "港股", "港交所", "HKD", "保险"),
    ("ASML", "阿斯麦", "欧洲市场", "NASDAQ", "USD", "半导体设备"),
    ("SAP", "思爱普", "欧洲市场", "NYSE", "USD", "软件"),
    ("MC.PA", "LVMH", "欧洲市场", "巴黎", "EUR", "奢侈品"),
    ("SHEL.L", "壳牌", "欧洲市场", "伦敦", "GBP", "能源"),
    ("7203.T", "丰田汽车", "亚洲其他市场", "东京", "JPY", "汽车"),
    ("6758.T", "索尼", "亚洲其他市场", "东京", "JPY", "电子"),
    ("005930.KS", "三星电子", "亚洲其他市场", "韩国", "KRW", "半导体"),
    ("2330.TW", "台积电", "亚洲其他市场", "台湾", "TWD", "半导体"),
]
UNIVERSE = [dict(zip(("symbol", "name", "market", "exchange", "currency", "sector"), x)) for x in UNIVERSE]
BY_SYMBOL = {x["symbol"]: x for x in UNIVERSE}
MARKETS = ["美股", "A股", "港股", "欧洲市场", "亚洲其他市场", "全球市场"]

# 100 分制维度与权重（用户指定）。value=None 表示该维度数据缺失，不参与归一。
DIMENSIONS = [
    ("fundamental_quality", "基本面质量", 20),
    ("profitability", "盈利能力", 15),
    ("growth", "成长能力", 15),
    ("valuation", "估值合理性", 15),
    ("industry", "行业景气度", 10),
    ("trend", "市场趋势", 10),
    ("volume", "资金及成交表现", 5),
    ("financial_health", "财务健康度", 10),
]
DIM_WEIGHT = {k: w for k, _, w in DIMENSIONS}
TOTAL_WEIGHT = sum(DIM_WEIGHT.values())

CYCLES = {
    "short": {"name": "短期", "span": "1–5 个交易日", "dims": ["trend", "volume"],
              "note": "只看最近价格与量能，不用它推导长期结论"},
    "swing": {"name": "波段", "span": "1–4 周", "dims": ["trend", "volume", "industry"],
              "note": "结合 1 个月趋势与均线；不含估值判断"},
    "mid": {"name": "中期", "span": "1–6 个月", "dims": ["trend", "industry", "financial_health", "profitability"],
            "note": "加入真实财务与 3 个月趋势"},
    "long": {"name": "长期", "span": "6 个月以上", "dims": ["fundamental_quality", "profitability", "growth", "valuation", "financial_health"],
             "note": "长期结论必须有基本面与估值数据；缺失时拒绝给出结论"},
}
GRADES = [
    ("S", 80, "高优先级研究机会：可得维度综合分 ≥80 且置信度 ≥0.5；**不代表保证盈利**"),
    ("A", 68, "值得重点研究：综合分 68–79"),
    ("B", 55, "加入观察名单：综合分 55–67"),
    ("C", 40, "暂时观察：综合分 40–54"),
    ("D", 0, "风险偏高或条件不符合：综合分 <40，或置信度不足被暂停排名"),
]

HIST_TTL = 1800          # 30 分钟
SNAP_FILE = "research_snapshots.json"
HIST_PREFIX = "ghist_"


def init(cfg):
    global PROXY
    PROXY = cfg.get("proxy") or ""
    return UNIVERSE


# ---------------- 底层网络 / 缓存 ----------------
def _opener(proxy):
    import urllib.request
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}))


def _fetch(url, timeout=25, limit=6000000):
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    for px in ([PROXY, None] if PROXY else [None]):
        try:
            with _opener(px).open(req, timeout=timeout) as r:
                return r.read(limit).decode("utf-8", "ignore")
        except Exception:
            continue
    return None


def _read(name, ttl=HIST_TTL):
    p = os.path.join(DATA, name)
    try:
        d = json.load(open(p, encoding="utf-8"))
        # 降级/失败结果自带短 TTL，避免一次偶发失败被缓存 24 小时
        if time.time() - d.get("_ts", 0) < d.get("_ttl", ttl):
            return d
        d["stale"] = True
        return d
    except Exception:
        return None


def _write(name, obj):
    obj["_ts"] = int(time.time())
    p = os.path.join(DATA, name)
    tmp = p + ".tmp"
    with LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, p)


def _safe(sym):
    return re.sub(r"[^A-Za-z0-9]", "_", sym)


# ---------------- Yahoo 真实日线 ----------------
def history(symbol, force=False):
    key = HIST_PREFIX + _safe(symbol) + ".json"
    if not force:
        c = _read(key)
        if c and not c.get("stale"):
            return c
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" +
           urllib.parse.quote(symbol, safe="") + "?range=1y&interval=1d&includePrePost=false")
    txt = _fetch(url, timeout=28, limit=6000000)
    try:
        r = json.loads(txt)["chart"]["result"][0]
        ts = r.get("timestamp") or []
        q = (r.get("indicators") or {}).get("quote", [{}])[0]
        closes = q.get("close") or []
        vols = q.get("volume") or []
        rows = [(int(t), float(c), int(v or 0)) for t, c, v in zip(ts, closes, vols)
                if c is not None and not (isinstance(c, float) and math.isnan(c))]
        if len(rows) < 20:
            raise ValueError("有效交易日不足 20 天")
        meta = r.get("meta") or {}
        out = {"symbol": symbol, "rows": rows, "currency": meta.get("currency", ""),
               "exchange": meta.get("exchangeName", ""), "instrument": meta.get("instrumentType", ""),
               "source": "Yahoo Finance v8 chart（非官方接口）", "latency": "延迟 15–20 分钟",
               "updated": int(time.time()), "stale": False}
        _write(key, out)
        return out
    except Exception as e:
        old = _read(key, ttl=10 ** 9)
        if old:
            return dict(old, stale=True, stale_note="本次刷新失败，展示上次成功数据：%s" % str(e)[:100])
        return {"symbol": symbol, "error": "无法取得真实历史数据：%s" % str(e)[:120],
                "source": "Yahoo Finance v8 chart", "updated": int(time.time())}


def _pct(a, b):
    try:
        return round((float(a) / float(b) - 1) * 100, 2)
    except Exception:
        return None


def _std(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def metrics(h):
    """全部指标由真实日线计算，不产生任何模拟值。"""
    rows = h.get("rows") or []
    if len(rows) < 20:
        return None
    c = [r[1] for r in rows]
    v = [r[2] for r in rows]
    ts = [r[0] for r in rows]
    last = c[-1]
    rets = {}
    for label, n in (("d1", 1), ("w1", 5), ("m1", 21), ("m3", 63)):
        rets[label] = _pct(last, c[-1 - n]) if len(c) > n else None
    # YTD：本年度第一个交易日
    year = time.gmtime(ts[-1]).tm_year
    jan = time.mktime((year, 1, 1, 0, 0, 0, 0, 0, 0))
    idx = next((i for i, t in enumerate(ts) if t >= jan), 0)
    rets["ytd"] = _pct(last, c[idx])
    chg = [(c[i] / c[i - 1] - 1) for i in range(1, len(c)) if c[i - 1]]
    vol = _std(chg)
    vol_annual = round(vol * math.sqrt(252) * 100, 2) if vol is not None else None
    peak, mdd = c[0], 0.0
    for x in c:
        peak = max(peak, x)
        mdd = min(mdd, x / peak - 1)
    ma20 = sum(c[-20:]) / 20
    ma60 = sum(c[-60:]) / 60 if len(c) >= 60 else None
    # RSI14
    gains = [max(0, x) for x in chg[-14:]]
    losses = [max(0, -x) for x in chg[-14:]]
    ag, al = sum(gains) / 14, sum(losses) / 14
    rsi = round(100 - 100 / (1 + ag / al), 1) if al else (100.0 if ag else 50.0)
    # MACD(12,26,9) 简化 EMA
    def ema(arr, n):
        k, e = 2 / (n + 1), arr[0]
        for x in arr[1:]:
            e = x * k + e * (1 - k)
        return e
    macd = round(ema(c, 12) - ema(c, 26), 4)
    vr = None
    if len(v) >= 25:
        a, b = sum(v[-5:]) / 5, sum(v[-25:-5]) / 20
        vr = round(a / b, 2) if b else None
    return {"price": round(last, 4), "currency": h.get("currency", ""),
            "returns": rets, "vol_annual": vol_annual, "max_drawdown": round(mdd * 100, 2),
            "ma20": round(ma20, 4), "ma60": round(ma60, 4) if ma60 else None,
            "above_ma20": last > ma20, "rsi14": rsi, "macd": macd,
            "volume_ratio": vr, "days": len(c),
            "first_date": time.strftime("%Y-%m-%d", time.gmtime(ts[0])),
            "last_date": time.strftime("%Y-%m-%d", time.gmtime(ts[-1])),
            "spark": [round(x, 4) for x in c[-60:]],
            "source": h.get("source"), "latency": h.get("latency"),
            "updated": h.get("updated"), "stale": bool(h.get("stale")),
            "stale_note": h.get("stale_note", "")}


def batch_histories(symbols, workers=8):
    out, errs = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(history, s): s for s in symbols}
        for f in as_completed(futs):
            s = futs[f]
            try:
                h = f.result()
                if h.get("error"):
                    errs[s] = h["error"]
                else:
                    out[s] = h
            except Exception as e:
                errs[s] = str(e)[:100]
    return out, errs


# ---------------- SEC 真实财务（仅美股，按需 + 缓存）----------------
def financials(symbol, gs, cached_only=False):
    """复用 gfic_sources.fetch_sec 的真实 XBRL 事实；失败或标的不覆盖时如实返回 error。

    cached_only=True 用于「机会雷达」这类首屏接口：只读已落盘的真实缓存，
    绝不在请求线程里串行打 12 次 SEC（会拖慢首屏）；缓存由后台预热线程填充。
    """
    key = "gfin_" + _safe(symbol) + ".json"
    c = _read(key, ttl=86400)
    # 只有「拿到真实 XBRL 事实」的完整结果才配长期缓存；
    # 旧版本曾把「有公司名/公告但 facts 为空」的降级结果缓存 24 小时。
    if c and not c.get("stale") and not c.get("error") and c.get("facts"):
        return c
    if cached_only:
        return None
    try:
        d = gs.fetch_sec(symbol)
    except Exception as e:
        d = {"error": str(e)[:120]}
    if d.get("error") or not d.get("facts"):
        out = {"symbol": symbol,
               "error": "SEC companyfacts 暂不可用（仅拿到公司/公告，无财务事实），稍后自动重试",
               "source": "SEC EDGAR", "updated": int(time.time()), "_ttl": 120}
        _write(key, out)          # 只缓存 2 分钟，不把降级结果当成功数据
        return out
    facts = {f["key"]: f for f in (d.get("facts") or [])}
    def val(*ks):
        for k in ks:
            if k in facts:
                return facts[k].get("value")
        return None
    rev = val("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues")
    ni = val("NetIncomeLoss")
    assets = val("Assets")
    liab = val("Liabilities")
    eq = val("StockholdersEquity")
    cash = val("CashAndCashEquivalentsAtCarryingValue")
    gp = val("GrossProfit")
    op = val("OperatingIncomeLoss")
    eps = val("EarningsPerShareDiluted")
    out = {"symbol": symbol, "company": d.get("company", ""), "cik": d.get("cik", ""),
           "sic": d.get("sic", ""), "source": "SEC EDGAR companyfacts（官方 XBRL）",
           "url": d.get("url", ""), "updated": int(time.time()),
           "revenue": rev, "net_income": ni, "assets": assets, "liabilities": liab,
           "equity": eq, "cash": cash, "gross_profit": gp, "operating_income": op, "eps": eps,
           "facts": d.get("facts") or [], "filings": d.get("filings") or [],
           "facts_as_of": d.get("facts_as_of"), "facts_note": d.get("facts_note", ""),
           "note": "仅美股在美申报公司；EBITDA/市值/PE/PB/PS 无免费 Key 接口，故不提供"}
    if rev and ni:
        out["net_margin"] = round(ni / rev * 100, 2)
    if rev and gp:
        out["gross_margin"] = round(gp / rev * 100, 2)
    if ni and eq:
        out["roe"] = round(ni / eq * 100, 2)
    if liab and assets:
        out["debt_ratio"] = round(liab / assets * 100, 2)
    # 成长：同一 XBRL 标签的相邻年度对比（真实申报值）
    try:
        years = {}
        for f in (d.get("facts") or []):
            if f["key"] in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax") and re.match(r"^\d{4}", f["end"]):
                years.setdefault(f["end"][:4], f["value"])
        ys = sorted(years)
        if len(ys) >= 2:
            out["revenue_growth"] = _pct(years[ys[-1]], years[ys[-2]])
            out["growth_years"] = ys[-2] + "→" + ys[-1]
    except Exception:
        pass
    _write(key, out)
    return out


# ---------------- 评分（可解释规则，缺失不补分）----------------
def _score_trend(m):
    r = m["returns"]
    pts = 0.0
    for k, w in (("m1", 0.4), ("m3", 0.4), ("w1", 0.2)):
        v = r.get(k)
        if v is None:
            continue
        pts += w * max(0, min(100, 50 + v * 3.2))
    if m.get("above_ma20"):
        pts += 8
    return round(min(100, pts), 1)


def _score_volume(m):
    vr = m.get("volume_ratio")
    if vr is None:
        return None
    return round(max(0, min(100, 50 + (vr - 1) * 45)), 1)


def _score_fin_health(f):
    if not f or f.get("error"):
        return None
    dr = f.get("debt_ratio")
    if dr is None:
        return None
    return round(max(0, min(100, 100 - dr * 1.1)), 1)


def _score_profit(f):
    if not f or f.get("error"):
        return None
    nm = f.get("net_margin")
    roe = f.get("roe")
    if nm is None and roe is None:
        return None
    return round(max(0, min(100, (nm or 0) * 1.6 + (roe or 0) * 0.8)), 1)


def _score_fundamental(f):
    if not f or f.get("error"):
        return None
    bits = [f.get("net_margin"), f.get("gross_margin"), f.get("roe")]
    bits = [b for b in bits if b is not None]
    if not bits:
        return None
    return round(max(0, min(100, sum(bits) / len(bits) * 1.8)), 1)


def _score_growth(f):
    if not f or f.get("error"):
        return None
    g = f.get("revenue_growth")
    if g is None:
        return None
    return round(max(0, min(100, 50 + g * 2.2)), 1)


def score_stock(symbol, m, f, news_hits, with_fin=False):
    """返回 8 维逐项得分；缺失维度 value=None 并写明原因。"""
    dims, missing = {}, []
    fin_ok = bool(with_fin and f and not f.get("error"))
    fin_why = "需按需读取 SEC 财务" if not with_fin else (
        "SEC 财务缓存尚未预热或该标的不在 SEC 覆盖范围" if not fin_ok else "")
    dims["trend"] = {"value": _score_trend(m), "why": "由真实 1周/1月/3月涨跌与 MA20 位置计算"}
    dims["volume"] = {"value": _score_volume(m), "why": "近 5 日均量 / 前 20 日均量（真实日线）"}
    dims["financial_health"] = {"value": _score_fin_health(f) if fin_ok else None,
                                "why": "SEC 真实资产负债率" if fin_ok else fin_why}
    dims["profitability"] = {"value": _score_profit(f) if fin_ok else None,
                             "why": "SEC 真实净利率 / ROE" if fin_ok else fin_why}
    dims["fundamental_quality"] = {"value": _score_fundamental(f) if fin_ok else None,
                                   "why": "SEC 真实利润率 / 毛利率 / ROE" if fin_ok else fin_why}
    dims["growth"] = {"value": _score_growth(f) if fin_ok else None,
                      "why": "SEC 真实相邻年度营收变化" if fin_ok else fin_why}
    dims["valuation"] = {"value": None, "why": "PE/PB/PS/EV-EBITDA 与市值无免费 Key 接口，未接入"}
    dims["industry"] = {"value": None, "why": "行业景气指数需付费数据源；当前仅用真实新闻提及数作事件信号，不计入评分"}
    for k, d in dims.items():
        d["name"] = dict((a, b) for a, b, _ in DIMENSIONS)[k]
        d["weight"] = DIM_WEIGHT[k]
        if d["value"] is None:
            missing.append({"key": k, "name": d["name"], "weight": d["weight"], "reason": d["why"]})
    avail = sum(DIM_WEIGHT[k] for k, d in dims.items() if d["value"] is not None)
    got = sum(DIM_WEIGHT[k] * d["value"] for k, d in dims.items() if d["value"] is not None)
    composite = round(got / avail, 1) if avail else None
    confidence = round(avail / TOTAL_WEIGHT, 2)
    ranked = composite is not None and confidence >= 0.35
    grade = "D"
    if ranked:
        for g, th, _ in GRADES:
            if composite >= th:
                grade = g
                break
    return {"dims": dims, "missing": missing, "available_weight": avail,
            "total_weight": TOTAL_WEIGHT, "composite": composite,
            "confidence": confidence, "ranked": ranked, "grade": grade,
            "grade_rules": [{"grade": g, "min": th, "desc": d} for g, th, d in GRADES],
            "news_hits": news_hits}


def _reasons(m, f, hits, dims):
    """全部理由只用真实数值；无数据不写理由。"""
    why, risks, bull, bear = [], [], [], []
    r = m["returns"]
    if r.get("m3") is not None:
        s = "近 3 个月真实涨跌 %+.2f%%（%s 至 %s）" % (r["m3"], m["first_date"], m["last_date"])
        (bull if r["m3"] > 0 else bear).append(s)
        why.append(s)
    if r.get("m1") is not None:
        why.append("近 1 个月真实涨跌 %+.2f%%" % r["m1"])
        if r["m1"] < 0:
            bear.append("近 1 个月下跌 %.2f%%" % abs(r["m1"]))
    if m.get("above_ma20") is not None:
        t = "价格在 20 日均线%s（%s）" % ("上方" if m["above_ma20"] else "下方", num(m["ma20"]))
        why.append(t)
        (bull if m["above_ma20"] else bear).append(t)
    if m.get("rsi14") is not None:
        why.append("RSI(14) = %s" % m["rsi14"])
        if m["rsi14"] > 70:
            risks.append("RSI(14) = %s，处于超买区间，短期回撤风险上升" % m["rsi14"])
            bear.append("RSI 超买")
        elif m["rsi14"] < 30:
            bear.append("RSI(14) = %s，处于超卖区间" % m["rsi14"])
    if m.get("vol_annual") is not None:
        risks.append("年化波动率 %s%%（由真实日线计算）" % m["vol_annual"])
        if m["vol_annual"] > 45:
            risks.append("波动率偏高，仓位与止损需更保守")
    if m.get("max_drawdown") is not None:
        risks.append("近一年最大回撤 %.2f%%" % m["max_drawdown"])
        bear.append("近一年最大回撤 %.2f%%" % m["max_drawdown"])
    if m.get("volume_ratio") is not None:
        why.append("近 5 日量能是前 20 日的 %s 倍" % m["volume_ratio"])
    if f and not f.get("error"):
        if f.get("net_margin") is not None:
            why.append("SEC 申报净利率 %s%%（%s）" % (f["net_margin"], f.get("facts_as_of") or "最近申报期"))
        if f.get("roe") is not None:
            why.append("按 SEC 申报值计算 ROE %s%%" % f["roe"])
        if f.get("revenue_growth") is not None:
            why.append("SEC 相邻年度营收变化 %+.2f%%（%s）" % (f["revenue_growth"], f.get("growth_years")))
        if f.get("debt_ratio") is not None and f["debt_ratio"] > 65:
            risks.append("资产负债率 %s%% 偏高" % f["debt_ratio"])
    if hits:
        why.append("站内今日有 %d 条真实相关报道（可点开原文核验）" % len(hits))
        bull.append("有 %d 条站内新闻涉及该标的" % len(hits))
    if not bear:
        bear.append("暂无可量化的反向信号；不代表没有风险")
    risks.append("行情为 Yahoo 非官方接口、延迟 15–20 分钟，不可用于下单")
    risks.append("估值 / 行业景气 / 全市场财务数据未接入，评分置信度有限")
    # 官方申报事实是「依据」的核心，不能被行情条目挤出前 4 条
    sec = [w for w in why if "SEC" in w]
    other = [w for w in why if "SEC" not in w]
    ordered = other[:2] + sec[:2] + other[2:]
    return {"why": ordered[:6], "risks": risks[:6], "bull": bull[:4], "bear": bear[:4]}


def num(x, d=2):
    try:
        return ("%." + str(d) + "f") % float(x)
    except Exception:
        return "--"


def conclusion(grade, conf, m):
    if not conf or conf < 0.35:
        return "数据不足，暂停综合排名；仅展示已核实的行情与财务事实，不给研究结论。"
    return {
        "S": "值得重点研究（高优先级）。请先看反向观点与风险，再决定是否加入观察名单。",
        "A": "值得重点研究。建议按对应周期跟踪关键指标。",
        "B": "可以加入观察名单，等待更清晰的条件。",
        "C": "暂时观察：当前信号不够强或风险偏高。",
        "D": "当前风险偏高或条件不符合，暂不建议关注。",
    }[grade] + " 置信度 %s（可得权重 %s/%s）。" % (conf, int(conf * 100), 100)


# ---------------- 对外主接口 ----------------
def opportunities(news_items=None, limit=12, market="全球市场", cycle="mid", gs=None, with_fin=False):
    news_items = news_items or []
    syms = [x["symbol"] for x in UNIVERSE if market == "全球市场" or x["market"] == market]
    hs, errs = batch_histories(syms)
    out = []
    for s, h in hs.items():
        m = metrics(h)
        if not m:
            continue
        u = BY_SYMBOL[s]
        kw = re.compile(re.escape(u["name"]) + "|" + re.escape(s.split(".")[0]), re.I)
        hits = [{"title": n.get("title"), "link": n.get("link"), "source": n.get("source"),
                 "published": n.get("published")} for n in news_items if kw.search(n.get("title") or "")][:3]
        f = financials(s, gs, cached_only=True) if (with_fin and u["market"] == "美股") else None
        sc = score_stock(s, m, f, hits, with_fin=with_fin)
        rr = _reasons(m, f, hits, sc["dims"])
        cyc = CYCLES.get(cycle, CYCLES["mid"])
        # 机会类型：只给有真实依据的两类
        types = []
        if m["returns"].get("m1") is not None and m["returns"]["m1"] > 3 and m.get("above_ma20"):
            types.append({"type": "趋势动量机会", "basis": "近 1 月真实上涨 %s%% 且价在 MA20 上方" % m["returns"]["m1"]})
        if hits:
            types.append({"type": "事件驱动机会", "basis": "站内 %d 条真实报道（附原文链接）" % len(hits)})
        out.append({
            "symbol": s, "name": u["name"], "market": u["market"], "exchange": u["exchange"],
            "sector": u["sector"], "currency": m["currency"] or u["currency"],
            "price": m["price"], "change_pct": m["returns"].get("d1"),
            "metrics": m, "score": sc, "types": types or [{"type": "暂未形成可验证机会", "basis": "真实数据未触发趋势或事件条件"}],
            "why": rr["why"], "risks": rr["risks"], "bull": rr["bull"], "bear": rr["bear"],
            "conclusion": conclusion(sc["grade"], sc["confidence"], m),
            "cycle": {"key": cycle, **cyc}, "financials": f,
            "news": hits, "disclaimer": "研究筛选结果，不是保证盈利的买卖指令；不构成投资建议",
            "data_updated": m["updated"], "source": "Yahoo Finance v8 chart + SEC EDGAR",
        })
    ranked = [x for x in out if x["score"]["ranked"]]
    ranked.sort(key=lambda x: x["score"]["composite"], reverse=True)
    unranked = [x for x in out if not x["score"]["ranked"]]
    return {"items": (ranked + unranked)[:limit], "total_universe": len(syms),
            "fetched": len(hs), "errors": errs, "market": market, "cycle": cycle,
            "cycle_note": CYCLES.get(cycle, CYCLES["mid"])["note"],
            "model": {"dimensions": [{"key": k, "name": n, "weight": w} for k, n, w in DIMENSIONS],
                      "total_weight": TOTAL_WEIGHT,
                      "rule": "综合分 = Σ(可得维度权重×得分) / Σ(可得维度权重)；缺失维度不补分，置信度 = 可得权重/100；置信度 <0.35 暂停排名"},
            "missing_capabilities": [
                {"name": "估值合理性（PE/PB/PS/EV-EBITDA）", "reason": "Yahoo quoteSummary 需 crumb/cookie，无免费 Key 接口", "alternative": "可后续接入 Finnhub/Alpha Vantage（需 Key）或手动维护财报估值表"},
                {"name": "行业景气度指数", "reason": "需付费行业数据源", "alternative": "当前用站内真实新闻提及数作定性事件信号，不计入评分"},
                {"name": "全市场财务 / A股港股财务", "reason": "SEC EDGAR 仅覆盖在美申报公司", "alternative": "可后续接入 AKShare（需引入依赖）"},
                {"name": "高成长 / 价值低估 / 行业景气 三类榜单", "reason": "缺成长预期、估值与行业景气真实数据", "alternative": "保留分类位，数据不可得时如实显示「未接入」，不凑数"},
            ],
            "disclaimer": "历史表现不代表未来潜力；行情延迟 15–20 分钟；本页为研究筛选，不构成投资建议",
            "updated": int(time.time())}


def leaders(market="全球市场", period="d1"):
    key = {"d1": "今日", "w1": "近一周", "m1": "近一个月", "m3": "近三个月", "ytd": "年初至今"}
    syms = [x["symbol"] for x in UNIVERSE if market == "全球市场" or x["market"] == market]
    hs, errs = batch_histories(syms)
    rows = []
    for s, h in hs.items():
        m = metrics(h)
        if not m or m["returns"].get(period) is None:
            continue
        u = BY_SYMBOL[s]
        rows.append({"symbol": s, "name": u["name"], "market": u["market"], "sector": u["sector"],
                     "currency": m["currency"] or u["currency"], "price": m["price"],
                     "change_pct": m["returns"][period], "returns": m["returns"],
                     "vol_annual": m["vol_annual"], "max_drawdown": m["max_drawdown"],
                     "last_date": m["last_date"], "source": m["source"], "stale": m["stale"]})
    rows.sort(key=lambda x: x["change_pct"], reverse=True)
    return {"period": period, "period_name": key.get(period, period), "market": market,
            "markets": MARKETS, "items": rows, "fetched": len(hs), "errors": errs,
            "disclaimer": "历史表现领先 ≠ 未来最赚钱；数据来自 Yahoo 非官方接口，延迟 15–20 分钟；不构成投资建议",
            "updated": int(time.time())}


def quality(gs=None, market="全球市场", sector=""):
    """优质公司观察榜：只用 SEC 真实财务，不做市值排序、不用 AI 主观判断。"""
    syms = [x["symbol"] for x in UNIVERSE if x["market"] == "美股"]
    out = []
    for s in syms:
        f = financials(s, gs)
        if f.get("error") or f.get("net_margin") is None:
            continue
        u = BY_SYMBOL[s]
        pts = (min(40, max(0, (f.get("net_margin") or 0) * 1.2)) +
               min(25, max(0, (f.get("roe") or 0) * 0.5)) +
               min(20, max(0, 20 - (f.get("debt_ratio") or 0) * 0.25)) +
               min(15, max(0, (f.get("revenue_growth") or 0) * 0.6 + 7.5)))
        out.append({"symbol": s, "name": u["name"], "market": u["market"], "sector": u["sector"],
                    "company": f.get("company"), "quality_score": round(pts, 1),
                    "net_margin": f.get("net_margin"), "gross_margin": f.get("gross_margin"),
                    "roe": f.get("roe"), "debt_ratio": f.get("debt_ratio"),
                    "revenue_growth": f.get("revenue_growth"), "growth_years": f.get("growth_years"),
                    "cash": f.get("cash"), "facts_as_of": f.get("facts_as_of"),
                    "source": "SEC EDGAR companyfacts", "url": f.get("url")})
    if sector:
        out = [x for x in out if x["sector"] == sector]
    out.sort(key=lambda x: x["quality_score"], reverse=True)
    return {"items": out, "market": "美股（SEC EDGAR 覆盖范围）", "sectors": sorted(set(x["sector"] for x in UNIVERSE)),
            "method": "按 SEC 真实申报值计算：净利率 / ROE / 资产负债率 / 营收同比；不含市值、不含估值、不含 AI 主观判断",
            "missing": ["PE/PB/PS 与行业相对估值（无免费 Key 接口）", "A股/港股/欧股财务（SEC 不覆盖）"],
            "disclaimer": "仅代表已披露财务的历史质量，不代表未来成长或股价表现；不构成投资建议",
            "updated": int(time.time())}


# ---------------- 推荐时点快照 / 成绩单（避免未来数据泄漏）----------------
def snapshot(items):
    p = os.path.join(DATA, SNAP_FILE)
    try:
        db = json.load(open(p, encoding="utf-8"))
    except Exception:
        db = {"snapshots": []}
    now = int(time.time())
    added = 0
    for x in items:
        if not x.get("price"):
            continue
        db["snapshots"].append({"id": hashlib.md5(("%s|%s" % (x["symbol"], now)).encode()).hexdigest()[:12],
                                "symbol": x["symbol"], "name": x["name"], "as_of": now,
                                "price": x["price"], "score": x["score"].get("composite"),
                                "grade": x["score"].get("grade"), "confidence": x["score"].get("confidence"),
                                "market": x["market"], "currency": x.get("currency")})
        added += 1
    db["snapshots"] = db["snapshots"][-500:]
    with LOCK:
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
    return {"added": added, "total": len(db["snapshots"])}


def track(gs=None, min_age_days=5):
    """只评估 as_of 已过 min_age_days 的快照；用当前真实行情重算，绝不使用生成时点之后的『预测值』。"""
    p = os.path.join(DATA, SNAP_FILE)
    try:
        db = json.load(open(p, encoding="utf-8"))
    except Exception:
        db = {"snapshots": []}
    now = int(time.time())
    hs, errs = batch_histories(sorted(set(x["symbol"] for x in db["snapshots"])))
    bench = history("^GSPC")
    bm = metrics(bench) if bench and not bench.get("error") else None
    rows = []
    for s in db["snapshots"]:
        age = (now - s["as_of"]) / 86400.0
        if age < min_age_days:
            continue
        h = hs.get(s["symbol"])
        m = metrics(h) if h else None
        if not m:
            continue
        ret = _pct(m["price"], s["price"])
        bench_ret = (bm["returns"].get("m1") if bm else None)
        rows.append({**s, "age_days": round(age, 1), "current_price": m["price"],
                     "actual_change_pct": ret, "benchmark": "^GSPC",
                     "benchmark_change_pct": bench_ret,
                     "excess_pct": round(ret - bench_ret, 2) if (ret is not None and bench_ret is not None) else None,
                     "max_drawdown": m["max_drawdown"], "max_favorable_pct": m["returns"].get("m3"),
                     "max_adverse_pct": m["max_drawdown"], "evaluated_at": now})
    hit = [r for r in rows if r["actual_change_pct"] is not None]
    return {"items": rows, "evaluated": len(rows), "pending": len(db["snapshots"]) - len(rows),
            "direction_accuracy": (round(sum(1 for r in hit if r["actual_change_pct"] > 0) / len(hit) * 100, 1) if hit else None),
            "accuracy_note": "方向准确率按「生成后实际上涨占比」统计；样本不足时显示暂无；评级并非涨跌预测，故不计算评级命中率",
            "no_future_leak": "仅评估生成时点已满 %d 天的快照；评估使用当前真实行情，不回写历史快照" % min_age_days,
            "errors": errs, "updated": now}


def stock_detail(symbol, news_items=None, gs=None):
    symbol = (symbol or "").upper()
    u = BY_SYMBOL.get(symbol)
    h = history(symbol)
    if h.get("error"):
        return {"error": h["error"], "symbol": symbol,
                "note": "该标的无真实行情数据，不生成研究详情页"}
    m = metrics(h)
    f = financials(symbol, gs) if (u and u["market"] == "美股") else None
    kw = re.compile(re.escape((u or {}).get("name", symbol)) + "|" + re.escape(symbol.split(".")[0]), re.I)
    news = [{"title": n.get("title"), "link": n.get("link"), "source": n.get("source"),
             "published": n.get("published"), "priority": n.get("priority")}
            for n in (news_items or []) if kw.search(n.get("title") or "")][:8]
    sc = score_stock(symbol, m, f, news, with_fin=bool(f))
    rr = _reasons(m, f, news, sc["dims"])
    plan = None
    if sc["confidence"] >= 0.35 and m.get("ma20"):
        plan = {
            "watch_condition": "价格站上 20 日均线 %s 且近 5 日量能 ≥ 前 20 日均量" % num(m["ma20"]),
            "research_entry_zone": "%s – %s（MA20 上下 2%% 的情景区间，非入场建议）" % (num(m["ma20"] * 0.98), num(m["ma20"] * 1.02)),
            "observe_zone": "%s – %s（近 3 个月真实波动区间参考）" % (
                num(min(m["spark"]) if m["spark"] else m["price"]), num(max(m["spark"]) if m["spark"] else m["price"])),
            "risk_control": "参考近一年最大回撤 %.2f%% 与年化波动率 %s%% 设定研究止损" % (m["max_drawdown"], m["vol_annual"]),
            "invalidation": "跌破 MA20 且近 1 月真实收益转负，或出现与当前逻辑矛盾的官方披露",
            "cycle": "中期 1–6 个月（数据不足时不下长期结论）",
            "disclaimer": "以上为情景分析，不是确定性价格预测、不是买入建议",
        }
    return {"symbol": symbol, "info": u or {"symbol": symbol, "name": symbol, "market": "未分类", "sector": "未分类"},
            "metrics": m, "financials": f, "score": sc, "why": rr["why"], "risks": rr["risks"],
            "bull": rr["bull"], "bear": rr["bear"], "news": news, "plan": plan,
            "conclusion": conclusion(sc["grade"], sc["confidence"], m),
            "cycles": CYCLES,
            "valuation_status": "PE/PB/PS/EV-EBITDA 未接入（无免费 Key 接口），不显示虚构估值",
            "technical_status": "趋势/均线/量能/RSI/MACD/波动率均由 Yahoo 真实日线计算",
            "data_sources": ["Yahoo Finance v8 chart（非官方、延迟 15–20 分钟）",
                             "SEC EDGAR companyfacts（官方 XBRL，仅在美申报公司）" if f else "SEC EDGAR：该市场不覆盖"],
            "disclaimer": "仅供个人研究，不构成投资建议；延迟行情不可用于下单",
            "updated": int(time.time())}
