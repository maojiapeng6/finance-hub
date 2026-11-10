/* ============================================================
   GFIC V2.1 · 投资决策驾驶舱 / AI 机会雷达 / 易懂模式 / 全站翻译 / 详情路由
   独立扩展层：不修改 v2.0 app.js，复用其 esc/num/get/post/toast/V/NAV/S 等全局。
   原则：所有数字来自站内真实 API；缺失数据显式标注，绝不用模拟值补位。
   ============================================================ */
(function () {
'use strict';

const A2 = {
  daily: '/api/daily/summary', opp: '/api/research/opportunities',
  leaders: '/api/research/leaders', quality: '/api/research/quality',
  stock: '/api/research/stock', track: '/api/research/track',
  detail: '/api/detail', dict: '/api/i18n/dict', glossary: '/api/i18n/glossary',
  priority: '/api/i18n/priority', terms: '/api/i18n/terms', stats: '/api/i18n/stats',
  translate: '/api/i18n/translate', transBatch: '/api/i18n/translate_batch'
};
const V21 = {
  lang: localStorage.getItem('gfic-lang') || 'zh-CN',
  easy: localStorage.getItem('gfic-easy') === '1',
  dict: {}, glossary: [], favorites: JSON.parse(localStorage.getItem('gfic-fav') || '[]'),
  daily: null, opp: null, leaders: null, quality: null, priorityDef: null,
  leaderPeriod: 'd1', leaderMarket: '全球市场', oppMarket: '全球市场', oppCycle: 'mid',
  translated: {}, transLang: '', lastDetail: '', charts: {}
};
window.V21 = V21;

/* ---------------- 通用 ---------------- */
/* app.js 的这些符号是「顶层 const」——在全局词法环境中跨脚本可见，
   但不会成为 window 属性，所以必须用裸标识符，不能用 window.xxx。
   switchView / mount / briefHTML 是顶层函数声明，才是真正的 window 属性。 */
const E = esc, N = num, SG = sign, CL = cls;
const t = k => (V21.dict && V21.dict[k]) || k;
const safe = s => E(String(s == null ? '' : s));
const dash = v => (v === null || v === undefined || v === '') ? '--' : v;
const pctHtml = v => `<span class="${CL(v)}">${v === null || v === undefined ? '--' : SG(v) + '%'}</span>`;
const discl = txt => `<div class="notice-box">⚠ ${safe(txt)}</div>`;
const srcNote = txt => `<div class="src-note"><span>${safe(txt)}</span></div>`;

function goDetail(type, id) { switchView('detail/' + type + '/' + encodeURIComponent(id)); }
function termLink(term, label) { return `<span class="term-link" data-term="${safe(term)}">${safe(label || term)}</span>`; }
function prioBadge(p, reason) {
  const k = String(p || 'P2').toLowerCase();
  return `<span class="prio-badge ${k}" data-prio="${safe(p)}" data-reason="${safe(reason || '')}" title="点击看等级定义">${safe(p)}</span>`;
}
function easyBlock(html) { return V21.easy ? `<div class="easy-explain">💡 <b>大白话：</b>${html}</div>` : ''; }

function bindClicks(root) {
  const host = root || document;
  host.querySelectorAll('[data-detail]').forEach(el => el.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    goDetail(el.dataset.detail, el.dataset.id);
  });
  host.querySelectorAll('[data-term]').forEach(el => el.onclick = e => {
    e.preventDefault(); e.stopPropagation(); openTerm(el.dataset.term);
  });
  host.querySelectorAll('[data-prio]').forEach(el => el.onclick = e => {
    e.preventDefault(); e.stopPropagation(); openPriority(el.dataset.prio, el.dataset.reason);
  });
  host.querySelectorAll('[data-go2]').forEach(el => el.onclick = e => {
    e.preventDefault(); e.stopPropagation(); switchView(el.dataset.go2);
  });
  host.querySelectorAll('[data-translate]').forEach(el => el.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    translateOne(el.dataset.translate, el.dataset.tid, el.closest('[data-tr-host]') || el.parentElement);
  });
}

/* ---------------- 弹窗：术语 / 等级 ---------------- */
async function openTerm(term) {
  const box = $('termBody'), ttl = $('termTitle');
  if (!box) return;
  $('termOverlay').hidden = false;
  ttl.textContent = '术语解释 · ' + term;
  box.innerHTML = loading('正在读取术语词典…');
  try {
    const d = await get(A2.glossary + '?term=' + encodeURIComponent(term));
    if (d.error) { box.innerHTML = `<p>${safe(d.error)}</p>`; return; }
    const fav = V21.favorites.includes(term);
    box.innerHTML = `
      <div class="vm-kv">
        <span>中文名称</span><b>${safe(d.zh)}</b>
        <span>英文</span><b>${safe(d.en)}</b>
        <span>所属领域</span><b>${safe(d.field)}</b>
      </div>
      <div class="vm-row"><h5>1. 通俗解释</h5><p>${safe(d.plain)}</p></div>
      <div class="vm-row"><h5>2. 指标作用</h5><p>${safe(d.use)}</p></div>
      <div class="vm-row"><h5>3. 数值高低通常代表什么</h5><p>偏高：${safe(d.high)}<br>偏低：${safe(d.low)}</p></div>
      <div class="vm-row"><h5>4. 对股票市场可能有什么影响</h5><p>${safe(d.impact)}</p></div>
      <div class="vm-row"><h5>5. 当前数值代表什么</h5><p>本术语${d.field === '估值' ? '的估值数据当前未接入（无免费 Key 接口），不显示虚构数值' : '若出现在页面数据中，会同时标注来源与统计截止期；请以详情页标注为准'}。</p></div>
      <div class="trans-tools"><button class="btn" id="btnFavTerm">${fav ? '★ 已收藏' : '☆ 收藏术语'}</button>
        <button class="btn" data-go2="glossary">打开完整词典 →</button></div>`;
    $('btnFavTerm').onclick = () => {
      V21.favorites = V21.favorites.includes(term) ? V21.favorites.filter(x => x !== term) : V21.favorites.concat(term);
      localStorage.setItem('gfic-fav', JSON.stringify(V21.favorites));
      $('termOverlay').hidden = true; toast(V21.favorites.includes(term) ? '已收藏术语' : '已取消收藏');
    };
    bindClicks(box);
  } catch (e) { box.innerHTML = `<p>读取失败：${safe(e.message)}</p>`; }
}

async function openPriority(level, reason) {
  const box = $('priorityBody'); if (!box) return;
  $('priorityOverlay').hidden = false; box.innerHTML = loading('正在读取等级规则…');
  try {
    const d = V21.priorityDef || (V21.priorityDef = await get(A2.priority));
    box.innerHTML = `
      <div class="notice-box">等级由明确的规则模型产生：<b>${safe(d.model)}</b>。${safe(d.note)}</div>
      ${Object.keys(d.levels).map(k => {
        const v = d.levels[k];
        return `<div class="vm-row"><h5>${k} · ${safe(v.name)} ${k === level ? '（本条）' : ''}</h5>
          <p>${safe(v.desc)}<br><b>判定规则：</b>${safe(v.rule)}<br><b>典型例子：</b>${safe((v.examples || []).join('、'))}</p></div>`;
      }).join('')}
      ${reason ? `<div class="vm-row"><h5>为什么这条被评为 ${safe(level)}</h5><p>${safe(reason)}</p></div>` : ''}`;
  } catch (e) { box.innerHTML = `<p>读取失败：${safe(e.message)}</p>`; }
}

/* ---------------- 国际化 / 翻译 ---------------- */
async function loadDict(lang) {
  try { V21.dict = await get(A2.dict + '?lang=' + encodeURIComponent(lang)); }
  catch (e) { V21.dict = {}; }
  applyI18n();
}
function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const v = V21.dict[el.dataset.i18n]; if (v) el.textContent = v;
  });
  document.documentElement.lang = V21.lang;
  const sel = $('langSel'); if (sel) sel.value = V21.lang;
  // 导航标题按词典切换（不改 v2.0 的 NAV 数据结构）
  NAV.forEach(g => g.items.forEach(i => {
    const k = 'v.' + i.id, v = V21.dict[k];
    if (v) i._t = v;
  }));
  try { renderNav(); } catch (e) { }
  const navMap = {}; NAV.forEach(g => g.items.forEach(i => navMap[i.id] = i));
  const m = navMap[S.view];
  if (m) $('pageTitle').textContent = m._t || m.t;
}
async function setLang(lang, silent) {
  V21.lang = lang; localStorage.setItem('gfic-lang', lang);
  await loadDict(lang);
  if (!silent) toast('已切换：' + (V21.dict._meta ? V21.dict._meta.name : lang) + '（固定文案为本地词典）');
  try { await mount(); await loadDaily(); } catch (e) { }
}
async function translateOne(text, tid, host) {
  if (!text) return;
  const lang = V21.lang === 'zh-CN' ? (V21.transLang || 'en') : V21.lang;
  const box = host && host.querySelector('[data-tr-out]');
  if (box) box.innerHTML = loading('正在翻译（结果会缓存）…');
  try {
    const d = await post(A2.translate, { text: text, lang: lang });
    V21.translated[tid] = d;
    const html = `<div class="bilingual">
      <div class="bl-label">原文 / ORIGINAL</div><div class="bl-orig">${safe(d.original)}</div>
      <div class="bl-label" style="margin-top:8px">译文 · ${safe(lang)}${d.cached ? ' · 缓存' : ''}</div>
      <div class="bl-trans">${safe(d.text)}</div>
      ${d.fallback ? `<div class="plain-note" style="color:var(--gold)">${safe(t('err.transFail'))}：${safe(d.reason || '')}</div>` : ''}
      ${d.preserved === false ? '<div class="plain-note" style="color:var(--gold)">译文未保留关键数字，已回退原文</div>' : ''}
      <div class="trans-tools"><button class="btn" data-retrans="${safe(tid)}">${safe(t('lbl.retranslate'))}</button>
        <a class="btn" href="#" data-orig="${safe(tid)}">${safe(t('lbl.original'))}</a></div></div>`;
    if (box) {
      box.innerHTML = html;
      box.querySelectorAll('[data-retrans]').forEach(b => b.onclick = () => post(A2.translate, { text: text, lang: lang, force: true }).then(r => { toast('已重新翻译'); V21.translated[tid] = r; box.querySelector('.bl-trans').textContent = r.text; }));
      box.querySelectorAll('[data-orig]').forEach(b => b.onclick = e => { e.preventDefault(); box.querySelector('.bl-orig').style.display = box.querySelector('.bl-orig').style.display === 'none' ? '' : 'none'; });
    }
  } catch (e) { if (box) box.innerHTML = `<p>翻译失败：${safe(e.message)}</p>`; }
}
function transTools(text, id) {
  return `<div class="trans-tools" data-tr-host>
    <button class="btn" data-translate="${safe(text)}" data-tid="${safe(id)}">${safe(t('lbl.translated'))} / 双语对照</button>
    <div data-tr-out></div></div>`;
}

/* ---------------- 右侧今日市场总结 ---------------- */
async function loadDaily() {
  const el = $('dailyBody'); if (!el) return;
  try {
    const d = V21.daily = await get(A2.daily);
    el.innerHTML = `
      <div class="daily-block"><h5>${safe(t('lbl.onesentence'))}</h5>
        <div class="daily-one">${safe(d.one_sentence)}</div></div>
      <div class="daily-block"><h5>${safe(t('lbl.threeEvents'))}</h5>
        ${(d.three_events || []).map(x => `<div class="daily-ev" data-detail="news" data-id="${safe(x.id)}">
          ${safe(x.title)}<small>${safe(x.source)} · ${dateCN(x.published)} · ${safe(x.impact)}
          ${x.assets && x.assets.length ? ' · 关联：' + safe(x.assets.join('、')) : ''}</small></div>`).join('') || '<div class="plain-note">暂无真实快讯</div>'}</div>
      <div class="daily-block"><h5>今日投资机会（研究筛选）</h5>
        ${(d.opportunities || []).map(x => `<div class="daily-ev" data-detail="stocks" data-id="${safe(x.symbol)}">
          <b>${safe(x.name)}</b> ${safe(x.symbol)} · ${safe(x.grade)} 级 · 综合分 ${dash(x.score)} · 置信度 ${dash(x.confidence)}
          <small>${safe((x.why || [])[0] || '')}</small></div>`).join('') || '<div class="plain-note">机会榜暂无足够真实数据，不凑数</div>'}</div>
      <div class="daily-block"><h5>${safe(t('lbl.riskToday'))}</h5>
        ${(d.risks || []).map(x => `<div class="daily-risk">${safe(x)}</div>`).join('')}</div>
      <div class="daily-block"><h5>${safe(t('lbl.temp'))} · 判断依据</h5>
        <div class="temp-pill">${safe(d.temperature.label)}</div>
        <div class="temp-note">${safe(d.temperature.basis)}<br>${safe(d.temperature.note)}</div></div>
      <div class="temp-note">${safe(d.disclaimer)}</div>`;
    bindClicks(el);
  } catch (e) { el.innerHTML = `<div class="plain-note">今日总结读取失败：${safe(e.message)}</div>`; }
}

/* ---------------- 卡片渲染 ---------------- */
function oppCard(x) {
  const g = x.score.grade, sc = x.score.composite, cf = x.score.confidence;
  return `<article class="opp-card g-${safe(g)}" data-detail="stocks" data-id="${safe(x.symbol)}">
    <div class="opp-top"><div>
      <div class="opp-name">${safe(x.name)}</div>
      <div class="opp-sym">${safe(x.symbol)} · ${safe(x.exchange)} · ${safe(x.market)}</div>
      <div class="opp-meta">${safe(x.sector)} · ${safe(x.currency)} · 更新 ${hhmm(x.data_updated)}</div>
    </div><div class="opp-score"><span class="grade-badge">${safe(g)}</span>
      <small>研究分 ${dash(sc)} / 置信度 ${dash(cf)}</small></div></div>
    <div class="opp-price"><b>${N(x.price)}</b>${pctHtml(x.change_pct)}<span class="tag">当日</span></div>
    <div class="opp-tags">${(x.types || []).map(t => `<span class="tag hot">${safe(t.type)}</span>`).join('')}
      <span class="tag warn">风险 ${safe(x.metrics.vol_annual !== null ? '波动率 ' + x.metrics.vol_annual + '%' : '数据缺失')}</span>
      <span class="tag">${safe(x.cycle.name)} ${safe(x.cycle.span)}</span></div>
    <div class="qa-box"><h5>${safe(t('lbl.why'))}</h5><ul>
      ${(x.why || []).map(w => `<li>${safe(w)}</li>`).join('') || '<li>暂无可核实理由</li>'}</ul></div>
    ${V21.easy ? easyBlock('研究分是把能拿到的真实数据（价格走势、量能、官方财报）按权重打分；缺的数据不算分，也不猜。' + (x.why[0] || '')) : ''}
    <div class="qa-box risk"><h5>${safe(t('lbl.caution'))}</h5><ul>
      ${(x.risks || []).slice(0, 3).map(w => `<li>${safe(w)}</li>`).join('')}</ul></div>
    <div class="qa-concl"><b>${safe(t('lbl.conclusion'))}：</b>${safe(x.conclusion)}</div>
    <div class="miss-note">⚠ ${safe(x.disclaimer)} · 缺失 ${x.score.missing.length} 个评分维度，置信度 ${cf}</div>
    <div class="opp-foot"><span>${safe(x.source)}</span><span>点击看完整研究详情 →</span></div>
  </article>`;
}

function marketOverview(m) {
  const groups = {};
  (m && m.quotes || []).forEach(x => (groups[x.group] = groups[x.group] || []).push(x));
  return `<div class="card">${cardHead(t('lbl.marketOverview') + ' · 全球市场', '首页只展示最重要数据', `<button class="btn" data-go2="quotes">${safe(t('lbl.viewall'))} →</button>`)}
    <div class="card-body"><div class="cockpit-3">
    ${Object.keys(groups).slice(0, 9).map(g => {
      const a = groups[g], avg = a.reduce((s, x) => s + (x.pct || 0), 0) / a.length;
      return `<div class="stat" data-detail="assets" data-id="${safe((a[0] || {}).symbol || '')}" style="cursor:pointer">
        <div class="s-label"><span>${safe(g)}</span><span>${a.length} 项</span></div>
        <div class="s-val ${CL(avg)}">${SG(avg)}%</div>
        <div class="s-meta">组均涨跌 · 点开看标的详情</div>
        <div class="s-src">Yahoo Finance · 延迟 15–20 分钟</div></div>`;
    }).join('')}</div>${srcNote('全部为真实延迟行情；不是实时行情，不可用于下单')}</div></div>`;
}

/* ---------------- 视图 1：投资决策驾驶舱（四屏） ---------------- */
V.dashboard = async host => {
  host.innerHTML = loading('正在读取真实市场数据…');
  let daily = {}, opp = {}, leaders = {}, quality = {}, mk = {};
  const rs = await Promise.allSettled([
    get(A2.daily), get(A2.opp), get(A2.leaders + '?period=d1'), get(A2.quality), get('/api/markets')
  ]);
  daily = rs[0].status === 'fulfilled' ? rs[0].value : {};
  opp = rs[1].status === 'fulfilled' ? rs[1].value : { items: [], missing_capabilities: [] };
  leaders = rs[2].status === 'fulfilled' ? rs[2].value : { items: [] };
  quality = rs[3].status === 'fulfilled' ? rs[3].value : { items: [] };
  mk = rs[4].status === 'fulfilled' ? rs[4].value : {};
  V21.daily = daily; V21.opp = opp; V21.leaders = leaders; V21.quality = quality;
  await loadDaily();
  const items = await (async () => { try { return (await get('/api/news?limit=12')).items || []; } catch (e) { return []; } })();

  host.innerHTML = `
  <!-- 第一屏：今日投资决策中心 -->
  <section class="screen" id="screen1">
    <div class="screen-head"><span class="screen-no">1</span><h2>${safe(t('lbl.opportunity'))} · AI 全球投资机会榜</h2>
      <span class="sh-sub">研究筛选结果，不是买卖指令</span></div>
    ${discl('历史表现不代表未来潜力；行情延迟 15–20 分钟；评分只在真实可得维度上计算，缺失维度不补分。')}
    <div class="cockpit-grid" style="margin-top:11px">
      ${(opp.items || []).slice(0, 4).map(oppCard).join('') ||
        '<div class="card"><div class="card-body"><div class="plain-note">机会榜暂无足够真实数据（数据源不可用或置信度不足），系统不凑数、不用模拟数据填充。</div></div></div>'}
    </div>
    <div class="v21-tabs" style="margin-top:10px">
      <button class="v21-tab" data-go2="opportunities">打开 AI 投资机会雷达 →</button>
      <button class="v21-tab" data-prio="P1">P1/P2/P3 等级说明</button>
      <button class="v21-tab" data-term="PE">估值指标为什么缺失？</button>
    </div>
    ${(opp.missing_capabilities || []).length ? `<div class="miss-note">未接入能力（如实列出）：${opp.missing_capabilities.map(x => `${safe(x.name)}（${safe(x.reason)}；替代：${safe(x.alternative)}）`).join('；')}</div>` : ''}

    <div class="cockpit-grid" style="margin-top:13px">
      <div class="card" style="margin:0">${cardHead('全球市场表现领先榜 · 今日', '真实历史涨跌 · 点击行看详情',
        `<button class="btn" data-go2="opportunities">${safe(t('lbl.viewall'))} →</button>`)}
        <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr>
          <th>#</th><th>名称</th><th>市场</th><th class="r">现价</th><th class="r">今日</th><th class="r">近1月</th></tr></thead><tbody>
        ${(leaders.items || []).slice(0, 6).map((x, i) => `<tr class="clickable" data-detail="stocks" data-id="${safe(x.symbol)}">
          <td class="rank-no">${i + 1}</td><td class="nm">${safe(x.name)} <small>${safe(x.symbol)}</small></td>
          <td>${safe(x.market)}</td><td class="r">${N(x.price)}</td><td class="r">${pctHtml(x.change_pct)}</td>
          <td class="r">${pctHtml(x.returns.m1)}</td></tr>`).join('') || '<tr><td colspan="6">暂无真实行情</td></tr>'}
        </tbody></table></div><div class="miss-note">⚠ ${safe(leaders.disclaimer || t('disclaimer.history'))}</div></div></div>

      <div class="card" style="margin:0">${cardHead('全球优质公司观察榜', 'SEC 官方申报值 · 非市值排序',
        `<button class="btn" data-go2="opportunities">查看全部 →</button>`)}
        <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr>
          <th>公司</th><th class="r">净利率</th><th class="r">ROE</th><th class="r">负债率</th><th class="r">质量分</th></tr></thead><tbody>
        ${(quality.items || []).slice(0, 6).map(x => `<tr class="clickable" data-detail="stocks" data-id="${safe(x.symbol)}">
          <td class="nm">${safe(x.name)} <small>${safe(x.symbol)}</small></td><td class="r">${dash(x.net_margin)}%</td>
          <td class="r">${dash(x.roe)}%</td><td class="r">${dash(x.debt_ratio)}%</td>
          <td class="r"><b>${N(x.quality_score, 1)}</b></td></tr>`).join('') || '<tr><td colspan="5">SEC 财务数据读取中或未覆盖，暂不展示（不以 AI 主观判断替代）</td></tr>'}
        </tbody></table></div><div class="miss-note">${safe((quality.method || ''))}；${safe((quality.missing || []).join('、'))}</div></div></div>
    </div>

    <div class="card" style="margin-top:13px">${cardHead(t('lbl.riskToday'), '不能只展示机会而隐藏风险')}
      <div class="card-body">${(daily.risks || []).map(x => `<div class="risk-item"><span class="ri-ico">⚠</span><span>${safe(x)}</span></div>`).join('') || '<div class="plain-note">暂无风险数据</div>'}
      ${easyBlock('风险提示就是提醒你：数据有延迟、有些关键指标还没接上、别把历史涨幅当成将来一定赚钱。')}</div></div>
  </section>

  <div class="screen-divider"></div>
  <!-- 第二屏：全球市场概况 -->
  <section class="screen" id="screen2">
    <div class="screen-head"><span class="screen-no">2</span><h2>${safe(t('lbl.marketOverview'))}</h2>
      <span class="sh-sub">全球股指 / 中国 / 美国 / 欧洲 / 亚洲 / 外汇 / 利率 / 商品 / 数字资产</span></div>
    ${marketOverview(mk)}
  </section>

  <div class="screen-divider"></div>
  <!-- 第三屏：今日全球金融快讯 -->
  <section class="screen" id="screen3">
    <div class="screen-head"><span class="screen-no">3</span><h2>${safe(t('lbl.flash'))}</h2>
      <span class="sh-sub">每条均可进入详情页 · 附一句话摘要与 AI 影响分析</span></div>
    <div class="card"><div class="card-body" style="padding:6px 12px">
      ${items.map(x => `<div class="flash-item" data-detail="news" data-id="${safe(x.id)}">
        <div class="fi-time">${dateCN(x.published)}</div>
        <div style="flex:1"><div class="fi-title">${safe(x.title)}</div>
          <div class="fi-meta">${prioBadge(x.priority, (x.priority_model || {}).why_this_item)}
            <span>${safe(x.source)}</span><span>${safe(x.category)}</span>
            <span>${safe((x.tags || []).join(' / '))}</span></div>
          <div class="fi-meta" style="color:var(--txt2)">${safe(x.hint || '')}</div>
          ${V21.easy ? easyBlock('这条新闻讲的是「' + safe((x.title || '').slice(0, 46)) + '…」。点开详情可以看到：这是什么意思、为什么发生、对你有什么影响、该关注什么。') : ''}
        </div></div>`).join('') || '<div class="plain-note">暂无真实资讯</div>'}
    </div>${srcNote('资讯来自站内真实 RSS 聚合，标题/时间/来源/原文链接未改写')}</div>
  </section>

  <div class="screen-divider"></div>
  <!-- 第四屏：AI 今日市场总结（右侧栏同步展示） -->
  <section class="screen" id="screen4">
    <div class="screen-head"><span class="screen-no">4</span><h2>${safe(t('lbl.aiSummary'))}</h2>
      <span class="sh-sub">右侧栏常驻，可独立滚动</span></div>
    <div class="cockpit-grid"><div class="card" style="margin:0">${cardHead(t('lbl.onesentence'), '基于站内真实数据')}
      <div class="card-body"><p style="font-size:14px;line-height:1.7">${safe(daily.one_sentence || '暂无数据')}</p>
      ${easyBlock('一句话看懂今天：市场涨跌家数、领涨领跌资产、以及最重要的官方消息。')}</div></div>
      <div class="card" style="margin:0">${cardHead(t('lbl.threeEvents'), '发生了什么 · 为什么重要 · 影响什么')}
      <div class="card-body">${(daily.three_events || []).map(x => `<div class="risk-item" data-detail="news" data-id="${safe(x.id)}" style="cursor:pointer">
        <span class="ri-ico">◆</span><span><b>${safe(x.title)}</b><br>${safe(x.why)}<br>${safe(x.impact)} · ${safe((x.assets || []).join('、'))}</span></div>`).join('') || '<div class="plain-note">暂无数据</div>'}</div></div></div>
    <div class="card" style="margin-top:12px">${cardHead(t('lbl.temp') + ' · 判断依据', '机械统计，不是资金流向')}
      <div class="card-body"><span class="temp-pill">${safe((daily.temperature || {}).label || '暂无')}</span>
      <p class="plain-note" style="margin-top:8px">${safe((daily.temperature || {}).basis || '')}<br>${safe((daily.temperature || {}).note || '')}</p></div></div>
  </section>

  <div class="card" style="margin-top:16px">${cardHead('数据口径与风险提示', '请先看这里再用于判断')}
    <div class="card-body"><p class="plain-note" style="margin:0">${safe(t('disclaimer.invest'))}；${safe(t('disclaimer.history'))}；社交讨论量 ≠ 资金流；宏观为统计发布值。
      ${termLink('PE', 'PE')} / ${termLink('PB', 'PB')} / ${termLink('ROE', 'ROE')} / ${termLink('CPI', 'CPI')} / ${termLink('PMI', 'PMI')} 等术语可点击查看解释。</p></div></div>`;
  bindClicks(host);
};

/* ---------------- 视图 2：AI 投资机会雷达 ---------------- */
V.opportunities = async host => {
  host.innerHTML = loading('正在计算真实数据评分…');
  let d = {}, l = {}, q = {}, tr = {};
  const rs = await Promise.allSettled([
    get(A2.opp + '?market=' + encodeURIComponent(V21.oppMarket) + '&cycle=' + V21.oppCycle),
    get(A2.leaders + '?market=' + encodeURIComponent(V21.leaderMarket) + '&period=' + V21.leaderPeriod),
    get(A2.quality), get(A2.track)
  ]);
  d = rs[0].status === 'fulfilled' ? rs[0].value : { items: [], missing_capabilities: [] };
  l = rs[1].status === 'fulfilled' ? rs[1].value : { items: [] };
  q = rs[2].status === 'fulfilled' ? rs[2].value : { items: [] };
  tr = rs[3].status === 'fulfilled' ? rs[3].value : {};
  V21.opp = d; V21.leaders = l; V21.quality = q;

  host.innerHTML = `
  <div class="screen-head"><span class="screen-no">★</span><h2>AI 全球投资机会雷达</h2>
    <span class="sh-sub">真实数据 · 可解释评分 · 缺失不补分</span></div>
  ${discl('这是研究筛选工具，不是保证盈利的买卖指令。S 级不代表保证赚钱。所有价格来自 Yahoo 非官方延迟接口，财务来自 SEC 官方申报。')}

  <div class="card">${cardHead('全球股票智能筛选', '市场 / 周期 / 评分区间')}
    <div class="card-body">
      <div style="font-size:11px;color:var(--txt3);margin-bottom:5px">市场</div>
      <div class="v21-tabs" id="oppMarkets">${(d.markets || ['全球市场']).concat(['美股', 'A股', '港股', '欧洲市场', '亚洲其他市场']).filter((v, i, a) => a.indexOf(v) === i).map(m =>
        `<button class="v21-tab ${m === V21.oppMarket ? 'on' : ''}" data-om="${safe(m)}">${safe(m)}</button>`).join('')}</div>
      <div style="font-size:11px;color:var(--txt3);margin-bottom:5px">研究周期（不同周期用不同指标）</div>
      <div class="v21-tabs" id="oppCycles">${[['short', '短期 1–5 日'], ['swing', '波段 1–4 周'], ['mid', '中期 1–6 月'], ['long', '长期 6 月+']].map(c =>
        `<button class="v21-tab ${c[0] === V21.oppCycle ? 'on' : ''}" data-oc="${c[0]}">${safe(c[1])}</button>`).join('')}</div>
      ${easyBlock('短期看最近几天价格与成交量；长期才看财报与估值。当前很多财报/估值数据没接上，所以长期结论会被明确拒绝，不会硬给。')}
      <div class="miss-note">当前周期说明：${safe(d.cycle_note || '')}。按国家/交易所/市值区间/估值区间/成长指标筛选需要付费全市场数据库，<b>未接入，不提供假筛选器</b>。</div>
    </div></div>

  <div class="card" style="margin-top:12px">${cardHead('AI 综合评分模型 · 100 分制', (d.model || {}).rule || '')}
    <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>维度</th><th class="r">权重</th><th>数据来源 / 缺失原因</th></tr></thead><tbody>
    ${((d.model || {}).dimensions || []).map(x => `<tr><td class="nm">${safe(x.name)}</td><td class="r">${x.weight}</td>
      <td>${x.key === 'valuation' ? '<span style="color:var(--gold)">数据缺失：无免费 Key 接口</span>' :
        (x.key === 'industry' ? '<span style="color:var(--gold)">数据缺失：需付费行业景气数据</span>' :
        (x.key === 'trend' || x.key === 'volume' ? 'Yahoo 真实日线（已接入）' : 'SEC 官方 XBRL（按需读取）'))}</td></tr>`).join('')}
    </tbody></table></div>
    <div class="miss-note">推荐等级：${(d.items && d.items[0] ? d.items[0].score.grade_rules : []).map(g => `<b>${safe(g.grade)}</b> ≥${g.min}`).join(' · ') || 'S/A/B/C/D'}；置信度 &lt;0.35 一律暂停排名。</div></div></div>

  <div class="screen-divider"></div>
  <div class="screen-head"><span class="screen-no">1</span><h2>机会榜（${d.items ? d.items.length : 0} 项 / 真实抓取 ${d.fetched || 0} / 失败 ${Object.keys(d.errors || {}).length}）</h2></div>
  <div class="cockpit-grid">${(d.items || []).slice(0, 8).map(oppCard).join('') || '<div class="plain-note">暂无足够真实数据</div>'}</div>
  ${(d.missing_capabilities || []).length ? `<div class="card" style="margin-top:12px">${cardHead('未接入的机会类型（不凑数）', '原因与可行替代方案')}
    <div class="card-body">${d.missing_capabilities.map(x => `<div class="risk-item"><span class="ri-ico">○</span><span><b>${safe(x.name)}</b><br>原因：${safe(x.reason)}<br>替代：${safe(x.alternative)}</span></div>`).join('')}</div></div>` : ''}

  <div class="screen-divider"></div>
  <div class="screen-head"><span class="screen-no">2</span><h2>全球市场表现领先榜</h2>
    <span class="sh-sub">${safe(t('disclaimer.history'))}</span></div>
  <div class="card"><div class="card-body">
    <div class="v21-tabs" id="leaderPeriods">${[['d1', '今日'], ['w1', '近一周'], ['m1', '近一个月'], ['m3', '近三个月'], ['ytd', '年初至今']].map(x =>
      `<button class="v21-tab ${x[0] === V21.leaderPeriod ? 'on' : ''}" data-lp="${x[0]}">${safe(x[1])}</button>`).join('')}</div>
    <div class="v21-tabs" id="leaderMarkets">${(l.markets || []).map(m => `<button class="v21-tab ${m === V21.leaderMarket ? 'on' : ''}" data-lm="${safe(m)}">${safe(m)}</button>`).join('')}</div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>名称</th><th>市场</th><th>行业</th>
      <th class="r">现价</th><th class="r">${safe(l.period_name || '')}</th><th class="r">近3月</th><th class="r">波动率</th><th class="r">最大回撤</th></tr></thead><tbody>
      ${(l.items || []).map((x, i) => `<tr class="clickable" data-detail="stocks" data-id="${safe(x.symbol)}">
        <td class="rank-no">${i + 1}</td><td class="nm">${safe(x.name)} <small>${safe(x.symbol)}</small></td>
        <td>${safe(x.market)}</td><td>${safe(x.sector)}</td><td class="r">${N(x.price)}</td>
        <td class="r">${pctHtml(x.change_pct)}</td><td class="r">${pctHtml(x.returns.m3)}</td>
        <td class="r">${dash(x.vol_annual)}%</td><td class="r">${dash(x.max_drawdown)}%</td></tr>`).join('') || '<tr><td colspan="9">暂无真实行情</td></tr>'}
      </tbody></table></div><div class="miss-note">⚠ ${safe(l.disclaimer || '')}</div></div></div>

  <div class="screen-divider"></div>
  <div class="screen-head"><span class="screen-no">3</span><h2>全球优质公司观察榜</h2></div>
  <div class="card"><div class="card-body">
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>公司</th><th>行业</th><th class="r">净利率</th><th class="r">毛利率</th>
      <th class="r">ROE</th><th class="r">负债率</th><th class="r">营收变化</th><th class="r">质量分</th></tr></thead><tbody>
      ${(q.items || []).map(x => `<tr class="clickable" data-detail="stocks" data-id="${safe(x.symbol)}">
        <td class="nm">${safe(x.name)} <small>${safe(x.symbol)}</small></td><td>${safe(x.sector)}</td>
        <td class="r">${dash(x.net_margin)}%</td><td class="r">${dash(x.gross_margin)}%</td>
        <td class="r">${dash(x.roe)}%</td><td class="r">${dash(x.debt_ratio)}%</td>
        <td class="r">${x.revenue_growth === null || x.revenue_growth === undefined ? '--' : SG(x.revenue_growth) + '%'}</td>
        <td class="r"><b>${N(x.quality_score, 1)}</b></td></tr>`).join('') || '<tr><td colspan="8">SEC 财务数据读取中或该市场不覆盖，不展示虚构数据</td></tr>'}
      </tbody></table></div>
      <div class="miss-note">${safe(q.method || '')}<br>未接入：${safe((q.missing || []).join('；'))}</div></div></div>

  <div class="screen-divider"></div>
  <div class="screen-head"><span class="screen-no">4</span><h2>历史研究成绩单 · 避免未来数据泄漏</h2></div>
  <div class="card"><div class="card-body">
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>标的</th><th>生成时间</th><th class="r">当时价格</th><th class="r">当前价格</th>
      <th class="r">实际涨跌</th><th class="r">基准 ^GSPC</th><th class="r">超额</th><th class="r">最大回撤</th></tr></thead><tbody>
      ${(tr.items || []).slice(0, 15).map(x => `<tr class="clickable" data-detail="stocks" data-id="${safe(x.symbol)}">
        <td class="nm">${safe(x.name)} <small>${safe(x.symbol)}</small></td><td>${dateCN(x.as_of)}</td>
        <td class="r">${N(x.price)}</td><td class="r">${N(x.current_price)}</td><td class="r">${pctHtml(x.actual_change_pct)}</td>
        <td class="r">${pctHtml(x.benchmark_change_pct)}</td><td class="r">${pctHtml(x.excess_pct)}</td>
        <td class="r">${dash(x.max_drawdown)}%</td></tr>`).join('') || `<tr><td colspan="8">已记录 ${tr.pending || 0} 条推荐时点快照，尚满评估期（${safe(tr.no_future_leak || '仅评估已满期的快照')}）</td></tr>`}
      </tbody></table></div>
      <div class="miss-note">已评估 ${tr.evaluated || 0} 条 · 方向准确率 ${dash(tr.direction_accuracy)}%<br>${safe(tr.accuracy_note || '')}</div></div></div>`;

  bindClicks(host);
  host.querySelectorAll('[data-om]').forEach(b => b.onclick = () => { V21.oppMarket = b.dataset.om; V.opportunities(host); });
  host.querySelectorAll('[data-oc]').forEach(b => b.onclick = () => { V21.oppCycle = b.dataset.oc; V.opportunities(host); });
  host.querySelectorAll('[data-lp]').forEach(b => b.onclick = () => { V21.leaderPeriod = b.dataset.lp; V.opportunities(host); });
  host.querySelectorAll('[data-lm]').forEach(b => b.onclick = () => { V21.leaderMarket = b.dataset.lm; V.opportunities(host); });
};

/* ---------------- 视图 3：术语词典 ---------------- */
V.glossary = async host => {
  host.innerHTML = loading('正在读取术语词典…');
  try {
    const d = await get(A2.terms); V21.glossary = d.items || [];
    host.innerHTML = `<div class="screen-head"><span class="screen-no">?</span><h2>${safe(t('v.glossary'))}</h2>
      <span class="sh-sub">悬停 / 点击解释 · 支持搜索与收藏 · 手机端点击即可</span></div>
      ${easyBlock('这一页把金融词翻成大白话。点任意一个词，会告诉你它是什么、数字高低代表什么、对股市可能有什么影响。')}
      <div class="card"><div class="card-body">
        <input id="glossQ" class="v21-sel" style="width:260px;height:32px" placeholder="搜索术语（如 PE / 市盈率 / 通胀）">
        <span class="miss-note">共 ${d.total} 个术语 · 领域：${safe((d.fields || []).join('、'))}</span>
        <div id="glossList" style="margin-top:11px"></div></div></div>
      <div class="card" style="margin-top:12px">${cardHead('重要等级说明', 'P1 / P2 / P3 由规则模型产生')}
        <div class="card-body"><button class="v21-tab" data-prio="P1">查看完整等级定义 →</button></div></div>`;
    const draw = kw => {
      const arr = (V21.glossary || []).filter(x => !kw || (x.term + x.zh + x.plain).toLowerCase().includes(kw.toLowerCase()));
      $('glossList').innerHTML = arr.length ? `<div class="glossary-grid">${arr.map(x => `
        <div class="gloss-card" data-term="${safe(x.term)}"><span class="gc-fav ${V21.favorites.includes(x.term) ? 'on' : ''}">★</span>
          <b>${safe(x.term)}</b><span class="gc-zh">${safe(x.zh)} · ${safe(x.field)}</span>
          <p>${safe(x.plain)}</p></div>`).join('')}</div>` : '<div class="plain-note">没有匹配的术语</div>';
      bindClicks($('glossList'));
    };
    draw('');
    $('glossQ').oninput = e => draw(e.target.value);
    bindClicks(host);
  } catch (e) { host.innerHTML = `<div class="plain-note">读取失败：${safe(e.message)}</div>`; }
};

/* ---------------- 视图 4：通用详情页 ---------------- */
async function stockDetail(host, symbol) {
  const d = await get(A2.stock + '?symbol=' + encodeURIComponent(symbol));
  if (d.error) { host.innerHTML = `<div class="card"><div class="card-body"><div class="plain-note">${safe(d.error)}</div></div></div>`; return; }
  const m = d.metrics, f = d.financials, s = d.score;
  host.innerHTML = `
  <div class="detail-head"><button class="detail-back" data-go2="opportunities">← ${safe(t('lbl.back'))}</button>
    <div><div class="detail-title">${safe(d.info.name)} <span style="color:var(--txt3);font:13px var(--mono)">${safe(symbol)}</span></div>
    <div class="detail-sub">${safe(d.info.market)} · ${safe(d.info.exchange)} · ${safe(d.info.sector)} · ${safe(m.currency || d.info.currency)} · 更新 ${hhmm(m.updated)}</div></div></div>
  ${discl(d.disclaimer)}
  ${easyBlock('这一页是「这家公司值不值得继续研究」的说明书。研究分只用拿得到的真实数据计算，缺的不猜；请同时看「看空理由」和「主要风险」，等级高不等于一定赚钱。')}
  <div class="detail-grid">
    <div class="detail-card"><h3>实时/延迟行情</h3><div class="kv-list">
      <span>当前价格</span><b>${N(m.price)} ${safe(m.currency)}</b>
      <span>当日涨跌</span><b class="${CL(m.returns.d1)}">${SG(m.returns.d1)}%</b>
      <span>近一周</span><b>${pctHtml(m.returns.w1)}</b>
      <span>近一月</span><b>${pctHtml(m.returns.m1)}</b>
      <span>近三月</span><b>${pctHtml(m.returns.m3)}</b>
      <span>年初至今</span><b>${pctHtml(m.returns.ytd)}</b>
      <span>数据区间</span><b>${safe(m.first_date)} → ${safe(m.last_date)}（${m.days} 个交易日）</b>
      <span>口径</span><b>${safe(m.latency)}</b></div>
      ${m.stale ? `<div class="notice-box">数据陈旧：${safe(m.stale_note)}</div>` : ''}
      ${lineSVG ? `<div style="margin-top:9px">${lineSVG(m.spark.map((v, i) => [String(i), v]), { id: 'sd' })}</div>` : ''}
    </div>
    <div class="detail-card"><h3>技术分析（真实日线计算）</h3><div class="kv-list">
      <span>${termLink('MA20', 'MA20')}</span><b>${N(m.ma20)} · 价格${m.above_ma20 ? '在上方' : '在下方'}</b>
      <span>MA60</span><b>${N(m.ma60)}</b>
      <span>${termLink('RSI', 'RSI(14)')}</span><b>${dash(m.rsi14)}</b>
      <span>${termLink('MACD', 'MACD')}</span><b>${dash(m.macd)}</b>
      <span>${termLink('Volatility', '年化波动率')}</span><b>${dash(m.vol_annual)}%</b>
      <span>${termLink('Max Drawdown', '最大回撤')}</span><b>${dash(m.max_drawdown)}%</b>
      <span>近 5 日量能比</span><b>${dash(m.volume_ratio)} ×</b></div>
      <div class="miss-note">${safe(d.technical_status)}</div></div>
    <div class="detail-card"><h3>财务分析（SEC 官方 XBRL）</h3>
      ${f && !f.error ? `<div class="kv-list">
        <span>公司</span><b>${safe(f.company)}</b>
        <span>营业收入</span><b>${f.revenue === null ? '数据缺失' : N(f.revenue)} USD</b>
        <span>净利润</span><b>${f.net_income === null ? '数据缺失' : N(f.net_income)} USD</b>
        <span>毛利率</span><b>${dash(f.gross_margin)}%</b>
        <span>${termLink('ROE', 'ROE')}</span><b>${dash(f.roe)}%</b>
        <span>资产负债率</span><b>${dash(f.debt_ratio)}%</b>
        <span>营收变化</span><b>${f.revenue_growth === null || f.revenue_growth === undefined ? '--' : SG(f.revenue_growth) + '%'}</b>
        <span>统计截止</span><b>${safe(f.facts_as_of || '见申报期')}</b></div>
        <div class="miss-note">${safe(f.facts_note || '')} · ${safe(f.note || '')}</div>`
        : `<div class="plain-note">${safe((f && f.error) || '该市场不在 SEC EDGAR 覆盖范围，财务数据未接入；不显示虚构财务指标。')}</div>`}
      <div class="miss-note">${safe(d.valuation_status)}</div></div>
    <div class="detail-card"><h3>AI 综合研究评分（可解释规则）</h3>
      <div class="kv-list"><span>综合分</span><b>${dash(s.composite)} / 100</b>
        <span>置信度</span><b>${dash(s.confidence)}（可得权重 ${s.available_weight}/100）</b>
        <span>等级</span><b>${safe(s.grade)}</b>
        <span>是否参与排名</span><b>${s.ranked ? '是' : '否（数据不足已暂停）'}</b></div>
      <div class="tbl-wrap" style="margin-top:8px"><table class="tbl"><thead><tr><th>维度</th><th class="r">权重</th><th class="r">得分</th></tr></thead><tbody>
      ${Object.keys(s.dims).map(k => `<tr><td>${safe(s.dims[k].name)}</td><td class="r">${s.dims[k].weight}</td>
        <td class="r">${s.dims[k].value === null ? '<span style="color:var(--gold)">数据缺失</span>' : N(s.dims[k].value, 1)}</td></tr>`).join('')}</tbody></table></div>
      <div class="miss-note">${safe((d.model_rule) || '综合分只在可得维度上归一，缺失不补分')}</div></div>
  </div>
  <div class="card" style="margin-top:12px">${cardHead('多头逻辑 / 空头逻辑 / 风险 / 结论失效条件', '必须保留反向观点')}
    <div class="card-body"><div class="detail-grid" style="gap:10px">
      <div><h5 style="color:var(--up);font-size:12px">看多理由</h5>${(d.bull || []).map(x => `<p>· ${safe(x)}</p>`).join('')}</div>
      <div><h5 style="color:var(--down);font-size:12px">看空理由与不确定因素</h5>${(d.bear || []).map(x => `<p>· ${safe(x)}</p>`).join('')}</div>
      <div><h5 style="color:var(--gold);font-size:12px">主要风险</h5>${(d.risks || []).map(x => `<p>· ${safe(x)}</p>`).join('')}</div>
      <div><h5 style="color:var(--cyan);font-size:12px">研究结论</h5><p>${safe(d.conclusion)}</p>
        ${d.plan ? `<p style="margin-top:6px"><b>结论失效条件：</b>${safe(d.plan.invalidation)}</p>` : ''}</div>
    </div></div></div>
  ${d.plan ? `<div class="card" style="margin-top:12px">${cardHead('投资研究计划（情景分析，非价格预测）', '仅数据足够时生成')}
    <div class="card-body"><div class="kv-list">
      <span>关注条件</span><b>${safe(d.plan.watch_condition)}</b>
      <span>研究入场区间</span><b>${safe(d.plan.research_entry_zone)}</b>
      <span>观察目标区间</span><b>${safe(d.plan.observe_zone)}</b>
      <span>风险控制条件</span><b>${safe(d.plan.risk_control)}</b>
      <span>逻辑失效条件</span><b>${safe(d.plan.invalidation)}</b>
      <span>预计研究周期</span><b>${safe(d.plan.cycle)}</b></div>
    <div class="notice-box">${safe(d.plan.disclaimer)}</div></div></div>` : '<div class="notice-box">数据不足，未生成研究计划；不提供确定性的价格预测。</div>'}
  <div class="card" style="margin-top:12px">${cardHead('公司近期新闻 / 监管公告', '站内真实资讯')}
    <div class="card-body">${(d.news || []).map(x => `<div class="risk-item" data-detail="news" data-id="${safe(x.id || '')}" style="cursor:pointer">
      <span class="ri-ico">▸</span><span>${safe(x.title)}<br><small>${safe(x.source)} · ${dateCN(x.published)}</small></span></div>`).join('') || '<div class="plain-note">暂无匹配到该公司的站内报道</div>'}
    <div class="miss-note">数据来源：${safe((d.data_sources || []).join('；'))}</div></div></div>`;
}

V.detail = async (host, key) => {
  host.innerHTML = loading('正在读取详情…');
  const parts = key.split('/');
  const type = parts[0], id = decodeURIComponent(parts.slice(1).join('/'));
  const back = `<button class="detail-back" data-go2="dashboard">← ${safe(t('lbl.back'))}</button>`;
  try {
    if (type === 'stocks') return await stockDetail(host, id);
    if (type === 'terms') return await V.glossary(host);
    const d = await get(A2.detail + '?type=' + encodeURIComponent(type) + '&id=' + encodeURIComponent(id));
    if (d.error) {
      host.innerHTML = `${back}<div class="card"><div class="card-body"><div class="plain-note">${safe(d.error)}</div>
        <div class="miss-note">${safe(t('err.noData'))}</div></div></div>`;
      bindClicks(host); return;
    }
    if (type === 'news' || type === 'events') {
      const it = d.item;
      host.innerHTML = `${back}
        <div class="detail-head"><div><div class="detail-title">${safe(it.title)}</div>
          <div class="detail-sub">${safe(it.source)} · ${dateCN(it.published)} · ${safe(it.category)} · ${safe(it.domain)}</div></div></div>
        ${easyBlock('这条消息说的是「' + safe((it.title || '').slice(0, 40)) + '…」。往下看：它为什么重要、影响到哪些行业和公司、以及有哪些相反的可能。')}
        <div class="card">${cardHead('重要等级与判定依据', '由规则模型产生')}
          <div class="card-body">${prioBadge(it.priority, (it.priority_model || {}).why_this_item)}
            <p class="plain-note" style="margin-top:7px">${safe((it.priority_model || {}).why_this_item || '')}</p>
            <div class="miss-note">${safe((it.priority_model || {}).model || '')} · ${safe((it.priority_model || {}).note || '')}</div></div></div>
        <div class="card" style="margin-top:12px">${cardHead('AI 摘要与小白解释', '不歪曲原始信息')}
          <div class="card-body"><p>${safe(d.ai_summary || '')}</p>
          ${(d.plain || []).map(x => `<div class="vm-row"><h5>${safe(x.q)}</h5><p>${safe(x.a)}</p></div>`).join('')}
          <div class="miss-note">事件背景：${safe(d.background)}<br>历史同类事件：${safe(d.historical)}</div></div></div>
        <div class="card" style="margin-top:12px">${cardHead('新闻原文 / 翻译 / 双语对照', '翻译结果缓存，失败回退原文')}
          <div class="card-body"><div class="bilingual"><div class="bl-label">原文标题 / ORIGINAL</div>
            <div class="bl-orig">${safe(it.title)}</div></div>
            ${transTools(it.title, 'news-' + (it.id || id))}
            <div class="trans-tools"><a class="btn" href="${safe(it.link)}" target="_blank" rel="noopener noreferrer">${safe(t('lbl.original'))} ↗</a>
              <a class="btn" href="${safe(it.search)}" target="_blank" rel="noopener noreferrer">搜相关其它来源 ↗</a>
              <a class="btn" href="${safe(it.site)}" target="_blank" rel="noopener noreferrer">${safe(it.domain)} ↗</a></div></div></div>
        <div class="detail-grid" style="margin-top:12px">
          <div class="detail-card"><h3>影响范围</h3><div class="kv-list">
            <span>相关国家/地区</span><b>${safe((d.countries || []).join('、'))}</b>
            <span>相关行业</span><b>${safe((d.industries || []).join('、'))}</b>
            <span>关联标的</span><b>${(it.symbols || []).length ? it.symbols.map(s => safe(s.name)).join('、') : '原文未识别到明确标的'}</b>
            <span>话题标签</span><b>${safe((d.tags || []).join('、') || '无')}</b>
            <span>潜在市场影响</span><b>见上方「影响范围」与原文，本站不推断未写明的因果</b></div></div>
          <div class="detail-card"><h3>关联股票 / 资产</h3>${(it.symbols || []).map(s =>
            `<p>· <a href="${safe(s.url)}" target="_blank" rel="noopener noreferrer">${safe(s.name)} ↗</a></p>`).join('') || '<p>暂无可识别标的</p>'}</div>
        </div>
        <div class="card" style="margin-top:12px">${cardHead('相关报道 / 其它来源', '站内真实资讯去重后匹配')}
          <div class="card-body">${(d.related || []).map(x => `<div class="risk-item" data-detail="news" data-id="${safe(x.id)}" style="cursor:pointer">
            <span class="ri-ico">▸</span><span>${safe(x.title)}<br><small>${safe(x.source)} · ${dateCN(x.published)}</small></span></div>`).join('') || '<div class="plain-note">暂无同话题其它报道</div>'}
            <div class="miss-note">${safe(d.other_sources)}</div></div></div>`;
    } else if (type === 'assets') {
      const it = d.item;
      host.innerHTML = `${back}<div class="detail-head"><div><div class="detail-title">${safe(it.name)} ${safe(id)}</div>
        <div class="detail-sub">${safe(it.group)} · ${safe(it.currency)} · 更新 ${hhmm(it.time)}</div></div></div>
        <div class="detail-grid"><div class="detail-card"><h3>行情</h3><div class="kv-list">
          <span>价格</span><b>${N(it.price)}</b><span>涨跌</span><b class="${CL(it.pct)}">${SG(it.pct)}%</b>
          <span>前收</span><b>${N(it.prev)}</b><span>数据源</span><b>Yahoo Finance v8 chart（非官方）</b></div>
          ${lineSVG ? lineSVG((it.spark || []).map((v, i) => [String(i), v]), { id: 'ad' }) : ''}
          <div class="notice-box">${safe(d.note)}</div></div>
          <div class="detail-card"><h3>详情入口</h3><p><a href="${safe(d.link)}" target="_blank" rel="noopener noreferrer">查看外部行情页 ↗</a></p>
          ${termLink('Volatility', '波动率')} · ${termLink('MA20', '均线')} 等指标解释可点击查看</div></div>`;
    } else if (type === 'macro') {
      host.innerHTML = `${back}<div class="detail-head"><div><div class="detail-title">${safe(d.indicator)} ${d.series ? safe(d.series.label || '') : ''}</div>
        <div class="detail-sub">${safe(d.source)}</div></div></div>
        <div class="detail-grid"><div class="detail-card"><h3>最新真实数值</h3><div class="kv-list">
          <span>数值</span><b>${d.series ? N(d.series.value) : '--'}</b>
          <span>统计截止</span><b>${safe(d.series ? d.series.as_of : '--')}</b>
          <span>频率</span><b>${safe(d.series ? d.series.frequency : '--')}</b>
          <span>来源</span><b><a href="${safe(d.series ? d.series.url : '#')}" target="_blank">官方链接 ↗</a></b></div>
          <div class="notice-box">${safe(d.note)}</div></div>
          ${d.explanation ? `<div class="detail-card"><h3>通俗解释 · ${safe(d.explanation.zh)}</h3>
            <p>${safe(d.explanation.plain)}</p><div class="kv-list"><span>作用</span><b>${safe(d.explanation.use)}</b>
            <span>偏高</span><b>${safe(d.explanation.high)}</b><span>偏低</span><b>${safe(d.explanation.low)}</b>
            <span>市场影响</span><b>${safe(d.explanation.impact)}</b></div></div>` : ''}
        </div>
        <div class="card" style="margin-top:12px">${cardHead('全部官方宏观序列', '点击可进入各指标详情')}
          <div class="card-body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>指标</th><th class="r">最新值</th><th>统计截止</th></tr></thead><tbody>
          ${(d.all_series || []).map(x => `<tr class="clickable" data-detail="macro" data-id="${safe(x.id)}">
            <td class="nm">${safe(x.label || x.name || x.id)}</td><td class="r">${N(x.value)}</td><td>${safe(x.as_of)}</td></tr>`).join('')}
          </tbody></table></div></div></div>`;
    } else if (type === 'sources') {
      const it = d.item;
      host.innerHTML = `${back}<div class="detail-head"><div><div class="detail-title">${safe(it.name)}</div>
        <div class="detail-sub">${safe(it.id)} · ${safe(it.grade)} 级 · ${safe(it.provider)}</div></div></div>
        <div class="detail-grid"><div class="detail-card"><h3>数据源真实状态</h3><div class="kv-list">
          <span>状态</span><b>${safe(it.status)}</b><span>启用</span><b>${it.enabled ? '是' : '否'}</b>
          <span>成功率</span><b>${safe(it.success_rate)}</b><span>最近耗时</span><b>${safe(it.last_ms)} ms</b>
          <span>覆盖</span><b>${safe(it.coverage)}</b><span>延迟</span><b>${safe(it.latency)}</b>
          <span>授权</span><b>${safe(it.license)}</b><span>最近错误</span><b>${safe(it.last_error || '无')}</b></div></div>
          <div class="detail-card"><h3>说明</h3><p>${safe(it.note || '')}</p><p>${safe(d.probe)}</p>
            <p>${safe(d.note)}</p><button class="v21-tab" data-go2="sources">返回数据源管理 →</button></div></div>`;
    } else if (type === 'industries' || type === 'alerts') {
      const arr = d.items || (d.rule ? [d.rule] : []);
      host.innerHTML = `${back}<div class="detail-head"><div><div class="detail-title">${safe(d.name || d.type || id)}</div>
        <div class="detail-sub">${safe(d.note || '')}</div></div></div>
        <div class="card"><div class="card-body">${arr.map(x => `<div class="risk-item"><span class="ri-ico">▸</span>
          <span>${safe(x.title || x.symbol || JSON.stringify(x).slice(0, 100))}</span></div>`).join('') || '<div class="plain-note">暂无真实数据</div>'}</div></div>`;
    } else {
      host.innerHTML = `${back}<div class="card"><div class="card-body"><div class="plain-note">未知详情类型：${safe(type)}</div></div></div>`;
    }
  } catch (e) {
    host.innerHTML = `${back}<div class="card"><div class="card-body"><div class="plain-note">详情读取失败：${safe(e.message)}</div>
      <div class="miss-note">${safe(t('err.noData'))}</div></div></div>`;
  }
  bindClicks(host);
};

/* ---------------- 路由：详情 hash + 直达 URL ---------------- */
const _origSwitch = window.switchView;
window.switchView = function (id) {
  if (typeof id === 'string' && id.indexOf('detail/') === 0) {
    S.view = id;
    const p = id.split('/'), type = p[1] || '', key = p.slice(2).join('/');
    $('pageTitle').textContent = ({ news: '快讯详情', events: '事件详情', stocks: '股票研究详情',
      assets: '资产详情', macro: '宏观指标详情', sources: '数据源详情',
      industries: '行业详情', alerts: '预警详情', terms: '金融术语词典' })[type] || '详情页';
    $('ptEyebrow').textContent = 'DETAIL / ' + type.toUpperCase();
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    $('sidebar').classList.remove('open');
    if (location.hash.slice(1) !== id) location.hash = id;
    // 必须显式 mount：hashchange 监听器在 h === S.view 时不会再次调用 switchView
    mount();
    window.scrollTo({ top: 0 });
    return;
  }
  _origSwitch(id);
  const navMap = {}; NAV.forEach(g => g.items.forEach(i => navMap[i.id] = i));
  const m = navMap[S.view];
  if (m) $('pageTitle').textContent = m._t || m.t;
};
const _origMount = window.mount;
window.mount = async function () {
  if (typeof S.view === 'string' && S.view.indexOf('detail/') === 0) {
    const host = $('viewHost'); host.innerHTML = loading();
    try { await V.detail(host, S.view.slice(7)); }
    catch (e) { host.innerHTML = `<div class="card"><div class="card-body"><div class="plain-note">详情页出错：${safe(e.message)}</div></div></div>`; }
    return;
  }
  return _origMount();
};
// 兼容 pathname 直达 /news/xxx、/stocks/AAPL 等（后端已做 SPA fallback）
function normalizePath() {
  const m = location.pathname.match(/^\/(news|events|stocks|assets|macro|sources|industries|alerts|terms)\/(.+)$/);
  if (m) {
    const h = 'detail/' + m[1] + '/' + decodeURIComponent(m[2]);
    history.replaceState(null, '', '/#' + h);
    S.view = h;
    return true;
  }
  // 单段视图直达：/opportunities、/glossary、/macro … 同样规范化成 hash 路由，
  // 否则后端虽回了 SPA 入口，前端仍停留在默认驾驶舱。
  const one = location.pathname.match(/^\/(dashboard|opportunities|glossary|news|events|geo|industry|social|quotes|heatmap|macro|fx|commodities|crypto|flows|etf|research|scoring|ai|backtest|watchlist|alerts|sources|about)\/?$/);
  if (one) {
    history.replaceState(null, '', '/#' + one[1]);
    S.view = one[1];
    return true;
  }
  return false;
}

/* ---------------- AI 简报引用编号改为站内详情 ---------------- */
const _origBriefHTML = window.briefHTML;
window.briefHTML = function (txt, refs) {
  const clean = String(txt || '').replace(/```[\s\S]*?```/g, '').replace(/\*\*/g, '').trim();
  const linkify = raw => E(raw).replace(/\[(\d{1,2})\]/g, (mm, n) => {
    const r = (refs || []).find(x => String(x.n) === n);
    if (!r) return mm;
    const q = E(JSON.stringify({ title: r.title, link: r.link, source: r.source }));
    return `<span class="ref" data-briefref="${n}" data-ref="${q}" title="点击查看站内快讯详情，或按住 Ctrl 打开原文">[${n}]</span>`;
  });
  const parts = clean.split(/(?=【[^】]+】)/).filter(Boolean); let h = '';
  for (const p of parts) {
    const m = p.match(/^【([^】]+)】\s*([\s\S]*)$/);
    if (m) h += `<div class="brief-sec"><h4>${E(m[1])}</h4><p>${linkify(m[2].trim())}</p></div>`;
    else if (/今日关键词|^关键词/.test(p)) h += `<div class="brief-key">${E(p.trim())}</div>`;
    else if (p.trim()) h += `<p class="brief-plain">${linkify(p.trim())}</p>`;
  }
  return h || `<div class="brief-plain">${linkify(clean)}</div>`;
};
document.addEventListener('click', e => {
  const el = e.target.closest('[data-briefref]'); if (!el) return;
  e.preventDefault();
  let r = {}; try { r = JSON.parse(el.dataset.ref); } catch (x) { }
  if (e.ctrlKey && r.link) { window.open(r.link, '_blank', 'noopener'); return; }
  // 用标题反查站内真实快讯 id，找不到时以标题为 id 显示诚实空态
  const hit = (S.news || []).find(x => x.title === r.title && x.id);
  goDetail('news', hit ? hit.id : encodeURIComponent(r.title || ''));
});

/* ---------------- 易懂模式 / 工具栏绑定 ---------------- */
function applyEasy() {
  document.body.dataset.easy = V21.easy ? '1' : '0';
  const b = $('btnEasy'); if (b) b.classList.toggle('on', V21.easy);
  localStorage.setItem('gfic-easy', V21.easy ? '1' : '0');
}
function bindV21() {
  const sel = $('langSel'); if (sel) sel.onchange = () => setLang(sel.value);
  const be = $('btnEasy'); if (be) be.onclick = () => {
    V21.easy = !V21.easy; applyEasy(); toast(V21.easy ? t('lbl.plainModeHint') : t('lbl.proModeHint')); mount();
  };
  const bt = $('btnTranslate'); if (bt) bt.onclick = async () => {
    if (V21.lang === 'zh-CN') { V21.transLang = V21.transLang === 'en' ? 'ja' : 'en'; }
    const lang = V21.lang === 'zh-CN' ? V21.transLang : V21.lang;
    if (V21.lang !== 'zh-CN') { toast('固定文案已切换为 ' + (V21.dict._meta || {}).name + '；动态内容可点「翻译」按需处理'); return; }
    toast('正在翻译当前页动态内容（' + lang + '）…');
    const nodes = [...document.querySelectorAll('.fi-title,.daily-one,.opp-name,.qa-concl')].slice(0, 8);
    let n = 0;
    for (const el of nodes) {
      try {
        const r = await post(A2.translate, { text: el.textContent, lang: lang });
        if (!r.fallback && r.text !== el.textContent) {
          el.dataset.origText = el.textContent;
          el.innerHTML = E(r.text) + `<div class="miss-note" style="display:block">原文：${E(r.original).slice(0, 160)}</div>`;
          n++;
        }
      } catch (x) { }
    }
    toast(n ? `已翻译 ${n} 处动态内容（已缓存，原文同时保留）` : '本次没有需要翻译的动态内容或翻译失败，已保留原文');
  };
  const bg = $('btnGlossary'); if (bg) bg.onclick = () => switchView('glossary');
  const ct = $('btnCloseTerm'); if (ct) ct.onclick = () => $('termOverlay').hidden = true;
  const cp = $('btnClosePriority'); if (cp) cp.onclick = () => $('priorityOverlay').hidden = true;
  $('termOverlay').onclick = e => { if (e.target.id === 'termOverlay') $('termOverlay').hidden = true; };
  $('priorityOverlay').onclick = e => { if (e.target.id === 'priorityOverlay') $('priorityOverlay').hidden = true; };
  const dr = $('btnDailyRefresh'); if (dr) dr.onclick = () => loadDaily();
  bindClicks(document);
}

/* ---------------- 启动 ---------------- */
/* app.js 的 init() 会在 v21.js 执行前就启动旧 V.dashboard 的异步渲染；
   把 viewHost 换成一个全新节点，旧渲染即使稍后完成也只会写进已脱离文档的旧节点，
   不会覆盖 V2.1 驾驶舱。不改动 app.js 一行。 */
function freshHost() {
  const old = $('viewHost'), parent = old && old.parentNode;
  if (!parent) return;
  const fresh = document.createElement('div');
  fresh.id = 'viewHost'; fresh.className = old.className;
  parent.replaceChild(fresh, old);
}

async function initV21() {
  freshHost();
  NAV[2].items.splice(3, 0, { id: 'opportunities', t: 'AI 投资机会', i: '★', e: 'RESEARCH / OPPORTUNITY RADAR' });
  NAV[3].items.splice(3, 0, { id: 'glossary', t: '金融术语词典', i: '?', e: 'SYSTEM / GLOSSARY' });
  NAV.forEach(g => g.items.forEach(i => NAVMAP[i.id] = i));
  normalizePath();
  applyEasy();
  bindV21();
  await loadDict(V21.lang);
  renderNav();
  try { V21.priorityDef = await get(A2.priority); } catch (e) { }
  try { V21.glossary = (await get(A2.terms)).items || []; } catch (e) { }
  await loadDaily();
  await mount();
  // 首次进入时若 hash 是详情路由，mount 已能正确渲染
}
initV21();
})();
