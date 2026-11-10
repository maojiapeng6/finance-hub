/* ============ 环球财经雷达 v2 · 前端逻辑 ============ */
const $ = id => document.getElementById(id);
const API = {
  news: '/api/news', quotes: '/api/quotes', markets: '/api/markets',
  brief: '/api/brief', sources: '/api/sources', refresh: '/api/refresh',
  ask: '/api/ask', status: '/api/status', events: '/api/events', overview: '/api/overview'
};
const CATS = ['全部', '全球局势', '财经宏观', '股市风向', '中国宏观', '商品外汇', '数字资产', '科技产业'];
const SYM_NAME = {
  '^GSPC': '标普500', '^IXIC': '纳斯达克', '^DJI': '道琼斯', '^RUT': '罗素2000', '^VIX': '恐慌指数VIX',
  '^FTSE': '英国富时100', '^GDAXI': '德国DAX', '^N225': '日经225', '^HSI': '恒生指数', '^STOXX50E': '欧洲STOXX50',
  '000001.SS': '上证指数', '399001.SZ': '深证成指', '399006.SZ': '创业板指',
  'EURUSD=X': '欧元/美元', 'USDJPY=X': '美元/日元', 'GBPUSD=X': '英镑/美元',
  'USDCNY=X': '美元/人民币', 'DX-Y.NYB': '美元指数',
  'CL=F': 'WTI原油', 'BZ=F': '布伦特原油', 'GC=F': '黄金', 'SI=F': '白银', 'HG=F': '铜', 'NG=F': '天然气',
  'BTC-USD': '比特币', 'ETH-USD': '以太坊', 'SOL-USD': 'Solana',
  '^TNX': '美债10Y收益率', '^FVX': '美债5Y收益率',
  'AAPL': '苹果', 'NVDA': '英伟达', 'MSFT': '微软', 'TSLA': '特斯拉',
  'META': 'Meta', 'GOOGL': '谷歌', 'AMZN': '亚马逊'
};
const S = {
  all: [], filtered: [], shown: 0, page: 20,
  cat: '全部', prio: '', lang: '', kw: '',
  quotes: [], qgroup: '全球指数', sources: [],
  lastNews: 0, lastQuotes: 0, auto: true, overview: null
};

/* ---------- 工具 ---------- */
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cls = v => v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
const sign = v => (v > 0 ? '+' : '') + Number(v).toFixed(2);
const fmtPrice = v => v == null ? '--' :
  (Math.abs(v) >= 1000 ? Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }) : Number(v).toFixed(2));
const qname = q => SYM_NAME[q.symbol] || q.name || q.symbol;

function ago(ts) {
  if (!ts) return { h: '--:--', d: '时间未知' };
  const d = new Date(ts * 1000), diff = Math.max(0, (Date.now() - ts * 1000) / 1000);
  let label;
  if (diff < 60) label = '刚刚';
  else if (diff < 3600) label = Math.floor(diff / 60) + ' 分钟前';
  else if (diff < 86400) label = Math.floor(diff / 3600) + ' 小时前';
  else if (diff < 172800) label = '昨天';
  else label = (d.getMonth() + 1) + '-' + String(d.getDate()).padStart(2, '0');
  return { h: String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'), d: label };
}
function hhmm(ts) {
  if (!ts) return '--:--';
  const d = new Date(ts * 1000);
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}
async function get(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
let toastTimer;
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.hidden = true, 2600);
}
const isZh = s => /[\u4e00-\u9fff]/.test(s || '');

/* 来源色块：由名称 hash 出稳定渐变，零外部依赖 */
function mediaStyle(name) {
  let h = 0; for (const c of (name || '?')) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `--m1:hsl(${h},48%,30%);--m2:hsl(${(h + 55) % 360},52%,24%)`;
}

/* ---------- 时钟 / 市场时段 ---------- */
function bjParts() {
  const d = new Date(Date.now() + 8 * 3600 * 1000);  // 统一按北京时间判断
  return { day: d.getUTCDay(), h: d.getUTCHours(), m: d.getUTCMinutes() };
}
function marketStatus() {
  const { day, h, m } = bjParts(), t = h * 60 + m, week = day >= 1 && day <= 5;
  const inRange = (a, b) => t >= a && t < b;
  const winter = (() => { const mo = new Date(Date.now() + 8 * 3600 * 1000).getUTCMonth() + 1; return mo >= 11 || mo <= 3; })();
  return [
    { n: 'A股', ok: week && (inRange(570, 690) || inRange(780, 900)), time: '09:30–15:00' },
    { n: '港股', ok: week && (inRange(570, 720) || inRange(780, 960)), time: '09:30–16:00' },
    { n: '欧股', ok: week && inRange(900, 1410), time: '15:00–23:30' },
    {
      n: '美股', ok: (week && (inRange(winter ? 1350 : 1290, 1440) || (day >= 2 && day <= 6 && inRange(0, winter ? 300 : 240)))),
      time: winter ? '22:30–05:00' : '21:30–04:00'
    }
  ];
}
function renderClocks() {
  $('marketClocks').innerHTML = marketStatus().map(s =>
    `<span class="clk ${s.ok ? 'open' : ''}" title="北京时间 ${s.time}"><i></i><b>${s.n}</b> ${s.ok ? '交易中' : '休市'}</span>`).join('');
}
function tickClock() {
  const d = new Date();
  $('clockTime').textContent = d.toLocaleTimeString('zh-CN', { hour12: false });
  $('clockDate').textContent = d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', weekday: 'short' });
}

/* ---------- 首屏总览 ---------- */
function moodText(score) {
  if (score > 25) return '偏暖 · 情绪乐观';
  if (score > 8) return '微暖 · 略偏多';
  if (score > -8) return '中性 · 多空均衡';
  if (score > -25) return '微冷 · 略偏空';
  return '偏冷 · 谨慎情绪';
}
function renderOverview(d) {
  S.overview = d;
  const s = d.sentiment || { score: 0 }, score = Number(s.score) || 0;
  $('kpiSent').textContent = (score > 0 ? '+' : '') + score;
  $('kpiSent').style.color = score > 12 ? 'var(--up)' : score < -12 ? 'var(--down)' : 'var(--gold)';
  $('kpiSentSub').textContent = moodText(score) + ' · 偏多 ' + (s.pos || 0) + ' / 偏空 ' + (s.neg || 0);
  $('kpiBar').style.width = Math.max(3, Math.min(100, (score + 100) / 2)) + '%';

  $('kpiNews').textContent = d.total || 0;
  $('kpiNewsSub').textContent = `其中官方原文 ${d.p1 || 0} 条 · 覆盖 ${d.quote_count || 0} 项行情`;
  const p1 = d.p1 || 0;
  $('kpiGrid').querySelector('.kpi-news .kpi-foot').innerHTML =
    `<span class="kpi-chip">P1 ${p1}</span><span class="kpi-chip p2">P2 ${Math.max(0, (d.total || 0) - p1)}</span><span class="kpi-chip p3">P3 社交</span>`;

  const fill = (id, sub, listId, arr, isUp) => {
    const first = arr && arr[0];
    if (!first) { $(id).textContent = '--'; $(sub).textContent = '等待行情…'; return; }
    $(id).textContent = qname(first);
    $(id).style.color = isUp ? 'var(--up)' : 'var(--down)';
    $(sub).textContent = (first.pct > 0 ? '+' : '') + Number(first.pct).toFixed(2) + '% · 现价 ' + fmtPrice(first.price);
    $(listId).innerHTML = arr.slice(0, 3).map(x =>
      `<span class="kpi-mini ${cls(x.pct)}">${esc(qname(x))} <b>${sign(x.pct)}%</b></span>`).join(' ');
  };
  fill('kpiTop', 'kpiTopSub', 'kpiTopList', d.top, true);
  fill('kpiBottom', 'kpiBottomSub', 'kpiBottomList', d.bottom, false);

  const top = (d.top || [])[0], bot = (d.bottom || [])[0];
  $('heroLine').textContent =
    `当前风向${moodText(score)}。今日已聚合 ${d.total || 0} 条快讯（官方原文 ${d.p1 || 0} 条）` +
    (top ? `，${qname(top)}领涨 ${sign(top.pct)}%` : '') +
    (bot ? `，${qname(bot)}领跌 ${sign(bot.pct)}%` : '') +
    `。下方每条都可点开原文，并附大白话解读与关联行情。`;
}
async function loadOverview() {
  try { renderOverview(await get(API.overview)); } catch (e) { $('heroLine').textContent = '总览加载中，可直接浏览下方实时资讯。'; }
}

/* ---------- 分类 Tabs ---------- */
function initTabs() {
  $('catTabs').innerHTML = CATS.map(c =>
    `<button class="tab${c === '全部' ? ' on' : ''}" data-c="${c}">${c}</button>`).join('');
  $('catTabs').addEventListener('click', e => {
    const b = e.target.closest('.tab'); if (!b) return;
    [...$('catTabs').children].forEach(x => x.classList.remove('on'));
    b.classList.add('on'); S.cat = b.dataset.c; applyFilter(true);
  });
  $('prioFilter').addEventListener('change', e => { S.prio = e.target.value; applyFilter(true); });
  $('langFilter').addEventListener('change', e => { S.lang = e.target.value; applyFilter(true); });
  let t;
  $('feedSearch').addEventListener('input', e => {
    clearTimeout(t); t = setTimeout(() => { S.kw = e.target.value.trim().toLowerCase(); applyFilter(true); }, 220);
  });
}

/* ---------- 资讯卡片 ---------- */
async function loadNews(silent) {
  if (!silent) $('feedList').innerHTML = '<div class="loading"><span class="spin"></span>正在聚合全球资讯…</div>';
  try {
    const d = await get(API.news + '?limit=300');
    S.all = d.items || []; S.lastNews = d.updated;
    $('feedCount').textContent = d.total + ' 条';
    applyFilter(false);
    if (d.errors && Object.keys(d.errors).length > 2 && !S.all.length) {
      $('feedList').innerHTML = '<div class="empty">暂时无法连接外网资讯源，请检查代理设置或稍后点「刷新」重试。</div>';
    }
  } catch (e) {
    if (!S.all.length) $('feedList').innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '，请点右上角「刷新」重试。</div>';
  }
}
function applyFilter(reset) {
  let a = S.all;
  if (S.cat !== '全部') a = a.filter(x => x.category === S.cat);
  if (S.prio) a = a.filter(x => x.priority === S.prio);
  if (S.lang === 'zh') a = a.filter(x => isZh(x.title));
  if (S.lang === 'en') a = a.filter(x => !isZh(x.title));
  if (S.kw) a = a.filter(x => (x.title + ' ' + (x.summary || '') + ' ' + (x.source || '') + ' ' + (x.hint || '')).toLowerCase().includes(S.kw));
  S.filtered = a;
  S.shown = Math.min(S.page, a.length);
  if (reset) window.scrollTo({ top: 0, behavior: 'smooth' });
  renderFeed();
}
function feedHTML(it) {
  const t = ago(it.published), p = (it.priority || 'P2').toLowerCase(), zh = isZh(it.title);
  const src = it.source || it.domain || '资讯';
  const initial = (src.replace(/[^A-Za-z\u4e00-\u9fff]/g, '')[0] || '•').toUpperCase();
  const pLabel = { p1: 'P1 官方', p2: 'P2 专业', p3: 'P3 社交' }[p] || 'P2 专业';
  const link = it.link || it.search || '#';
  const site = it.site || (it.domain ? 'https://' + it.domain : '');
  const syms = (it.symbols || []).map(s =>
    `<a class="nc-sym" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)} 行情 ↗</a>`).join('');
  const tags = (it.tags || []).map(w =>
    `<span class="nc-tag" data-w="${esc(w)}">#${esc(w)}</span>`).join('');
  return `<article class="news-card ${p}">
    <div class="nc-media" style="${mediaStyle(src)}">
      <span class="nc-initial">${esc(initial)}</span>
      ${it.image ? `<img src="${esc(it.image)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ''}
      <span class="nc-media-lbl">${esc(it.domain || src)}</span>
    </div>
    <div class="nc-main">
      <div class="nc-meta">
        <span class="nc-src">${esc(src)}</span>
        <span class="tag tag-cat">${esc(it.category || '资讯')}</span>
        <span class="tag tag-${p}">${pLabel}</span>
        <span class="tag ${zh ? 'tag-zh' : 'tag-en'}">${zh ? '中文' : 'EN'}</span>
        <span class="nc-time">${esc(t.d)} · ${esc(t.h)}</span>
      </div>
      <a class="nc-title" href="${esc(link)}" target="_blank" rel="noopener noreferrer">${esc(it.title)}<span class="ext">↗</span></a>
      ${it.summary ? `<div class="nc-sum">${esc(it.summary)}</div>` : ''}
      <div class="nc-hint"><b>大白话</b>${esc(it.hint || '点击打开原文查看全文；用「搜相关」可比对同一话题的其他报道。')}</div>
      <div class="nc-actions">
        <a class="nc-cta" href="${esc(link)}" target="_blank" rel="noopener noreferrer">打开原文 ↗</a>
        ${site ? `<a class="nc-link" href="${esc(site)}" target="_blank" rel="noopener noreferrer">来源主页</a>` : ''}
        ${it.search ? `<a class="nc-link" href="${esc(it.search)}" target="_blank" rel="noopener noreferrer">搜相关报道</a>` : ''}
        ${syms}${tags}
      </div>
    </div></article>`;
}
function renderFeed() {
  const box = $('feedList');
  if (!S.filtered.length) {
    box.innerHTML = S.prio === 'P3'
      ? '<div class="empty">社交源（Reddit 等）偶发被平台限流，暂时没有新内容。<br>可点右上角「信息源」查看 X / Reddit / 雪球等 P3 渠道，或切回「全部等级」。</div>'
      : '<div class="empty">没有符合条件的动态，换个分类或清空搜索试试 🙂<br><br><a class="nc-cta" href="https://www.bing.com/news" target="_blank" rel="noopener noreferrer">去 Bing 新闻看看 ↗</a></div>';
  } else {
    box.innerHTML = S.filtered.slice(0, S.shown).map(feedHTML).join('');
  }
  const more = S.shown < S.filtered.length;
  $('btnMore').disabled = !more;
  $('btnMore').textContent = more ? `加载更多动态 ↓（还有 ${S.filtered.length - S.shown} 条）` : '已经到底啦';
  $('feedHint').textContent = `显示 ${Math.min(S.shown, S.filtered.length)} / ${S.filtered.length} 条`;
}

/* ---------- 行情 ---------- */
function sparkSVG(arr, positive) {
  if (!arr || arr.length < 2) return '<svg class="qspark"></svg>';
  const min = Math.min(...arr), max = Math.max(...arr), rng = (max - min) || 1;
  const w = 100, h = 26;
  const pts = arr.map((v, i) => `${(i / (arr.length - 1) * w).toFixed(1)},${(h - 2 - (v - min) / rng * (h - 5)).toFixed(1)}`).join(' ');
  const c = positive ? '#fb7185' : '#34d399';
  const id = 'g' + Math.random().toString(36).slice(2, 8);
  return `<svg class="qspark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${c}" stop-opacity=".32"/><stop offset="100%" stop-color="${c}" stop-opacity="0"/>
    </linearGradient></defs>
    <polygon points="0,${h} ${pts} ${w},${h}" fill="url(#${id})"/>
    <polyline points="${pts}" fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}
function renderTicker() {
  const list = S.quotes.filter(q => ['^GSPC', '^IXIC', '^DJI', '^N225', '^HSI', '000001.SS',
    '399001.SZ', 'CL=F', 'GC=F', 'BTC-USD', 'USDCNY=X', '^VIX'].includes(q.symbol));
  if (!list.length) { $('tickerTrack').innerHTML = '<div class="ticker-empty">行情加载中…</div>'; return; }
  const one = list.map(q => `<span class="tk"><span class="n">${esc(qname(q))}</span>
      <span class="v">${fmtPrice(q.price)}</span>
      <span class="c ${cls(q.pct)}">${sign(q.pct)}%</span></span>`).join('');
  $('tickerTrack').innerHTML = one + one;
}
function initQuoteTabs() {
  const groups = ['全球指数', '中国指数', '外汇', '大宗商品', '数字资产', '利率', '龙头个股'];
  $('quoteTabs').innerHTML = groups.map(g =>
    `<button class="qtab${g === S.qgroup ? ' on' : ''}" data-g="${g}">${g}</button>`).join('');
  $('quoteTabs').addEventListener('click', e => {
    const b = e.target.closest('.qtab'); if (!b) return;
    [...$('quoteTabs').children].forEach(x => x.classList.remove('on'));
    b.classList.add('on'); S.qgroup = b.dataset.g; renderQuoteList();
  });
}
function renderQuoteList() {
  const list = S.quotes.filter(q => q.group === S.qgroup);
  if (!list.length) { $('quoteList').innerHTML = '<div class="loading">该分组暂无数据（免费源可能受限）</div>'; return; }
  $('quoteList').innerHTML = list.map(q => `<div class="qrow">
    <div class="qname">${esc(qname(q))}<small>${esc(q.symbol)}</small></div>
    <div class="qprice ${cls(q.pct)}">${fmtPrice(q.price)}</div>
    <div>${sparkSVG(q.spark, q.pct >= 0)}</div>
    <div class="qpct ${cls(q.pct)}">${sign(q.pct)}%</div>
  </div>`).join('');
}
async function loadQuotes() {
  try {
    const d = await get(API.quotes);
    S.quotes = d.items || []; S.lastQuotes = d.updated;
    renderTicker(); renderQuoteList();
    $('quoteTime').textContent = hhmm(d.updated);
    $('quoteHint').textContent = `${S.quotes.length} 项 · 免费源约15分钟延迟`;
  } catch (e) { $('quoteHint').textContent = '行情连接失败'; }
}

/* ---------- 温度计 / 热词 ---------- */
async function loadMarkets() {
  try {
    const d = await get(API.markets);
    if (d.quotes && d.quotes.length && !S.quotes.length) { S.quotes = d.quotes; renderTicker(); renderQuoteList(); }
    const s = d.sentiment || { score: 0, pos: 0, neg: 0, total: 0 };
    $('tempScore').textContent = (s.score > 0 ? '+' : '') + s.score;
    $('tempScore').style.color = s.score > 12 ? 'var(--up)' : s.score < -12 ? 'var(--down)' : 'var(--gold)';
    $('gaugeArc').setAttribute('stroke-dasharray', `${((s.score + 100) / 200 * 258).toFixed(1)} 258`);
    $('gaugeLine').setAttribute('transform', `rotate(${(s.score / 100) * 90} 100 100)`);
    let v, desc;
    if (s.score > 25) { v = '偏暖 · 情绪乐观'; desc = '近期快讯里偏多措辞明显占优，市场情绪积极；但仍需留意是否过热。'; }
    else if (s.score > 8) { v = '微暖 · 略偏多'; desc = '利好消息略多于利空，风向温和偏积极，建议结合盘面确认。'; }
    else if (s.score > -8) { v = '中性 · 多空均衡'; desc = '多空消息大致平衡，市场缺乏一致方向，宜等待更明确的信号。'; }
    else if (s.score > -25) { v = '微冷 · 略偏空'; desc = '利空措辞略占上风，情绪偏谨慎，注意控制仓位与风险。'; }
    else { v = '偏冷 · 谨慎情绪'; desc = '负面消息明显偏多，市场避险情绪较重，请特别留意风险提示。'; }
    $('tempVerdict').textContent = v;
    $('tempVerdict').style.color = s.score > 8 ? 'var(--up)' : s.score < -8 ? 'var(--down)' : 'var(--gold)';
    $('tempDesc').textContent = desc;
    const tot = s.total || 1;
    $('sentPos').style.width = (s.pos / tot * 100) + '%';
    $('sentNeg').style.width = (s.neg / tot * 100) + '%';
    $('posNum').textContent = s.pos; $('negNum').textContent = s.neg;
    const tp = d.topics || [], max = tp.length ? tp[0].count : 1;
    $('topicBody').innerHTML = tp.length ? tp.map(t =>
      `<span class="tpc${t.count >= max * .6 ? ' hot' : ''}" title="点击搜索该关键词" data-w="${esc(t.word)}">${esc(t.word)}<b>${t.count}</b></span>`
    ).join('') : '<span class="tpc">暂无热词</span>';
    $('topicBody').onclick = e => {
      const el = e.target.closest('.tpc'); if (!el || !el.dataset.w) return;
      $('feedSearch').value = el.dataset.w; S.kw = el.dataset.w.toLowerCase(); applyFilter(true);
    };
  } catch (e) { /* 静默 */ }
}

/* ---------- AI 简报 ---------- */
function briefHTML(txt, refs) {
  const clean = txt.replace(/```[\s\S]*?```/g, '').replace(/\*\*/g, '').trim();
  // 把 [编号] 变成可点开的原文链接：简报每句话都能回溯到一手资讯
  const linkify = raw => esc(raw).replace(/\[(\d{1,2})\]/g, (m, n) => {
    const r = (refs || []).find(x => String(x.n) === n);
    return r && r.link
      ? `<a class="ref" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer" title="${esc(r.source)}：${esc(r.title)}">[${n}]</a>`
      : m;
  });
  const parts = clean.split(/(?=【[^】]+】)/).filter(Boolean);
  let html = '';
  for (const p of parts) {
    const m = p.match(/^【([^】]+)】\s*([\s\S]*)$/);
    if (m) html += `<div class="brief-sec"><h4>${esc(m[1])}</h4><p>${linkify(m[2].trim())}</p></div>`;
    else if (/今日关键词|^关键词/.test(p)) html += `<div class="brief-key">${esc(p.trim())}</div>`;
    else if (p.trim()) html += `<p class="brief-plain">${esc(p.trim())}</p>`;
  }
  return html || `<div class="brief-plain">${linkify(clean)}</div>`;
}
async function loadBrief(regen) {
  if (regen) $('briefBody').innerHTML = '<div class="loading"><span class="spin"></span>AI 正在重新解读最新资讯…</div>';
  try {
    const d = await get(API.brief + (regen ? '?regen=1' : ''));
    if (d.status === 'ok' && d.text) {
      $('briefBody').innerHTML = briefHTML(d.text, d.refs || []);
      $('briefMeta').innerHTML = `<span>生成于 ${hhmm(d.updated)} · 句末编号可点开原文</span><span>AI 归纳，仅供辅助判断</span>`;
    } else {
      $('briefBody').innerHTML = `<div class="err-box">${esc(d.err || 'AI 简报正在准备中，稍后自动重试…')}</div>`;
      $('briefMeta').textContent = 'AI 服务暂不可用，其余功能不受影响';
    }
  } catch (e) { $('briefBody').innerHTML = '<div class="err-box">简报加载失败，请稍后点「重生成」</div>'; }
}

/* ---------- AI 问答 ---------- */
async function ask(q) {
  if (!q) return;
  const box = $('askAnswer'); box.hidden = false;
  box.textContent = 'AI 正在结合最新资讯思考…';
  $('btnAsk').disabled = true;
  try {
    const d = await get(API.ask, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ q })
    });
    box.textContent = d.answer || d.error || '暂无回答';
  } catch (e) { box.textContent = 'AI 暂时无法回答：' + e.message; }
  $('btnAsk').disabled = false;
}

/* ---------- 信息源抽屉 ---------- */
async function openSources() {
  $('drawerMask').hidden = false; $('drawer').hidden = false;
  if (!S.sources.length) {
    $('srcBody').innerHTML = '<div class="loading"><span class="spin"></span>加载信息源…</div>';
    try { S.sources = await get(API.sources); } catch (e) { S.sources = []; }
  }
  renderSources('');
}
function renderSources(kw) {
  const k = kw.toLowerCase();
  const list = S.sources.filter(s => !k ||
    (s.name + ' ' + s.url + ' ' + s.cat + ' ' + (s.desc || '')).toLowerCase().includes(k));
  $('srcCount').textContent = `共 ${list.length} 个源 · 点击直达官网`;
  const groups = {};
  list.forEach(s => (groups[s.cat] = groups[s.cat] || []).push(s));
  const keys = Object.keys(groups).sort();
  $('srcBody').innerHTML = keys.length ? keys.map(g =>
    `<div class="src-group"><h3>${esc(g)} · ${groups[g].length}</h3>${groups[g].map(s =>
      `<a class="src-item" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">
        <span class="src-badge ${(s.prio || 'P2').toLowerCase()}">${esc(s.prio)}</span>
        <span class="src-info"><b>${esc(s.name)}</b><small>${esc(s.desc || s.url)}</small></span>
        <span class="src-open">打开 ↗</span></a>`).join('')}</div>`).join('')
    : '<div class="empty">没有找到匹配的信息源</div>';
}
function closeSources() { $('drawerMask').hidden = true; $('drawer').hidden = true; }

/* ---------- 刷新 / 实时 ---------- */
async function refreshAll() {
  const b = $('btnRefresh'); b.classList.add('spin');
  try { await get(API.refresh + '?what=all'); } catch (e) { }
  await Promise.all([loadNews(true), loadQuotes(), loadMarkets(), loadOverview(), loadBrief(false)]);
  b.classList.remove('spin'); $('newBar').hidden = true;
  toast('已更新全部数据');
}
function initSSE() {
  // 无头浏览器截图 / 排障时用 ?nosse=1 关闭长连接，避免页面永不空闲
  if (location.search.includes('nosse')) { $('liveTxt').textContent = '快照模式'; return; }
  try {
    const es = new EventSource(API.events);
    es.onopen = () => { $('livePill').classList.remove('off'); $('liveTxt').textContent = '实时连接'; };
    es.onmessage = ev => {
      let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
      if (S.lastNews && d.news_updated > S.lastNews) {
        $('newBar').hidden = false;
        $('newCount').textContent = Math.max(1, d.news_count - S.all.length);
      }
      if (S.auto && d.quotes_updated > S.lastQuotes) loadQuotes();
    };
    es.onerror = () => { $('livePill').classList.add('off'); $('liveTxt').textContent = '重连中'; };
  } catch (e) { $('liveTxt').textContent = '轮询模式'; }
}

/* ---------- 事件绑定 ---------- */
function bind() {
  $('btnRefresh').onclick = refreshAll;
  $('btnMore').onclick = () => { S.shown = Math.min(S.shown + S.page, S.filtered.length); renderFeed(); };
  $('btnSources').onclick = openSources;
  $('btnCloseDrawer').onclick = closeSources;
  $('drawerMask').onclick = closeSources;
  $('srcSearch').addEventListener('input', e => renderSources(e.target.value.trim()));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeSources();
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); $('feedSearch').focus(); }
  });
  $('autoSwitch').onchange = e => { S.auto = e.target.checked; toast(S.auto ? '自动刷新已开启' : '自动刷新已暂停'); };
  $('btnRegenBrief').onclick = () => loadBrief(true);
  $('btnCopyBrief').onclick = () => {
    navigator.clipboard?.writeText($('briefBody').innerText)
      .then(() => toast('简报已复制')).catch(() => toast('复制失败，请手动选中'));
  };
  $('newBar').onclick = async () => { $('newBar').hidden = true; await loadNews(false); toast('已载入最新动态'); };
  $('btnAsk').onclick = () => { const q = $('askText').value.trim(); if (q) { ask(q); $('askText').value = ''; } };
  $('askText').addEventListener('keydown', e => {
    if (e.key === 'Enter') { const q = e.target.value.trim(); if (q) { ask(q); e.target.value = ''; } }
  });
  $('askChips').onclick = e => { const b = e.target.closest('button'); if (b) ask(b.textContent.trim()); };
  // 卡片内话题标签：站内反查
  $('feedList').addEventListener('click', e => {
    const el = e.target.closest('.nc-tag'); if (!el) return;
    e.preventDefault();
    $('feedSearch').value = el.dataset.w; S.kw = el.dataset.w.toLowerCase(); applyFilter(true);
  });
  let guard = false;
  window.addEventListener('scroll', () => {
    if (guard || S.shown >= S.filtered.length) return;
    if (window.innerHeight + window.scrollY > document.body.offsetHeight - 480) {
      guard = true; S.shown = Math.min(S.shown + S.page, S.filtered.length); renderFeed();
      setTimeout(() => guard = false, 350);
    }
  });
}

/* ---------- 启动 ---------- */
async function boot() {
  tickClock(); setInterval(tickClock, 1000);
  renderClocks(); setInterval(renderClocks, 60000);
  initTabs(); initQuoteTabs(); bind();
  await Promise.all([loadNews(false), loadQuotes(), loadMarkets(), loadOverview(), loadBrief(false)]);
  initSSE();
  setInterval(() => { if (!S.auto) return; loadQuotes(); loadMarkets(); renderClocks(); }, 60000);
  setInterval(() => { if (S.auto) loadBrief(false); }, 5 * 60000);
  setInterval(() => { if (S.auto) { loadNews(true); loadOverview(); } }, 8 * 60000);
  $('footTime').textContent = '最后同步 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
}
boot();
