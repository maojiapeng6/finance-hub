/* ============================================================
   GFIC 2.0 · 全球金融情报中心 — 前端逻辑
   原则：所有显示的数据来自站内真实 API；无数据显示明确空态；
        未接入的模块诚实列出缺失数据源，不伪装成已完成。
   ============================================================ */
const $ = id => document.getElementById(id);
const API = {
  dashboard:'/api/dashboard', news:'/api/news', quotes:'/api/quotes',
  markets:'/api/markets', overview:'/api/overview', brief:'/api/brief',
  sources:'/api/sources', sourceStatus:'/api/sources/status',
  sourceToggle:'/api/sources/toggle', sourceProbe:'/api/sources/probe',
  macro:'/api/macro', crypto:'/api/crypto', sec:'/api/sec',
  heatmap:'/api/heatmap', watchlist:'/api/watchlist',
  watchlistSave:'/api/watchlist/save', alerts:'/api/alerts',
  alertsSave:'/api/alerts/save', alertsCheck:'/api/alerts/check',
  search:'/api/search', refresh:'/api/refresh', ask:'/api/ask',
  status:'/api/status', events:'/api/events'
};

const NAV = [
  {g:'情报中枢 / INTELLIGENCE', items:[
    {id:'dashboard', t:'全球金融驾驶舱', i:'◉', e:'INTELLIGENCE / OVERVIEW'},
    {id:'news',      t:'全球实时资讯',   i:'≡', e:'INTELLIGENCE / NEWSFEED'},
    {id:'events',    t:'AI 全球事件分析', i:'◇', e:'INTELLIGENCE / EVENTS'},
    {id:'geo',       t:'全球地缘政治',   i:'◎', e:'INTELLIGENCE / GEOPOLITICS'},
    {id:'industry',  t:'产业链与行业',   i:'⌗', e:'INTELLIGENCE / INDUSTRY'},
    {id:'social',    t:'社交与市场情绪', i:'♡', e:'INTELLIGENCE / SENTIMENT'},
  ]},
  {g:'市场监控 / MARKETS', items:[
    {id:'quotes',      t:'全球行情',     i:'↗', e:'MARKETS / QUOTES'},
    {id:'heatmap',     t:'市场涨跌热力图', i:'▦', e:'MARKETS / HEATMAP'},
    {id:'macro',       t:'全球宏观经济', i:'▤', e:'MARKETS / MACRO'},
    {id:'fx',          t:'外汇与利率',   i:'⇄', e:'MARKETS / FX & RATES'},
    {id:'commodities', t:'商品与期货',   i:'◆', e:'MARKETS / COMMODITIES'},
    {id:'crypto',      t:'数字资产',     i:'₿', e:'MARKETS / DIGITAL ASSETS'},
    {id:'flows',       t:'全球资金流向', i:'≈', tag:'未接入', e:'MARKETS / FLOWS'},
    {id:'etf',         t:'全球基金与 ETF', i:'▣', tag:'未接入', e:'MARKETS / FUNDS'},
  ]},
  {g:'研究工作台 / RESEARCH', items:[
    {id:'research', t:'公司研究 · SEC', i:'⌕', e:'RESEARCH / COMPANY'},
    {id:'scoring',  t:'AI 股票评分推荐', i:'★', tag:'未接入', e:'RESEARCH / SCORING'},
    {id:'ai',       t:'AI 金融工作台', i:'✦', e:'RESEARCH / AI WORKBENCH'},
    {id:'backtest', t:'AI 预测成绩单', i:'◷', tag:'未接入', e:'RESEARCH / TRACK RECORD'},
  ]},
  {g:'资产与系统 / SYSTEM', items:[
    {id:'watchlist', t:'自选股与组合', i:'☆', e:'SYSTEM / WATCHLIST'},
    {id:'alerts',    t:'全球风险预警', i:'⚑', e:'SYSTEM / ALERTS'},
    {id:'sources',   t:'数据源管理',   i:'⚙', e:'SYSTEM / DATA SOURCES'},
    {id:'about',     t:'系统说明与清单', i:'ⓘ', e:'SYSTEM / ABOUT'},
  ]},
];
const NAVMAP = {}; NAV.forEach(g => g.items.forEach(i => NAVMAP[i.id] = i));

const S = {
  view:'dashboard', dashboard:null, news:[], quotes:[], markets:null,
  sources:null, catalog:[], macro:null, crypto:null, heatmap:null,
  watchlist:null, alerts:null, sec:null,
  cat:'全部', prio:'', lang:'', kw:'', shown:20, page:20,
  newsCount:0, briefLoaded:false, theme:localStorage.getItem('gfic-theme')||'dark',
  filter:{grade:'', status:'', kw:''}, clocks:null
};

/* ---------------- 工具 ---------------- */
const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (v,d=2) => (v===null||v===undefined||isNaN(v))?'--':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const sign = v => (v>0?'+':'') + num(v,2);
const cls = v => v>0?'up':(v<0?'down':'flat');
const ago = ts => { const s=Math.max(0,Math.floor(Date.now()/1000)-Number(ts||0));
  if(s<60)return'刚刚'; if(s<3600)return Math.floor(s/60)+' 分钟前'; if(s<86400)return Math.floor(s/3600)+' 小时前'; return Math.floor(s/86400)+' 天前'; };
const hhmm = ts => ts ? new Date(Number(ts)*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}) : '--:--';
const dateCN = ts => ts ? new Date(Number(ts)*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '--';
function toast(m){ const t=$('toast'); t.textContent=m; t.hidden=false; clearTimeout(t._t); t._t=setTimeout(()=>t.hidden=true,2600); }
async function get(u){ const r=await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }
async function post(u,b){ const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }
const loading = (txt='正在读取真实数据…') => `<div class="loading"><span class="spin"></span>${esc(txt)}</div>`;
const srcNote = (arr) => `<div class="src-note">${arr.map(x=>`<span>${x}</span>`).join('<span>·</span>')}</div>`;
function cardHead(title, sub, right){ return `<div class="card-head"><h2>${esc(title)}</h2>${sub?`<span class="sub">${esc(sub)}</span>`:''}${right?`<div class="right">${right}</div>`:''}</div>`; }

function sparkSVG(arr, up){
  if(!arr||arr.length<2) return '';
  const w=74,h=24,min=Math.min(...arr),max=Math.max(...arr),rg=(max-min)||1;
  const pts=arr.map((v,i)=>`${(i/(arr.length-1)*w).toFixed(1)},${(h-2-(v-min)/rg*(h-4)).toFixed(1)}`).join(' ');
  const c=up?'var(--up)':'var(--down)';
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}
function lineSVG(points, opt={}){
  if(!points||points.length<2) return '<div class="plain-note">暂无足够历史点绘制图表</div>';
  const vals=points.map(p=>Number(p[1])).filter(v=>isFinite(v));
  if(!vals.length) return '<div class="plain-note">暂无有效数值</div>';
  const w=300,h=104,min=Math.min(...vals),max=Math.max(...vals),rg=(max-min)||1;
  const xy=points.map((p,i)=>[i/(points.length-1)*w, h-8-(Number(p[1])-min)/rg*(h-20)]);
  const d=xy.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area=d+` L${w} ${h} L0 ${h} Z`;
  const col=opt.color||'var(--cyan)';
  return `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="lg${opt.id||'a'}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${col}" stop-opacity=".28"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <path d="${area}" fill="url(#lg${opt.id||'a'})"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${xy[xy.length-1][0].toFixed(1)}" cy="${xy[xy.length-1][1].toFixed(1)}" r="3" fill="${col}"/></svg>
    <div class="chart-axis"><span>${esc(points[0][0])}</span><span>${esc(points[points.length-1][0])}</span></div>`;
}
function heatColor(p){
  const a=Math.min(.42,.06+Math.abs(p)/2.2);
  return p>0?`rgba(255,77,94,${a})`:(p<0?`rgba(22,199,154,${a})`:'var(--panel2)');
}
function emptyState(o){
  return `<div class="empty-state"><div class="empty-ico">${o.icon||'◌'}</div>
    <h3>${esc(o.title)}</h3><p>${o.desc}</p>
    ${o.list?`<ul class="empty-list">${o.list.map(x=>`<li class="${x.ok?'ok':''}">${x.t}</li>`).join('')}</ul>`:''}
    ${o.cta?`<div class="empty-cta">${o.cta}</div>`:''}</div>`;
}

/* ---------------- 导航 ---------------- */
function renderNav(){
  $('nav').innerHTML = NAV.map(g=>`<div class="nav-group">${esc(g.g)}</div>` + g.items.map(i=>
    `<button class="nav-item ${S.view===i.id?'active':''}" data-view="${i.id}" title="${esc(i.t)}">
      <span class="ni-ico">${i.i}</span><span class="ni-txt">${esc(i.t)}</span>
      ${i.tag?`<span class="ni-tag na">${esc(i.tag)}</span>`:''}</button>`).join('')).join('');
  $('nav').querySelectorAll('.nav-item').forEach(b=>b.onclick=()=>switchView(b.dataset.view));
}
function switchView(id){
  if(!NAVMAP[id]) id='dashboard';
  S.view=id; const m=NAVMAP[id];
  document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.view===id));
  $('pageTitle').textContent=m.t; $('ptEyebrow').textContent=m.e;
  $('sidebar').classList.remove('open');
  location.hash=id;
  window.scrollTo({top:0,behavior:'smooth'});
  mount();
}
async function mount(){
  const host=$('viewHost');
  host.innerHTML=loading();
  try{
    const fn=V[S.view]||V.dashboard;
    await fn(host);
  }catch(e){
    host.innerHTML=`<div class="card"><div class="card-body">${emptyState({
      icon:'!', title:'本模块数据暂时不可用',
      desc:`读取真实数据时出错：${esc(e.message)}。系统不会用模拟数据填充，请稍后点右上角刷新重试。`,
      cta:`<button class="btn primary" onclick="refreshAll()">重新加载</button>`})}</div></div>`;
  }
}

/* ---------------- 通用：资讯卡片 / 信息流 ---------------- */
function newsCard(it){
  const p=it.priority||'P2';
  const badge=p==='P1'?'badge a':(p==='P3'?'badge d':'badge c');
  const img=it.image?`<img src="${esc(it.image)}" loading="lazy" onerror="this.parentNode.innerHTML='<span>◈</span>'">`:'<span>◈</span>';
  return `<article class="news-card">
    <div class="nc-img">${img}</div>
    <div class="nc-main">
      <div class="nc-meta">
        <span class="badge ${badge}">${p}${p==='P1'?' 官方':(p==='P3'?' 社交':' 专业')}</span>
        <span>${esc(it.category||'')}</span><span>·</span>
        <span>${esc(it.source||it.domain||'')}</span><span>·</span><span>${ago(it.published)}</span>
        ${it.region==='zh'?'<span class="badge">中文</span>':''}
      </div>
      <a class="nc-title" href="${esc(it.link||'#')}" target="_blank" rel="noopener noreferrer">${esc(it.title)}</a>
      ${it.summary?`<div class="nc-sum">${esc(it.summary)}</div>`:''}
      <div class="nc-hint"><b>大白话：</b>${esc(it.hint||'点「打开原文」看全文；用「搜相关」可比对同一话题的其他报道。')}</div>
      <div class="nc-actions">
        <a class="nc-link pri" href="${esc(it.link||'#')}" target="_blank" rel="noopener noreferrer">打开原文 ↗</a>
        <a class="nc-link" href="${esc(it.search||'#')}" target="_blank" rel="noopener noreferrer">搜相关报道</a>
        ${(it.symbols||[]).map(s=>`<a class="nc-link" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)}行情 ↗</a>`).join('')}
        ${(it.tags||[]).map(t=>`<span class="nc-tag">#${esc(t)}</span>`).join('')}
        ${it.site?`<a class="nc-link" href="${esc(it.site)}" target="_blank" rel="noopener noreferrer">${esc(it.domain)}</a>`:''}
      </div>
    </div></article>`;
}
async function ensureNews(){ if(!S.news.length){ const d=await get(API.news+'?limit=900'); S.news=d.items||[]; S.newsCount=d.total||S.news.length; } return S.news; }
function filterNews(cfg={}){
  let a=S.news.slice();
  if(cfg.categories && !cfg.tabs) a=a.filter(x=>cfg.categories.includes(x.category));
  else if(S.cat&&S.cat!=='全部') a=a.filter(x=>x.category===S.cat);
  if(cfg.priority) a=a.filter(x=>x.priority===cfg.priority);
  if(S.prio) a=a.filter(x=>x.priority===S.prio);
  if(S.lang) a=a.filter(x=>(x.region||'en')===S.lang);
  if(S.kw){ const k=S.kw.toLowerCase(); a=a.filter(x=>(x.title||'').toLowerCase().includes(k)||(x.summary||'').toLowerCase().includes(k)); }
  if(cfg.q){ const k=cfg.q.toLowerCase(); a=a.filter(x=>(x.title||'').toLowerCase().includes(k)); }
  return a;
}
function feedView(host,cfg={}){
  const a=filterNews(cfg), shown=a.slice(0,S.shown);
  const tabs=cfg.tabs||['全部','全球局势','财经宏观','股市风向','中国宏观','商品外汇','数字资产','科技产业'];
  host.innerHTML=`
  <div class="card">
    ${cardHead(cfg.title||'全球实时资讯', cfg.sub||'按时间倒序 · 同源去重 · 每条都可点开原文',
      `<span class="badge a">共 ${a.length} 条</span>`)}
    <div class="card-body">
      <div class="feed-tools" style="margin-bottom:11px">
        <div class="tabs" id="fTabs">${tabs.map(t=>`<button class="tab ${S.cat===t?'active':''}" data-cat="${esc(t)}">${esc(t)}</button>`).join('')}</div>
        <select class="sel" id="fPrio"><option value="">全部等级</option><option value="P1" ${S.prio==='P1'?'selected':''}>P1 官方</option><option value="P2" ${S.prio==='P2'?'selected':''}>P2 专业</option><option value="P3" ${S.prio==='P3'?'selected':''}>P3 社交</option></select>
        <select class="sel" id="fLang"><option value="">全部语言</option><option value="zh" ${S.lang==='zh'?'selected':''}>中文</option><option value="en" ${S.lang==='en'?'selected':''}>英文</option></select>
        <input class="inp" id="fKw" placeholder="筛选标题关键词…" value="${esc(S.kw)}" style="flex:1;min-width:150px">
        <button class="btn" id="fClear">清空</button>
      </div>
      ${cfg.notice||''}
      <div class="feed-list" id="feedList">${shown.length?shown.map(newsCard).join(''):
        `<div class="empty-state"><div class="empty-ico">⌕</div><h3>暂无符合条件的资讯</h3><p>当前筛选条件下没有真实资讯。清空筛选或切换分类即可继续浏览（系统不会用模拟数据补位）。</p></div>`}</div>
      <div class="feed-foot">${shown.length<a.length?`<button class="more-btn" id="btnMore">加载更多 ↓（还有 ${a.length-shown.length} 条）</button>`:`<span class="plain-note">已显示全部 ${a.length} 条</span>`}</div>
    </div>
    ${srcNote(['来源：Google News RSS / 官方 RSS / 专业媒体 RSS','仅存标题·摘要·时间·原文链接','不复制新闻全文','P3 社交源偶发限流'])}
  </div>`;
  $('fTabs').onclick=e=>{const b=e.target.closest('.tab'); if(!b)return; S.cat=b.dataset.cat; S.shown=20; mount();};
  $('fPrio').onchange=e=>{S.prio=e.target.value;S.shown=20;mount();};
  $('fLang').onchange=e=>{S.lang=e.target.value;S.shown=20;mount();};
  let tmr; $('fKw').oninput=e=>{clearTimeout(tmr);tmr=setTimeout(()=>{S.kw=e.target.value.trim();S.shown=20;mount();},350);};
  $('fClear').onclick=()=>{S.cat=cfg.tabs?cfg.tabs[0]:'全部';S.prio='';S.lang='';S.kw='';S.shown=20;mount();};
  if($('btnMore')) $('btnMore').onclick=()=>{S.shown+=S.page;mount();};
}

/* ---------------- 各视图 ---------------- */
const V = {};

/* 01 驾驶舱 */
V.dashboard = async host => {
  const [d,q,m]=await Promise.all([get(API.dashboard),get(API.quotes),get(API.markets)]);
  S.dashboard=d; S.quotes=q.items||[]; S.markets=m;
  const top=d.top&&d.top[0], bot=d.bottom&&d.bottom[0], sen=d.sentiment||{};
  const groups={}; (q.items||[]).forEach(x=>(groups[x.group]=groups[x.group]||[]).push(x));
  const gnames=Object.keys(groups);
  host.innerHTML=`
  <div class="hero">
    <div class="hero-top"><div>
      <div class="hero-eyebrow"><span class="pulse"></span> LIVE · 全球市场情报聚合</div>
      <h2>市场正在发生什么，一眼看清</h2>
      <p>已聚合 <b>${d.total}</b> 条去重资讯（其中 P1 官方原文 <b>${d.p1}</b> 条）、<b>${d.quote_count}</b> 项行情与 <b>${Object.keys(d.macro||{}).length}</b> 类官方宏观数据。${top?`当前 <b class="${cls(top.pct)}">${esc(top.name)}领涨 ${sign(top.pct)}%</b>`:''}${bot?`，<b class="${cls(bot.pct)}">${esc(bot.name)}领跌 ${sign(bot.pct)}%</b>`:''}。</p>
    </div><div class="hero-stamp">数据更新 ${hhmm(d.updated)}<br>免费数据源 · ¥0</div></div>
    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-top"><span>市场情绪</span><span class="kpi-ico">◑</span></div>
        <div class="kpi-val ${cls(sen.score)}">${sen.score>0?'+':''}${sen.score||0}</div>
        <div class="kpi-sub">基于最新 ${sen.total||0} 条资讯标题的关键词统计</div>
        <div class="kpi-bar"><i style="width:${Math.min(100,50+(sen.score||0)/2)}%"></i></div></div>
      <div class="kpi"><div class="kpi-top"><span>今日快讯</span><span class="kpi-ico">≡</span></div>
        <div class="kpi-val">${d.total}</div><div class="kpi-sub">其中 P1 官方原文 ${d.p1} 条</div>
        <div class="kpi-foot"><span class="kpi-chip">P1 官方</span><span class="kpi-chip p2">P2 专业</span><span class="kpi-chip p3">P3 社交</span></div></div>
      <div class="kpi"><div class="kpi-top"><span>领涨资产</span><span class="kpi-ico">↗</span></div>
        <div class="kpi-val small ${top?cls(top.pct):''}">${top?esc(top.name):'暂无数据'}</div>
        <div class="kpi-sub">${top?sign(top.pct)+'% · '+num(top.price):'行情源暂无数据'}</div>
        <div class="kpi-foot">${(d.top||[]).slice(1,4).map(x=>`<span class="kpi-chip">${esc(x.name)} ${sign(x.pct)}%</span>`).join('')}</div></div>
      <div class="kpi"><div class="kpi-top"><span>领跌资产</span><span class="kpi-ico">↘</span></div>
        <div class="kpi-val small ${bot?cls(bot.pct):''}">${bot?esc(bot.name):'暂无数据'}</div>
        <div class="kpi-sub">${bot?sign(bot.pct)+'% · '+num(bot.price):'行情源暂无数据'}</div>
        <div class="kpi-foot">${(d.bottom||[]).slice(1,4).map(x=>`<span class="kpi-chip">${esc(x.name)} ${sign(x.pct)}%</span>`).join('')}</div></div>
    </div>
  </div>

  <div class="card">
    ${cardHead('全球市场速览','真实行情 · 涨红跌绿', `<span class="badge warn">延迟 15–20 分钟</span><button class="btn" data-go="quotes">全部行情 →</button>`)}
    <div class="card-body"><div class="grid-4">
      ${gnames.slice(0,8).map(g=>{const arr=groups[g], avg=arr.reduce((s,x)=>s+(x.pct||0),0)/arr.length;
        return `<div class="stat"><div class="s-label"><span>${esc(g)}</span><span>${arr.length} 项</span></div>
          <div class="s-val ${cls(avg)}">${sign(avg)}%</div><div class="s-meta">组均涨跌幅</div>
          <div class="s-src">Yahoo Finance · 非官方接口</div></div>`;}).join('')}
    </div>${srcNote(['数据来源：Yahoo Finance v8 chart（非官方公开接口）','延迟约 15–20 分钟，仅供方向判断，不可用于下单','无数据的标的不会以模拟值补位'])}</div>
  </div>

  <div class="grid-2" style="margin-top:14px">
    <div class="card" style="margin:0">
      ${cardHead('最新重大动态','按时间倒序', `<button class="btn" data-go="news">查看全部 →</button>`)}
      <div class="card-body" style="padding:10px 12px"><div class="timeline">${(await ensureNews()).slice(0,7).map(x=>
        `<div class="tl-item ${x.priority==='P1'?'p1':''}"><div class="tl-time">${dateCN(x.published)} · ${esc(x.source||'')}</div>
         <a class="tl-title" href="${esc(x.link||'#')}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a>
         <div class="tl-meta"><span class="badge ${x.priority==='P1'?'a':'c'}">${esc(x.priority)}</span> ${esc(x.category||'')} · ${ago(x.published)}</div></div>`).join('')}</div></div>
    </div>
    <div class="card" style="margin:0">
      ${cardHead('官方宏观快照','FRED / 美国财政部 / ECB', `<button class="btn" data-go="macro">宏观详情 →</button>`)}
      <div class="card-body"><div id="dashMacro">${loading('正在读取官方宏观数据…')}</div></div>
    </div>
  </div>

  <div class="card" style="margin-top:14px">
    ${cardHead('数据口径与风险提示','请先看这里再用于判断')}
    <div class="card-body"><div class="grid-3">
      <div class="stat"><div class="s-label">行情</div><div class="s-val" style="font-size:14px">延迟 15–20 分钟</div><div class="s-meta">Yahoo 非官方接口；不可用于下单</div></div>
      <div class="stat"><div class="s-label">宏观</div><div class="s-val" style="font-size:14px">统计发布值</div><div class="s-meta">日/月/季/年频，不是实时数据</div></div>
      <div class="stat"><div class="s-label">数字资产</div><div class="s-val" style="font-size:14px">交易所实时</div><div class="s-meta">Binance / Coinbase / Kraken / OKX 官方接口</div></div>
    </div><p class="plain-note">社交讨论量 ≠ 真实资金流；成交额 ≠ 资金净流入；CFTC 持仓为周频报告，不是实时持仓。本平台仅供个人研究，不构成投资建议。</p></div>
    ${srcNote([`数据源：${d.sources?d.sources.live:0} 个已接入 / ${d.sources?d.sources.total:0} 个注册`,'全部免费公开源','密钥仅存服务端'])}
  </div>`;
  host.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go));
  loadDashMacro();
};
async function loadDashMacro(){
  const el=$('dashMacro'); if(!el)return;
  try{
    const m=S.macro||(S.macro=await get(API.macro));
    const p=m.parts||{}, f=(p.fred||{}).series||[], t=p.treasury||{}, e=p.ecb_fx||{};
    const pick=id=>f.find(x=>x.id===id);
    const rows=[];
    if(pick('UNRATE')) rows.push(['美国失业率',pick('UNRATE').value+' %',pick('UNRATE').as_of]);
    if(pick('CPIAUCSL')) rows.push(['美国 CPI',num(pick('CPIAUCSL').value,1),pick('CPIAUCSL').as_of]);
    if(pick('FEDFUNDS')) rows.push(['联邦基金利率',pick('FEDFUNDS').value+' %',pick('FEDFUNDS').as_of]);
    if(t.date) rows.push(['美债 10Y',((t.curve||[]).find(c=>c.tenor==='10年')||{}).yield+' %',t.date]);
    if(e.date) rows.push(['ECB 欧元/美元',(e.rates.find(r=>r[0]==='USD')||[])[1],e.date]);
    el.innerHTML=rows.length?`<div class="tbl-wrap"><table class="tbl"><thead><tr><th>指标</th><th class="r">最新值</th><th class="r">统计截止</th></tr></thead><tbody>
      ${rows.map(r=>`<tr><td class="nm">${esc(r[0])}</td><td class="r"><b>${esc(String(r[1]))}</b></td><td class="r" style="color:var(--txt3)">${esc(String(r[2]))}</td></tr>`).join('')}
      </tbody></table></div>${srcNote(['FRED / U.S. Treasury / ECB 官方公开数据','统计发布值，非实时'])}`:
      `<div class="plain-note">官方宏观数据源本次返回暂无数据，请稍后刷新。</div>`;
  }catch(e){ el.innerHTML=`<div class="plain-note">宏观数据暂时不可用：${esc(e.message)}</div>`; }
}

/* 02 资讯 */
V.news = async host => { await ensureNews(); S.shown=20; S.cat='全部'; S.prio=''; S.lang=''; S.kw='';
  return feedView(host,{title:'全球实时资讯',sub:'按地区 / 资产 / 主题分类 · 同源去重',tabs:undefined}); };

/* 03 事件分析 */
V.events = async host => {
  await ensureNews();
  const themes=[
    {k:'地缘与冲突',re:/战争|冲突|地缘|中东|军事|制裁|停火|war|geopolitic|conflict|missile/i,assets:['黄金','原油','美元'],desc:'冲突/制裁类报道'},
    {k:'关税与贸易',re:/关税|贸易|出口管制|tariff|trade|export control|sanction/i,assets:['全球股指','汇率','半导体'],desc:'贸易政策与供应链'},
    {k:'央行与利率',re:/美联储|降息|加息|利率|央行|Fed|FOMC|通胀|CPI|货币政策|ECB|BOJ/i,assets:['美债','黄金','成长股'],desc:'货币政策与通胀'},
    {k:'公司重大事件',re:/财报|营收|业绩|并购|收购|IPO|earnings|merger|acquisition|guidance/i,assets:['相关个股'],desc:'财报与并购'},
    {k:'能源供应',re:/原油|OPEC|天然气|能源|EIA|oil|crude|gas/i,assets:['WTI原油','能源股'],desc:'能源供需与库存'},
    {k:'科技与AI',re:/AI|人工智能|芯片|半导体|英伟达|NVIDIA|算力|数据中心|chip/i,assets:['NVDA','半导体'],desc:'AI 与半导体产业链'},
    {k:'数字资产',re:/比特币|以太坊|加密|BTC|ETH|crypto|ETF/i,assets:['BTC','ETH'],desc:'加密市场与资金'},
  ];
  const now=Date.now()/1000;
  const blocks=themes.map(t=>{
    const hits=S.news.filter(x=>t.re.test(x.title)).slice(0,6);
    return {t,hits};
  }).filter(b=>b.hits.length);
  host.innerHTML=`
  <div class="card">${cardHead('AI 全球事件分析','基于站内真实资讯的主题聚类','<span class="badge warn">规则聚类 · 非 AI 编造</span>')}
    <div class="card-body"><p class="plain-note" style="margin:0 0 12px">
      本页按关键词把<b>真实抓取的资讯标题</b>归入主题，只呈现「已确认的报道」，不做因果推断、不生成未发生的事实。
      需要解读时点「让 AI 分析」，回答会明确区分站内事实与常识解释，并标注数据口径。</p>
      <div class="grid-2">${blocks.map(b=>`
        <div class="chart-box">
          <h4>${esc(b.t.k)} <span class="badge">${b.hits.length} 条报道</span></h4>
          <div class="cb-sub">${esc(b.t.desc)} · 关联观察：${b.t.assets.map(a=>`<span class="badge c">${esc(a)}</span>`).join(' ')}</div>
          ${b.hits.slice(0,4).map(x=>`<div style="font-size:10.5px;line-height:1.5;margin:5px 0">
             <a href="${esc(x.link||'#')}" target="_blank" rel="noopener noreferrer" style="color:var(--txt2)">· ${esc(x.title.slice(0,62))}${x.title.length>62?'…':''}</a>
             <span style="color:var(--txt3)"> [${esc(x.source||'')}]</span></div>`).join('')}
          <div style="margin-top:9px;display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn" data-ask="基于站内真实资讯，客观归纳「${esc(b.t.k)}」主题下已报道的事实，不要推测未发生的事，并说明数据口径与不确定性">让 AI 分析该主题</button>
            <button class="btn" data-kw="${esc(b.t.k)}">查看全部相关资讯</button>
          </div>
        </div>`).join('')||'<div class="plain-note">当前资讯中未匹配到预设主题</div>'}</div>
      ${srcNote(['聚类依据：关键词规则（非 AI 生成）','每条标题均可点开原文核验','未确认信息不会被当作事实展示'])}
    </div></div>`;
  host.querySelectorAll('[data-ask]').forEach(b=>b.onclick=()=>{switchView('ai');setTimeout(()=>ask(b.dataset.ask),260);});
  host.querySelectorAll('[data-kw]').forEach(b=>b.onclick=()=>{S.view='news';S.kw=b.dataset.kw;S.cat='全部';S.shown=20;switchView('news');});
};

/* 04 地缘 / 05 产业链 / 06 社交 */
V.geo = async host => { await ensureNews(); S.shown=20;S.cat='全球局势';S.prio='';S.lang='';S.kw='';
  feedView(host,{title:'全球地缘政治',sub:'冲突 · 制裁 · 贸易 · 能源安全 · 航运',
    categories:['全球局势'],tabs:['全球局势'],
    notice:`<p class="plain-note" style="margin:0 0 10px">本地图/事件时间线由 <b>真实资讯</b> 构成（未接入地图可视化数据源，故不绘制虚构地图）。地缘类报道常推升避险资产，但报道量不等于资金流。</p>`}); };
V.industry = async host => { await ensureNews(); S.shown=20;S.cat='科技产业';S.prio='';S.lang='';S.kw='';
  feedView(host,{title:'全球产业链与行业分析',sub:'半导体 · AI · 新能源 · 医药 · 消费 · 航运',
    categories:['科技产业','数字资产'],tabs:['科技产业','数字资产','全部'],
    notice:`<p class="plain-note" style="margin:0 0 10px">行业趋势以真实新闻呈现；<b>产业链上下游图谱、行业景气度指数尚未接入数据源</b>，故不生成虚构图谱。可点击每条资讯的「关联标的」查看相关行情。</p>`}); };
V.social = async host => {
  await ensureNews(); const p3=S.news.filter(x=>x.priority==='P3');
  const m=S.markets||await get(API.markets); const tps=(m.topics||[]).slice(0,18);
  host.innerHTML=`
  <div class="card">${cardHead('社交媒体与市场情绪','讨论热度 ≠ 真实资金流','<span class="badge warn">D 级数据</span>')}
    <div class="card-body">
      <div class="grid-3" style="margin-bottom:12px">
        <div class="stat"><div class="s-label">情绪得分</div><div class="s-val ${cls((m.sentiment||{}).score)}">${(m.sentiment||{}).score||0}</div><div class="s-meta">基于资讯标题关键词，非社交专属</div></div>
        <div class="stat"><div class="s-label">P3 社区条目</div><div class="s-val">${p3.length}</div><div class="s-meta">Reddit r/stocks 等公开 RSS</div></div>
        <div class="stat"><div class="s-label">热门话题</div><div class="s-val">${tps.length}</div><div class="s-meta">全站标题词频统计</div></div>
      </div>
      <div class="chart-box"><h4>今日热词（真实词频）</h4><div class="cb-sub">点击可反查相关资讯；词频高只说明被报道得多，不代表资金流入</div>
        <div class="topics" style="padding:6px 0">${tps.map(t=>`<button class="topic" data-kw="${esc(t.word)}">${esc(t.word)}<b>×${t.count}</b></button>`).join('')||'<span class="plain-note">暂无热词</span>'}</div></div>
      <div style="margin-top:12px" class="chart-box"><h4>社区最新讨论</h4><div class="cb-sub">非官方来源，未经独立核实，不得单独作为投资结论</div>
        <div class="feed-list" style="margin-top:9px">${p3.length?p3.slice(0,8).map(newsCard).join(''):
          `<div class="plain-note">P3 社交源本次抓取暂无数据（Reddit 偶发限流）。系统不会用模拟帖子填充。</div>`}</div></div>
      ${srcNote(['P3 数据源：Reddit r/stocks 公开 RSS','D 级非官方数据','未接入 X / Telegram / YouTube（需平台 API 授权）'])}
    </div></div>`;
  host.querySelectorAll('[data-kw]').forEach(b=>b.onclick=()=>{S.view='news';S.kw=b.dataset.kw;S.cat='全部';S.shown=20;switchView('news');});
};

/* 07 全球行情 */
V.quotes = async host => {
  const q=await get(API.quotes); S.quotes=q.items||[];
  const groups={}; S.quotes.forEach(x=>(groups[x.group]=groups[x.group]||[]).push(x));
  host.innerHTML=`
  <div class="card">${cardHead('全球行情','指数 / 股票 / 外汇 / 商品 / 加密 / 利率',
    `<span class="badge warn">延迟 15–20 分钟</span><span class="badge">${S.quotes.length} 项</span>`)}
    <div class="card-body">
      ${Object.keys(groups).map(g=>`<div style="margin-bottom:16px"><div class="heat-title">${esc(g)} · ${groups[g].length} 项</div>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>标的</th><th>名称</th><th class="r">最新价</th><th class="r">涨跌</th><th class="r">涨跌幅</th><th>日内走势</th><th class="r">更新时间</th></tr></thead><tbody>
        ${groups[g].map(x=>`<tr><td class="sym">${esc(x.symbol)}</td><td class="nm">${esc(x.name)}</td>
          <td class="r">${num(x.price)}</td><td class="r ${cls(x.change)}">${sign(x.change)}</td>
          <td class="r ${cls(x.pct)}"><b>${sign(x.pct)}%</b></td><td>${sparkSVG(x.spark,x.pct>=0)}</td>
          <td class="r" style="color:var(--txt3)">${hhmm(x.time)}</td></tr>`).join('')}
        </tbody></table></div></div>`).join('')||'<div class="plain-note">行情源暂无数据</div>'}
      ${srcNote(['数据来源：Yahoo Finance v8 chart（<b>非官方</b>公开接口）','约 15–20 分钟延迟','失败标的显示暂无数据，不补模拟值',`失败 ${Object.keys(q.errors||{}).length} 项`])}
    </div></div>`;
};

/* 08 热力图 */
V.heatmap = async host => {
  const h=await get(API.heatmap); S.heatmap=h;
  const groups={}; (h.cells||[]).forEach(x=>(groups[x.group]=groups[x.group]||[]).push(x));
  const up=(h.cells||[]).filter(x=>x.pct>0).length, dn=(h.cells||[]).filter(x=>x.pct<0).length;
  host.innerHTML=`
  <div class="card">${cardHead('全球市场涨跌热力图','色深 = 涨跌幅绝对值 · 涨红跌绿',
    `<span class="badge up">涨 ${up}</span><span class="badge ok">跌 ${dn}</span><span class="badge">共 ${(h.cells||[]).length}</span>`)}
    <div class="card-body">
      <div class="heat-legend" style="margin-bottom:12px"><span>跌</span>
        <i style="background:rgba(22,199,154,.42)"></i><i style="background:rgba(22,199,154,.2)"></i>
        <i style="background:var(--panel2)"></i><i style="background:rgba(255,77,94,.2)"></i>
        <i style="background:rgba(255,77,94,.42)"></i><span>涨</span>
        <span style="margin-left:auto">中国市场习惯：红涨绿跌</span></div>
      ${Object.keys(groups).map(g=>`<div class="heat-group"><div class="heat-title">${esc(g)}</div>
        <div class="heat-cells">${groups[g].map(x=>`<div class="heat-cell" style="background:${heatColor(x.pct)}" title="${esc(x.name)} ${esc(x.symbol)}">
          <div class="hc-n">${esc(x.name)}</div><div class="hc-p ${cls(x.pct)}">${sign(x.pct)}%</div>
          <div class="hc-s">${num(x.price)} · ${esc(x.symbol)}</div></div>`).join('')}</div></div>`).join('')||'<div class="plain-note">暂无行情数据</div>'}
      ${srcNote([esc(h.source||'Yahoo Finance'),'延迟行情','色块仅表示涨跌幅，不代表成交额或资金流'])}
    </div></div>`;
};

/* 09 宏观经济 */
V.macro = async host => {
  const m=S.macro||(S.macro=await get(API.macro)); const p=m.parts||{};
  const f=(p.fred||{}).series||[], wb=(p.worldbank||{}).countries||[], eu=p.eurostat||{}, tr=p.treasury||{}, fd=(p.fiscaldata||{}).rows||[];
  host.innerHTML=`
  ${p.fred?`<div class="card">${cardHead('美国宏观 · FRED 官方序列',`${f.length} 组真实统计序列`,'<span class="badge a">A 级官方</span>')}
    <div class="card-body"><div class="grid-4">${f.map(x=>`<div class="stat">
      <div class="s-label"><span>${esc(x.name)}</span><span class="badge">${esc(x.frequency)}频</span></div>
      <div class="s-val">${num(x.value,2)}</div><div class="s-meta">${esc(x.unit)} · 截至 ${esc(x.as_of)} ${x.change!==null?`· 环比 <span class="${cls(x.change)}">${sign(x.change)}</span>`:''}</div>
      <div class="chart-box" style="margin-top:8px;padding:6px;border:0;background:none">${lineSVG(x.points.map(q=>[q[0],q[1]]),{id:x.id,color:x.change<0?'var(--down)':'var(--cyan)'})}</div>
      <div class="s-src"><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">FRED ${esc(x.id)} ↗</a> · ${esc(x.origin)}</div>
    </div>`).join('')}</div>
    ${srcNote(['来源：FRED（Federal Reserve Bank of St. Louis）官方 CSV 导出','月度/季度/日频统计发布值，<b>不是实时数据</b>','每条带统计截止期与原始序列链接'])}</div></div>`:
    `<div class="card"><div class="card-body"><div class="plain-note">FRED 官方宏观数据本次返回暂无数据（${esc((m.errors||{}).fred||'数据源不可用')}），不补模拟值。</div></div></div>`}

  ${tr.curve?`<div class="card">${cardHead('美国国债收益率曲线',`财政部官方 · ${esc(tr.date)}`,'<span class="badge a">A 级官方</span>')}
    <div class="card-body"><div class="grid-2">
      <div class="chart-box"><h4>期限结构</h4><div class="cb-sub">单位 % · 每日收盘后更新</div>
        ${lineSVG(tr.curve.map(c=>[c.tenor,c.yield]),{id:'curve',color:'var(--purple)'})}
        <div class="bar-row" style="margin-top:10px"><span class="bl">10Y-2Y 利差</span><span class="bt"><i style="width:${Math.min(100,Math.abs(tr.spread_10y_2y||0)*40)}%"></i></span><span class="bv ${cls(tr.spread_10y_2y)}">${num(tr.spread_10y_2y,2)} pct</span></div>
      </div>
      <div class="chart-box"><h4>10 年期近 30 个交易日</h4><div class="cb-sub">官方日度曲线历史值</div>
        ${lineSVG((tr.history||[]).map(x=>[x[0],x[1]]),{id:'dgs10',color:'var(--cyan)'})}
        <div class="tbl-wrap" style="margin-top:8px"><table class="tbl"><tbody>
        ${tr.curve.slice(0,6).map(c=>`<tr><td class="nm">${esc(c.tenor)}</td><td class="r">${num(c.yield,2)} %</td></tr>`).join('')}</tbody></table></div></div>
    </div>${srcNote(['来源：U.S. Department of the Treasury 官方 Atom XML','日更收盘数据',`<a href="${esc(tr.url)}" target="_blank" rel="noopener noreferrer">官方原始页 ↗</a>`])}</div></div>`:''}

  ${wb.length?`<div class="card">${cardHead('全球 GDP 与通胀 · World Bank','年度数据 · 多国对比','<span class="badge a">A 级官方</span>')}
    <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>国家</th><th>指标</th><th class="r">最新值</th><th class="r">年份</th><th class="r">单位</th><th>历史点</th></tr></thead><tbody>
      ${wb.map(x=>`<tr><td><b>${esc(x.country)}</b></td><td class="nm">${esc(x.indicator)}</td>
        <td class="r">${num(x.last_value,2)}</td><td class="r">${esc(x.last_date)}</td><td class="r">${esc(x.unit)}</td>
        <td>${(x.points||[]).map(q=>`<span class="badge">${esc(q[0])}: ${num(q[1],0)}</span>`).join(' ')}</td></tr>`).join('')}
      </tbody></table></div>${srcNote(['来源：World Bank 开放数据 API','<b>年度数据，发布有滞后，不可当实时值</b>','许可：CC BY 4.0',`数据最后更新 ${esc((p.worldbank||{}).countries?.[0]?.lastupdated||'')}`])}</div></div>`:''}

  ${eu.points?`<div class="card">${cardHead('欧元区通胀 · Eurostat HICP','月频年同比', '<span class="badge a">A 级官方</span>')}
    <div class="card-body"><div class="grid-2"><div class="stat"><div class="s-label">最新值</div><div class="s-val">${num(eu.value,2)} %</div>
      <div class="s-meta">统计期 ${esc(eu.as_of)} · 月频，官方数据集截止期为准</div></div>
      <div class="chart-box"><h4>历史走势</h4><div class="cb-sub">单位 %</div>${lineSVG(eu.points,{id:'hicp',color:'var(--gold)'})}</div></div>
      ${srcNote(['来源：Eurostat 官方 API（prc_hicp_manr）','公开数据需注明来源','月频，非实时'])}</div></div>`:''}

  ${fd.length?`<div class="card">${cardHead('美国财政 · 国债平均利率','Fiscal Data 官方接口','<span class="badge a">A 级官方</span>')}
    <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>记录日期</th><th>证券类型</th><th class="r">平均利率</th></tr></thead><tbody>
      ${fd.slice(0,6).map(r=>`<tr><td class="nm">${esc(r.record_date)}</td><td class="nm">${esc(r.security_desc||r.security_type_desc||'')}</td><td class="r">${esc(r.avg_interest_rate_amt||'--')}</td></tr>`).join('')}
      </tbody></table></div>${srcNote(['来源：U.S. Treasury Fiscal Data API','月度统计值'])}</div></div>`:''}

  ${Object.keys(m.errors||{}).length?`<div class="card"><div class="card-body"><p class="plain-note">本次未返回数据的分项：${Object.entries(m.errors).map(([k,v])=>`<span class="badge warn">${esc(k)}：${esc(v)}</span>`).join(' ')}。系统保留上次成功数据并标记陈旧，不生成模拟值。</p></div></div>`:''}`;
};

/* 10 外汇与利率 */
V.fx = async host => {
  const m=S.macro||(S.macro=await get(API.macro)); const p=m.parts||{}, e=p.ecb_fx||{}, fr=p.frankfurter||{}, tr=p.treasury||{}, f=(p.fred||{}).series||[];
  const ch=f.find(x=>x.id==='DEXCHUS'), d2=f.find(x=>x.id==='DGS2'), d10=f.find(x=>x.id==='DGS10'), ff=f.find(x=>x.id==='FEDFUNDS');
  host.innerHTML=`
  ${e.rates?`<div class="card">${cardHead('ECB 官方参考汇率',`每 1 EUR 兑 · ${esc(e.date)}`,'<span class="badge a">A 级官方</span>')}
    <div class="card-body"><div class="grid-4">${e.rates.map(r=>`<div class="stat"><div class="s-label">EUR / ${esc(r[0])}</div>
      <div class="s-val">${num(r[1],4)}</div><div class="s-meta">官方日度参考汇率</div></div>`).join('')}</div>
      <p class="plain-note">⚠️ 这是<b>央行官方参考汇率</b>，与银行间即期、零售换汇、CFD 报价口径不同，不可混用；约每工作日 16:00 CET 发布。</p>
      ${srcNote(['来源：ECB 欧洲央行 eurofxref-daily.xml','日更，非实时',`<a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">官方页 ↗</a>`])}</div></div>`:
    `<div class="card"><div class="card-body"><div class="plain-note">ECB 参考汇率暂无数据</div></div></div>`}

  <div class="grid-2" style="margin-top:14px">
    ${fr.rates?`<div class="card" style="margin:0">${cardHead('USD 基准多币种',`Frankfurter · ${esc(fr.date)}`,'<span class="badge b">B 级</span>')}
      <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>货币</th><th class="r">1 USD 兑</th></tr></thead><tbody>
      ${fr.rates.map(r=>`<tr><td class="nm">${esc(r[0])}</td><td class="r">${num(r[1],4)}</td></tr>`).join('')}</tbody></table></div>
      ${srcNote(['Frankfurter 开源 API，底层为 ECB 参考汇率','日更，非实时','<b>口径不同于银行间即期</b>'])}</div></div>`:''}
    <div class="card" style="margin:0">${cardHead('利率与汇率关键值','FRED / 美国财政部','<span class="badge a">A 级官方</span>')}
      <div class="card-body"><div class="grid-2">
        ${[['联邦基金利率',ff],['美国 2Y 国债',d2],['美国 10Y 国债',d10],['人民币/美元',ch]].filter(x=>x[1]).map(([n,x])=>
          `<div class="stat"><div class="s-label">${esc(n)}</div><div class="s-val">${num(x.value,2)}</div>
           <div class="s-meta">${esc(x.unit)} · 截至 ${esc(x.as_of)} · ${esc(x.frequency)}频</div>
           <div class="s-src">FRED ${esc(x.id)}</div></div>`).join('')}
        ${tr.date?`<div class="stat span-2"><div class="s-label">收益率曲线 10Y-2Y 期限利差</div>
          <div class="s-val ${cls(tr.spread_10y_2y)}">${num(tr.spread_10y_2y,2)} pct</div>
          <div class="s-meta">官方 ${esc(tr.date)} 收盘曲线；负值常被视为倒挂</div></div>`:''}
      </div>${srcNote(['FRED 官方统计值','美国财政部日度曲线','均为统计发布值，非实时'])}</div></div>
  </div>`;
};

/* 11 商品与期货 */
V.commodities = async host => {
  const q=await get(API.quotes); const arr=(q.items||[]).filter(x=>x.group==='大宗商品');
  host.innerHTML=`
  <div class="card">${cardHead('商品与期货','黄金 / 白银 / 原油 / 天然气 / 铜',
    '<span class="badge warn">延迟行情</span><span class="badge">连续期货合约</span>')}
    <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>合约</th><th>名称</th><th class="r">最新价</th><th class="r">涨跌幅</th><th>日内走势</th></tr></thead><tbody>
      ${arr.map(x=>`<tr><td class="sym">${esc(x.symbol)}</td><td class="nm">${esc(x.name)}</td>
        <td class="r">${num(x.price)}</td><td class="r ${cls(x.pct)}"><b>${sign(x.pct)}%</b></td>
        <td>${sparkSVG(x.spark,x.pct>=0)}</td></tr>`).join('')||'<tr><td colspan="5" class="plain-note">商品行情暂无数据</td></tr>'}
      </tbody></table></div>
      ${srcNote(['Yahoo Finance 连续期货报价（非官方，延迟）','CL=F/BZ=F 原油 · GC=F/SI=F 贵金属 · HG=F 铜 · NG=F 天然气','现货价与期货价不可混用'])}</div></div>

  <div class="card">${cardHead('期权链 / 隐含波动率 / 持仓报告','数据覆盖状态')}
    <div class="card-body">${emptyState({icon:'◌',title:'期权与 COT 持仓数据未接入',
      desc:'免费官方源目前没有可靠的期权链（IV / Put-Call / 行权价 / 持仓量）数据；CFTC COT Socrata 接口经当前代理 TLS SNI 不可达。系统按要求明确显示「未接入」，不虚构任何数值。',
      list:[{t:'已接入：商品期货连续合约延迟行情（Yahoo）',ok:true},{t:'已接入：EIA 能源官方评论 RSS（资讯视图）',ok:true},
        {t:'未接入：期权链、隐含波动率、Put/Call 比率'},{t:'未接入：CFTC COT 商业/非商业持仓（周频）'},{t:'说明：COT 是周频持仓报告，不是实时资金流'},
        {t:'替代方案：后续接入 CFTC 官网公开报表文件或授权供应商'}],
      cta:`<button class="btn primary" data-go="sources">查看数据源状态与缺口 →</button>`})}
    </div></div>`;
  host.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go));
};

/* 12 数字资产 */
V.crypto = async host => {
  const c=await get(API.crypto); S.crypto=c; const coins=c.coins||{};
  host.innerHTML=`
  <div class="card">${cardHead('数字资产 · 多交易所交叉验证','交易所官方公开接口 · 实时',
    `<span class="badge a">A 级官方接口</span><span class="badge">${Object.keys(coins).length} 个币种</span>`)}
    <div class="card-body">
      ${Object.keys(coins).length?Object.entries(coins).map(([k,v])=>`
        <div style="margin-bottom:18px"><div class="heat-title">${esc(k)} · ${v.exchanges} 家交易所报价 · 中位价 ${num(v.median,2)}</div>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>交易所</th><th>交易对</th><th class="r">最新价</th><th class="r">24h 涨跌</th><th class="r">24h 量</th></tr></thead><tbody>
        ${v.rows.map(r=>`<tr><td><b>${esc(r.exchange)}</b></td><td class="nm">${esc(r.pair)}</td>
          <td class="r">${num(r.price,2)}</td><td class="r ${cls(r.pct)}">${r.pct===null?'--':sign(r.pct)+'%'}</td>
          <td class="r" style="color:var(--txt3)">${num(r.volume,0)}</td></tr>`).join('')}
        </tbody></table></div>
        <div class="grid-3" style="margin-top:8px">
          <div class="stat"><div class="s-label">所间最大价差</div><div class="s-val">${num(v.spread_pct,4)}%</div><div class="s-meta">USDT 与 USD 计价差异属正常现象</div></div>
          <div class="stat"><div class="s-label">平均 24h 涨跌</div><div class="s-val ${cls(v.avg_pct)}">${v.avg_pct===null?'--':sign(v.avg_pct)+'%'}</div><div class="s-meta">多所口径平均</div></div>
          <div class="stat"><div class="s-label">数据状态</div><div class="s-val" style="font-size:14px">${c.stale?'陈旧缓存':'实时'}</div><div class="s-meta">${hhmm(c.updated)} 采集</div></div>
        </div></div>`).join(''):'<div class="plain-note">交易所接口本次全部无数据，不补模拟价格。</div>'}
      ${srcNote(['来源：Binance / Coinbase Exchange / Kraken / OKX 官方公开 ticker','实时（秒级请求）','多所交叉验证：价差非错误数据','交易对 USDT/USD 计价不同，不可直接等同'])}
    </div></div>`;
};

/* 13/14 诚实空态：资金流、ETF */
V.flows = async host => {
  const q=await get(API.quotes); const cells=(q.items||[]).filter(x=>x.pct!==null);
  const up=cells.filter(x=>x.pct>0).length, dn=cells.filter(x=>x.pct<0).length;
  host.innerHTML=`<div class="card">${cardHead('全球资金流向','真实覆盖状态')}
    <div class="card-body">${emptyState({icon:'≈',title:'资金流数据未接入（不把成交额冒充资金流）',
      desc:'V2.0 明确要求：ETF 资金流、成交额、持仓变化、资金费率是不同口径，不能混为一谈。当前免费源未提供可靠的净流入/流出数据，因此本页不展示任何资金流数字。',
      list:[{t:'未接入：ETF 申赎/净流入、个股主力资金净流入'},{t:'未接入：CFTC COT 持仓变化（周频报告，非实时）'},{t:'未接入：交易所资金费率、永续持仓量、清算数据'},
        {t:'说明：成交额 ≠ 资金净流入；讨论热度 ≠ 资金流'},{t:'已接入：全市场涨跌幅分布（下方为真实市场广度，非资金流）',ok:true}],
      cta:`<button class="btn primary" data-go="sources">查看数据源缺口 →</button><button class="btn" data-go="heatmap">看市场涨跌热力图 →</button>`})}
      <div class="grid-3" style="margin-top:14px">
        <div class="stat"><div class="s-label">上涨标的</div><div class="s-val up">${up}</div><div class="s-meta">真实行情统计</div></div>
        <div class="stat"><div class="s-label">下跌标的</div><div class="s-val down">${dn}</div><div class="s-meta">真实行情统计</div></div>
        <div class="stat"><div class="s-label">覆盖率</div><div class="s-val">${cells.length}</div><div class="s-meta">当前接入标的数</div></div>
      </div>${srcNote(['以上为<b>市场广度</b>（涨跌家数），不是资金流','Yahoo 延迟行情'])}</div></div>`;
  host.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go));
};
V.etf = async host => {
  host.innerHTML=`<div class="card">${cardHead('全球基金与 ETF','真实覆盖状态')}
    <div class="card-body">${emptyState({icon:'▣',title:'ETF 净值与持仓数据未接入',
      desc:'ETF 的前十大持仓、行业/国家分布、费率、资产规模、净值需要基金公司披露或供应商授权数据。当前免费源未提供可靠数据，页面按规范显示「暂无数据」，不虚构净值或持仓。',
      list:[{t:'未接入：ETF 基本资料、净值、费率、规模'},{t:'未接入：前十大持仓、行业分布、国家分布'},{t:'未接入：ETF 历史表现与资金流'},
        {t:'可获取：部分 ETF 的延迟市价（见「全球行情」）',ok:true},{t:'接入路径：基金公司公开披露文件 / Twelve Data / 授权供应商'},],
      cta:`<button class="btn primary" data-go="sources">查看数据源与接入评估 →</button><button class="btn" data-go="quotes">看已有行情 →</button>`})}
    </div>${srcNote(['未接入模块明确标注，不伪装成已完成'])}</div>`;
  host.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go));
};

/* 15 公司研究 SEC */
V.research = async host => {
  host.innerHTML=`<div class="card">${cardHead('公司研究 · SEC EDGAR','美股申报公司 · XBRL 真实财务','<span class="badge a">A 级官方</span>')}
    <div class="card-body">
      <div class="form-row" style="margin-bottom:12px">
        <input class="inp" id="secSym" placeholder="输入美股代码，如 AAPL / NVDA / MSFT / TSLA" value="AAPL" style="flex:1;min-width:200px">
        <button class="btn primary" id="secGo">查询申报与财务</button>
        <span class="badge">覆盖约 10,414 家在美申报公司</span>
      </div>
      <p class="plain-note" style="margin:0 0 10px">仅覆盖在 SEC 申报的公司（<b>不含 A 股 / 港股</b>）。财务数值取自 XBRL 公司事实的<b>原始申报值</b>，未经复权或口径调整；不同公司标签可能不同，请结合原文申报核验。</p>
      <div id="secOut">${loading('输入代码后查询 SEC 官方数据…')}</div>
    </div>${srcNote(['来源：SEC EDGAR submissions + companyfacts','申报披露即更新','仅原始申报事实，不构成估值或买卖建议'])}</div>
  <div class="card">${cardHead('关于「AI 股票评分推荐」','为什么本系统暂不给出评分')}
    <div class="card-body"><p class="plain-note" style="margin:0">评分模型需要估值（PE/PB/PS）、成长性、行业景气度、资金表现等<b>结构化数据</b>。当前仅接入 SEC 原始财务与延迟行情，缺少可靠的估值与行业数据源。按 V2.0「禁止无数据生成结论」的要求，评分模块显示为未接入，不输出虚构分数或目标价。<button class="btn" data-go="scoring" style="margin-left:8px">查看评分缺口 →</button></p></div></div>`;
  host.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go));
  const run=async()=>{ const sym=($('secSym').value||'').trim().toUpperCase(); if(!sym)return;
    $('secOut').innerHTML=loading('正在读取 SEC 官方申报数据…');
    try{ const d=await get(API.sec+'?symbol='+encodeURIComponent(sym)); S.sec=d; renderSec(d); }catch(e){ $('secOut').innerHTML=`<div class="plain-note">查询失败：${esc(e.message)}</div>`; } };
  $('secGo').onclick=run; $('secSym').onkeydown=e=>{if(e.key==='Enter')run();};
  run();
};
function renderSec(d){
  const el=$('secOut'); if(!el)return;
  if(d.error){ el.innerHTML=emptyState({icon:'⌕',title:'未找到该公司',desc:esc(d.error),
    list:[{t:`SEC 代码表覆盖约 ${d.universe||'—'} 家在美申报公司`},{t:'A 股 / 港股需接入交易所或授权数据源'},{t:'本系统不会编造公司财务数据'}],
    cta:`<button class="btn primary" data-go="sources">查看数据源缺口 →</button>`});
    el.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go)); return; }
  el.innerHTML=`<div class="grid-2" style="margin-bottom:12px">
    <div class="stat"><div class="s-label">公司</div><div class="s-val" style="font-size:17px">${esc(d.company)}</div>
      <div class="s-meta">${esc(d.symbol)} · CIK ${esc(d.cik)} · ${esc(d.sic||'')}</div></div>
    <div class="stat"><div class="s-label">数据来源</div><div class="s-val" style="font-size:14px">SEC EDGAR</div>
      <div class="s-meta">申报 ${esc(String((d.filings||[]).length))} 条 · 财务事实 ${esc(String((d.facts||[]).length))} 项 · 截至 ${esc(d.facts_as_of||'')}</div>
      <div class="s-src"><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">SEC 公司页 ↗</a></div></div></div>
    <div class="grid-2"><div class="chart-box"><h4>关键财务事实（XBRL 原始申报值）</h4><div class="cb-sub">${esc(d.facts_note||'')}</div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>指标</th><th class="r">数值</th><th class="r">期间</th></tr></thead><tbody>
      ${(d.facts||[]).map(f=>`<tr><td class="nm" title="${esc(f.label)}">${esc(f.label.length>22?f.label.slice(0,22)+'…':f.label)}</td>
        <td class="r">${num(f.value,0)}</td><td class="r" style="color:var(--txt3)">${esc(f.end)}</td></tr>`).join('')||'<tr><td colspan="3">暂无财务事实</td></tr>'}
      </tbody></table></div></div>
      <div class="chart-box"><h4>最近申报文件</h4><div class="cb-sub">可点开 SEC 官方原文</div>
      ${(d.filings||[]).map(f=>`<div style="font-size:10.5px;padding:5px 0;border-bottom:1px dashed var(--line)">
        <span class="badge a">${esc(f.form)}</span> <span style="color:var(--txt3);font-family:var(--mono)">${esc(f.date)}</span>
        ${f.link?`<a href="${esc(f.link)}" target="_blank" rel="noopener noreferrer" style="color:var(--cyan);margin-left:6px">原文 ↗</a>`:''}</div>`).join('')||'<div class="plain-note">暂无申报记录</div>'}</div></div>`;
}

/* 16 评分空态 */
V.scoring = async host => {
  const st=await get(API.sourceStatus); const planned=st.sources.filter(s=>s.status==='planned');
  host.innerHTML=`<div class="card">${cardHead('AI 股票推荐评分','模型与数据缺口如实展示')}
    <div class="card-body">${emptyState({icon:'★',title:'评分系统未启用：缺少结构化基本面数据',
      desc:'V2.0 要求评分必须说明模型、数据来源、数据日期与权重，并禁止在无数据情况下生成买入价、目标价或收益承诺。当前免费源无法覆盖全部评分维度，因此不输出任何虚构分数。',
      list:[{t:'已具备：SEC XBRL 原始财务（营收/净利/资产/负债/EPS）',ok:true},{t:'已具备：延迟行情与近期新闻',ok:true},
        {t:'缺失：PE / PB / PS 等估值指标与历史分位'},{t:'缺失：行业景气度、分析师预期、机构持仓'},{t:'缺失：A 股 / 港股财务与全市场基本面'},{t:'缺失：真实资金流与成交量异动数据'},
        {t:'接入路径：' + planned.map(p=>p.name).slice(0,4).join(' / ') + '（需用户提供免费 Key 并实测覆盖范围）'}],
      cta:`<button class="btn primary" data-go="research">查看已接入的 SEC 真实财务 →</button><button class="btn" data-go="sources">数据源缺口清单 →</button>`})}
    </div>${srcNote(['不做无数据评分','不输出目标价/收益承诺','模型一旦启用需公开权重与数据日期'])}</div>`;
  host.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go));
};

/* 17 AI 工作台 */
V.ai = async host => {
  const [d,st]=await Promise.all([get(API.dashboard),get(API.sourceStatus)]);
  const presets=[
    {t:'全球市场问答',q:'用大白话总结当前全球市场的主要动向，只能引用站内数据，并说明数据口径'},
    {t:'宏观经济研究',q:'根据站内 FRED 与世界银行数据，说明当前美国失业率、CPI、联邦基金利率与美债曲线的最新值和统计截止期'},
    {t:'新闻事件分析',q:'归纳站内最新重大资讯中已确认的事实，不要推测未发生的事，区分事实与解读'},
    {t:'资产对比',q:'对比站内 BTC 在各交易所的报价与价差，说明计价口径差异，不要给买卖建议'},
    {t:'风险分析',q:'基于站内数据指出当前值得留意的风险，同时给出反面证据与数据局限'},
    {t:'数据源核验',q:'站内哪些数据是可实时使用的、哪些是延迟或统计发布值？哪些模块尚未接入？'},
  ];
  host.innerHTML=`
  <div class="hero" style="padding:16px 18px"><div class="hero-top"><div>
    <div class="hero-eyebrow"><span class="pulse"></span> AI RESEARCH WORKBENCH</div>
    <h2 style="font-size:19px">AI 金融工作台</h2>
    <p>AI 回答会读取 <b>GFIC 站内真实数据</b>（资讯 / 行情 / 宏观 / 加密），而非只凭模型自身知识。回答须区分已验证事实、常识解释与个人观点，并标注来源与口径。</p>
  </div></div></div>
  <div class="card">${cardHead('当前可调用的站内数据','真实接入状态')}
    <div class="card-body"><div class="grid-4">
      <div class="stat"><div class="s-label">资讯</div><div class="s-val">${d.total}</div><div class="s-meta">去重后 · P1 官方 ${d.p1} 条</div></div>
      <div class="stat"><div class="s-label">行情标的</div><div class="s-val">${d.quote_count}</div><div class="s-meta">延迟 15–20 分钟</div></div>
      <div class="stat"><div class="s-label">官方宏观分类</div><div class="s-val">${Object.keys(d.macro||{}).length}</div><div class="s-meta">FRED / WB / ECB / 财政部等</div></div>
      <div class="stat"><div class="s-label">可用数据源</div><div class="s-val">${st.summary.live}</div><div class="s-meta">A 级官方 ${st.summary.grade_a} 个 · 成本 ¥0</div></div>
    </div></div></div>
  <div class="card">${cardHead('研究任务','点击即向 AI 发起（使用右侧助手，结果在那里展示）')}
    <div class="card-body"><div class="grid-3">${presets.map(p=>`<button class="chart-box" data-preset="${esc(p.q)}" style="text-align:left;cursor:pointer">
      <h4 style="color:var(--cyan)">${esc(p.t)}</h4><div class="cb-sub" style="margin:0">${esc(p.q)}</div></button>`).join('')}</div>
      <p class="plain-note">AI 由内网 freellmapi 提供（OpenAI 兼容），密钥仅存服务端、不下发浏览器。上游不稳定时系统会重试并如实报错，不会编造答案。</p>
    </div></div>
  <div class="card">${cardHead('AI 事实核验口径','每个结论按四类区分')}
    <div class="card-body"><div class="grid-4">
      <div class="stat"><div class="s-label">① 已验证事实</div><div class="s-val" style="font-size:13px">站内真实数据</div><div class="s-meta">带来源、时间与口径</div></div>
      <div class="stat"><div class="s-label">② 常识解释</div><div class="s-val" style="font-size:13px">公开金融常识</div><div class="s-meta">不作为事实引用</div></div>
      <div class="stat"><div class="s-label">③ AI 推断</div><div class="s-val" style="font-size:13px">需标注不确定</div><div class="s-meta">不得冒充已发生事实</div></div>
      <div class="stat"><div class="s-label">④ 未接入</div><div class="s-val" style="font-size:13px">明确说没有</div><div class="s-meta">期权链/ETF持仓/资金流等</div></div>
    </div></div></div>`;
  host.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{ask(b.dataset.preset);window.scrollTo({top:0,behavior:'smooth'});toast('已发起 AI 研究，回答见右侧助手');});
};

/* 18 回测成绩单 */
V.backtest = async host => {
  host.innerHTML=`<div class="card">${cardHead('AI 历史回测与预测成绩单','真实记录状态')}
    <div class="card-body">${emptyState({icon:'◷',title:'暂无历史 AI 观点记录',
      desc:'成绩单只统计真实生成过、且带数据截止时间的 AI 观点，并同时展示成功与失败样本以防前视偏差。系统刚上线，尚未积累历史观点，因此本页为空，不展示任何虚构命中率或回测曲线。',
      list:[{t:'需要：预测生成时间、使用数据截止时间、标的代码、方向与周期',},{t:'需要：预测逻辑、预期条件、实际结果、最大有利/不利变动'},
        {t:'需要：基准对比、回撤、样本数与命中率（含失败样本）'},{t:'已具备：真实行情与宏观数据的落盘缓存能力',ok:true},
        {t:'后续：在 AI 工作台生成观点时自动落库，再按周期回放计算成绩'}],
      cta:`<button class="btn primary" data-go="ai">前往 AI 工作台 →</button><button class="btn" data-go="sources">数据持久化状态 →</button>`})}
    </div>${srcNote(['不展示只含成功案例的成绩单','防止未来数据泄漏与前视偏差'])}</div>`;
  host.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>switchView(b.dataset.go));
};

/* 19 自选股与组合 */
V.watchlist = async host => {
  const [w,q]=await Promise.all([get(API.watchlist),get(API.quotes)]); S.watchlist=w;
  const qmap={}; (q.items||[]).forEach(x=>qmap[x.symbol]=x);
  const items=w.items||[], pf=w.portfolio||[];
  const totalCost=pf.reduce((s,p)=>s+(Number(p.cost)||0)*(Number(p.qty)||0),0);
  const totalVal=pf.reduce((s,p)=>s+(qmap[p.symbol]?qmap[p.symbol].price*(Number(p.qty)||0):0),0);
  host.innerHTML=`
  <div class="card">${cardHead('自选股与模拟组合','手动录入 · 本地持久化 · 不接真实交易账户')}
    <div class="card-body">
      <div class="form-row"><input class="inp" id="wlSym" placeholder="标的代码（须与行情源一致，如 AAPL / ^GSPC / BTC-USD）" style="flex:2;min-width:190px">
        <input class="inp" id="wlName" placeholder="备注名称（可选）"><button class="btn primary" id="wlAdd">加入自选</button></div>
      <div class="pill-list">${items.length?items.map((x,i)=>`<span class="pill"><b>${esc(x.symbol)}</b>${esc(x.name||'')}
        ${qmap[x.symbol]?`<span class="${cls(qmap[x.symbol].pct)}">${num(qmap[x.symbol].price)} ${sign(qmap[x.symbol].pct)}%</span>`:'<span class="badge warn">暂无行情</span>'}
        <button data-del="${i}" title="删除">✕</button></span>`).join(''):'<span class="plain-note">暂无自选，添加一个试试</span>'}</div>
      ${srcNote(['行情取自 Yahoo 延迟接口','未匹配到行情的标的显示「暂无行情」，不生成模拟价格'])}
    </div></div>
  <div class="card">${cardHead('模拟持仓','浮动盈亏按真实行情计算 · 仅研究用途')}
    <div class="card-body">
      <div class="form-row"><input class="inp" id="pfSym" placeholder="代码" style="max-width:130px"><input class="inp" id="pfCost" placeholder="成本价" type="number" step="0.01" style="max-width:110px">
        <input class="inp" id="pfQty" placeholder="数量" type="number" step="1" style="max-width:100px"><button class="btn primary" id="pfAdd">录入持仓</button></div>
      <div class="grid-3" style="margin:12px 0">
        <div class="stat"><div class="s-label">持仓成本</div><div class="s-val">${num(totalCost,2)}</div><div class="s-meta">手动录入值</div></div>
        <div class="stat"><div class="s-label">当前市值</div><div class="s-val">${num(totalVal,2)}</div><div class="s-meta">按延迟行情估算</div></div>
        <div class="stat"><div class="s-label">浮动盈亏</div><div class="s-val ${cls(totalVal-totalCost)}">${num(totalVal-totalCost,2)}</div><div class="s-meta">${totalCost?sign((totalVal-totalCost)/totalCost*100)+'%':'--'}</div></div>
      </div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>代码</th><th class="r">成本</th><th class="r">数量</th><th class="r">现价</th><th class="r">市值</th><th class="r">盈亏</th><th></th></tr></thead><tbody>
        ${pf.map((p,i)=>{const qq=qmap[p.symbol], price=qq?qq.price:null, mv=price?price*p.qty:null, pl=mv!==null?mv-p.cost*p.qty:null;
          return `<tr><td class="sym">${esc(p.symbol)}</td><td class="r">${num(p.cost)}</td><td class="r">${num(p.qty,0)}</td>
          <td class="r">${price===null?'暂无行情':num(price)}</td><td class="r">${mv===null?'--':num(mv)}</td>
          <td class="r ${cls(pl)}">${pl===null?'--':num(pl)}</td><td><button class="mini" data-pfdel="${i}">删除</button></td></tr>`;}).join('')||'<tr><td colspan="7" class="plain-note">暂无模拟持仓</td></tr>'}
      </tbody></table></div>
      <p class="plain-note">不同市场币种未做汇率换算；成本与数量由用户手动录入，系统不连接券商、不自动下单。</p>
    </div>${srcNote(['数据持久化于服务端 data/watchlist.json','容器重启后不丢失','行情延迟，盈亏仅供研究参考'])}</div>`;
  const save=async data=>{ const r=await post(API.watchlistSave,{data}); S.watchlist=r.data; toast(r.ok?'已保存':'保存失败'); mount(); };
  $('wlAdd').onclick=()=>{const s=$('wlSym').value.trim().toUpperCase(); if(!s)return toast('请输入标的代码');
    const d=JSON.parse(JSON.stringify(S.watchlist)); d.items=d.items||[]; if(d.items.some(x=>x.symbol===s))return toast('已在自选中');
    d.items.push({symbol:s,name:$('wlName').value.trim(),added:Date.now()}); save(d);};
  $('pfAdd').onclick=()=>{const s=$('pfSym').value.trim().toUpperCase(),c=Number($('pfCost').value),q2=Number($('pfQty').value);
    if(!s||!isFinite(c)||!isFinite(q2)||c<=0||q2<=0)return toast('请完整填写代码 / 成本价 / 数量');
    const d=JSON.parse(JSON.stringify(S.watchlist)); d.portfolio=d.portfolio||[]; d.portfolio.push({symbol:s,cost:c,qty:q2}); save(d);};
  host.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{const d=JSON.parse(JSON.stringify(S.watchlist));d.items.splice(Number(b.dataset.del),1);save(d);});
  host.querySelectorAll('[data-pfdel]').forEach(b=>b.onclick=()=>{const d=JSON.parse(JSON.stringify(S.watchlist));d.portfolio.splice(Number(b.dataset.pfdel),1);save(d);});
};

/* 20 风险预警 */
V.alerts = async host => {
  const [a,q]=await Promise.all([get(API.alerts),get(API.quotes)]); S.alerts=a;
  const syms=(q.items||[]).map(x=>x.symbol);
  host.innerHTML=`
  <div class="card">${cardHead('全球风险预警','基于真实行情的站内提醒')}
    <div class="card-body">
      <div class="form-row">
        <select class="sel" id="alSym">${syms.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('')}</select>
        <select class="sel" id="alType"><option value="above">价格突破 ↑</option><option value="below">价格跌破 ↓</option><option value="pct_up">涨幅达到 %</option><option value="pct_down">跌幅达到 %</option></select>
        <input class="inp" id="alTh" placeholder="阈值" type="number" step="0.01" style="max-width:110px">
        <button class="btn primary" id="alAdd">添加规则</button>
        <button class="btn" id="alCheck">立即检查</button>
      </div>
      <p class="plain-note">预警基于 <b>Yahoo 延迟行情</b> 触发，仅作站内提醒，不构成交易指令；同一规则 30 分钟内不重复提醒。</p>
      <div class="tbl-wrap" style="margin-top:10px"><table class="tbl"><thead><tr><th>标的</th><th>条件</th><th class="r">阈值</th><th class="r">状态</th><th></th></tr></thead><tbody>
        ${(a.rules||[]).map((r,i)=>`<tr><td class="sym">${esc(r.symbol)}</td><td class="nm">${{above:'价格突破',below:'价格跌破',pct_up:'涨幅达到',pct_down:'跌幅达到'}[r.type]||r.type}</td>
          <td class="r">${num(r.threshold)}</td><td class="r"><span class="badge ${r.enabled===false?'':'ok'}">${r.enabled===false?'已停用':'启用'}</span></td>
          <td><button class="mini" data-aldel="${i}">删除</button></td></tr>`).join('')||'<tr><td colspan="5" class="plain-note">暂无预警规则</td></tr>'}
      </tbody></table></div>
    </div>${srcNote(['规则持久化于 data/alerts.json','后台每 45 秒检查一次','无行情数据时不会误触发'])}</div>
  <div class="card">${cardHead('通知记录','真实触发结果')}
    <div class="card-body"><div id="alNotif">${(a.notifications||[]).length?a.notifications.map(n=>
      `<div class="notif"><time>${dateCN(n.time)}</time><span>${esc(n.message)} <span style="color:var(--txt3)">· ${esc(n.source||'')}</span></span></div>`).join(''):
      '<div class="plain-note">暂无触发记录。添加规则并等待行情满足条件后会出现在这里（不会用模拟触发填充）。</div>'}</div></div></div>
  <div class="card">${cardHead('尚未接入的预警类型','真实覆盖状态')}
    <div class="card-body"><p class="plain-note">当前仅支持<b>价格 / 涨跌幅</b>预警。以下类型因缺少对应数据源未接入，不提供假按钮：成交量异动、波动率异常、财报发布日历、央行决议日历、组合风险敞口、重大地缘事件自动识别、Telegram 推送。</p></div></div>`;
  const save=async d=>{const r=await post(API.alertsSave,{data:d});S.alerts=r.data;toast(r.ok?'已保存':'保存失败');mount();};
  $('alAdd').onclick=()=>{const th=Number($('alTh').value); if(!isFinite(th)||th===0)return toast('请填写有效阈值');
    const d=JSON.parse(JSON.stringify(S.alerts)); d.rules=d.rules||[];
    d.rules.push({symbol:$('alSym').value,type:$('alType').value,threshold:th,enabled:true});save(d);};
  host.querySelectorAll('[data-aldel]').forEach(b=>b.onclick=()=>{const d=JSON.parse(JSON.stringify(S.alerts));d.rules.splice(Number(b.dataset.aldel),1);save(d);});
  $('alCheck').onclick=async()=>{toast('正在按真实行情检查…');const r=await get(API.alertsCheck);
    $('alNotif').innerHTML=(r.notifications||[]).length?r.notifications.map(n=>
      `<div class="notif"><time>${dateCN(n.time)}</time><span>${esc(n.message)}</span></div>`).join(''):
      `<div class="plain-note">本次检查无规则命中（${r.rules} 条规则）。${esc(r.note||'')}</div>`;
    toast(`检查完成，新增 ${r.fired.length} 条提醒`); updateNotifyBadge(); };
};

/* 21 数据源管理 */
V.sources = async host => {
  const st=await get(API.sourceStatus); S.sources=st;
  const s=st.sources;
  const grades=['','A','B','C','D'], statuses=['','live','blocked','planned'];
  host.innerHTML=`
  <div class="hero" style="padding:15px 18px"><div class="hero-top"><div>
    <div class="hero-eyebrow"><span class="pulse"></span> DATA SOURCE REGISTRY</div>
    <h2 style="font-size:19px">数据源管理与成本评估</h2>
    <p>每个数据源的等级、覆盖范围、延迟、授权、成功率、最近成功/失败时间与费用均来自<b>真实请求记录</b>。可独立启停、单独探测；未接入的源如实标注原因与替代方案。</p></div></div>
    <div class="kpi-grid" style="margin-top:13px">
      <div class="kpi"><div class="kpi-top">注册数据源</div><div class="kpi-val">${st.summary.total}</div><div class="kpi-sub">A 级官方 ${st.summary.grade_a} 个</div></div>
      <div class="kpi"><div class="kpi-top">实测可用</div><div class="kpi-val" style="color:var(--down)">${st.summary.live}</div><div class="kpi-sub">已启用 ${st.summary.enabled} 个</div></div>
      <div class="kpi"><div class="kpi-top">不可用 / 未接入</div><div class="kpi-val" style="color:var(--gold)">${st.summary.blocked+st.summary.planned}</div><div class="kpi-sub">已标注原因与替代方案</div></div>
      <div class="kpi"><div class="kpi-top">月度成本</div><div class="kpi-val">¥0</div><div class="kpi-sub">全部免费公开源 · 无自动订阅</div></div>
    </div></div>
  <div class="card">${cardHead('数据源清单','独立启停 / 连接探测 / 授权与延迟说明',
    `<span class="badge">共 ${s.length} 个</span>`)}
    <div class="card-body">
      <div class="src-toolbar">
        <select class="sel" id="sGrade"><option value="">全部等级</option>${grades.slice(1).map(g=>`<option value="${g}" ${S.filter.grade===g?'selected':''}>${g} 级</option>`).join('')}</select>
        <select class="sel" id="sStatus"><option value="">全部状态</option><option value="live" ${S.filter.status==='live'?'selected':''}>已接入</option><option value="blocked" ${S.filter.status==='blocked'?'selected':''}>实测不可用</option><option value="planned" ${S.filter.status==='planned'?'selected':''}>未接入</option></select>
        <input class="inp" id="sKw" placeholder="搜索名称 / 供应商 / 覆盖范围" value="${esc(S.filter.kw)}" style="flex:1;min-width:170px">
        <button class="btn" id="sClear">清空</button>
        <button class="btn" id="sProbeAll">探测全部可用源</button>
      </div>
      <div id="probeSummary" class="plain-note"></div>
      <div class="src-grid" id="srcGrid"></div>
      ${srcNote(['A 级 = 交易所/政府/央行/监管','B = 成熟专业供应商','C = 公开媒体/非官方接口','D = 社区数据（不可单独作投资结论）',
                 '成功率与最近成功/失败时间由真实请求统计','免费接口达限额时降级为上次成功数据并标记陈旧'])}
    </div></div>`;
  const draw=()=>{const list=s.filter(x=>(!S.filter.grade||x.grade===S.filter.grade)&&(!S.filter.status||x.status===S.filter.status)
      &&(!S.filter.kw||[x.name,x.provider,x.coverage,x.note].join(' ').toLowerCase().includes(S.filter.kw.toLowerCase())));
    $('srcGrid').innerHTML=list.map(x=>`<div class="src-card ${x.status}" data-id="${esc(x.id)}">
      <div class="sc-top"><span class="badge ${x.grade.toLowerCase()}">${x.grade} 级</span>
        <b>${esc(x.name)}</b>
        <span class="badge ${x.status==='live'?'ok':(x.status==='blocked'?'err':'warn')}">${x.status==='live'?'已接入':(x.status==='blocked'?'不可用':'未接入')}</span>
        ${x.official?'<span class="badge">官方</span>':'<span class="badge c">非官方</span>'}</div>
      <div class="sc-provider">${esc(x.provider)} · ${esc(x.coverage)}</div>
      <div class="sc-kv">
        <span>数据延迟</span><span>${esc(x.latency||'—')}</span>
        <span>刷新周期</span><span>${x.refresh?Math.round(x.refresh/60)+' 分钟':'—'}</span>
        <span>授权 / 许可</span><span>${esc((x.license||'—').slice(0,30))}</span>
        <span>费用</span><span>${esc(x.cost)}</span>
        <span>请求 成功/失败</span><span>${x.ok} / ${x.fail}</span>
        <span>成功率</span><span>${x.success_rate===null?'—':x.success_rate+'%'}</span>
        <span>最近成功</span><span>${x.last_ok?dateCN(x.last_ok):'—'}</span>
        <span>最近失败</span><span>${x.last_fail?dateCN(x.last_fail):'—'}</span>
        <span>上次耗时</span><span>${x.last_ms?x.last_ms+' ms':'—'}</span>
        <span>状态</span><span>${x.stale?'<span style="color:var(--gold)">数据陈旧</span>':'正常'}</span>
      </div>
      ${x.last_error?`<div class="sc-note" style="color:var(--up)">最近错误：${esc(x.last_error)}</div>`:''}
      ${x.note?`<div class="sc-note">${esc(x.note)}</div>`:''}
      <div class="sc-actions">
        <button class="switch ${x.enabled&&x.status==='live'?'on':''}" data-toggle="${esc(x.id)}" title="启停该数据源" ${x.status!=='live'?'disabled style="opacity:.4;cursor:not-allowed"':''}></button>
        <span style="font-size:10px;color:var(--txt3)">${x.enabled&&x.status==='live'?'已启用':'已停用'}</span>
        <button class="btn" data-probe="${esc(x.id)}" style="margin-left:auto">连接探测</button>
        ${x.home?`<a class="btn" href="${esc(x.home)}" target="_blank" rel="noopener noreferrer">官网 ↗</a>`:''}
      </div><div class="probe-out" id="po-${esc(x.id)}" hidden></div>
    </div>`).join('')||'<div class="plain-note">没有符合条件的数据源</div>';
    $('srcGrid').querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{
      const id=b.dataset.toggle, cur=st.sources.find(y=>y.id===id), on=!(cur.enabled&&cur.status==='live');
      b.textContent=''; try{ const r=await post(API.sourceToggle,{id,enabled:on}); S.sources=r;
        const nx=r.sources.find(y=>y.id===id); cur.enabled=nx.enabled; b.classList.toggle('on',nx.enabled);
        b.nextElementSibling.textContent=nx.enabled?'已启用':'已停用'; toast(`已${nx.enabled?'启用':'停用'} ${nx.name}`);
      }catch(e){toast('操作失败：'+e.message);} });
    $('srcGrid').querySelectorAll('[data-probe]').forEach(b=>b.onclick=async()=>{
      const id=b.dataset.probe, out=$('po-'+id); out.hidden=false; out.textContent='正在发起真实请求…';
      try{const r=await post(API.sourceProbe,{id}); out.textContent=`${r.ok?'✓ 连接成功':'✕ 连接失败'} · ${r.ms||0} ms · ${r.bytes||0} B ${r.error?'· '+r.error:''} ${r.sample?'· '+r.sample.slice(0,50):''}`;
        out.style.color=r.ok?'var(--down)':'var(--up)';}catch(e){out.textContent='探测失败：'+e.message;} });
  };
  draw();
  $('sGrade').onchange=e=>{S.filter.grade=e.target.value;draw();};
  $('sStatus').onchange=e=>{S.filter.status=e.target.value;draw();};
  let tmr; $('sKw').oninput=e=>{clearTimeout(tmr);tmr=setTimeout(()=>{S.filter.kw=e.target.value.trim();draw();},300);};
  $('sClear').onclick=()=>{S.filter={grade:'',status:'',kw:''};$('sGrade').value='';$('sStatus').value='';$('sKw').value='';draw();};
  $('sProbeAll').onclick=async()=>{ const box=$('probeSummary'); const ids=s.filter(x=>x.status==='live'&&['fred','worldbank','eurostat','ecb_fx','frankfurter','treasury','fiscaldata','sec_edgar','binance','coinbase','kraken','okx','yahoo','gnews','boj'].includes(x.id));
    let ok=0,fail=0,done=0; box.textContent=`正在真实探测 ${ids.length} 个数据源…`;
    await Promise.all(ids.map(async x=>{ try{const r=await post(API.sourceProbe,{id:x.id}); r.ok?ok++:fail++;}catch(e){fail++;}
      done++; box.textContent=`探测进度 ${done}/${ids.length} · 成功 ${ok} · 失败 ${fail}`; }));
    box.textContent=`✓ 探测完成：${ok} 成功 / ${fail} 失败。结果来自真实网络请求，未使用模拟状态。`;
    toast('数据源探测完成'); };
};

/* 22 系统说明 */
V.about = async host => {
  const [st,status]=await Promise.all([get(API.sourceStatus),get(API.status)]);
  const s=st.sources;
  const planned=s.filter(x=>x.status==='planned'), blocked=s.filter(x=>x.status==='blocked');
  host.innerHTML=`
  <div class="hero" style="padding:16px 18px"><div class="hero-top"><div>
    <div class="hero-eyebrow"><span class="pulse"></span> SYSTEM / DELIVERY CHECKLIST</div>
    <h2 style="font-size:19px">GFIC 全球金融情报中心 v2.0</h2>
    <p>部署于飞牛 NAS Docker，端口固定 <b>6789</b>。采用<b>零第三方依赖的 Python 标准库单文件服务 + 可插拔数据源适配层</b>，
    已接入 ${st.summary.live} 个真实免费数据源（A 级官方 ${st.summary.grade_a} 个），月度成本 <b>¥0</b>。</p></div></div></div>
  <div class="grid-2" style="margin-top:14px">
    <div class="card" style="margin:0">${cardHead('已完成（真实可用）')}
      <div class="card-body"><ul class="empty-list" style="margin:0">
        ${[ '22 个独立模块视图、专业金融终端界面（暗/浅主题、响应式）',
            '统一数据源适配层：33 源注册 / 独立启停 / 真实成功率与耗时 / 连接探测',
            '官方宏观：FRED 10 序列、World Bank、Eurostat、美国财政部收益率曲线与 FiscalData',
            '官方汇率：ECB 29 币种参考汇率、Frankfurter USD 基准',
            'SEC EDGAR：10414 家公司代码表、申报文件、XBRL 原始财务事实',
            '数字资产：Binance / Coinbase / Kraken / OKX 四所实时交叉验证',
            '资讯：Google News 中英 17 主题 + 19 个直连 RSS，去重、分级、富化、多个可点链接',
            'AI 简报：编号溯源到原文；AI 助手读取站内真实数据并标注口径',
            '成功数据落盘缓存，容器重启不丢；失败保留上次数据并标记陈旧',
            '自选股 / 模拟组合 / 价格预警：真实持久化与真实行情触发',
          ].map(x=>`<li class="ok">${esc(x)}</li>`).join('')}
      </ul></div></div>
    <div class="card" style="margin:0">${cardHead('未完成 / 未接入（如实列出）')}
      <div class="card-body"><ul class="empty-list" style="margin:0">
        ${[ '未采用 PostgreSQL / Redis / FastAPI / React 多容器架构（当前零依赖单容器更稳，见下方说明）',
            '未接入实时交易所行情：当前行情为 Yahoo 非官方接口，延迟 15–20 分钟',
            '未接入期权链、隐含波动率、Put/Call、ETF 持仓与净值',
            '未接入资金净流入、CFTC COT 持仓、资金费率与清算数据',
            '未接入 A 股 / 港股财务全量、龙虎榜、融资融券、股东变化',
            '未接入 X / Telegram / YouTube 社交源（需平台 API 授权）',
            '未接入 AI 评分模型、目标价与回测成绩单（缺结构化基本面数据）',
            '未实现登录认证与 HTTPS 反向代理（局域网内部使用，后续可加）',
          ].map(x=>`<li>${esc(x)}</li>`).join('')}
      </ul></div></div>
  </div>
  <div class="card">${cardHead('架构取舍说明','为什么没有照搬 5 容器 + React + PostgreSQL')}
    <div class="card-body"><p class="plain-note" style="margin:0">
      V2.0 明确要求「不需要为了架构复杂而增加容器数量」「优先保证稳定性」「不要为了追求功能数量而牺牲稳定性」「不允许把未实现的按钮伪装成已完成」。
      因此本次在<b>已实机验证稳定的单容器</b>上做实质升级：把「可插拔供应商、统一数据标准、真实状态、持久化、降级、授权标注」这些架构目标落到适配层与 API，
      而不是先搭 5 个容器再留一堆空页面。后续若确需多实例、登录和全文检索，可在不改动前端的前提下把适配层数据写入 PostgreSQL。</p>
      ${srcNote([`容器：finance-radar（${esc(String(status.version||'GFIC 2.0'))}）`,'端口 6789','目录 /vol1/1000/docker/finance-radar/','数据卷 ./data 持久化'])}</div></div>
  <div class="card">${cardHead('数据源授权与使用限制')}
    <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>类别</th><th>来源</th><th>口径与限制</th></tr></thead><tbody>
      <tr><td><span class="badge a">A 级</span></td><td class="nm">FRED / 美国财政部 / World Bank / Eurostat / ECB / SEC / 美联储 / EIA / WTO / BOJ</td><td class="nm">官方公开数据；个人内部展示；宏观为统计发布值，不是实时行情</td></tr>
      <tr><td><span class="badge a">A 级</span></td><td class="nm">Binance / Coinbase / Kraken / OKX 公开 ticker</td><td class="nm">交易所官方接口；实时；遵守交易所接口条款与所在地规则</td></tr>
      <tr><td><span class="badge b">B 级</span></td><td class="nm">Frankfurter</td><td class="nm">基于 ECB 参考汇率的开源封装，日更，非银行间即期报价</td></tr>
      <tr><td><span class="badge c">C 级</span></td><td class="nm">Yahoo Finance / Google News / 媒体 RSS</td><td class="nm"><b>非官方</b>；行情延迟；新闻仅存标题/摘要/链接，不复制全文、不绕过付费墙</td></tr>
      <tr><td><span class="badge d">D 级</span></td><td class="nm">Reddit r/stocks</td><td class="nm">社区数据，未经核实，不得单独作为重大投资结论依据</td></tr>
    </tbody></table></div>
    <p class="plain-note">未接入源：${blocked.concat(planned).map(x=>`<span class="badge warn">${esc(x.name)}</span>`).join(' ')}。均已在「数据源管理」标注原因与替代方案。</p></div></div>
  <div class="card">${cardHead('风险声明')}
    <div class="card-body"><p class="plain-note" style="margin:0">本平台仅供个人研究，<b>不构成投资建议</b>。免费行情存在 15–20 分钟延迟，不可用于下单；宏观数据是统计发布值；社交讨论量不等于真实资金流；AI 输出可能存在误差，重要结论请点击原文与官方来源核验。系统不会用模拟行情、随机价格或虚构新闻填充任何真实金融页面。</p></div></div>`;
};

/* ---------------- 全局组件 ---------------- */
function renderClocks(){
  const defs=[['纽约','America/New_York',9.5,16],['伦敦','Europe/London',8,16.5],['上海','Asia/Shanghai',9.5,15],['香港','Asia/Hong_Kong',9.5,16],['东京','Asia/Tokyo',9,15]];
  const now=new Date();
  $('clocks').innerHTML=defs.map(([n,tz,o,c])=>{
    let h,mi; try{ const p=new Intl.DateTimeFormat('en-US',{timeZone:tz,hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(now);
      h=Number(p.find(x=>x.type==='hour').value); mi=Number(p.find(x=>x.type==='minute').value);}catch(e){h=now.getHours();mi=now.getMinutes();}
    const v=h+mi/60, wd=now.getUTCDay(), open=(wd>=1&&wd<=5&&v>=o&&v<c);
    return `<div class="mc ${open?'open':''}"><i></i><span class="mc-name">${n}</span><b>${String(h).padStart(2,'0')}:${String(mi).padStart(2,'0')}</b><span style="color:var(--txt3)">${open?'开盘':'休市'}</span></div>`;
  }).join('');
}
function tickClock(){ const n=new Date(); $('clockTime').textContent=n.toLocaleTimeString('zh-CN',{hour12:false});
  $('clockDate').textContent=n.toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit',weekday:'short'}); }
async function renderTicker(){
  try{ const q=await get(API.quotes); S.quotes=q.items||[];
    if(!S.quotes.length){ $('tickerTrack').innerHTML='<span class="ticker-idle">行情源暂无数据</span>'; return; }
    const pick=S.quotes.slice(0,26);
    const one=pick.map(x=>`<span class="tk"><b>${esc(x.name)}</b><span class="p">${num(x.price)}</span><span class="c ${cls(x.pct)}">${sign(x.pct)}%</span></span>`).join('');
    $('tickerTrack').innerHTML=one+one;
    $('quoteTime').textContent='更新 '+hhmm(q.updated);
  }catch(e){ $('tickerTrack').innerHTML='<span class="ticker-idle">行情暂不可用</span>'; }
}
async function renderMood(){
  try{ const m=S.markets||(S.markets=await get(API.markets)); const s=m.sentiment||{}, sc=s.score||0;
    $('gaugeVal').textContent=(sc>0?'+':'')+sc;
    const ratio=Math.max(0,Math.min(1,(sc+100)/200));
    $('gaugeArc').setAttribute('stroke-dasharray',`${(ratio*258).toFixed(1)} 258`);
    $('gaugeArc').setAttribute('stroke',sc>8?'var(--up)':(sc<-8?'var(--down)':'var(--cyan)'));
    const label=sc>25?'偏多':(sc>8?'略偏多':(sc>-8?'中性':(sc>-25?'略偏空':'偏空')));
    $('moodLabel').textContent=label; $('gaugeText').textContent=label;
    const tot=(s.pos||0)+(s.neg||0)||1;
    $('posBar').style.width=((s.pos||0)/tot*100)+'%'; $('negBar').style.width=((s.neg||0)/tot*100)+'%';
    $('posTxt').textContent=`偏多 ${s.pos||0} 条`; $('negTxt').textContent=`偏空 ${s.neg||0} 条`;
    $('topicBody').innerHTML=(m.topics||[]).slice(0,16).map(t=>`<button class="topic" data-topic="${esc(t.word)}">${esc(t.word)}<b>×${t.count}</b></button>`).join('')||'<span class="rb-sub">暂无热词</span>';
    $('topicBody').querySelectorAll('[data-topic]').forEach(b=>b.onclick=()=>{S.view='news';S.kw=b.dataset.topic;S.cat='全部';S.shown=20;switchView('news');});
  }catch(e){ $('moodLabel').textContent='暂无数据'; }
}
function briefHTML(txt,refs){
  const clean=String(txt||'').replace(/```[\s\S]*?```/g,'').replace(/\*\*/g,'').trim();
  const linkify=raw=>esc(raw).replace(/\[(\d{1,2})\]/g,(m,n)=>{
    const r=(refs||[]).find(x=>String(x.n)===n);
    return r&&r.link?`<a class="ref" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer" title="${esc(r.source)}：${esc(r.title)}">[${n}]</a>`:m;});
  const parts=clean.split(/(?=【[^】]+】)/).filter(Boolean); let h='';
  for(const p of parts){ const m=p.match(/^【([^】]+)】\s*([\s\S]*)$/);
    if(m)h+=`<div class="brief-sec"><h4>${esc(m[1])}</h4><p>${linkify(m[2].trim())}</p></div>`;
    else if(/今日关键词|^关键词/.test(p))h+=`<div class="brief-key">${esc(p.trim())}</div>`;
    else if(p.trim())h+=`<p class="brief-plain">${linkify(p.trim())}</p>`; }
  return h||`<div class="brief-plain">${linkify(clean)}</div>`;
}
async function loadBrief(regen){
  const el=$('briefBody'); if(regen)el.innerHTML=loading('AI 正在重新归纳站内资讯…');
  try{ const d=await get(API.brief+(regen?'?regen=1':''));
    if(d.status==='ok'&&d.text){ el.innerHTML=briefHTML(d.text,d.refs||[]);
      $('briefMeta').innerHTML=`<span>生成于 ${hhmm(d.updated)} · 句末编号可点开原文</span><span>AI 归纳，仅供辅助判断</span>`; }
    else el.innerHTML=`<div class="plain-note">${esc(d.err||'AI 简报尚未就绪')}。系统不会编造简报内容，可点「重生成」再试。</div>`;
  }catch(e){ el.innerHTML=`<div class="plain-note">简报读取失败：${esc(e.message)}</div>`; }
}
async function ask(q){
  const log=$('askLog'); if(!q)return;
  if(!/站内|数据|口径/.test(q)) q=q;
  log.insertAdjacentHTML('beforeend',`<div class="ask-msg q">▸ ${esc(q)}</div><div class="ask-msg a" id="askPending"><span class="spin" style="display:inline-block;vertical-align:-2px"></span> AI 正在读取站内真实数据…</div>`);
  log.scrollTop=log.scrollHeight;
  try{ const d=await post(API.ask,{q}); const p=$('askPending');
    if(p){p.id='';p.innerHTML=esc(String(d.answer||d.error||'暂无回答').replace(/\*\*/g,''));}
  }catch(e){ const p=$('askPending'); if(p){p.id='';p.textContent='AI 服务暂时不可用：'+e.message;} }
  log.scrollTop=log.scrollHeight;
}
async function updateNotifyBadge(){
  try{const a=await get(API.alerts); const n=(a.notifications||[]).length;
    const b=$('notifyBadge'); b.hidden=!n; b.textContent=n>99?'99+':n; S.alerts=a;}catch(e){}
}
async function refreshAll(){
  toast('正在刷新真实数据…');
  try{ await get(API.refresh+'?what=all'); S.macro=null; S.news=[]; S.markets=null; S.crypto=null;
    await Promise.all([renderTicker(),renderMood(),updateNotifyBadge()]); await mount(); await loadBrief(false);
    toast('已刷新：资讯 / 行情 / 宏观 / 数据源缓存'); }catch(e){ toast('刷新失败：'+e.message); }
}
function initSSE(){
  if(new URLSearchParams(location.search).has('nosse')) { $('livePill').classList.add('on');$('liveTxt').textContent='已连接'; return; }
  try{ const es=new EventSource(API.events);
    es.onmessage=ev=>{ try{const d=JSON.parse(ev.data);
      $('livePill').classList.add('on'); $('liveTxt').textContent='实时连接';
      if(d.news_count>(S.newsCount||0)&&S.newsCount){ $('newCount').textContent=d.news_count-S.newsCount; $('newBar').hidden=false; }
      S.newsCount=d.news_count||S.newsCount; }catch(e){} };
    es.onerror=()=>{$('livePill').classList.remove('on');$('liveTxt').textContent='重连中';};
  }catch(e){ $('liveTxt').textContent='轮询模式'; }
}
async function openSearch(){
  $('searchOverlay').hidden=false; $('globalSearch').focus(); $('searchResults').innerHTML='<div class="sp-hint">输入关键词开始检索站内真实数据</div>';
}
async function doSearch(kw){
  const box=$('searchResults'); if(!kw.trim()){box.innerHTML='<div class="sp-hint">输入关键词开始检索站内真实数据</div>';return;}
  box.innerHTML=loading('检索中…');
  try{ const [r,q]=await Promise.all([get(API.search+'?q='+encodeURIComponent(kw)),get(API.quotes)]);
    const hits=(q.items||[]).filter(x=>x.symbol.toLowerCase().includes(kw.toLowerCase())||(x.name||'').toLowerCase().includes(kw.toLowerCase()));
    box.innerHTML=`
      ${r.news.length?`<div class="sp-group">资讯 ${r.news.length} 条</div>`+r.news.slice(0,12).map(x=>
        `<a class="sp-item" href="${esc(x.link||'#')}" target="_blank" rel="noopener noreferrer">${esc(x.title)}<small>${esc(x.source||'')} · ${ago(x.published)} · ${esc(x.category||'')}</small></a>`).join(''):''}
      ${r.sources.length?`<div class="sp-group">权威信息源 ${r.sources.length} 个</div>`+r.sources.slice(0,10).map(x=>
        `<a class="sp-item" href="${esc(x.url||'#')}" target="_blank" rel="noopener noreferrer">${esc(x.name||x.title||'')}<small>${esc(x.cat||x.desc||'')} · ${esc(x.url||'')}</small></a>`).join(''):''}
      ${hits.length?`<div class="sp-group">行情标的 ${hits.length} 项</div>`+hits.slice(0,10).map(x=>
        `<a class="sp-item" href="https://finance.yahoo.com/quote/${encodeURIComponent(x.symbol)}" target="_blank" rel="noopener noreferrer">${esc(x.name)} (${esc(x.symbol)})<small>${num(x.price)} · <span class="${cls(x.pct)}">${sign(x.pct)}%</span> · 延迟行情</small></a>`).join(''):''}
      ${(!r.news.length&&!r.sources.length&&!hits.length)?'<div class="sp-hint">没有找到匹配内容（站内不使用模拟数据补位）</div>':''}`;
  }catch(e){box.innerHTML=`<div class="sp-hint">检索失败：${esc(e.message)}</div>`;}
}
function applyTheme(){
  const qp=new URLSearchParams(location.search);
  const q=qp.get('theme'); if(q==='light'||q==='dark') S.theme=q;
  document.documentElement.dataset.theme=S.theme; localStorage.setItem('gfic-theme',S.theme);
}

/* ---------------- 绑定 / 启动 ---------------- */
function bind(){
  $('btnTheme').onclick=()=>{S.theme=S.theme==='dark'?'light':'dark';applyTheme();toast('已切换'+(S.theme==='dark'?'暗色':'浅色')+'主题');};
  $('btnRefresh').onclick=refreshAll;
  $('btnSearch').onclick=openSearch;
  $('btnCloseSearch').onclick=()=>$('searchOverlay').hidden=true;
  $('searchOverlay').onclick=e=>{if(e.target.id==='searchOverlay')$('searchOverlay').hidden=true;};
  let st; $('globalSearch').oninput=e=>{clearTimeout(st);st=setTimeout(()=>doSearch(e.target.value),300);};
  $('btnNotify').onclick=()=>{ $('notifyOverlay').hidden=false; const a=S.alerts||{};
    $('notifyBody').innerHTML=(a.notifications||[]).length?a.notifications.map(n=>
      `<div class="notif"><time>${dateCN(n.time)}</time><span>${esc(n.message)}<br><span style="color:var(--txt3)">${esc(n.source||'')}</span></span></div>`).join(''):
      '<div class="plain-note">暂无预警通知。可在「全球风险预警」添加规则，命中真实行情后此处会显示。</div>'; };
  $('btnCloseNotify').onclick=()=>$('notifyOverlay').hidden=true;
  $('notifyOverlay').onclick=e=>{if(e.target.id==='notifyOverlay')$('notifyOverlay').hidden=true;};
  $('btnGoAlerts').onclick=()=>{$('notifyOverlay').hidden=true;switchView('alerts');};
  $('btnMob').onclick=()=>$('sidebar').classList.toggle('open');
  $('btnSide').onclick=()=>{const sb=$('sidebar');sb.classList.toggle('mini');
    document.querySelector('.app-shell').style.gridTemplateColumns=sb.classList.contains('mini')?'64px minmax(0,1fr)':'236px minmax(0,1fr)';
    document.querySelectorAll('.brand-text,.side-status,.nav-group,.nav-item .ni-txt,.nav-item .ni-tag,.side-foot').forEach(x=>x.style.display=sb.classList.contains('mini')?'none':'');};
  $('newBar').onclick=async()=>{$('newBar').hidden=true;S.news=[];await ensureNews();toast('已载入最新动态');if(S.view==='news'||S.view==='dashboard')mount();};
  $('btnRegenBrief').onclick=()=>loadBrief(true);
  $('btnCopyBrief').onclick=()=>{const t=$('briefBody').innerText; navigator.clipboard?.writeText(t).then(()=>toast('简报已复制')).catch(()=>toast('复制失败'));};
  $('btnAsk').onclick=()=>{const q=$('askText').value.trim();if(q){ask(q);$('askText').value='';}};
  $('askText').onkeydown=e=>{if(e.key==='Enter'){const q=e.target.value.trim();if(q){ask(q);e.target.value='';}}};
  $('askChips').onclick=e=>{const b=e.target.closest('button');if(b)ask(b.textContent.trim());};
  document.addEventListener('keydown',e=>{
    if(e.key==='/'&&!/INPUT|TEXTAREA/.test(document.activeElement.tagName)){e.preventDefault();openSearch();}
    if(e.key==='Escape'){$('searchOverlay').hidden=true;$('notifyOverlay').hidden=true;}
  });
  let lastScroll=0; window.addEventListener('scroll',()=>{
    if(S.view!=='news'||Date.now()-lastScroll<400)return;
    if(window.innerHeight+window.scrollY>=document.body.offsetHeight-500&&$('btnMore')){lastScroll=Date.now();$('btnMore').click();}
  });
  window.addEventListener('hashchange',()=>{const h=location.hash.slice(1);if(h&&h!==S.view)switchView(h);});
}
async function init(){
  applyTheme(); renderNav(); bind(); renderClocks(); tickClock();
  setInterval(tickClock,1000); setInterval(renderClocks,60000);
  renderTicker(); renderMood(); loadBrief(false); updateNotifyBadge(); initSSE();
  const h=location.hash.slice(1); if(h&&NAVMAP[h]){S.view=h;const m=NAVMAP[h];$('pageTitle').textContent=m.t;$('ptEyebrow').textContent=m.e;renderNav();}
  await mount();
}
init();
