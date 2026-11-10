#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFIC 全站翻译 / 术语词典 / 优先级规则（V2.1）

原则：
- 固定界面文案用**本地静态词典**，不调用 AI（零成本、零延迟、可离线）。
- 动态内容（新闻标题/摘要/AI 文本）才按需走内网 freellmapi，结果**磁盘缓存**。
- 翻译时用占位符保护股票代码、公司名、数字、币种、时间、URL；翻译后逐个校验，
  任何交易信息发生变化即判失败并回退原文（严禁翻译错误改变金融数字）。
- 翻译失败一律回退原文，绝不输出空白或伪造译文。
"""
import os, re, json, time, hashlib, threading, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)
LOCK = threading.RLock()
CACHE_FILE = os.path.join(DATA, "i18n_cache.json")
CFG = {}
CACHE = {}
LOADED = False

LANGS = {
    "zh-CN": "简体中文", "zh-TW": "繁體中文", "en": "English",
    "ja": "日本語", "ko": "한국어",
}
SUPPORTED = list(LANGS)

# ---------------- 本地静态界面词典（固定文案不调 AI）----------------
# key -> [zh-CN, zh-TW, en, ja, ko]
_UI = {
"brand.sub": ["全球金融情报中心", "全球金融情報中心", "Global Financial Intelligence Center", "グローバル金融情報センター", "글로벌 금융 정보 센터"],
"nav.intelligence": ["情报中枢 / INTELLIGENCE", "情報中樞 / INTELLIGENCE", "Intelligence", "インテリジェンス", "인텔리전스"],
"nav.markets": ["市场监控 / MARKETS", "市場監控 / MARKETS", "Markets", "マーケット", "시장"],
"nav.research": ["研究工作台 / RESEARCH", "研究工作台 / RESEARCH", "Research", "リサーチ", "리서치"],
"nav.system": ["资产与系统 / SYSTEM", "資產與系統 / SYSTEM", "Assets & System", "資産とシステム", "자산 및 시스템"],
"v.dashboard": ["全球金融驾驶舱", "全球金融駕駛艙", "Global Markets Cockpit", "グローバル市場コックピット", "글로벌 시장 콕핏"],
"v.news": ["全球实时资讯", "全球即時資訊", "Global Newsfeed", "グローバルニュース", "글로벌 뉴스"],
"v.events": ["AI 全球事件分析", "AI 全球事件分析", "AI Global Events", "AI グローバルイベント", "AI 글로벌 이벤트"],
"v.geo": ["全球地缘政治", "全球地緣政治", "Geopolitics", "地政学", "지정학"],
"v.industry": ["产业链与行业", "產業鏈與行業", "Industries", "産業チェーン", "산업 체인"],
"v.social": ["社交与市场情绪", "社交與市場情緒", "Social Sentiment", "ソーシャルセンチメント", "소셜 심리"],
"v.quotes": ["全球行情", "全球行情", "Global Quotes", "グローバル相場", "글로벌 시세"],
"v.heatmap": ["市场涨跌热力图", "市場漲跌熱力圖", "Market Heatmap", "市場ヒートマップ", "시장 히트맵"],
"v.macro": ["全球宏观经济", "全球宏觀經濟", "Macro Economy", "マクロ経済", "거시 경제"],
"v.fx": ["外汇与利率", "外匯與利率", "FX & Rates", "為替と金利", "외환 및 금리"],
"v.commodities": ["商品与期货", "商品與期貨", "Commodities", "商品・先物", "원자재"],
"v.crypto": ["数字资产", "數位資產", "Digital Assets", "デジタル資産", "디지털 자산"],
"v.flows": ["全球资金流向", "全球資金流向", "Global Fund Flows", "グローバル資金フロー", "글로벌 자금 흐름"],
"v.etf": ["全球基金与 ETF", "全球基金與 ETF", "Funds & ETF", "ファンド・ETF", "펀드 및 ETF"],
"v.research": ["公司研究 · SEC", "公司研究 · SEC", "Company Research · SEC", "企業研究 · SEC", "기업 연구 · SEC"],
"v.opportunities": ["AI 投资机会", "AI 投資機會", "AI Opportunities", "AI 投資機会", "AI 투자 기회"],
"v.scoring": ["AI 股票评分推荐", "AI 股票評分推薦", "AI Stock Scoring", "AI 株式スコア", "AI 주식 점수"],
"v.ai": ["AI 金融工作台", "AI 金融工作台", "AI Workbench", "AI ワークベンチ", "AI 워크벤치"],
"v.backtest": ["AI 预测成绩单", "AI 預測成績單", "AI Track Record", "AI 予測実績", "AI 예측 성적"],
"v.watchlist": ["自选股与组合", "自選股與組合", "Watchlist & Portfolio", "ウォッチリスト", "관심종목"],
"v.alerts": ["全球风险预警", "全球風險預警", "Risk Alerts", "リスクアラート", "리스크 알림"],
"v.sources": ["数据源管理", "資料源管理", "Data Sources", "データソース", "데이터 소스"],
"v.about": ["系统说明与清单", "系統說明與清單", "System & Inventory", "システム説明", "시스템 안내"],
"v.glossary": ["金融术语词典", "金融術語詞典", "Financial Glossary", "金融用語辞典", "금융 용어 사전"],
"tool.search": ["搜索资讯 / 数据源 / 标的", "搜尋資訊 / 資料源 / 標的", "Search news / sources / symbols", "ニュース・ソース・銘柄を検索", "뉴스/소스/종목 검색"],
"tool.refresh": ["立即刷新全部数据", "立即刷新全部資料", "Refresh all data", "全データを更新", "전체 데이터 새로고침"],
"tool.theme": ["切换深浅主题", "切換深淺主題", "Toggle theme", "テーマ切替", "테마 전환"],
"tool.notify": ["风险预警通知", "風險預警通知", "Risk notifications", "リスク通知", "리스크 알림"],
"tool.lang": ["语言", "語言", "Language", "言語", "언어"],
"tool.translate": ["一键翻译当前页", "一鍵翻譯目前頁", "Translate this page", "このページを翻訳", "이 페이지 번역"],
"tool.easy": ["易懂模式", "易懂模式", "Plain-language mode", "やさしい解説モード", "쉬운 설명 모드"],
"tool.pro": ["专业模式", "專業模式", "Professional mode", "プロモード", "전문 모드"],
"tool.glossary": ["术语词典", "術語詞典", "Glossary", "用語辞典", "용어 사전"],
"lbl.loading": ["正在读取真实数据…", "正在讀取真實資料…", "Loading real data…", "実データを読み込み中…", "실제 데이터 불러오는 중…"],
"lbl.updated": ["数据更新", "資料更新", "Updated", "更新", "업데이트"],
"lbl.source": ["数据来源", "資料來源", "Source", "出典", "출처"],
"lbl.risk": ["风险", "風險", "Risk", "リスク", "리스크"],
"lbl.why": ["为什么值得关注？", "為什麼值得關注？", "Why it matters", "注目すべき理由", "주목할 이유"],
"lbl.caution": ["需要注意什么？", "需要注意什麼？", "What to watch", "注意点", "주의 사항"],
"lbl.conclusion": ["AI 研究结论", "AI 研究結論", "Research conclusion", "調査結論", "리서치 결론"],
"lbl.detail": ["查看详情", "查看詳情", "View details", "詳細を見る", "상세 보기"],
"lbl.viewall": ["查看全部", "查看全部", "View all", "すべて見る", "전체 보기"],
"lbl.back": ["返回", "返回", "Back", "戻る", "뒤로"],
"lbl.original": ["查看原文", "查看原文", "View original", "原文を見る", "원문 보기"],
"lbl.bilingual": ["双语对照", "雙語對照", "Bilingual", "対訳", "이중 언어"],
"lbl.retranslate": ["重新翻译", "重新翻譯", "Re-translate", "再翻訳", "다시 번역"],
"lbl.translated": ["中文翻译", "中文翻譯", "Translation", "翻訳", "번역"],
"lbl.noData": ["暂无数据", "暫無資料", "No data", "データなし", "데이터 없음"],
"lbl.notConnected": ["未接入", "未接入", "Not connected", "未接続", "미연결"],
"lbl.priority": ["重要等级", "重要等級", "Priority", "重要度", "중요도"],
"lbl.today": ["今日", "今日", "Today", "今日", "오늘"],
"lbl.opportunity": ["今日最值得关注的投资机会", "今日最值得關注的投資機會", "Today's research opportunities", "本日の注目投資機会", "오늘의 투자 기회"],
"lbl.leaders": ["全球市场表现领先榜", "全球市場表現領先榜", "Top performers", "値上がり率ランキング", "상승률 순위"],
"lbl.quality": ["全球优质公司观察榜", "全球優質公司觀察榜", "Quality company watchlist", "優良企業ウォッチ", "우량 기업 관찰"],
"lbl.riskToday": ["今日重大风险", "今日重大風險", "Today's key risks", "本日の主要リスク", "오늘의 주요 리스크"],
"lbl.marketOverview": ["全球市场概况", "全球市場概況", "Global market overview", "グローバル市場概況", "글로벌 시장 개요"],
"lbl.flash": ["今日全球金融快讯", "今日全球金融快訊", "Today's financial briefs", "本日の金融速報", "오늘의 금융 속보"],
"lbl.aiSummary": ["AI 今日市场总结", "AI 今日市場總結", "AI daily market summary", "AI 本日の市場まとめ", "AI 오늘의 시장 요약"],
"lbl.onesentence": ["今日市场一句话总结", "今日市場一句話總結", "One-sentence market summary", "今日の市場を一言で", "오늘 시장 한 줄 요약"],
"lbl.threeEvents": ["今日三个关键事件", "今日三個關鍵事件", "Three key events", "本日の重要イベント3つ", "오늘의 핵심 이벤트 3"],
"lbl.temp": ["今日市场温度", "今日市場溫度", "Market temperature", "市場温度", "시장 온도"],
"lbl.plainModeHint": ["已切换为易懂模式：专业术语会附上大白话解释", "已切換為易懂模式：專業術語會附上大白話解釋", "Plain-language mode on: jargon now has simple explanations", "やさしい解説モード：専門用語に解説を表示", "쉬운 설명 모드: 전문 용어에 해설 표시"],
"lbl.proModeHint": ["已切换为专业模式", "已切換為專業模式", "Professional mode on", "プロモードに切替", "전문 모드로 전환"],
"disclaimer.invest": ["本平台仅供个人研究，不构成投资建议；延迟行情不可用于下单", "本平台僅供個人研究，不構成投資建議；延遲行情不可用於下單", "For personal research only. Not investment advice. Delayed quotes must not be used for trading.", "本サービスは個人研究用です。投資助言ではありません。遅延相場は発注に使えません。", "본 플랫폼은 개인 연구용이며 투자 권유가 아닙니다. 지연 시세는 주문에 사용할 수 없습니다."],
"disclaimer.history": ["历史表现领先不代表未来最赚钱", "歷史表現領先不代表未來最賺錢", "Past performance does not guarantee future results", "過去の実績は将来の成果を保証しません", "과거 실적이 미래 수익을 보장하지 않습니다"],
"disclaimer.research": ["研究筛选结果，不是保证盈利的买卖指令", "研究篩選結果，不是保證盈利的買賣指令", "Research screening results, not a profitable trade instruction", "調査スクリーニング結果であり、利益を保証する売買指示ではありません", "리서치 스크리닝 결과이며 수익을 보장하는 매매 지시가 아닙니다"],
"err.notFound": ["未找到该内容或数据已过期", "未找到該內容或資料已過期", "Content not found or expired", "コンテンツが見つからないか期限切れです", "콘텐츠를 찾을 수 없거나 만료되었습니다"],
"err.transFail": ["翻译失败，已回退显示原文", "翻譯失敗，已回退顯示原文", "Translation failed; showing original text", "翻訳に失敗したため原文を表示", "번역 실패, 원문을 표시합니다"],
"err.noData": ["系统不会用模拟数据填充，请稍后刷新重试", "系統不會用模擬資料填充，請稍後刷新重試", "No simulated data is used. Please refresh later.", "模擬データは使用しません。後で更新してください。", "모의 데이터를 사용하지 않습니다. 나중에 새로고침하세요."],
}
# 简繁转换使用下方紧凑「字符对」字典（本地、零依赖、不调 AI）
# 用紧凑「简繁字符对」表覆盖高频字（避免整段文本表体积）
_T_PAIRS = {
"资":"資","讯":"訊","全球":"全球","金融":"金融","情报":"情報","中心":"中心","驾驶":"駕駛","舱":"艙","实时":"即時","资讯":"資訊",
"市场":"市場","监控":"監控","研究":"研究","工作台":"工作台","资产":"資產","系统":"系統","事件":"事件","分析":"分析","地缘":"地緣",
"政治":"政治","产业":"產業","链":"鏈","行业":"行業","社交":"社交","情绪":"情緒","行情":"行情","涨跌":"漲跌","热力":"熱力","图":"圖",
"宏观":"宏觀","经济":"經濟","外汇":"外匯","利率":"利率","商品":"商品","期货":"期貨","数字":"數位","资金":"資金","流向":"流向","基金":"基金",
"公司":"公司","评":"評","分":"分","推荐":"推薦","预测":"預測","成绩":"成績","单":"單","自选":"自選","股":"股","组合":"組合","风险":"風險",
"预警":"預警","数据":"資料","源":"源","管理":"管理","说明":"說明","清单":"清單","术语":"術語","词典":"詞典","搜索":"搜尋","标的":"標的",
"刷新":"刷新","主题":"主題","通知":"通知","语言":"語言","翻译":"翻譯","当前":"目前","页":"頁","易懂":"易懂","模式":"模式","专业":"專業",
"加载":"載入","读取":"讀取","真实":"真實","更新":"更新","来源":"來源","为什么":"為什麼","值得":"值得","关注":"關注","需要":"需要",
"注意":"注意","什么":"什麼","结论":"結論","查看":"查看","详情":"詳情","全部":"全部","返回":"返回","原文":"原文","双语":"雙語","对照":"對照",
"重新":"重新","暂无":"暫無","未接入":"未接入","重要":"重要","等级":"等級","今日":"今日","机会":"機會","领先":"領先","榜":"榜",
"优质":"優質","观察":"觀察","概况":"概況","快讯":"快訊","总结":"總結","一句话":"一句話","三个":"三個","关键":"關鍵","温度":"溫度",
"风险":"風險","构成":"構成","投资":"投資","建议":"建議","延迟":"延遲","不可":"不可","用于":"用於","下单":"下單","历史":"歷史","表现":"表現",
"代表":"代表","未来":"未來","最":"最","赚钱":"賺錢","筛选":"篩選","结果":"結果","保证":"保證","盈利":"盈利","买卖":"買賣","指令":"指令",
"失败":"失敗","回退":"回退","显示":"顯示","模拟":"模擬","填充":"填充","稍后":"稍後","重试":"重試","未找到":"未找到","内容":"內容","过期":"過期",
"个":"個","条":"條","项":"項","类":"類","组":"組","涨":"漲","跌":"跌","红":"紅","绿":"綠","币":"幣","种":"種","时":"時","间":"間",
"数":"數","据":"據","价":"價","额":"額","净":"淨","流入":"流入","成交":"成交","财":"財","务":"務","报":"報","营收":"營收","利润":"利潤",
"现金":"現金","流":"流","负债":"負債","率":"率","估值":"估值","成长":"成長","行业":"行業","景气":"景氣","趋":"趨","势":"勢","动":"動","量":"量",
"周":"週","月":"月","日":"日","年":"年","今":"今","明":"明","后":"後","前":"前","内":"內","外":"外","开":"開","关":"關","启":"啟","停":"停",
"设":"設","置":"置","状态":"狀態","成功":"成功","错误":"錯誤","请":"請","点":"點","击":"擊","可":"可","不":"不","无":"無","有":"有",
"这":"這","为":"為","与":"與","从":"從","对":"對","将":"將","并":"並","或":"或","及":"及","等":"等","中":"中","文":"文","简":"簡","繁":"繁",
"体":"體","译":"譯","原":"原","双":"雙","语":"語","对":"對","照":"照","词":"詞","典":"典","解":"解","释":"釋","规":"規","则":"則","级":"級",
"别":"別","标":"標","签":"籤","说":"說","明":"明","义":"義","义":"義","数":"數","值":"值","高":"高","低":"低","通":"通","常":"常",
"货":"貨","币":"幣","盘":"盤","面":"面","简":"簡","报":"報","引":"引","用":"用","编":"編","号":"號","来":"來","源":"源","链":"鏈","接":"接",
}
_T_PHRASES = {k: v for k, v in _T_PAIRS.items() if len(k) > 1}
_T_MAP = {ord(k): v for k, v in _T_PAIRS.items() if len(k) == 1}

# ---------------- 术语词典 ----------------
GLOSSARY = {
"PE": {"zh": "市盈率", "en": "Price/Earnings", "plain": "投资者愿意为公司每赚 1 元利润支付多少钱。比如 PE=20，就是愿意花 20 元买它每年 1 元的利润。", "use": "粗略判断股价相对利润贵不贵", "high": "偏高可能代表市场期待高成长，也可能是股价偏贵", "low": "偏低可能是便宜，也可能代表市场担心公司前景", "impact": "PE 整体抬升常伴随风险偏好上升；利率上行通常会压低高 PE 成长股", "field": "估值"},
"PB": {"zh": "市净率", "en": "Price/Book", "plain": "股价相对于公司净资产的水平。PB=1 表示股价约等于账面净资产。", "use": "银行、保险等资产型公司常用", "high": "可能代表品牌/技术等无形资产价值高，或股价偏贵", "low": "可能低估，也可能资产质量有问题", "impact": "破净（PB<1）常引发对资产质量的讨论", "field": "估值"},
"PS": {"zh": "市销率", "en": "Price/Sales", "plain": "市值除以营业收入，用于还没稳定盈利的成长公司。", "use": "亏损期公司估值参考", "high": "市场给的收入溢价高", "low": "收入估值偏低", "impact": "收入增速变化时 PS 敏感", "field": "估值"},
"EV/EBITDA": {"zh": "企业价值倍数", "en": "EV/EBITDA", "plain": "把公司整体价值（含债务）与息税折旧摊销前利润比较，比 PE 更适合比较负债不同的公司。", "use": "跨资本结构比较", "high": "整体估值偏贵", "low": "整体估值偏低", "impact": "并购定价常用", "field": "估值"},
"ROE": {"zh": "净资产收益率", "en": "Return on Equity", "plain": "公司用股东的钱赚钱的能力。ROE=15% 表示每 100 元股东权益一年赚约 15 元。", "use": "衡量盈利质量", "high": "通常代表竞争优势强，但高负债也会推高 ROE", "low": "赚钱效率偏弱", "impact": "长期高 ROE 常是优质公司的特征之一", "field": "盈利能力"},
"CPI": {"zh": "居民消费价格指数", "en": "Consumer Price Index", "plain": "一篮子日常消费品的价格变化，用来衡量通货膨胀。", "use": "观察物价与货币政策", "high": "通胀压力上升，央行可能加息", "low": "需求偏弱，甚至有通缩风险", "impact": "高于预期常压制债券与高估值成长股", "field": "宏观"},
"PPI": {"zh": "工业生产者出厂价格指数", "en": "Producer Price Index", "plain": "工厂出厂价的变化，常是 CPI 的先行信号。", "use": "观察上游成本", "high": "成本上升，可能挤压中下游利润", "low": "工业需求偏弱", "impact": "影响周期股与制造业毛利", "field": "宏观"},
"PMI": {"zh": "采购经理指数", "en": "Purchasing Managers' Index", "plain": "问企业采购经理「这个月比上月好不好」，50 是荣枯线。", "use": "观察经济景气", "high": "高于 50 表示扩张", "low": "低于 50 表示收缩", "impact": "影响周期股、工业品与汇率预期", "field": "宏观"},
"GDP": {"zh": "国内生产总值", "en": "Gross Domestic Product", "plain": "一个国家一年创造的最终商品与服务总价值。", "use": "衡量经济总量与增速", "high": "增长强劲", "low": "增长放缓或衰退", "impact": "影响企业盈利预期与央行政策", "field": "宏观"},
"Treasury Yield": {"zh": "美国国债收益率", "en": "Treasury Yield", "plain": "买美国国债能拿到的年化回报，是全球资产定价的「地板」。", "use": "无风险利率基准", "high": "抬高贴现率，压制高估值股票", "low": "流动性宽松，利好风险资产", "impact": "10Y-2Y 倒挂常被视为衰退信号之一", "field": "利率"},
"10Y-2Y": {"zh": "美债期限利差", "en": "10Y-2Y Spread", "plain": "10 年期减 2 年期国债收益率。为正说明长期回报更高；为负叫「倒挂」。", "use": "观察衰退预期", "high": "曲线陡峭，增长预期强", "low": "倒挂，市场担心未来经济走弱", "impact": "影响银行股与周期股", "field": "利率"},
"Put/Call": {"zh": "看跌/看涨期权比率", "en": "Put/Call Ratio", "plain": "买保险（看跌）的人相对买上涨（看涨）的人有多少。", "use": "观察市场避险情绪", "high": "避险需求强，情绪偏谨慎", "low": "情绪偏乐观", "impact": "极端值有时是反向指标，不能单独作结论", "field": "衍生品"},
"FRED": {"zh": "美联储经济数据库", "en": "Federal Reserve Economic Data", "plain": "美国圣路易斯联储公开的宏观数据集合，本站 CPI、失业率、利率序列都来自它。", "use": "官方宏观数据来源", "high": "-", "low": "-", "impact": "统计发布值，不是实时行情", "field": "数据源"},
"RSI": {"zh": "相对强弱指标", "en": "Relative Strength Index", "plain": "衡量最近涨跌力道，0–100。一般 70 以上算超买、30 以下算超卖。", "use": "观察短期过热/过冷", "high": ">70 超买，回撤风险上升", "low": "<30 超卖", "impact": "只是力道指标，不代表一定反转", "field": "技术"},
"MACD": {"zh": "指数平滑异同移动平均线", "en": "MACD", "plain": "用两条不同速度的平均线差值观察趋势变化。", "use": "趋势与动能", "high": "正值代表短期均线在长期均线上方", "low": "负值代表动能转弱", "impact": "滞后指标，需配合其他信号", "field": "技术"},
"MA20": {"zh": "20 日均线", "en": "20-day Moving Average", "plain": "最近 20 个交易日收盘价的平均，常用来看一个月趋势。", "use": "趋势参考", "high": "价在均线上方，短期偏强", "low": "价在均线下方，短期偏弱", "impact": "均线不是支撑位的保证", "field": "技术"},
"Max Drawdown": {"zh": "最大回撤", "en": "Max Drawdown", "plain": "从阶段最高点跌到最低点最多亏了多少，用来衡量「最难受的时候有多难受」。", "use": "风险度量", "high": "绝对值大代表波动剧烈", "low": "走势相对平稳", "impact": "决定仓位与心理承受度", "field": "风险"},
"Volatility": {"zh": "年化波动率", "en": "Annualized Volatility", "plain": "把每日涨跌的剧烈程度换算成一整年的波动幅度。", "use": "风险度量", "high": "价格上蹿下跳", "low": "走势平缓", "impact": "高波动品种需要更小的仓位", "field": "风险"},
"COT": {"zh": "交易者持仓报告", "en": "Commitments of Traders", "plain": "美国监管公布的期货持仓周报。", "use": "观察大类资金仓位", "high": "-", "low": "-", "impact": "**周频且有滞后，不是实时持仓**", "field": "风险"},
"HICP": {"zh": "调和消费者物价指数", "en": "Harmonised Index of Consumer Prices", "plain": "欧元区统一口径的通胀指标。", "use": "ECB 货币政策参考", "high": "通胀压力", "low": "需求偏弱", "impact": "影响欧元汇率与欧债", "field": "宏观"},
"XBRL": {"zh": "可扩展商业报告语言", "en": "eXtensible Business Reporting Language", "plain": "上市公司财报的结构化数据格式，本站 SEC 财务事实直接读它。", "use": "财务数据标准化", "high": "-", "low": "-", "impact": "官方原始申报值，未经过分析师调整", "field": "数据源"},
"ETF": {"zh": "交易型开放式指数基金", "en": "Exchange Traded Fund", "plain": "像股票一样能买卖的一篮子资产。", "use": "分散配置", "high": "-", "low": "-", "impact": "本站暂未接入 ETF 持仓与净值数据", "field": "产品"},
"stale": {"zh": "数据陈旧标记", "en": "Stale data", "plain": "本次刷新失败，展示的是上次成功抓取的真实数据，并明确标注。", "use": "降级提示", "high": "-", "low": "-", "impact": "绝不用模拟值补位", "field": "数据口径"},
}
PRIORITY_RULES = {
"P1": {"name": "重大信息", "desc": "可能影响全球市场、主要资产或重要政策",
       "rule": "官方/监管/交易所/央行来源，或标题命中系统级关键词（利率决议、CPI、战争、制裁、系统性风险）",
       "examples": ["央行利率决议", "证监会/SEC 监管公告", "主要经济体 CPI/GDP", "战争与制裁"]},
"P2": {"name": "重要信息", "desc": "可能影响特定行业、国家或公司",
       "rule": "专业财经媒体来源，或标题命中行业/公司级关键词（财报、并购、产品发布、产业政策）",
       "examples": ["龙头公司财报", "行业政策", "大额订单", "大宗商品供需"]},
"P3": {"name": "一般信息", "desc": "具有参考价值，但短期影响相对有限",
       "rule": "社区/社交/评论类来源，或未命中上述关键词的一般报道",
       "examples": ["市场评论", "观点文章", "社交讨论"]},
}
_P1_KW = re.compile(r"fed|fomc|cpi|inflation|rate decision|央行|利率决议|加息|降息|通胀|战争|制裁|war|sanction|tariff|关税|recession|衰退|崩盘|crash|emergency|紧急", re.I)
_P2_KW = re.compile(r"earnings|revenue|guidance|merger|acquisition|ipo|财报|营收|并购|收购|订单|产能|政策|oil|opec|芯片|半导体|财报", re.I)
_P1_SOURCE = re.compile(r"sec\.gov|federalreserve|ecb\.europa|pbc\.gov|csrc|gov\.cn|treasury|bls\.gov|eia\.gov|wto\.org|boj", re.I)


def init(cfg):
    global CFG, CACHE, LOADED
    CFG = cfg
    try:
        CACHE = json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:
        CACHE = {}
    LOADED = True
    return {"langs": LANGS, "ui_keys": len(_UI), "glossary_terms": len(GLOSSARY),
            "cache_entries": len(CACHE)}


def dictionary(lang):
    if lang not in LANGS:
        lang = "zh-CN"
    idx = SUPPORTED.index(lang)
    out = {k: v[idx] for k, v in _UI.items()}
    out["_meta"] = {"lang": lang, "name": LANGS[lang], "total_keys": len(_UI),
                    "coverage": "全站固定文案词典；动态内容按需 AI 翻译并缓存",
                    "fallback": "未命中词条回退简体中文原文"}
    return out


def priority_of(item):
    """明确规则产生的等级，返回 (等级, 理由, 命中项)。不改变原有 priority 字段，只增加可解释性。"""
    title, src, link = item.get("title") or "", item.get("source") or "", item.get("link") or ""
    hits = []
    if _P1_SOURCE.search(link + " " + src):
        hits.append("官方/监管来源")
    if _P1_KW.search(title):
        hits.append("系统级关键词：" + (_P1_KW.search(title).group(0)))
    if hits:
        return "P1", "命中 P1 规则（" + "；".join(hits) + "）", hits
    h2 = _P2_KW.search(title)
    if h2:
        return "P2", "命中 P2 规则（行业/公司级关键词：" + h2.group(0) + "）", [h2.group(0)]
    if re.search(r"reddit|forum|社区|论坛|opinion|评论", (link + src), re.I):
        return "P3", "命中 P3 规则（社区/评论类来源，短期影响有限）", ["社区/评论来源"]
    return "P2", "命中 P2 规则（专业财经媒体一般报道）", ["专业媒体"]


def priority_definition():
    return {"levels": PRIORITY_RULES,
            "model": "规则模型：来源分级（官方>专业媒体>社区）+ 标题关键词分级（系统级>行业公司级>一般）；先判 P1 再判 P2 最后 P3",
            "note": "等级仅表示「信息潜在影响范围」，不代表涨跌方向，也不代表投资建议；每条新闻在详情页显示具体命中规则"}


def glossary(term=None, q=None):
    if term:
        t = GLOSSARY.get(term.upper()) or GLOSSARY.get(term)
        if not t:
            return {"error": "词典中暂无该术语", "term": term, "available": sorted(GLOSSARY)[:20]}
        return {"term": term, **t}
    items = [{"term": k, **v} for k, v in GLOSSARY.items()]
    if q:
        items = [x for x in items if q.lower() in (x["term"] + x["zh"] + x["plain"]).lower()]
    return {"items": items, "total": len(GLOSSARY),
            "fields": sorted(set(v["field"] for v in GLOSSARY.values())),
            "note": "点击/悬停可看解释；手机端点击即可；数值高低含义为通俗说明，不构成投资建议"}


# ---------------- 动态翻译 ----------------
_PROTECT = [
    re.compile(r"https?://[^\s\"'<>]+"),
    re.compile(r"\b[A-Z]{1,6}(?:\.[A-Z]{2,3})?(?:-\w+)?\b"),          # 股票代码 / 缩写
    re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?"),                # 日期
    re.compile(r"[+\-]?\d[\d,]*(?:\.\d+)?\s*(?:%|％|元|美元|USD|CNY|HKD|EUR|JPY|KRW|TWD|亿元|万亿|基点|bp|B|M|K)?"),
]
_PLACE = "⟦{}⟧"


def protect(text):
    tokens = []
    def sub(m):
        tokens.append(m.group(0))
        return _PLACE.format(len(tokens) - 1)
    out = str(text or "")
    for pat in _PROTECT:
        out = pat.sub(sub, out)
    return out, tokens


def restore(text, tokens):
    out = str(text or "")
    for i, t in enumerate(tokens):
        out = out.replace(_PLACE.format(i), t)
        out = out.replace("⟦%d⟧" % i, t)
    return out


def _llm_translate(masked, target, force=False):
    llm = CFG.get("llm", {}) or {}
    if not llm.get("enabled"):
        return None, "AI 未启用"
    base = (llm.get("base_url") or "").rstrip("/")
    models = [m for m in (llm.get("models") or [llm.get("model", "auto")]) if m != "auto"] or ["auto"]
    names = {"en": "English", "ja": "Japanese", "ko": "Korean", "zh-TW": "Traditional Chinese"}
    sys = ("You are a financial translator. Translate ONLY into %s. "
           "Never change, remove or add any placeholder like ⟦0⟧, and never alter numbers, "
           "tickers, currency codes, dates or URLs. Keep it faithful and concise. "
           "Output the translation only, no notes, no markdown." % names.get(target, target))
    for model in models[:3]:
        payload = {"model": model, "messages": [{"role": "system", "content": sys},
                                                {"role": "user", "content": masked}],
                   "temperature": 0.1, "max_tokens": 900}
        req = urllib.request.Request(base + "/chat/completions",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + (llm.get("api_key") or "")})
        try:
            # 内网 AI 强制直连，不经外网代理
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with op.open(req, timeout=llm.get("timeout", 40)) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
            t = (d["choices"][0]["message"]["content"] or "").strip()
            t = re.sub(r"^```[a-z]*|```$", "", t, flags=re.M).strip().replace("**", "")
            if t and len(t) < 6000:
                return t, None
        except Exception as e:
            last = str(e)[:100]
    return None, "上游翻译失败：" + locals().get("last", "无可用模型")


def _cache_get(k):
    with LOCK:
        return CACHE.get(k)


def _cache_put(k, v):
    with LOCK:
        CACHE[k] = {"text": v, "ts": int(time.time())}
        if len(CACHE) > 3000:
            for kk in sorted(CACHE, key=lambda x: CACHE[x]["ts"])[:500]:
                CACHE.pop(kk, None)
        try:
            with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(CACHE, f, ensure_ascii=False)
            os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        except Exception:
            pass


def translate(text, target="zh-CN", force=False):
    """单条翻译。返回 {text, original, cached, fallback, reason, preserved}"""
    src = str(text or "")
    if not src.strip():
        return {"text": "", "original": src, "lang": target, "cached": False, "fallback": False, "preserved": True}
    if target == "zh-CN":
        return {"text": src, "original": src, "lang": target, "cached": False, "fallback": False, "preserved": True}
    key = hashlib.sha256((target + "|" + src).encode("utf-8")).hexdigest()
    if not force:
        c = _cache_get(key)
        if c:
            return {"text": c["text"], "original": src, "lang": target, "cached": True,
                    "fallback": False, "preserved": True}
    if target == "zh-TW":
        out = src
        for k, v in sorted(_T_PHRASES.items(), key=lambda x: -len(x[0])):
            out = out.replace(k, v)
        out = out.translate(_T_MAP)
        return {"text": out, "original": src, "lang": target, "cached": False,
                "fallback": False, "preserved": True, "engine": "本地简繁字典（不调用 AI）"}
    masked, tokens = protect(src)
    t, err = _llm_translate(masked, target, force)
    if not t:
        return {"text": src, "original": src, "lang": target, "cached": False,
                "fallback": True, "reason": err, "preserved": True}
    out = restore(t, tokens)
    # 关键校验：所有被保护的金融信息必须原样出现，否则判失败回退原文
    missing = [x for x in tokens if len(x) >= 2 and x not in out]
    if missing:
        return {"text": src, "original": src, "lang": target, "cached": False,
                "fallback": True, "preserved": False,
                "reason": "译文未保留关键数字/代码/时间，已回退原文；缺失 %d 项" % len(missing)}
    _cache_put(key, out)
    return {"text": out, "original": src, "lang": target, "cached": False,
            "fallback": False, "preserved": True, "engine": "freellmapi（内网 AI）"}


def translate_batch(items, target="en", fields=("title", "summary"), limit=8):
    out = []
    for it in list(items or [])[:limit]:
        rec = dict(it)
        for f in fields:
            if it.get(f):
                rec[f + "_translated"] = translate(it[f], target)
        rec["original"] = {f: it.get(f) for f in fields}
        rec["lang"] = target
        out.append(rec)
    return {"items": out, "total": len(out), "lang": target,
            "note": "固定文案走本地词典；动态内容按需 AI 翻译并缓存；失败自动回退原文",
            "cache_entries": len(CACHE)}


def stats():
    return {"langs": LANGS, "ui_keys": len(_UI), "glossary_terms": len(GLOSSARY),
            "cache_entries": len(CACHE), "protected_patterns": len(_PROTECT),
            "static_only_langs": ["zh-CN", "zh-TW"],
            "note": "简繁用本地字典；英日韩动态内容走内网 AI 翻译，结果磁盘缓存；页面固定文案永不调用 AI"}
