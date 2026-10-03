/* This demo is entirely local: no API calls, persistence, subscriptions, or email. */
(() => {
  'use strict';
  const translations = {
    'zh-CN': {
      costNotice:'实际简报依赖大模型，需配置模型服务。Token/API 费用取决于服务商、文献数量与文本长度；本合成演示不调用 API，不产生模型费用。',skip:'跳至文献预览',brandCaption:'你的开放科研简报',eyebrow:'OPEN SOURCE · 为持续探索而生',
      heroLine1:'跟上研究，',heroLine2:'留住思考的时间。',heroDescription:'把关注的主题，变成一份有出处、有脉络的文献简报。先看全貌，再深入值得读的每一篇。',
      readDemo:'阅读示例简报',getStarted:'开始自托管',heroFootnote:'免费开源 · 无需注册即可体验 · 不收集邮箱',
      previewEyebrow:'RESEARCH BRIEF / 阅读路径',sample:'合成示例',previewTitle:'从一片森林，看到两个研究视角',topicBvoc:'森林 BVOC 与胁迫响应',topicCanopy:'树种识别与遥感',previewBvoc:'机制、树种差异与实验边界',previewCanopy:'光谱、冠层结构与模型泛化',previewBottom:'主题概览 → 结构化解读 → 证据出处',
      philosophyLabel:'WHY WE BUILD / 我们相信',philosophy:'我们相信，在知识爆炸、信息产生与传播的速度远超阅读与消化能力的时代，借助工具高效获取信息至关重要。我们应把宝贵的神经元留给更关键的信息，做出更重要的判断。',
      featureSources:'多源发现',featureEvidence:'回到证据',featureEvidenceDetail:'逐条结论，保留原文依据',featureSchedule:'按你的节奏',featureScheduleDetail:'主题、时间与中英文输出',
      digestEyebrow:'THE READING ROOM / 在线演示',digestTitle:'一份简报，如何呈现？',emailPreview:'查看邮件原版',demoNoticeTitle:'这是合成演示，不是真实科研结论。',demoNotice:'所有论文、作者、日期与研究数据均为虚构，仅用于展示版式和证据结构。此页面不检索文献、不调用模型、不保存设置，也不发送邮件。',
      overviewEyebrow:'01 / 研究概览',fixedFixture:'固定合成样本',overviewTitle:'把单篇发现，放回研究语境。',overviewScope:'2 篇合成样本 · 2 个主题',overviewDate:'固定示例日期：2026-10-03',papersTitle:'逐篇阅读',referencesTitle:'引用与证据',auditLink:'查看完整 JSON ↗',referencesNotice:'编号在整份简报中保持一致。以下记录均为本地合成样本，不对应真实发表论文。',
      previewOnly:'仅界面预览',configTitle:'你的阅读偏好',configDescription:'试着切换主题与语言，看看简报的阅读方式。',topicLabel:'关注主题',allTopics:'全部示例主题',scheduleLabel:'投递频率示意',daily:'每天',weekdays:'每个工作日',weekly:'每周一',timeLabel:'时间示意',timezoneLabel:'时区示意',languageLabel:'输出语言',configDisclaimer:'以上操作仅改变本页演示，不会创建订阅或定时任务。实际使用需部署后端、配置检索网络、兼容模型接口与 SMTP。支持配置兼容的国内模型服务，具体服务需自行验证。',setupGuide:'查看部署说明',readingNoteLabel:'一个小原则',readingNote:'好的科研简报，不只告诉你发现了什么，也告诉你证据止于何处。',
      ctaTitle:'让下一次阅读，从好问题开始。',ctaText:'把仓库交给你的编程 Agent 协助部署，或按文档手动配置。源码与证据结构都保持开放。',viewSource:'查看 GitHub 源码',footerTagline:'少一点噪声，多一点理解。',security:'安全说明',feedback:'反馈',
      highlights:'核心亮点',question:'科学问题',methods:'实验或模型方法',findings:'主要结果',evidenceToggle:'展开结论与原文证据',evidenceNotice:'以下原文同样来自合成样本，并非真实论文。',evidenceLabel:'合成原文',referenceLabel:'引用编号',count:'篇合成示例',schedulePreview:'预览：',notScheduled:'（未启用）',missingTime:'请选择时间',exportNotice:'导入演示文献：',exportRis:'下载 RIS',exportBib:'下载 BibTeX'
    },
    en: {
      costNotice:'Real digests require a configured language model. Token/API fees depend on your provider, paper count, and text length. This synthetic demo makes no API calls and incurs no model fees.',skip:'Skip to the digest',brandCaption:'Your open research brief',eyebrow:'OPEN SOURCE · STAY CURIOUS',
      heroLine1:'Keep up with research.',heroLine2:'Make room to think.',heroDescription:'Turn the topics you care about into a research brief with context and traceable evidence. See the bigger picture, then dive into the papers that matter.',
      readDemo:'Explore the demo',getStarted:'Self-host your own',heroFootnote:'Open source · No account needed to explore · No email collected',
      previewEyebrow:'RESEARCH BRIEF / READING PATH',sample:'Synthetic demo',previewTitle:'One forest. Two research perspectives.',topicBvoc:'Forest BVOCs & stress',topicCanopy:'Tree species & remote sensing',previewBvoc:'Mechanisms, species differences, experimental scope',previewCanopy:'Spectra, canopy structure, model generalization',previewBottom:'Research context → Structured analysis → Evidence',
      philosophyLabel:'WHY WE BUILD / OUR BELIEF',philosophy:'We believe that when knowledge grows and information travels faster than we can read and absorb it, tools for finding information efficiently are essential. We should save our precious neurons for the information that matters most, and for making more important judgments.',
      featureSources:'Discover across sources',featureEvidence:'Return to the evidence',featureEvidenceDetail:'Source passages behind individual claims',featureSchedule:'Read at your own pace',featureScheduleDetail:'Your topics, timing, and output language',
      digestEyebrow:'THE READING ROOM / LIVE DEMO',digestTitle:'What does a research brief look like?',emailPreview:'Original email layout',demoNoticeTitle:'Synthetic demonstration, not real research findings.',demoNotice:'All papers, authors, dates, and data are invented to demonstrate layout and evidence structure. This page retrieves no literature, calls no model, saves no settings, and sends no email.',
      overviewEyebrow:'01 / RESEARCH CONTEXT',fixedFixture:'Fixed synthetic samples',overviewTitle:'Put individual findings in context.',overviewScope:'2 synthetic papers · 2 topics',overviewDate:'Fixed sample date: 2026-10-03',papersTitle:'A closer look',referencesTitle:'References & evidence',auditLink:'Full evidence JSON ↗',referencesNotice:'Reference numbers stay consistent throughout the brief. These locally authored synthetic records do not correspond to published papers.',
      previewOnly:'Preview only',configTitle:'Your reading preferences',configDescription:'Explore topics and languages to see how a brief reads.',topicLabel:'Research topic',allTopics:'All demo topics',scheduleLabel:'Illustrative frequency',daily:'Every day',weekdays:'Every weekday',weekly:'Every Monday',timeLabel:'Example time',timezoneLabel:'Example timezone',languageLabel:'Output language',configDisclaimer:'These controls only change this demo. They do not create a subscription or scheduled task. Real use requires a deployed backend, retrieval access, a compatible model endpoint, and SMTP. Compatible domestic Chinese model services can be configured; verify your chosen provider separately.',setupGuide:'Read the setup guide',readingNoteLabel:'A SMALL PRINCIPLE',readingNote:'A useful research brief shows not just what was found, but where the evidence ends.',
      ctaTitle:'Start your next reading session with a better question.',ctaText:'Give the repository to your coding agent for setup help, or configure it manually. The source and evidence structure stay open.',viewSource:'Explore the GitHub project',footerTagline:'Less noise. More understanding.',security:'Security',feedback:'Feedback',
      highlights:'Core highlights',question:'Scientific question',methods:'Experimental or model methods',findings:'Main results',evidenceToggle:'Expand claims and source evidence',evidenceNotice:'These source passages are also synthetic, not excerpts from real papers.',evidenceLabel:'SYNTHETIC SOURCE',referenceLabel:'Reference',count:'synthetic papers',schedulePreview:'Preview: ',notScheduled:'(not enabled)',missingTime:'Choose a time',exportNotice:'Import the demo records:',exportRis:'Download RIS',exportBib:'Download BibTeX'
    }
  };
  const byId = id => document.getElementById(id);
  let language = new URLSearchParams(window.location.search).get('lang') === 'en' ? 'en' : 'zh-CN';
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function renderOverview() {
    const target = byId('overview-content');
    target.replaceChildren();
    for (const paragraph of window.PAPER_TRACKER_DEMO[language].overview.paragraphs) {
      const p = element('p');
      for (const sentence of paragraph.sentences) {
        p.append(document.createTextNode(sentence.text));
        for (const citation of sentence.citations) {
          const link = element('a', 'citation', `[${citation.ref}]`);
          link.href = `#reference-${citation.ref}`;
          link.setAttribute('aria-label', `${translations[language].referenceLabel} ${citation.ref}`);
          link.title = citation.evidence;
          p.append(link);
        }
        p.append(document.createTextNode(' '));
      }
      target.append(p);
    }
  }
  function renderPapers() {
    const t = translations[language];
    const dataset = window.PAPER_TRACKER_DEMO[language];
    const topic = byId('topic').value;
    const selected = dataset.papers.map((paper, i) => ({ paper, number: i + 1 }))
      .filter(({ paper }) => topic === 'all' || (topic === 'bvoc' ? paper.source_id === 'forest-bvoc' : paper.source_id === 'canopy-species'));
    const countLabel = language === 'en' && selected.length === 1 ? 'synthetic paper' : t.count;
    byId('paper-count').textContent = `${selected.length} ${countLabel}`;
    const list = byId('paper-list');
    list.replaceChildren();
    for (const { paper, number } of selected) {
      const card = element('article', 'paper-card');
      card.id = `paper-${number}`;
      const top = element('div', 'paper-topline');
      const label = element('span', 'topic-label');
      label.append(element('span', 'status-dot'), document.createTextNode(paper.source_id === 'forest-bvoc' ? t.topicBvoc : t.topicCanopy));
      top.append(label, element('span', 'paper-number', String(number).padStart(2, '0')));
      card.append(top);
      const title = element('h3', '', paper.title.replace(/^\[.*?\]\s*/, ''));
      card.append(title);
      const meta = element('p', 'paper-meta');
      meta.append(element('span', 'synthetic-badge', t.sample), document.createTextNode(`${paper.authors.join(' · ')} · ${paper.publication_date}`));
      card.append(meta);
      for (const key of ['highlights', 'question', 'methods', 'findings']) {
        const section = element('div', 'paper-section');
        section.append(element('h4', '', t[key]));
        const statements = element('ul');
        for (const item of paper.analysis.fields[key]) statements.append(element('li', '', item.text));
        section.append(statements);
        card.append(section);
      }
      const details = element('details', 'evidence-details');
      details.append(element('summary', '', t.evidenceToggle), element('p', 'muted', t.evidenceNotice));
      for (const [key, items] of Object.entries(paper.analysis.fields)) {
        for (const item of items) {
          const evidence = element('div', 'evidence-item');
          evidence.append(element('span', 'evidence-label', t[key]), element('p', '', item.text), element('span', 'evidence-label', t.evidenceLabel), element('p', 'evidence-quote', item.evidence));
          details.append(evidence);
        }
      }
      card.append(details);
      list.append(card);
    }
    const refs = byId('reference-list');
    refs.replaceChildren();
    // The complete global reference list remains visible even when cards are filtered.
    dataset.papers.forEach((paper, i) => {
      const item = element('li');
      item.id = `reference-${i + 1}`;
      item.append(element('span', 'reference-title', paper.title), document.createTextNode(`${paper.journal}. ${paper.publication_date}. ${paper.kind}.`));
      refs.append(item);
    });
  }
  function renderSchedule() {
    const t = translations[language];
    const time = byId('time').value || t.missingTime;
    byId('schedule-summary').textContent = `${t.schedulePreview}${t[byId('schedule').value]} · ${time} · ${byId('timezone').value} ${t.notScheduled}`;
  }
  function setLanguage(next) {
    language = next === 'en' ? 'en' : 'zh-CN';
    document.documentElement.lang = language;
    document.title = language === 'en' ? 'Paper Tracker · Research, with context.' : 'Paper Tracker · 留住思考的时间';
    for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = translations[language][node.dataset.i18n];
    for (const button of document.querySelectorAll('[data-language]')) {
      const active = button.dataset.language === language;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    }
    byId('output-language').value = language;
    byId('email-preview-link').href = `preview/demo.${language}.html`;
    byId('audit-link').href = `preview/demo.${language}.json`;
    byId('ris-link').href = `preview/demo.${language}.ris`;
    byId('bib-link').href = `preview/demo.${language}.bib`;
    renderOverview();
    renderPapers();
    renderSchedule();
  }
  for (const button of document.querySelectorAll('[data-language]')) button.addEventListener('click', () => setLanguage(button.dataset.language));
  byId('output-language').addEventListener('change', event => setLanguage(event.target.value));
  byId('topic').addEventListener('change', renderPapers);
  for (const id of ['schedule','time','timezone']) byId(id).addEventListener('change', renderSchedule);
  byId('time').addEventListener('input', renderSchedule);
  setLanguage(language);
})();
