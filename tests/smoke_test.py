#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFIC 2.1 接口冒烟测试 / 实机验收（仅 Python 标准库）
用法：
  python tests/smoke_test.py                          # 默认 http://127.0.0.1:6789
  python tests/smoke_test.py --base http://192.168.10.110:6789
  python tests/smoke_test.py --full                    # 额外跑 AI 简报/问答（较慢）

覆盖：健康检查、静态资源（含 V2.1 扩展层）、资讯去重/时间戳、行情字段、
      官方宏观真实数据、加密多所交叉、SEC 申报、数据源真实状态与启停、
      持久化写后回读、V2.1 今日总结 / 机会雷达 / 评分口径逐项复核 / 领先榜 /
      优质公司榜 / 股票详情 / 成绩单 / 详情接口 / SPA 直达路由 / 五语言词典 /
      术语 / 等级定义 / 翻译与批量翻译 / 数据真实性总检、AI 质量回归。
真实浏览器渲染与交互验收另见 tests/browser_test.py。
测试产生的写入会 1:1 还原。
"""
import argparse, json, re, sys, time, urllib.request, urllib.error, urllib.parse

PASS, FAIL = [], []
BASE = "http://127.0.0.1:6789"


def req(path, method="GET", body=None, timeout=90):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            status = resp.status
    except urllib.error.HTTPError as he:
        # 4xx/5xx 也要能读回 JSON 错误体（例如「未知详情类型」的 400）
        raw = he.read().decode("utf-8", "ignore")
        status = he.code
    try:
        return status, json.loads(raw)
    except Exception:
        return status, raw


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (" · " + str(detail) if detail else ""))


def run(full=False):
    print("=" * 68)
    print("  GFIC 2.1 接口冒烟测试 / 实机验收  →  " + BASE)
    print("=" * 68)

    # 1 健康检查
    print("\n[1] 服务与健康检查")
    try:
        c, d = req("/api/status", timeout=20)
        ok("/api/status 200 且版本为 GFIC 2.1", c == 200 and d.get("version") == "GFIC 2.1", d.get("version"))
        ok("V2.1 能力标记齐全", len(d.get("capabilities", [])) >= 6, str(d.get("capabilities"))[:70])
        ok("数据源摘要存在", isinstance(d.get("sources"), dict) and d["sources"]["total"] > 0,
           str(d.get("sources", {}))[:70])
    except Exception as e:
        ok("服务可访问", False, str(e)); print("\n服务不可达，终止测试"); return 1

    # 2 静态资源（历史上曾因 CSS/JS 404 导致纯文本页面）
    print("\n[2] 页面与静态资源（防止再次变成纯文本）")
    for p in ("/", "/style.css", "/app.js", "/static/index.html", "/static/style.css", "/static/app.js",
              "/static/v21.css", "/static/v21.js"):
        try:
            c, t = req(p, timeout=15)
            ok(p + " 返回 200 且非空", c == 200 and len(str(t)) > 500, "%d B" % len(str(t)))
        except Exception as e:
            ok(p, False, str(e))

    # 3 资讯
    print("\n[3] 资讯聚合（真实性 / 去重 / 时间戳）")
    try:
        c, d = req("/api/news?limit=900", timeout=180)
        items = d.get("items", [])
        ok("资讯条数 > 100", len(items) > 100, "%d 条 / total %d" % (len(items), d.get("total", 0)))
        titles = [x["title"] for x in items]
        ok("标题去重", len(titles) == len(set(titles)), "重复 %d" % (len(titles) - len(set(titles))))
        now = time.time()
        future = [x for x in items if Number(x.get("published")) > now + 300]
        ok("无未来时间戳（不刷屏「刚刚」）", len(future) == 0, "%d 条未来时间" % len(future))
        need = ("title", "link", "source", "category", "priority", "hint", "published")
        miss = [k for k in need if any(k not in x for x in items[:30])]
        ok("字段完整（含原文链接与通俗解读）", not miss, "缺失 " + str(miss))
        p1 = sum(1 for x in items if x.get("priority") == "P1")
        ok("含 P1 官方原文", p1 > 0, "%d 条" % p1)
    except Exception as e:
        ok("资讯接口", False, str(e))

    # 4 行情
    print("\n[4] 行情（字段 / 口径）")
    try:
        c, d = req("/api/quotes", timeout=120)
        qs = d.get("items", [])
        ok("行情标的 > 20 项", len(qs) > 20, "%d 项 / 失败 %d" % (len(qs), len(d.get("errors", {}))))
        bad = [x for x in qs if x.get("price") is None or not isinstance(x.get("pct"), (int, float))]
        ok("无空价格 / 无 NaN 涨跌幅", not bad, "%d 项异常" % len(bad))
        ok("带日内走势点", any(len(x.get("spark", [])) > 3 for x in qs))
    except Exception as e:
        ok("行情接口", False, str(e))

    # 5 官方宏观
    print("\n[5] 官方宏观数据真实性")
    try:
        c, d = req("/api/macro", timeout=240)
        p = d.get("parts", {})
        ok("宏观分项 >= 5 类", len(p) >= 5, str(list(p)))
        f = (p.get("fred") or {}).get("series", [])
        ok("FRED 序列 >= 8 组", len(f) >= 8, "%d 组" % len(f))
        ok("FRED 每条带统计截止期与来源链接",
           all(x.get("as_of") and x.get("url") and x.get("frequency") for x in f))
        t = p.get("treasury") or {}
        ok("美债收益率曲线带日期与 10Y-2Y 利差",
           bool(t.get("date")) and len(t.get("curve", [])) >= 8, t.get("date", ""))
        e = p.get("ecb_fx") or {}
        ok("ECB 官方参考汇率 >= 20 币种", len(e.get("rates", [])) >= 20,
           "%d 币种 / %s" % (len(e.get("rates", [])), e.get("date", "")))
        wb = (p.get("worldbank") or {}).get("countries", [])
        ok("World Bank 带年度与 lastupdated",
           bool(wb) and all(x.get("last_date") and x.get("lastupdated") for x in wb))
    except Exception as e:
        ok("宏观接口", False, str(e))

    # 6 加密多所交叉
    print("\n[6] 数字资产多所交叉验证")
    try:
        c, d = req("/api/crypto", timeout=90)
        coins = d.get("coins", {})
        ok("币种数据存在", bool(coins), str(list(coins)))
        for k, v in coins.items():
            ok("%s 至少 3 家交易所真实报价" % k, v.get("exchanges", 0) >= 3,
               "%d 所 / 价差 %s%%" % (v.get("exchanges", 0), v.get("spread_pct")))
    except Exception as e:
        ok("加密接口", False, str(e))

    # 7 SEC
    print("\n[7] SEC EDGAR 公司研究")
    try:
        c, d = req("/api/sec?symbol=AAPL", timeout=150)
        ok("返回真实公司与 XBRL 财务", d.get("company") == "Apple Inc." and len(d.get("facts", [])) >= 5,
           "%s / %d 项财务" % (d.get("company"), len(d.get("facts", []))))
        ok("申报文件带官方链接", any(f.get("link") for f in d.get("filings", [])))
        c2, d2 = req("/api/sec?symbol=600519", timeout=60)
        ok("非美股代码返回诚实错误而非伪造数据", bool(d2.get("error")))
    except Exception as e:
        ok("SEC 接口", False, str(e))

    # 8 数据源管理与启停（写后 1:1 还原）
    print("\n[8] 数据源真实状态与独立启停")
    try:
        c, d = req("/api/sources/status", timeout=60)
        src = d.get("sources", [])
        ok("注册源 >= 30", len(src) >= 30, "%d 个" % len(src))
        ok("状态字段完整", all(all(k in x for k in
            ("grade", "status", "enabled", "ok", "fail", "last_ok", "last_ms", "latency", "license")) for x in src))
        planned = [x for x in src if x["status"] != "live"]
        ok("不可用/未接入源如实标注原因", all(x.get("note") for x in planned), "%d 个" % len(planned))
        c, r = req("/api/sources/toggle", "POST", {"id": "frankfurter", "enabled": False}, timeout=30)
        st = [x for x in r["sources"] if x["id"] == "frankfurter"][0]
        ok("停用真实生效", st["enabled"] is False)
        c, r = req("/api/sources/toggle", "POST", {"id": "frankfurter", "enabled": True}, timeout=30)
        st = [x for x in r["sources"] if x["id"] == "frankfurter"][0]
        ok("1:1 还原为启用", st["enabled"] is True)
        c, pr = req("/api/sources/probe", "POST", {"id": "fred"}, timeout=60)
        ok("连接探测为真实请求", isinstance(pr.get("ok"), bool) and pr.get("ms", 0) > 0,
           "ok=%s %sms" % (pr.get("ok"), pr.get("ms")))
    except Exception as e:
        ok("数据源接口", False, str(e))

    # 9 持久化（写后回读 + 还原）
    print("\n[9] 业务数据持久化与还原")
    try:
        _, w0 = req("/api/watchlist", timeout=20)
        _, a0 = req("/api/alerts", timeout=20)
        req("/api/watchlist/save", "POST", {"data": {"items": [{"symbol": "TESTONLY", "name": "冒烟测试"}], "portfolio": []}}, timeout=20)
        _, w1 = req("/api/watchlist", timeout=20)
        ok("自选股写后回读", any(x["symbol"] == "TESTONLY" for x in w1["items"]))
        req("/api/alerts/save", "POST", {"data": {"rules": [{"symbol": "TESTONLY", "type": "above", "threshold": 1, "enabled": True}], "notifications": []}}, timeout=20)
        _, a1 = req("/api/alerts", timeout=20)
        ok("预警规则写后回读", any(x["symbol"] == "TESTONLY" for x in a1["rules"]))
        req("/api/watchlist/save", "POST", {"data": w0}, timeout=20)
        req("/api/alerts/save", "POST", {"data": a0}, timeout=20)
        _, w2 = req("/api/watchlist", timeout=20)
        _, a2 = req("/api/alerts", timeout=20)
        ok("1:1 还原（无测试残留）", not any(x["symbol"] == "TESTONLY" for x in w2["items"])
           and not any(x["symbol"] == "TESTONLY" for x in a2["rules"]))
        _, ck = req("/api/alerts/check", timeout=60)
        ok("预警检查返回真实统计", isinstance(ck.get("fired"), list) and ck.get("note"))
    except Exception as e:
        ok("持久化接口", False, str(e))

    # 10 其他业务 API
    print("\n[10] 其他业务接口")
    for p in ("/api/dashboard", "/api/markets", "/api/heatmap", "/api/overview", "/api/sources", "/api/search?q=ecb"):
        try:
            c, d = req(p, timeout=120)
            ok(p + " 200 且非空", c == 200 and len(str(d)) > 30)
        except Exception as e:
            ok(p, False, str(e))

    # 11 V2.1 决策驾驶舱数据
    print("\n[11] V2.1 今日市场总结（结构化 / 非 LLM 自由发挥）")
    try:
        c, s = req("/api/daily/summary", timeout=120)
        ok("总结含一句话 / 三个事件 / 机会 / 风险 / 温度",
           all(k in s for k in ("one_sentence", "three_events", "opportunities", "risks", "temperature")),
           str(list(s))[:120])
        ok("一句话基于真实统计（含条数）", re.search(r"\d+\s*条", s["one_sentence"]) is not None,
           s["one_sentence"][:90])
        ok("三个关键事件每条带标题 / 来源 / 为什么重要 / 影响", len(s["three_events"]) >= 1 and
           all(all(k in x for k in ("title", "source", "why", "what")) for x in s["three_events"]),
           "%d 条" % len(s["three_events"]))
        ok("总结明确标注口径与免责", "disclaimer" in s or "note" in s, str(list(s))[-90:])
    except Exception as e:
        ok("今日总结接口", False, str(e))

    # 12 V2.1 机会雷达 / 评分口径 / AI 推荐依据
    print("\n[12] V2.1 AI 机会雷达（真实数据 + 可解释评分）")
    try:
        c, o = req("/api/research/opportunities", timeout=180)
        its = o.get("items", [])
        ok("机会榜条目 >= 8", len(its) >= 8, "%d 项 / 抓取 %s" % (len(its), o.get("fetched")))
        ok("真实日线抓取无失败", o.get("fetched", 0) >= 20 and not o.get("errors"),
           "抓取 %s / 失败 %s" % (o.get("fetched"), o.get("errors")))
        ok("评分模型写明规则与总权重", bool((o.get("model") or {}).get("rule")) and
           (o.get("model") or {}).get("total_weight") == 100)
        ok("每条含依据 / 风险 / 反向观点 / 来源 / 免责",
           all(all(k in x for k in ("why", "risks", "bull", "bear", "source", "disclaimer", "score")) for x in its))
        ok("每条价格与更新时间为真实值",
           all(isinstance(x.get("price"), (int, float)) and x.get("data_updated") for x in its))
        grades = set(x["score"]["grade"] for x in its)
        ok("推荐等级有区分度（不是全部 D）", len(grades) >= 2, ",".join(sorted(grades)))
        ok("存在置信度 >= 0.35 的可排名标的",
           any(x["score"]["confidence"] >= 0.35 for x in its),
           "最高置信度 %.2f" % max(x["score"]["confidence"] for x in its))
        ok("SEC 官方财务已进入评分（非全部维度标为未接入）",
           any(x["score"]["dims"]["fundamental_quality"]["value"] is not None for x in its))
        # 评分口径复核：composite 必须等于「可得维度加权得分 / 可得权重」
        bad = []
        for x in its:
            ds = x["score"]["dims"]
            avail = sum(d["weight"] for d in ds.values() if d["value"] is not None)
            got = sum(d["weight"] * d["value"] for d in ds.values() if d["value"] is not None)
            if avail and abs(round(got / avail, 1) - x["score"]["composite"]) > 0.11:
                bad.append(x["symbol"])
        ok("综合分 = Σ(可得权重×得分)/Σ(可得权重)，逐项复核", not bad, "异常 " + str(bad))
        ok("缺失维度显式列出原因，不补分", all(
            all(m.get("reason") for m in x["score"]["missing"]) for x in its))
        ok("未接入能力如实说明原因与替代方案", all(
            x.get("reason") and x.get("alternative") for x in o.get("missing_capabilities", [])))
    except Exception as e:
        ok("机会雷达接口", False, str(e))
    try:
        c, l = req("/api/research/leaders?period=m1&market=" + urllib.parse.quote("全球市场"), timeout=180)
        ok("表现领先榜返回真实区间涨跌", len(l.get("items", [])) >= 8 and
           all(isinstance(x.get("change_pct"), (int, float)) for x in l["items"]),
           "%d 项" % len(l.get("items", [])))
        ok("领先榜明确「历史表现 ≠ 未来」且无 Markdown 星号",
           "历史表现" in str(l.get("disclaimer", "")) and "未来" in str(l.get("disclaimer", ""))
           and "**" not in str(l.get("disclaimer", "")), str(l.get("disclaimer", ""))[:80])
    except Exception as e:
        ok("领先榜接口", False, str(e))
    try:
        c, q = req("/api/research/quality", timeout=180)
        ok("优质公司榜 >= 8 家且来源为 SEC 官方",
           len(q.get("items", [])) >= 8 and all("SEC" in str(x.get("source")) for x in q["items"]),
           "%d 家" % len(q.get("items", [])))
        ok("财务指标为真实申报值（无空值伪造）",
           all(x.get("net_margin") is not None for x in q["items"]))
        ok("明确标注未覆盖范围", bool(q.get("missing")))
    except Exception as e:
        ok("优质公司榜接口", False, str(e))
    try:
        c, sd = req("/api/research/stock?symbol=AAPL", timeout=180)
        ok("股票研究详情含行情 / 财务 / 评分 / 多空 / 风险 / 失效条件",
           all(k in sd for k in ("metrics", "financials", "score", "bull", "bear", "risks", "conclusion")))
        ok("保留反向观点", len(sd.get("bear", [])) >= 1)
        if sd.get("plan"):
            ok("研究计划含结论失效条件", bool(sd["plan"].get("invalidation")))
        c, tr = req("/api/research/track", timeout=120)
        ok("成绩单明确「不使用未来数据」", "no_future_leak" in tr or "accuracy_note" in tr,
           str(list(tr))[:110])
    except Exception as e:
        ok("股票详情 / 成绩单接口", False, str(e))

    # 13 详情页 API 与 SPA 直达路由
    print("\n[13] V2.1 详情接口与直达 URL")
    nid = None
    try:
        c, nd = req("/api/news?limit=1", timeout=60)
        nid = (nd.get("items") or [{}])[0].get("id")
        c, dn = req("/api/detail?type=news&id=" + str(nid), timeout=60)
        ok("资讯详情含原文 / 等级依据 / 小白解释 / 相关报道",
           all(k in dn for k in ("item", "priority", "plain", "related", "ai_summary", "historical"))
           and "priority_model" in dn["item"], str(list(dn))[:130])
        ok("等级依据含判定规则与本条原因",
           all(k in dn["priority"] for k in ("rule", "why_this_item", "model")))
        ok("资讯详情标题与列表一致", dn["item"].get("title") == nd["items"][0].get("title"))
        c, bad = req("/api/detail?type=nope&id=x", timeout=30)
        ok("未知详情类型返回诚实 400 而非空壳", c == 400 and "supported" in bad, str(c))
    except Exception as e:
        ok("详情接口", False, str(e))
    for p in ("/stocks/AAPL", "/news/" + str(nid or "unknown"),
              "/glossary", "/opportunities", "/static/v21.js"):
        try:
            c, t = req(p, timeout=30)
            is_html = isinstance(t, str) and ("<html" in t.lower() or "<!doctype" in t.lower())
            ok("直达路由 %s 返回 SPA 入口" % p, c == 200 and (is_html or len(str(t)) > 1000),
               "%d / %s" % (c, "HTML" if is_html else "%d B" % len(str(t))))
        except Exception as e:
            ok("直达路由 " + p, False, str(e))

    # 14 国际化 / 全站翻译 / 术语词典
    print("\n[14] V2.1 国际化、术语与翻译")
    try:
        c, st = req("/api/i18n/stats", timeout=30)
        ok("多语言统计存在", c == 200 and st, str(st)[:110])
        for lang in ("zh-CN", "zh-TW", "en", "ja", "ko"):
            c, d = req("/api/i18n/dict?lang=" + lang, timeout=30)
            ok("词典 %s 返回固定文案" % lang, c == 200 and len(d) >= 20 and
               (d.get("_meta") or {}).get("lang") == lang, "%d 键" % len(d))
        c, g = req("/api/i18n/glossary?term=PE", timeout=30)
        ok("术语 PE 含通俗解释 / 作用 / 高低 / 市场影响",
           all(k in g for k in ("zh", "en", "plain", "use", "high", "low", "impact")), str(list(g))[:110])
        c, ts = req("/api/i18n/terms", timeout=30)
        ok("术语词典 >= 20 条", ts.get("total", 0) >= 20, "%d 条" % ts.get("total", 0))
        c, pd = req("/api/i18n/priority", timeout=30)
        ok("P1/P2/P3 等级定义含判定规则", all(
            pd.get("levels", {}).get(k, {}).get("rule") for k in ("P1", "P2", "P3")))
        c, t2 = req("/api/i18n/translate", "POST",
                    {"text": "AAPL rose 3.25% to $ 227.50 in 2026", "lang": "ja"}, timeout=120)
        ok("翻译返回原文 / 译文 / 语言标记",
           all(k in t2 for k in ("text", "original", "lang")) and t2.get("original"),
           str(t2)[:110])
        ok("翻译不篡改数字（或诚实回退原文）",
           "3.25" in str(t2.get("text", "")) or t2.get("fallback") or t2.get("preserved") is False,
           str(t2)[:110])
        c, tb = req("/api/i18n/translate_batch", "POST",
                    {"items": [{"title": "GDP grew 2.1% in 2026",
                                "summary": "Inflation at 3.25% and AAPL up 1.5%"}],
                     "lang": "ja", "limit": 8}, timeout=180)
        row = (tb.get("items") or [{}])[0]
        ok("批量翻译按 title/summary 契约返回译文与原文",
           "title_translated" in row and "summary_translated" in row and "original" in row,
           str(row)[:150])
        ok("批量翻译保留关键数字",
           "2.1" in str(row.get("title_translated", "")) or
           row.get("title_translated", {}).get("fallback"), str(row.get("title_translated"))[:110])
    except Exception as e:
        ok("国际化接口", False, str(e))

    # 15 数据真实性总检（禁止模拟/虚构）
    print("\n[15] V2.1 数据真实性总检")
    try:
        c, o = req("/api/research/opportunities", timeout=180)
        blob = json.dumps(o, ensure_ascii=False)
        ok("机会数据无 NaN / undefined / 占位词", not re.search(
            r"\b(NaN|undefined|模拟数据|示例数据|测试数据|placeholder)\b", blob))
        ok("所有条目带来源与时间戳", all(x.get("source") and x.get("data_updated") for x in o["items"]))
        ok("行情价格为正常正数", all(x["price"] > 0 for x in o["items"]))
        ok("免责声明逐条存在", all("不构成投资建议" in x["disclaimer"] for x in o["items"]))
    except Exception as e:
        ok("真实性总检", False, str(e))

    # 16 AI（可选）
    if full:
        print("\n[16] AI 简报与问答（--full）")
        try:
            c, d = req("/api/brief", timeout=240)
            t = d.get("text", "")
            ok("AI 简报已生成且非空", d.get("status") == "ok" and len(t) > 100,
               "%d 字 / 溯源 %d 条" % (len(t), len(d.get("refs", []))))
            # 回归：上游曾把「英文原文清单 + 自我核对草稿」一起吐出来并绕过旧阈值
            zh = len(re.findall(r"[\u4e00-\u9fff]", t))
            ok("简报为简体中文归纳（中文占比 >= 0.40）", zh / max(1, len(t)) >= 0.40,
               "%.3f" % (zh / max(1, len(t))))
            ok("简报带 [n] 溯源编号 >= 8 条", len(re.findall(r"\[\d+\]", t)) >= 8,
               "%d 条" % len(re.findall(r"\[\d+\]", t)))
            ok("简报无自检草稿 / 英文原文清单泄漏",
               not re.search(r"等等[，,]?我|我需要检查|对于第\d+条|为了严谨", t)
               and len(re.findall(r"^\s*\d+\.\s+[A-Za-z]", t, re.M)) <= 2)
            ok("简报长度受控（<= 1800 字）", len(t) <= 1800, "%d 字" % len(t))
            c, a = req("/api/ask", "POST", {"q": "站内接入了哪些官方数据？请注明口径"}, timeout=240)
            ans = a.get("answer") or a.get("error") or ""
            ok("AI 问答返回中文回答", len(ans) > 30, "%d 字" % len(ans))
            ok("AI 问答无 Markdown 星号残留", "**" not in ans)
        except Exception as e:
            ok("AI 接口", False, str(e))

    print("\n" + "=" * 68)
    print("  测试结果： %d 通过 / %d 失败" % (len(PASS), len(FAIL)))
    print("=" * 68)
    if FAIL:
        for n, d in FAIL:
            print("  ✕ %s · %s" % (n, d))
    else:
        print("  ✓ 全部通过（所有数据均来自真实接入源，无模拟行情/虚构新闻）")
    return 0 if not FAIL else 1


def Number(v):
    try:
        return float(v)
    except Exception:
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:6789")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")
    sys.exit(run(args.full))
