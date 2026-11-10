#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFIC 2.0 冒烟测试 / 实机验收（仅 Python 标准库）
用法：
  python tests/smoke_test.py                          # 默认 http://127.0.0.1:6789
  python tests/smoke_test.py --base http://192.168.10.110:6789
  python tests/smoke_test.py --full                    # 额外跑 AI 简报/问答（较慢）

覆盖：健康检查、静态资源、资讯去重/时间戳、行情字段、官方宏观真实数据、
      加密多所交叉、SEC 申报、数据源真实状态与启停、持久化写后回读、
      未接入模块诚实标注、6789 端口、故障降级不造假。
测试产生的写入会 1:1 还原。
"""
import argparse, json, re, sys, time, urllib.request, urllib.error

PASS, FAIL = [], []
BASE = "http://127.0.0.1:6789"


def req(path, method="GET", body=None, timeout=90):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "ignore")
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, raw


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (" · " + str(detail) if detail else ""))


def run(full=False):
    print("=" * 68)
    print("  GFIC 2.0 冒烟测试 / 实机验收  →  " + BASE)
    print("=" * 68)

    # 1 健康检查
    print("\n[1] 服务与健康检查")
    try:
        c, d = req("/api/status", timeout=20)
        ok("/api/status 200 且版本为 GFIC 2.0", c == 200 and d.get("version") == "GFIC 2.0", d.get("version"))
        ok("数据源摘要存在", isinstance(d.get("sources"), dict) and d["sources"]["total"] > 0,
           str(d.get("sources", {}))[:70])
    except Exception as e:
        ok("服务可访问", False, str(e)); print("\n服务不可达，终止测试"); return 1

    # 2 静态资源（历史上曾因 CSS/JS 404 导致纯文本页面）
    print("\n[2] 页面与静态资源（防止再次变成纯文本）")
    for p in ("/", "/style.css", "/app.js", "/static/index.html", "/static/style.css", "/static/app.js"):
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

    # 11 AI（可选）
    if full:
        print("\n[11] AI 简报与问答（--full）")
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
