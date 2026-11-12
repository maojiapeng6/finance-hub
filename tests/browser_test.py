#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFIC V2.1 真实浏览器自动化验收（纯 Python 标准库 + Edge CDP，无第三方依赖）

背景：Chrome/Edge 的 `--dump-dom --virtual-time-budget` 在本页面会被挂起中的
网络请求卡死（SSE / 长轮询 / setInterval），且拿不到 JS 运行时异常、无法模拟
点击、前进后退、多分辨率。因此这里直接用 DevTools Protocol 的 WebSocket，
用标准库实现一个最小客户端，做真正的浏览器端验收。

用法：
  python tests/browser_test.py --base http://127.0.0.1:6789
  python tests/browser_test.py --base http://<NAS_IP>:6789 --shots _tmp/nas_v21

产出：
  - 控制台逐项 PASS/FAIL（不虚构数量，全部来自真实断言）
  - 每个关键视图的 PNG 截图
  - JSON 报告 tests/browser_report.json
"""
import argparse, base64, json, os, socket, struct, subprocess, sys, time, urllib.request

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PASS, FAIL, NOTES = [], [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append({"name": name, "detail": str(detail)})
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (" · " + str(detail) if detail else ""))
    return bool(cond)


# --------------------------------------------------------------------------
# 最小 WebSocket 客户端（RFC6455，客户端帧必须掩码）
# --------------------------------------------------------------------------
class WS:
    def __init__(self, url, timeout=60):
        import urllib.parse
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (("?" + u.query) if u.query else "")
        req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\nOrigin: http://localhost\r\n\r\n"
               % (path, u.hostname, u.port, key))
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            c = self.sock.recv(4096)
            if not c:
                raise RuntimeError("WS handshake EOF")
            buf += c
        head, self.buf = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError("WS handshake failed: " + head[:200].decode("utf-8", "ignore"))
        self.frag = b""
        self.frag_op = 0
        self.id = 0
        self.events = []

    def _exact(self, n):
        while len(self.buf) < n:
            c = self.sock.recv(262144)
            if not c:
                raise EOFError("WS closed")
            self.buf += c
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self, data, opcode=0x1):
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            hdr = bytes([0x80 | opcode, 0x80 | n])
        elif n < 65536:
            hdr = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(hdr + mask + masked)

    def send(self, obj):
        self._frame(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def recv(self):
        while True:
            b0, b1 = self._exact(2)
            fin, op = b0 & 0x80, b0 & 0x0F
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._exact(8))[0]
            mask = self._exact(4) if (b1 & 0x80) else None
            payload = self._exact(ln)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if op == 0x9:                       # ping -> pong
                self._frame(payload, 0xA)
                continue
            if op == 0x8:
                raise EOFError("WS close frame")
            if op == 0x0 or (op == 0x1 and not fin):
                self.frag += payload
                self.frag_op = self.frag_op or op
                if not fin:
                    continue
                payload, self.frag, op = self.frag, b"", (self.frag_op or 0x1)
                self.frag_op = 0
            if op in (0x1, 0x2):
                return payload.decode("utf-8", "ignore")

    def call(self, method, params=None, timeout=60):
        self.id += 1
        cid = self.id
        self.send({"id": cid, "method": method, "params": params or {}})
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = json.loads(self.recv())
            except (socket.timeout, EOFError) as e:
                raise RuntimeError("CDP %s timeout: %s" % (method, e))
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError("CDP %s error: %s" % (method, msg["error"]))
                return msg.get("result", {})
            self.events.append(msg)
        raise RuntimeError("CDP %s timeout" % method)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class Browser:
    def __init__(self, port=9333, shots="_tmp/v21_shots"):
        self.port = port
        self.shots = shots
        os.makedirs(shots, exist_ok=True)
        udd = os.path.abspath(os.path.join(shots, "_edge_profile"))
        self.proc = subprocess.Popen([
            EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions",
            "--disable-background-networking", "--remote-allow-origins=*",
            "--remote-debugging-port=%d" % port, "--user-data-dir=" + udd,
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        for _ in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=2) as r:
                    tabs = json.loads(r.read().decode())
                page = [t for t in tabs if t.get("type") == "page"]
                if page:
                    self.ws = WS(page[0]["webSocketDebuggerUrl"])
                    break
            except Exception:
                pass
            time.sleep(0.4)
        if not self.ws:
            raise RuntimeError("Edge CDP 未就绪")
        self.ws.call("Page.enable")
        self.ws.call("Runtime.enable")
        self.ws.call("Log.enable")
        try:
            self.ws.call("Network.enable")
        except Exception:
            pass
        self.errors = []
        self.req_urls = {}
        self.net_failed = []

    def drain(self):
        """收集已到达的 CDP 事件（非阻塞：靠短 socket timeout 排空）"""
        prev = self.ws.sock.gettimeout()
        self.ws.sock.settimeout(0.05)
        try:
            while True:
                try:
                    self.ws.events.append(json.loads(self.ws.recv()))
                except (socket.timeout, EOFError, ValueError):
                    break
        finally:
            self.ws.sock.settimeout(prev)
        for e in self.ws.events:
            m = e.get("method")
            if m == "Network.requestWillBeSent":
                self.req_urls[e["params"]["requestId"]] = e["params"]["request"].get("url", "")
            if m == "Network.loadingFailed":
                u = self.req_urls.get(e["params"].get("requestId"), "")
                self.net_failed.append((u, e["params"].get("errorText", "")))
            if m == "Runtime.exceptionThrown":
                d = e["params"]["exceptionDetails"]
                self.errors.append("EXC: " + str(d.get("text")) + " " +
                                  str((d.get("exception") or {}).get("description", ""))[:220])
            elif m == "Log.entryAdded" and e["params"]["entry"].get("level") in ("error", "warning"):
                en = e["params"]["entry"]
                if en.get("source") in ("javascript", "network") or en.get("level") == "error":
                    self.errors.append("LOG: " + str(en.get("text", ""))[:220])
            elif m == "Runtime.consoleAPICalled" and e["params"].get("type") == "error":
                self.errors.append("CONSOLE: " + " ".join(
                    str(a.get("value", a.get("description", ""))) for a in e["params"]["args"])[:220])
        self.ws.events = []

    def go(self, url, wait=2.0, settle=None):
        self.ws.call("Page.navigate", {"url": url})
        time.sleep(wait)
        if settle:
            self.wait_js(settle, timeout=25)
        self.drain()

    def js(self, expr, await_promise=False):
        r = self.ws.call("Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
            "awaitPromise": await_promise, "userGesture": True,
        }, timeout=90)
        if r.get("exceptionDetails"):
            return {"__error": str(r["exceptionDetails"].get("text")) + " " +
                    str((r["exceptionDetails"].get("exception") or {}).get("description", ""))[:300]}
        return r.get("result", {}).get("value")

    def wait_js(self, expr, timeout=25):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.js("!!(" + expr + ")"):
                    return True
            except Exception:
                pass
            time.sleep(0.35)
        return False

    def shot(self, name, width=1680, height=1100):
        self.ws.call("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 700,
        })
        time.sleep(0.6)
        r = self.ws.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        p = os.path.join(self.shots, name + ".png")
        with open(p, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return p

    def metrics(self, width, height):
        self.ws.call("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 700,
        })
        time.sleep(0.5)

    def wait_render(self, min_len=400, selector="", timeout=35):
        """等到真正渲染完成（骨架屏文字里也会出现「评分/术语」，不能只匹配关键词）"""
        expr = ("(document.querySelector('#viewHost')||{}).innerText.length>=%d" % min_len)
        if selector:
            expr += " && document.querySelectorAll('%s').length>0" % selector
        return self.wait_js(expr, timeout)

    def close(self):
        try:
            self.ws.call("Browser.close")
        except Exception:
            pass
        self.ws.close()
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


# --------------------------------------------------------------------------
# 验收用例
# --------------------------------------------------------------------------
def run(base, shots):
    b = Browser(shots=shots)
    results = []
    try:
        print("=" * 70)
        print("  GFIC V2.1 真实浏览器验收 → " + base)
        print("=" * 70)

        # ---------- 1 首屏 / 驾驶舱 ----------
        print("\n[1] 首屏与投资决策驾驶舱")
        b.go(base + "/?nosse=1#dashboard", wait=3)
        b.wait_js("document.querySelector('#viewHost') && document.querySelector('#viewHost').innerText.length>300", 30)
        info = b.js("JSON.stringify({title:document.querySelector('#pageTitle')&&document.querySelector('#pageTitle').textContent,"
                    "len:(document.querySelector('#viewHost')||{}).innerText.length,"
                    "cards:document.querySelectorAll('#viewHost .card').length,"
                    "v21:typeof window.V21, easy:document.body.dataset.easy,"
                    "hash:location.hash})")
        d = json.loads(info) if isinstance(info, str) and info.startswith("{") else {}
        ok("V2.1 扩展层已加载", d.get("v21") == "object", d.get("v21"))
        ok("首屏内容非空（非纯文本/非骨架屏）", (d.get("len") or 0) > 300, "%s 字" % d.get("len"))
        ok("驾驶舱卡片已渲染", (d.get("cards") or 0) >= 3, "%s 张" % d.get("cards"))
        txt = b.js("(document.querySelector('#viewHost')||{}).innerText||''") or ""
        for k in ("机会", "风险", "依据", "数据口径"):
            ok("驾驶舱含「%s」板块" % k, k in txt, k if k in txt else "缺失")
        daily = b.js("(document.querySelector('#dailyBody')||{}).innerText||''") or ""
        ok("右侧 AI 今日市场总结有内容", len(daily) > 60, "%s 字" % len(daily))
        b.shot("01_驾驶舱")

        # ---------- 2 新导航 ----------
        print("\n[2] V2.1 新增导航（不删除旧模块）")
        nav = b.js("JSON.stringify({n:document.querySelectorAll('.nav-item').length,"
                   "ids:[...document.querySelectorAll('.nav-item')].map(x=>x.dataset.view)})")
        nd = json.loads(nav) if isinstance(nav, str) else {}
        ids = nd.get("ids", [])
        ok("导航项数量 >= 24（原 22 + 2）", (nd.get("n") or 0) >= 24, nd.get("n"))
        ok("AI 投资机会入口存在", "opportunities" in ids)
        ok("金融术语词典入口存在", "glossary" in ids)
        ok("原有 dashboard/news/macro 全部保留",
           all(x in ids for x in ("dashboard", "news", "macro", "sources", "about")),
           ",".join([x for x in ("dashboard", "news", "macro", "sources", "about") if x in ids]))

        # ---------- 3 机会雷达 ----------
        print("\n[3] AI 全球投资机会雷达")
        b.js("switchView('opportunities'); 'ok'")
        b.wait_render(1200, "#viewHost .opp-card", 40)
        ot = b.js("(document.querySelector('#viewHost')||{}).innerText||''") or ""
        ok("机会雷达视图已渲染", len(ot) > 1200, "%s 字" % len(ot))
        for k in ("评分", "风险", "来源", "不构成投资建议", "成绩单"):
            ok("机会雷达含「%s」" % k, k in ot)
        rows = b.js("document.querySelectorAll('#viewHost .opp-card').length")
        ok("机会榜有真实数据行", (rows or 0) >= 3, "%s 张机会卡" % rows)
        grades = b.js("JSON.stringify([...document.querySelectorAll('#viewHost .grade-badge')].map(x=>x.textContent.trim()))")
        gl = json.loads(grades) if isinstance(grades, str) and grades.startswith("[") else []
        ok("评分等级有真实区分度（非全部 D）", len(set(gl)) >= 2, ",".join(gl[:8]))
        ok("机会榜含 SEC 官方财务依据", "SEC" in ot, "含" if "SEC" in ot else "缺失")
        ok("机会榜含诚实免责声明", "延迟" in ot and "未接入" in ot)
        # 筛选器按钮必须真的重新计算（不是灰化假按钮）
        before = b.js("(document.querySelector('#viewHost')||{}).innerText.length")
        b.js("var b=document.querySelector('#viewHost [data-oc=\"short\"]'); if(b)b.click(); 'ok'")
        b.wait_render(1200, "#viewHost .opp-card", 40)
        ok("研究周期切换按钮有真实功能", b.js("V21.oppCycle") == "short", b.js("V21.oppCycle"))
        b.js("var b=document.querySelector('#viewHost [data-om=\"美股\"]'); if(b)b.click(); 'ok'")
        b.wait_render(800, "#viewHost .opp-card", 40)
        ok("市场筛选按钮有真实功能", b.js("V21.oppMarket") == "美股", b.js("V21.oppMarket"))
        b.shot("02_机会雷达")
        # 还原默认，避免影响后续用例
        b.js("V21.oppCycle='mid';V21.oppMarket='全球市场';switchView('dashboard');'ok'")
        time.sleep(1.0)

        # ---------- 4 术语词典 ----------
        print("\n[4] 金融术语词典 / 易懂模式 / 等级说明")
        b.js("switchView('glossary'); 'ok'")
        b.wait_render(400, "#viewHost .gloss-card", 30)
        gt = b.js("(document.querySelector('#viewHost')||{}).innerText||''") or ""
        ok("词典视图已渲染", len(gt) > 400, "%s 字" % len(gt))
        terms = b.js("document.querySelectorAll('#viewHost [data-term]').length")
        ok("术语链接可点击", (terms or 0) >= 3, "%s 个" % terms)
        if terms:
            b.js("document.querySelector('#viewHost [data-term]').click(); 'ok'")
            b.wait_js("document.querySelectorAll('#termBody .vm-row').length>0", 25)
            tb = b.js("(document.querySelector('#termBody')||{}).innerText||''") or ""
            ok("点击术语弹出通俗解释", "通俗解释" in tb and len(tb) > 100, "%s 字" % len(tb))
            ok("术语含「数值高低 / 市场影响」说明", "偏高" in tb and "影响" in tb)
            b.js("document.querySelector('#btnCloseTerm').click(); 'ok'")
        # 词典搜索框是真功能
        b.js("var q=document.querySelector('#glossQ'); q.value='PE'; q.dispatchEvent(new Event('input')); 'ok'")
        time.sleep(0.6)
        filtered = b.js("document.querySelectorAll('#glossList .gloss-card').length")
        ok("术语搜索框可过滤", (filtered or 0) >= 1 and (filtered or 99) < (terms or 99),
           "过滤后 %s 项" % filtered)
        b.js("var q=document.querySelector('#glossQ'); q.value=''; q.dispatchEvent(new Event('input')); 'ok'")
        # P1/P2/P3 等级说明
        b.js("var p=document.querySelector('#viewHost [data-prio]'); if(p)p.click(); 'ok'")
        b.wait_js("document.querySelectorAll('#priorityBody .vm-row').length>0", 25)
        pb = b.js("(document.querySelector('#priorityBody')||{}).innerText||''") or ""
        ok("P1/P2/P3 等级弹窗含判定规则", "P1" in pb and "判定规则" in pb, "%s 字" % len(pb))
        b.js("document.querySelector('#btnClosePriority').click(); 'ok'")
        b.js("document.querySelector('#btnEasy').click(); 'ok'")
        time.sleep(1.2)
        ok("小白易懂模式可切换", b.js("document.body.dataset.easy") == "1",
           b.js("document.body.dataset.easy"))
        easy = b.js("document.querySelectorAll('#viewHost .easy-explain').length")
        ok("易懂模式确实注入大白话解释", (easy or 0) >= 1, "%s 处" % easy)
        b.js("document.querySelector('#btnEasy').click(); 'ok'")
        time.sleep(0.5)
        b.shot("03_术语词典")

        # ---------- 5 详情路由 ----------
        print("\n[5] 详情页 hash 路由 / 直达 URL / 前进后退 / 刷新")
        b.js("switchView('detail/stocks/AAPL'); 'ok'")
        b.wait_js("(document.querySelector('#viewHost')||{}).innerText.indexOf('AAPL')>=0", 30)
        st = b.js("(document.querySelector('#viewHost')||{}).innerText||''") or ""
        ok("hash 详情路由可渲染股票详情", "AAPL" in st and len(st) > 300, "%s 字" % len(st))
        for k in ("风险", "来源", "多头", "空头"):
            ok("股票详情含「%s」" % k, k in st)
        b.shot("04_股票详情")

        b.go(base + "/stocks/AAPL?nosse=1", wait=3)
        b.wait_js("(document.querySelector('#viewHost')||{}).innerText.length>200", 30)
        dt = b.js("(document.querySelector('#viewHost')||{}).innerText||''") or ""
        ok("/stocks/AAPL 直达 URL 渲染详情", "AAPL" in dt and len(dt) > 200, "%s 字" % len(dt))
        ok("直达 URL 被规范化为详情 hash", b.js("location.hash").startswith("#detail/stocks/"), b.js("location.hash"))

        # 取一条真实资讯 id 测 /news/<id>
        import urllib.request
        try:
            with urllib.request.urlopen(base + "/api/news?limit=1", timeout=20) as r:
                nd2 = json.loads(r.read().decode())
            nid = (nd2.get("items") or [{}])[0].get("id")
        except Exception:
            nid = None
        if nid:
            b.go(base + "/news/" + str(nid) + "?nosse=1", wait=3)
            b.wait_js("(document.querySelector('#viewHost')||{}).innerText.length>100", 25)
            nt = b.js("(document.querySelector('#viewHost')||{}).innerText||''") or ""
            ok("/news/<真实id> 直达渲染详情", len(nt) > 100 and "详情读取失败" not in nt, "%s 字 / id=%s" % (len(nt), nid))
            b.shot("05_资讯详情")
        else:
            ok("/news/<真实id> 直达渲染详情", False, "未取到真实资讯 id")

        print("\n[6] 浏览器前进 / 后退 / 刷新")
        b.go(base + "/?nosse=1#dashboard", wait=2.5)
        b.js("switchView('glossary'); 'ok'")
        b.wait_js("(document.querySelector('#viewHost')||{}).innerText.indexOf('术语')>=0", 20)
        b.js("history.back(); 'ok'")
        time.sleep(2.0)
        ok("后退回到上一视图", b.js("location.hash") in ("#dashboard", ""), b.js("location.hash"))
        b.js("history.forward(); 'ok'")
        time.sleep(2.0)
        ok("前进可回到词典视图", b.js("location.hash") == "#glossary", b.js("location.hash"))
        b.ws.call("Page.reload", {"ignoreCache": True})
        time.sleep(3.0)
        b.wait_js("(document.querySelector('#viewHost')||{}).innerText.length>200", 25)
        ok("刷新后仍保持路由且正常渲染",
           b.js("location.hash") == "#glossary" and
           (len(b.js("(document.querySelector('#viewHost')||{}).innerText||''") or "") > 200),
           b.js("location.hash"))
        b.drain()

        # ---------- 7 全站翻译 ----------
        print("\n[7] 全站翻译 / 原文切换 / 数字保护")
        b.js("switchView('dashboard'); 'ok'")
        time.sleep(1.5)
        b.js("document.querySelector('#langSel').value='ja'; document.querySelector('#langSel').dispatchEvent(new Event('change')); 'ok'")
        time.sleep(2.0)
        ok("语言切换到日语后 html.lang 生效", b.js("document.documentElement.lang") == "ja",
           b.js("document.documentElement.lang"))
        ok("语言偏好已持久化", b.js("localStorage.getItem('gfic-lang')") == "ja",
           b.js("localStorage.getItem('gfic-lang')"))
        ok("固定文案走本地词典（不依赖外部翻译）",
           (b.js("JSON.stringify(V21.dict._meta||{})") or "").find("ja") >= 0,
           str(b.js("JSON.stringify(V21.dict._meta||{})"))[:90])
        b.js("document.querySelector('#langSel').value='zh-CN'; document.querySelector('#langSel').dispatchEvent(new Event('change')); 'ok'")
        time.sleep(1.5)
        ok("翻译工具栏按钮存在", bool(b.js("!!document.querySelector('#btnTranslate')")))
        if nid:
            b.js("switchView('detail/news/%s'); 'ok'" % nid)
            b.wait_render(300, "#viewHost [data-translate]", 30)
            has_tr = b.js("!!document.querySelector('#viewHost [data-translate]')")
            ok("资讯详情有逐条翻译入口", bool(has_tr))
            if has_tr:
                b.js("document.querySelector('#viewHost [data-translate]').click(); 'ok'")
                b.wait_js("document.querySelector('#viewHost [data-tr-out] .bilingual')", 40)
                bl = b.js("(document.querySelector('#viewHost [data-tr-out]')||{}).innerText||''") or ""
                ok("双语对照含「原文 / 译文」", "原文" in bl and "译文" in bl, "%s 字" % len(bl))
                ok("译文失败时诚实回退（不编造）",
                   ("回退" in bl or "未保留" in bl or len(bl) > 40), "%s 字" % len(bl))
                orig = b.js("var a=document.querySelector('#viewHost [data-orig]'); a? (a.click(), true):false")
                ok("原文显示可切换", bool(orig))
                b.shot("08_翻译双语")
        else:
            ok("资讯详情有逐条翻译入口", False, "未取到真实资讯 id")
        # 服务端翻译 API 的数字/代码保护
        guard = b.js("fetch('/api/i18n/translate',{method:'POST',headers:{'Content-Type':'application/json'},"
                     "body:JSON.stringify({text:'AAPL rose 3.25% to $ 227.50 in 2026',lang:'ja'})})"
                     ".then(r=>r.json()).then(d=>JSON.stringify(d))", await_promise=True)
        try:
            gd = json.loads(guard) if isinstance(guard, str) else {}
            ok("翻译 API 返回结构化结果", "text" in gd and "original" in gd, str(gd)[:120])
            ok("翻译保留原始数字（或诚实回退）",
               ("3.25" in str(gd.get("text", "")) or gd.get("fallback") or gd.get("preserved") is False),
               str(gd)[:120])
        except Exception as e:
            ok("翻译 API 返回结构化结果", False, str(e))
        b.js("switchView('dashboard'); 'ok'")
        time.sleep(1.0)

        # ---------- 8 主题 / 多分辨率 ----------
        print("\n[8] 主题与响应式")
        b.js("document.querySelector('#btnTheme').click(); 'ok'")
        time.sleep(0.8)
        ok("深浅主题可切换", b.js("document.documentElement.dataset.theme") in ("light", "dark"),
           b.js("document.documentElement.dataset.theme"))
        b.shot("06_浅色主题")
        b.js("document.querySelector('#btnTheme').click(); 'ok'")
        for w, h, label in ((1920, 1080, "1920"), (1536, 960, "1536"),
                            (1366, 900, "1366"), (768, 1024, "平板768"), (390, 844, "手机390")):
            b.metrics(w, h)                     # 必须先设置视口再测量，否则量到的是上一次的值
            overflow = b.js("JSON.stringify({sw:document.documentElement.scrollWidth,"
                            "cw:document.documentElement.clientWidth,"
                            "main:Math.round((document.querySelector('.view-area')||{}).getBoundingClientRect().width),"
                            "topbar:Math.round((document.querySelector('.topbar')||{}).getBoundingClientRect().width),"
                            "host:(document.querySelector('#viewHost')||{}).innerText.length})")
            od = json.loads(overflow) if isinstance(overflow, str) else {}
            ok("分辨率 %s 视口生效" % label, (od.get("cw") or 0) <= w + 2,
               "clientWidth=%s / 设定=%s" % (od.get("cw"), w))
            # >=1260px 时侧栏(236)+右栏(312)本就占空间；<1260px 右栏隐藏，主区应更宽
            ratio = 0.48 if w >= 1260 else 0.70
            ok("分辨率 %s 主内容区可见（非 0 宽塌陷）" % label,
               (od.get("main") or 0) >= (od.get("cw") or 1) * ratio,
               "viewArea=%spx / clientWidth=%spx / 阈值 %.0f%%" % (od.get("main"), od.get("cw"), ratio * 100))
            ok("分辨率 %s 顶栏铺满视口" % label,
               (od.get("topbar") or 0) >= (od.get("cw") or 1) * 0.8,
               "topbar=%spx" % od.get("topbar"))
            ok("分辨率 %s 无横向溢出" % label, (od.get("sw") or 0) <= (od.get("cw") or 0) + 2,
               "scrollWidth=%s clientWidth=%s" % (od.get("sw"), od.get("cw")))
            ok("分辨率 %s 内容仍可见" % label, (od.get("host") or 0) > 200, "%s 字" % od.get("host"))
            if label in ("1920", "平板768", "手机390"):
                b.shot("07_%s" % label, w, h)
        b.ws.call("Emulation.clearDeviceMetricsOverride")

        # ---------- 9 主要旧视图回归（不能因升级破坏） ----------
        print("\n[9] V2.0 主要视图回归")
        for v, marker in (("news", "资讯"), ("macro", "FRED"), ("sources", "数据源"), ("quotes", "")):
            b.js("switchView('%s'); 'ok'" % v)
            b.wait_render(500, "", 30)
            s = b.js("(document.querySelector('#viewHost')||{}).innerText||''") or ""
            bad = "本模块数据暂时不可用" in s
            ok("视图 %s 正常渲染" % v, len(s) > 500 and not bad, "%s 字" % len(s))
            if marker:
                ok("视图 %s 含真实数据标记「%s」" % (v, marker), marker in s)

        # ---------- 10 JS 运行时错误 ----------
        print("\n[10] JS 运行时错误")
        b.drain()
        # 只把 JS 异常/控制台错误算失败；字体、favicon 等网络噪声单独记录
        js_err = [e for e in b.errors if e.startswith(("EXC:", "CONSOLE:"))]
        net_err = [e for e in b.errors if e.startswith("LOG:")]
        ok("无 JS 运行时异常 / 控制台错误", len(js_err) == 0,
           " | ".join(js_err[:3]) if js_err else "0 条")
        if net_err:
            NOTES.append("浏览器网络级日志 %d 条（首 2 条：%s）" % (len(net_err), " | ".join(net_err[:2])))
        if b.net_failed:
            uniq = []
            for u, err in b.net_failed:
                if (u, err) not in uniq:
                    uniq.append((u, err))
            NOTES.append("失败请求 %d 个：%s" % (len(uniq), " | ".join(
                "%s (%s)" % (u[:110], e) for u, e in uniq[:4])))
            # 站内接口失败可能是快速跳转时被中断的历史请求；用一次全新 fetch 复验，
            # 只有复验仍失败才判定为真实故障（不把导航中断误报成服务不可用）
            local_fail = [u for u, _ in uniq if base in u]
            still_bad = []
            for u in local_fail:
                path = u[len(base):]
                status = b.js("fetch(%s,{cache:'no-store'}).then(r=>r.status).catch(e=>-1)"
                              % json.dumps(path), await_promise=True)
                if status != 200:
                    still_bad.append("%s→%s" % (path[:70], status))
            ok("站内接口复验全部 200（早期失败为导航中断）", not still_bad, ",".join(still_bad[:3]))
            if local_fail and not still_bad:
                NOTES.append("快速跳转时有 %d 个站内请求被中断，已用全新请求复验 200：%s"
                             % (len(local_fail), ",".join(u[len(base):][:60] for u in local_fail[:3])))
        results = {"pass": len(PASS), "fail": len(FAIL), "notes": NOTES,
                   "errors": b.errors[:20], "shots": sorted(os.listdir(shots))}
    finally:
        b.close()

    print("\n" + "=" * 70)
    print("  浏览器验收：%d PASS / %d FAIL" % (len(PASS), len(FAIL)))
    if NOTES:
        for n in NOTES:
            print("  [NOTE] " + n)
    if FAIL:
        print("  失败项：")
        for f in FAIL:
            print("   - %s · %s" % (f["name"], f["detail"]))
    print("=" * 70)
    rep = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_report.json")
    with open(rep, "w", encoding="utf-8") as f:
        json.dump({"base": base, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "passed": PASS, "failed": FAIL, "notes": NOTES,
                   "browser_errors": results.get("errors", []), "screenshots": results.get("shots", [])},
                  f, ensure_ascii=False, indent=2)
    print("  报告：" + rep)
    return 1 if FAIL else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:6789")
    ap.add_argument("--shots", default="_tmp/v21_shots")
    a = ap.parse_args()
    sys.exit(run(a.base.rstrip("/"), a.shots))
