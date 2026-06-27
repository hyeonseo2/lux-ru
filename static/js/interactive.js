const ACCOUNT_LABEL_MAP = {
  taxable: '주식계좌',
  pension_saving: '연금저축',
  isa: 'ISA',
  irp: 'IRP',
  deposit: '예수금/입출금',
  etc: '기타',
};

const SAMPLE_POSITIONS = [
  { ticker: '005930', name: '삼성전자', amount: 12400000, accountType: 'taxable', accountLabel: '주식계좌' },
  { ticker: '000660', name: 'SK하이닉스', amount: 4350000, accountType: 'taxable', accountLabel: '주식계좌' },
  { ticker: '091160', name: 'KODEX 반도체', amount: 8120000, accountType: 'taxable', accountLabel: '주식계좌' },
  { ticker: 'NVDA', name: '엔비디아', amount: 11900000, accountType: 'taxable', accountLabel: '주식계좌' },
  { ticker: 'QQQ', name: 'QQQ', amount: 6780000, accountType: 'pension_saving', accountLabel: '연금저축' },
  { ticker: 'SCHD', name: 'SCHD', amount: 3900000, accountType: 'pension_saving', accountLabel: '연금저축' },
  { ticker: '273130', name: 'KODEX 종합채권', amount: 2100000, accountType: 'isa', accountLabel: 'ISA' },
];

const GAMES = {
  buy_sell: {
    title: '군중 트레이더',
    role: 'Hybrid Game Master',
    avatar: '群',
    avatarClass: 'trader',
    eyebrow: 'Buy/Sell Hybrid Agent',
    intro: '먼저 3턴 매매 본능 테스트를 진행합니다. 게임이 끝난 뒤 GM과 결과를 대화로 해석합니다.',
  },
  balance: {
    title: '짓궂은 진행자',
    role: 'Turn Game Master',
    avatar: '↔',
    avatarClass: 'balance',
    eyebrow: 'Balance Turn Agent',
    intro: '양자택일을 피할 수 없습니다. 먼저 끌리는 선택과 이유를 말해 주세요.',
  },
  saju: {
    title: '투자 사주 도사',
    role: 'Persona Game Master',
    avatar: '道',
    avatarClass: 'saju',
    eyebrow: 'Saju Persona Agent',
    intro: '생년월일과 시간을 입력해 간단 만세력을 만든 뒤, 자기 인식과 실제 행동의 괴리를 봅니다.',
  },
};

const PERSONA_ART = {
  buy_sell: `
    <span class="portrait-market-line"></span>
    <span class="portrait-head"><i></i></span>
    <span class="portrait-body"></span>
    <span class="portrait-screen"><b></b><b></b><b></b></span>
    <span class="portrait-badge">GM</span>
  `,
  balance: `
    <span class="portrait-scale"><i></i><i></i><b></b></span>
    <span class="portrait-head"><i></i></span>
    <span class="portrait-body"></span>
    <span class="portrait-choice left">A</span>
    <span class="portrait-choice right">B</span>
  `,
  saju: `
    <span class="portrait-orbit"></span>
    <span class="portrait-head"><i></i></span>
    <span class="portrait-body"></span>
    <span class="portrait-scroll"><b></b><b></b><b></b></span>
    <span class="portrait-moon"></span>
  `,
};

const BALANCE_QUESTIONS = [
  {
    title: '둘 중 하나만 고른다면?',
    left: { label: '넓게 분산할래요', signal: { diversification: -4, stability_growth: -2, time_horizon: -1 } },
    right: { label: '확신 종목에 집중할래요', signal: { diversification: 4, stability_growth: 3, risk_tolerance: 2 } },
  },
  {
    title: '급락장에서 더 가까운 선택은?',
    left: { label: '목표 비중대로 조정할래요', signal: { behavior_bias: -3, diversification: -2 } },
    right: { label: '뉴스를 더 보고 결정할래요', signal: { behavior_bias: 3, time_horizon: 2 } },
  },
  {
    title: '기대수익과 안정성 중 우선순위는?',
    left: { label: '수익 낮아도 편한 게 좋아요', signal: { stability_growth: -4, risk_tolerance: -2 } },
    right: { label: '흔들려도 성장 기회를 볼래요', signal: { stability_growth: 4, risk_tolerance: 3 } },
  },
];

const SAJU_PROMPTS = [
  {
    title: '투자 사주 첫 괘',
    text: '만세력으로 본 기질과 스스로 믿는 투자 성향이 같은지 봅니다. 당신은 어떤 투자자라고 생각하나요?',
    choices: [
      { label: '장기로 보는 편이에요', message: '저는 장기 가치투자형에 가깝다고 생각해요. 급등락에는 크게 흔들리고 싶지 않습니다.', signal: { time_horizon: -4, behavior_bias: -2 } },
      { label: '기회 보이면 빨리 움직여요', message: '기회가 보이면 빠르게 움직이는 편이에요. 놓치는 게 더 싫습니다.', signal: { risk_tolerance: 3, behavior_bias: 4, time_horizon: 4 } },
      { label: '현금흐름이 더 편해요', message: '안정적인 현금흐름과 배당을 더 믿는 편입니다.', signal: { risk_tolerance: -2, stability_growth: -4, sector_tags: ['배당/방어'] } },
    ],
  },
  {
    title: '오행으로 보는 섹터 기질',
    text: '어떤 섹터 이야기를 들을 때 마음이 먼저 움직이나요?',
    choices: [
      { label: 'AI/반도체가 끌려요', message: 'AI와 반도체 같은 성장 섹터를 보면 가장 먼저 관심이 갑니다.', signal: { stability_growth: 4, risk_tolerance: 2, sector_tags: ['기술/성장'] } },
      { label: '금융/배당이 편해요', message: '금융, 배당, 현금흐름이 있는 쪽이 더 편합니다.', signal: { stability_growth: -3, risk_tolerance: -2, sector_tags: ['배당/방어'] } },
      { label: '헬스케어도 끌려요', message: '헬스케어나 바이오처럼 장기 테마가 있는 섹터가 끌립니다.', signal: { time_horizon: -2, stability_growth: 2, sector_tags: ['헬스케어'] } },
    ],
  },
  {
    title: '외면과 내면의 괴리',
    text: '스스로 믿는 투자 스타일과 실제 매매 습관이 다르다고 느낀 적이 있나요?',
    choices: [
      { label: '말보다 행동이 단기예요', message: '말로는 장기투자라고 하지만 실제로는 가격을 자주 보고 빨리 움직입니다.', signal: { behavior_bias: 4, time_horizon: 4 } },
      { label: '생각보다 보수적이에요', message: '공격적으로 투자하고 싶지만 실제로는 손실이 보이면 금방 방어적으로 바뀝니다.', signal: { risk_tolerance: -3, behavior_bias: 2 } },
      { label: '원칙과 행동이 비슷해요', message: '제 생각과 행동은 비교적 일치한다고 느낍니다. 정한 규칙은 지키려 합니다.', signal: { behavior_bias: -3, diversification: -1 } },
    ],
  },
];

const STEMS = ['갑', '을', '병', '정', '무', '기', '경', '신', '임', '계'];
const BRANCHES = ['자', '축', '인', '묘', '진', '사', '오', '미', '신', '유', '술', '해'];
const FIVE_ELEMENTS = {
  갑: '목', 을: '목', 병: '화', 정: '화', 무: '토', 기: '토', 경: '금', 신: '금', 임: '수', 계: '수',
  자: '수', 축: '토', 인: '목', 묘: '목', 진: '토', 사: '화', 오: '화', 미: '토', 신: '금', 유: '금', 술: '토', 해: '수',
};

const state = {
  sessionId: null,
  activeGame: 'buy_sell',
  portfolioPositions: [],
  portfolioAnalysis: null,
  events: [],
  wikis: {},
  report: null,
  startedGames: {},
  lastTurns: { buy_sell: null, balance: null, saju: null },
  messages: { buy_sell: [], balance: [], saju: [] },
  turnByGame: { buy_sell: 0, balance: 0, saju: 0 },
  startedAt: performance.now(),
  instrumentCache: {},
  suggestions: [],
  suggestionSeq: 0,
  chartFrame: null,
  tradeTimer: null,
  trade: createTradeState(),
  saju: { birthDate: '', birthTime: '', calendar: null },
};

const $ = (selector) => document.querySelector(selector);

function createTradeState() {
  return {
    status: 'ready',
    round: 0,
    maxRounds: 3,
    stockName: '',
    initialAsset: 10000000,
    totalAsset: 10000000,
    phase: 'idle',
    basePrice: 50000,
    currentPrice: 50000,
    buyPrice: null,
    buyTime: null,
    buyAtMs: 0,
    startAt: 0,
    timeLimitMs: 10000,
    results: [],
    roundResults: [],
    priceHistory: [],
    timeHistory: [],
    heartRate: 72,
    trend: 0,
    volatility: 0.012,
    hasBought: false,
    hasSold: false,
    roundEnding: false,
    tickTimer: null,
    timerTimer: null,
    nextTimer: null,
    newsTimer: null,
    tauntTimers: [],
    newsFiredCount: 0,
    lastNewsAt: null,
    scenario: null,
    eventLog: [],
  };
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderInlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return html;
}

function splitMarkdownRow(line) {
  return line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function markdownToHtml(markdown) {
  const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
  const html = [];
  let listOpen = false;
  let paragraph = [];

  const closeList = () => {
    if (listOpen) {
      html.push('</ul>');
      listOpen = false;
    }
  };
  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${renderInlineMarkdown(paragraph.join(' '))}</p>`);
      paragraph = [];
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i];
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      closeList();
      continue;
    }
    if (/^\|/.test(line) && lines[i + 1] && isMarkdownTableSeparator(lines[i + 1].trim())) {
      flushParagraph();
      closeList();
      const headers = splitMarkdownRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i].trim())) {
        rows.push(splitMarkdownRow(lines[i].trim()));
        i += 1;
      }
      i -= 1;
      html.push('<div class="md-table-wrap"><table><thead><tr>');
      headers.forEach((header) => html.push(`<th>${renderInlineMarkdown(header)}</th>`));
      html.push('</tr></thead><tbody>');
      rows.forEach((row) => {
        html.push('<tr>');
        headers.forEach((_, index) => html.push(`<td>${renderInlineMarkdown(row[index] || '')}</td>`));
        html.push('</tr>');
      });
      html.push('</tbody></table></div>');
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(heading[1].length + 1, 5);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    if (/^---+$/.test(line)) {
      flushParagraph();
      closeList();
      html.push('<hr>');
      continue;
    }
    const listItem = line.match(/^[-*]\s+(.+)$/);
    if (listItem) {
      flushParagraph();
      if (!listOpen) {
        html.push('<ul>');
        listOpen = true;
      }
      html.push(`<li>${renderInlineMarkdown(listItem[1])}</li>`);
      continue;
    }
    paragraph.push(line);
  }
  flushParagraph();
  closeList();
  return html.join('');
}

function setMarkdownPreview(host, markdown, emptyText) {
  if (!host) return;
  const value = String(markdown || '').trim();
  host.classList.toggle('empty', !value);
  host.classList.add('markdown-rendered');
  host.innerHTML = value ? markdownToHtml(value) : `<p>${escapeHtml(emptyText || '')}</p>`;
}

function formatWon(value) {
  const n = Number(value) || 0;
  if (n >= 100000000) return `${(n / 100000000).toFixed(1).replace(/\.0$/, '')}억`;
  if (n >= 10000) return `${Math.round(n / 10000).toLocaleString('ko-KR')}만`;
  return n.toLocaleString('ko-KR');
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const raw = await response.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch (_) {
    throw new Error('API 응답을 해석하지 못했습니다.');
  }
  if (!response.ok || data.success === false) {
    throw new Error(data.message || data.detail || `API 오류 (${response.status})`);
  }
  return data;
}

function setBusy(button, busy, label) {
  if (!button) return;
  button.disabled = busy;
  if (label) button.textContent = label;
}

function toGamePositions() {
  return state.portfolioPositions.map((p) => ({
    ticker: p.ticker,
    symbol: p.ticker,
    name: p.name,
    amount: Number(p.amount) || 0,
    account_type: p.accountType || 'taxable',
    account_label: p.accountLabel || ACCOUNT_LABEL_MAP[p.accountType] || '주식계좌',
  }));
}

function cacheInstrument(symbol, name) {
  if (!symbol) return;
  state.instrumentCache[String(symbol).toUpperCase()] = name || symbol;
}

function addPosition(position) {
  const ticker = String(position.ticker || position.symbol || '').trim().toUpperCase();
  const amount = Number(position.amount || position.amount_krw || 0);
  if (!ticker || !Number.isFinite(amount) || amount <= 0) return false;
  const accountType = position.accountType || position.account_type || 'taxable';
  const item = {
    ticker,
    name: String(position.name || state.instrumentCache[ticker] || ticker).trim(),
    amount,
    accountType,
    accountLabel: position.accountLabel || position.account_label || ACCOUNT_LABEL_MAP[accountType] || '주식계좌',
  };
  const key = `${item.ticker}__${item.accountType}`;
  if (state.portfolioPositions.some((p) => `${p.ticker}__${p.accountType}` === key)) return false;
  state.portfolioPositions.push(item);
  cacheInstrument(item.ticker, item.name);
  renderPositions();
  return true;
}

function renderPositions() {
  const host = $('#positionList');
  if (!host) return;
  if (!state.portfolioPositions.length) {
    host.innerHTML = '<div class="empty">아직 추가된 보유종목이 없습니다.</div>';
    return;
  }
  host.innerHTML = state.portfolioPositions.map((p, index) => `
    <div class="position-item">
      <div><strong>${escapeHtml(p.name || p.ticker)}</strong><span>${escapeHtml(p.ticker)} · ${escapeHtml(p.accountLabel)}</span></div>
      <b>${formatWon(p.amount)}원</b>
      <button type="button" data-remove-position="${index}">×</button>
    </div>
  `).join('');
  host.querySelectorAll('[data-remove-position]').forEach((button) => {
    button.addEventListener('click', () => {
      state.portfolioPositions.splice(Number(button.dataset.removePosition), 1);
      renderPositions();
    });
  });
}

function loadSamplePortfolio() {
  SAMPLE_POSITIONS.forEach(addPosition);
  setScreenshotStatus('샘플 포트폴리오를 불러왔습니다. 포트폴리오 연결을 눌러 X-Ray를 반영하세요.', 'success');
}

function setScreenshotStatus(text, kind = '') {
  const el = $('#screenshotStatus');
  if (!el) return;
  el.textContent = text || '';
  el.className = `screenshot-status ${kind}`.trim();
}

function renderScreenshotWarnings(warnings) {
  const el = $('#screenshotWarnings');
  if (!el) return;
  if (!Array.isArray(warnings) || !warnings.length) {
    el.innerHTML = '';
    return;
  }
  el.innerHTML = `<ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join('')}</ul>`;
}

async function handleScreenshotFile(file) {
  if (!file) return;
  if (!file.type || !file.type.startsWith('image/')) {
    setScreenshotStatus('이미지 파일만 업로드할 수 있습니다.', 'error');
    return;
  }
  const form = new FormData();
  form.append('file', file);
  setScreenshotStatus('OpenAI vision으로 이미지를 분석 중입니다...');
  renderScreenshotWarnings([]);
  try {
    const response = await fetch('/api/upload/screenshot', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok || !data.success) {
      setScreenshotStatus((data.warnings && data.warnings[0]) || data.detail || '이미지 분석에 실패했습니다.', 'error');
      renderScreenshotWarnings(data.warnings);
      return;
    }
    let added = 0;
    (data.positions || []).forEach((p) => {
      if (addPosition({
        ticker: p.ticker,
        name: p.name,
        amount: p.amount,
        accountType: p.account_type,
        accountLabel: p.account_label,
      })) added += 1;
    });
    setScreenshotStatus(`이미지에서 ${added}개 종목을 추가했습니다.`, 'success');
    renderScreenshotWarnings(data.warnings);
  } catch (error) {
    setScreenshotStatus(`업로드 오류: ${error.message}`, 'error');
  } finally {
    $('#screenshotFileInput').value = '';
  }
}

async function fetchSuggestions(query) {
  const q = String(query || '').trim();
  if (!q) {
    renderSuggestions([]);
    return;
  }
  const seq = ++state.suggestionSeq;
  try {
    const data = await api(`/api/portfolio/search-instruments?q=${encodeURIComponent(q)}&limit=8`);
    if (seq !== state.suggestionSeq) return;
    state.suggestions = (data.results || []).map((item) => ({
      symbol: String(item.symbol || '').toUpperCase(),
      name: item.name_ko || item.name_en || item.name || item.symbol,
      market: item.market || '',
    })).filter((item) => item.symbol);
    state.suggestions.forEach((item) => cacheInstrument(item.symbol, item.name));
    renderSuggestions(state.suggestions);
  } catch (_) {
    renderSuggestions([]);
  }
}

function renderSuggestions(items) {
  const host = $('#tickerSuggest');
  if (!host) return;
  if (!items.length) {
    host.classList.remove('open');
    host.innerHTML = '';
    return;
  }
  host.classList.add('open');
  host.innerHTML = items.map((item) => `
    <button type="button" data-symbol="${escapeHtml(item.symbol)}" data-name="${escapeHtml(item.name)}">
      <strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.symbol)} · ${escapeHtml(item.market)}</span>
    </button>
  `).join('');
  host.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => {
      $('#tickerInput').value = button.dataset.symbol;
      $('#tickerInput').dataset.selectedSymbol = button.dataset.symbol;
      $('#tickerInput').dataset.selectedName = button.dataset.name;
      renderSuggestions([]);
      $('#amountInput').focus();
    });
  });
}

function addManualPosition() {
  const tickerInput = $('#tickerInput');
  const rawTicker = String(tickerInput.value || '').trim();
  const selectedSymbol = tickerInput.dataset.selectedSymbol || '';
  const selectedName = tickerInput.dataset.selectedName || '';
  const ticker = (selectedSymbol || rawTicker).toUpperCase().replace(/[^A-Z0-9.\-]/g, '');
  const amount = Number($('#amountInput').value);
  const accountType = $('#accountTypeInput').value || 'taxable';
  if (!ticker || !amount || amount <= 0) {
    setScreenshotStatus('종목과 금액을 입력해 주세요.', 'error');
    return;
  }
  const name = selectedName || state.instrumentCache[ticker] || rawTicker || ticker;
  addPosition({ ticker, name, amount, accountType });
  tickerInput.value = '';
  tickerInput.dataset.selectedSymbol = '';
  tickerInput.dataset.selectedName = '';
  $('#amountInput').value = '';
  setScreenshotStatus(`${name}을(를) 추가했습니다.`, 'success');
}

async function initSession(reset = false) {
  if (state.sessionId && !reset) return;
  if (!state.portfolioPositions.length) {
    setScreenshotStatus('사진, 검색 입력, 샘플 중 하나로 포트폴리오를 먼저 추가해 주세요.', 'error');
    return;
  }
  setBusy($('#initSessionBtn'), true, '연결 중...');
  try {
    const data = await api('/api/games/session', {
      method: 'POST',
      body: JSON.stringify({ positions: toGamePositions() }),
    });
    state.sessionId = data.session_id;
    state.portfolioAnalysis = data.portfolio_analysis;
    state.events = [];
    state.wikis = {};
    state.report = null;
    state.startedGames = {};
    state.lastTurns = { buy_sell: null, balance: null, saju: null };
    state.messages = { buy_sell: [], balance: [], saju: [] };
    state.turnByGame = { buy_sell: 0, balance: 0, saju: 0 };
    state.trade = createTradeState();
    $('#sessionId').textContent = state.sessionId;
    setScreenshotStatus('포트폴리오 X-Ray가 게임 세션에 연결됐습니다.', 'success');
    renderPortfolioSummary();
    renderEvents();
    renderTraits();
    renderWiki();
    renderReport();
    await startActiveGame();
  } catch (error) {
    setScreenshotStatus(error.message, 'error');
  } finally {
    setBusy($('#initSessionBtn'), false, '포트폴리오 연결');
  }
}

async function resetSession() {
  state.sessionId = null;
  await initSession(true);
}

function renderPortfolioSummary() {
  const host = $('#portfolioSummary');
  const analysis = state.portfolioAnalysis;
  if (!analysis) {
    host.innerHTML = '<div class="empty">포트폴리오 X-Ray 연결 대기 중입니다.</div>';
    return;
  }
  const maxExposure = analysis.max_exposure || {};
  host.innerHTML = `
    <div class="summary-row"><span>총 평가액</span><b>${formatWon(analysis.total_value)}원</b></div>
    <div class="summary-row"><span>HHI</span><b>${Math.round(analysis.hhi || 0).toLocaleString('ko-KR')}</b></div>
    <div class="summary-row"><span>최대 노출</span><b>${escapeHtml(maxExposure.name || '-')}</b></div>
    <div class="summary-row"><span>최대 비중</span><b>${Number(maxExposure.pct || 0).toFixed(1)}%</b></div>
  `;
}

function addMessage(gameId, role, text, label = '') {
  state.messages[gameId].push({ role, text, label });
}

async function startActiveGame() {
  renderActiveGame();
  if (!state.sessionId || state.startedGames[state.activeGame]) {
    renderChat();
    return;
  }
  const game = GAMES[state.activeGame];
  const data = await api(`/api/games/${state.activeGame}/start`, {
    method: 'POST',
    body: JSON.stringify({ session_id: state.sessionId, context: { persona: game.title, source: 'interactive_ui' } }),
  });
  state.startedGames[state.activeGame] = true;
  state.events.unshift(data.event);
  addMessage(state.activeGame, 'gm', data.gm_message || game.intro, game.title);
  if (state.activeGame === 'buy_sell') {
    addMessage('buy_sell', 'system', '먼저 손절·존버 미니게임 창에서 3턴 매수/매도 테스트를 끝내면 채팅 해석이 열립니다.', 'Game Logger');
  }
  renderEvents();
  renderChat();
}

function renderActiveGame() {
  const game = GAMES[state.activeGame];
  $('#gameTitle').textContent = game.title;
  $('#gameEyebrow').textContent = game.eyebrow;
  renderPersonaAvatar(state.activeGame);
  $('#personaRole').textContent = game.role;
  $('#personaName').textContent = game.title;
  document.querySelectorAll('.game-tab').forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.game === state.activeGame);
  });
  renderVisualSurface();
  renderQuickChoices();
  renderChat();
  renderWiki();
  state.startedAt = performance.now();
}

function renderPersonaAvatar(gameId) {
  const game = GAMES[gameId];
  const host = $('#personaAvatar');
  if (!host || !game) return;
  host.className = `persona-avatar persona-${game.avatarClass || gameId}`;
  host.setAttribute('aria-label', `${game.title} 아바타`);
  host.innerHTML = PERSONA_ART[gameId] || `<span class="portrait-fallback">${escapeHtml(game.avatar)}</span>`;
}

function renderVisualSurface() {
  if (state.chartFrame) cancelAnimationFrame(state.chartFrame);
  if (state.activeGame === 'buy_sell') renderTradeGameBoard();
  else if (state.activeGame === 'balance') renderDilemmaBoard();
  else renderSajuBoard();
}

function primaryTradeName() {
  const top = [...state.portfolioPositions].sort((a, b) => b.amount - a.amount)[0];
  return top ? top.name : '대표 종목';
}

const TRADE_TIMER_CIRC = 276.46;
const TRADE_SCENARIOS = {
  1: { key: 'news_sensitivity', label: '뉴스 민감도', trend: () => (Math.random() - 0.5) * 0.2, volatility: () => 0.012 + Math.random() * 0.012, newsCount: 3, fakeNewsRatio: 0.5 },
  2: { key: 'downtrend_response', label: '하락 대응', trend: () => -0.45 - Math.random() * 0.25, volatility: () => 0.010 + Math.random() * 0.008, newsCount: 1, fakeNewsRatio: 0.2 },
  3: { key: 'uptrend_response', label: '상승 대응', trend: () => 0.45 + Math.random() * 0.25, volatility: () => 0.010 + Math.random() * 0.008, newsCount: 1, fakeNewsRatio: 0.2 },
};

const TRADE_TAUNTS = {
  1: { start: '속보 뜬다 속보. 믿어도 되나?', rising: '다들 달려든다. 너도 탈래?', falling: '악재 떴어. 던지는 사람 많아.' },
  2: { start: '분위기 안 좋은데 들어갈 거야?', rising: '잠깐 반등일 수도 있어. 속지 마.', falling: '계속 빠진다. 손절 안 해?' },
  3: { start: '오늘 느낌 좋다. 가볼까?', rising: '더 간다 더 가. 벌써 팔게?', falling: '어, 꺾이나? 고점일 수도.' },
  holdingProfit: ['벌써 플러스네. 더 먹을래?', '익절각인데 욕심부리다 뱉는다?', '여기서 만족할 거야, 더 볼 거야?'],
  holdingLoss: ['물렸네. 존버할 거야?', '지금 끊는 게 약일 수도.', '심장 쫄깃하지? 어쩔 거야.'],
};

function tradeMoney(value) {
  return `₩${Math.floor(Number(value) || 0).toLocaleString('ko-KR')}`;
}

function tradeRate(value, digits = 2) {
  const n = Number(value) || 0;
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
}

function fallbackTradeNews(stockName, category) {
  const stock = stockName || '대표 종목';
  const map = {
    surge: [`${stock}, 외국인 대량 매수세 유입`, `${stock} 깜짝 호재 발표설`, `${stock} 기관 매수 폭증`],
    crash: [`${stock}, 단기 차익실현 매물 확대`, `${stock} 악재 루머 확산`, `${stock} 투매 조짐`],
    volatile: [`${stock} 변동성 급확대`, `${stock} 거래량 폭증`, `${stock} 수급 불안정`],
  };
  return map[category][Math.floor(Math.random() * map[category].length)];
}

function renderTradeGameBoard() {
  const t = state.trade;
  const last = t.roundResults[t.roundResults.length - 1];
  $('#visualSurface').innerHTML = `
    <div class="trade-launch">
      <div>
        <span class="eyebrow">Buy/Sell Instinct Test</span>
        <h2>손절·존버 미니게임</h2>
        <p>별도 게임 창에서 3턴 차트, AI 트레이더 자극, 속보 반응을 기록합니다. 완료 후 GM 채팅 해석이 열립니다.</p>
      </div>
      <div class="trade-launch-grid">
        <div><span>상태</span><b>${t.status === 'completed' ? '완료' : t.status === 'running' ? '진행 중' : '대기'}</b></div>
        <div><span>진행</span><b>${Math.min(t.round || 0, t.maxRounds)} / ${t.maxRounds}</b></div>
        <div><span>최근 결과</span><b style="color:${last ? (last.profitRate >= 0 ? 'var(--green)' : 'var(--red)') : 'inherit'}">${last ? tradeRate(last.profitRate, 1) : '-'}</b></div>
      </div>
      <div class="trade-launch-actions">
        <button type="button" id="openTradeModalBtn">${t.status === 'completed' ? '다시 플레이' : t.status === 'running' ? '게임 창 보기' : '게임 창 열기'}</button>
        <span>${state.sessionId ? '로그 세션 연결됨' : '포트폴리오 연결 후 시작 가능'}</span>
      </div>
    </div>
  `;
  $('#openTradeModalBtn').addEventListener('click', openTradeModal);
}

function setTradeModal(open) {
  const bg = $('#tradeModalBg');
  if (!bg) return;
  bg.classList.toggle('open', open);
  bg.setAttribute('aria-hidden', open ? 'false' : 'true');
}

function openTradeModal() {
  if (!state.sessionId) {
    renderTradeSessionGate();
  } else if (state.trade.status === 'running') {
    renderTradeFrame();
    updateTradeUi();
    drawTradeCanvas();
  } else if (state.trade.status === 'completed') {
    renderTradeResult();
  } else {
    renderTradeIntro();
  }
  setTradeModal(true);
}

function closeTradeModal() {
  if (state.trade.status === 'running') stopTradeGame(true);
  setTradeModal(false);
}

function renderTradeSessionGate() {
  $('#tradeModal').innerHTML = `
    <div class="modal-head">
      <div>
        <span class="eyebrow">손절·존버 미니게임</span>
        <h2>포트폴리오 연결이 필요합니다</h2>
      </div>
      <button class="modal-close" id="tradeCloseBtn" type="button">×</button>
    </div>
    <div class="modal-body">
      <div class="trade-intro-card">
        <div class="trade-intro-icon">⚡</div>
        <h3>게임 로그를 위키와 리포트에 연결하려면 세션이 먼저 필요합니다.</h3>
        <p>사진 업로드, 종목 검색, 샘플 데이터 중 하나로 포트폴리오를 연결한 뒤 다시 시작해 주세요.</p>
        <button class="primary-action" id="tradeLoadSampleBtn" type="button">샘플 포트폴리오 연결 후 시작</button>
      </div>
    </div>
  `;
  $('#tradeCloseBtn').addEventListener('click', closeTradeModal);
  $('#tradeLoadSampleBtn').addEventListener('click', async () => {
    loadSamplePortfolio();
    await initSession(true);
    renderTradeIntro();
  });
}

function renderTradeIntro() {
  const previous = state.trade.status === 'completed' ? summarizeTrade(state.trade) : null;
  $('#tradeModal').innerHTML = `
    <div class="modal-head">
      <div>
        <span class="eyebrow">AI Trader Game</span>
        <h2>3번의 시장, 당신의 진짜 본능은?</h2>
      </div>
      <button class="modal-close" id="tradeCloseBtn" type="button">×</button>
    </div>
    <div class="modal-body">
      <div class="trade-intro-card">
        <div class="trade-intro-icon">⚡</div>
        <h3>AI 트레이더 '쩐주'와 함께하는 3턴 매매 본능 테스트</h3>
        <p>각 턴 10초 안에 매수 1번과 매도 1번을 결정합니다. 뉴스 자극과 망설임, 손절·존버 반응은 모두 공통 로그에 기록됩니다.</p>
        <div class="trade-rule-grid">
          <div><b>1</b><span>뉴스 민감도</span></div>
          <div><b>2</b><span>하락 대응</span></div>
          <div><b>3</b><span>상승 대응</span></div>
        </div>
        <label class="trade-stock-label" for="tradeStockInput">거래할 종목명</label>
        <div class="trade-stock-row">
          <input id="tradeStockInput" type="text" maxlength="24" value="${escapeHtml(primaryTradeName())}">
          <button id="tradeStartBtn" type="button">테스트 시작</button>
        </div>
        <div class="trade-quick-stocks">
          ${['삼성전자', '테슬라', '카카오', 'NVIDIA', '비트코인'].map((name) => `<button type="button" data-stock="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join('')}
        </div>
      </div>
      ${previous ? `<div class="trade-prev-result">저장된 결과: <b>${escapeHtml(previous.type)}</b> · 최종 ${tradeRate(previous.totalReturn, 1)}</div>` : ''}
      <p class="trade-disclaimer">본 콘텐츠는 투자 성향 진단용 가상 시뮬레이션이며 투자자문이 아닙니다.</p>
    </div>
  `;
  $('#tradeCloseBtn').addEventListener('click', closeTradeModal);
  $('#tradeStartBtn').addEventListener('click', startTradeGame);
  document.querySelectorAll('[data-stock]').forEach((button) => {
    button.addEventListener('click', () => {
      $('#tradeStockInput').value = button.dataset.stock;
    });
  });
}

function stopTradeGame(resetStatus = false) {
  const t = state.trade;
  if (t.tickTimer) clearTimeout(t.tickTimer);
  if (t.timerTimer) clearTimeout(t.timerTimer);
  if (t.nextTimer) clearTimeout(t.nextTimer);
  if (t.newsTimer) clearTimeout(t.newsTimer);
  (t.tauntTimers || []).forEach((id) => clearTimeout(id));
  t.tickTimer = null;
  t.timerTimer = null;
  t.nextTimer = null;
  t.newsTimer = null;
  t.tauntTimers = [];
  if (resetStatus && t.status === 'running') {
    state.trade = createTradeState();
    renderTradeGameBoard();
    renderQuickChoices();
    renderChat();
  }
}

async function ensureBuySellStarted() {
  if (state.startedGames.buy_sell) return;
  const data = await api('/api/games/buy_sell/start', {
    method: 'POST',
    body: JSON.stringify({ session_id: state.sessionId, context: { persona: GAMES.buy_sell.title, source: 'interactive_trade_modal' } }),
  });
  state.startedGames.buy_sell = true;
  state.events.unshift(data.event);
  addMessage('buy_sell', 'gm', data.gm_message || GAMES.buy_sell.intro, GAMES.buy_sell.title);
  addMessage('buy_sell', 'system', '손절·존버 미니게임 창에서 3턴 매매 테스트를 완료하면 채팅 해석이 열립니다.', 'Game Logger');
  renderEvents();
  renderChat();
}

async function startTradeGame() {
  if (!state.sessionId) {
    renderTradeSessionGate();
    return;
  }
  stopTradeGame(false);
  await ensureBuySellStarted();
  const stockName = String($('#tradeStockInput')?.value || primaryTradeName()).trim() || primaryTradeName();
  state.trade = createTradeState();
  state.trade.stockName = stockName;
  state.trade.status = 'running';
  state.trade.totalAsset = state.trade.initialAsset;
  renderTradeFrame();
  startTradeRound();
}

function renderTradeFrame() {
  const t = state.trade;
  $('#tradeModal').innerHTML = `
    <div class="modal-head compact">
      <div>
        <span class="eyebrow">손절·존버 미니게임</span>
        <h2>${escapeHtml(t.stockName || primaryTradeName())}</h2>
      </div>
      <button class="modal-close" id="tradeCloseBtn" type="button">×</button>
    </div>
    <div class="modal-body trade-game-body">
      <div class="trade-game-head">
        <div><strong id="tradeStockName">${escapeHtml(t.stockName || primaryTradeName())}</strong><span id="tradeTotalAsset">${tradeMoney(t.totalAsset)}</span></div>
        <b id="tradeRoundLabel">턴 1 / ${t.maxRounds}</b>
      </div>
      <div class="trade-rounds" id="tradeRoundDots"></div>
      <div class="trade-timer-row">
        <div class="trade-timer">
          <svg viewBox="0 0 100 100">
            <circle class="timer-bg" cx="50" cy="50" r="44"></circle>
            <circle class="timer-progress" id="tradeTimerProgress" cx="50" cy="50" r="44" stroke-dasharray="${TRADE_TIMER_CIRC}" stroke-dashoffset="0"></circle>
          </svg>
          <div id="tradeTimerText">10.0</div>
        </div>
        <div>
          <div id="tradeTimerStatus">턴 준비</div>
          <strong id="tradeInstruction">매수 타이밍</strong>
          <span id="tradeSub">직감을 믿되, 로그는 냉정하게 남습니다.</span>
        </div>
      </div>
      <div class="trade-price-grid">
        <div><span>현재가</span><b id="tradeCurrentPrice">-</b></div>
        <div><span>매수가</span><b id="tradeBuyPrice">-</b></div>
        <div><span>손익률</span><b id="tradeProfitRate">-</b></div>
      </div>
      <div class="ai-trader">
        <div class="ai-trader-avatar">🤖</div>
        <div>
          <span>AI 트레이더 '쩐주'</span>
          <b id="aiTraderMsg">준비됐어?</b>
        </div>
      </div>
      <div class="news-ticker" id="tradeNewsTicker"><strong>속보</strong><span id="tradeNewsContent"></span></div>
      <div class="trade-chart-wrap">
        <div class="status-badge waiting" id="tradeStatusBadge">대기중</div>
        <div class="heart-rate"><span>♥</span><b id="tradeHeartRate">72</b></div>
        <canvas id="tradeChart"></canvas>
      </div>
      <div class="trade-actions modal-actions">
        <button class="trade-action trade-buy" id="tradeBuyBtn" type="button">매수<span>지금 사기</span></button>
        <button class="trade-action trade-sell" id="tradeSellBtn" type="button" disabled>매도<span>매수 후 활성</span></button>
      </div>
      <div class="trade-note" id="tradeRoundNote">준비가 끝나면 차트가 바로 움직입니다.</div>
    </div>
  `;
  $('#tradeCloseBtn').addEventListener('click', closeTradeModal);
  $('#tradeBuyBtn').addEventListener('click', executeTradeBuy);
  $('#tradeSellBtn').addEventListener('click', executeTradeSell);
}

function startTradeRound() {
  const t = state.trade;
  if (t.round >= t.maxRounds) {
    finishTradeGame();
    return;
  }
  stopTradeGame(false);
  t.round += 1;
  const scenario = TRADE_SCENARIOS[t.round];
  t.status = 'running';
  t.phase = 'buy';
  t.scenario = scenario;
  t.roundEnding = false;
  t.hasBought = false;
  t.hasSold = false;
  t.basePrice = 40000 + Math.random() * 20000;
  t.currentPrice = t.basePrice;
  t.buyPrice = null;
  t.buyTime = null;
  t.buyAtMs = null;
  t.startAt = 0;
  t.priceHistory = [t.basePrice];
  t.timeHistory = [0];
  t.trend = scenario.trend();
  t.volatility = scenario.volatility();
  t.heartRate = 72;
  t.newsFiredCount = 0;
  t.lastNewsAt = null;
  $('#tradeRoundLabel').textContent = `턴 ${t.round} / ${t.maxRounds}`;
  $('#tradeTimerStatus').textContent = `${scenario.label} · 턴 ${t.round}/${t.maxRounds}`;
  $('#tradeInstruction').textContent = '매수 타이밍';
  $('#tradeSub').textContent = ['직감을 믿으세요.', '타이밍을 잡으세요.', '침착하게 대응하세요.'][Math.floor(Math.random() * 3)];
  $('#tradeBuyBtn').disabled = false;
  $('#tradeSellBtn').disabled = true;
  $('#tradeBuyPrice').textContent = '-';
  $('#tradeBuyPrice').style.color = '#8b95b0';
  $('#tradeProfitRate').textContent = '-';
  $('#tradeProfitRate').style.color = '#8b95b0';
  $('#tradeStatusBadge').className = 'status-badge waiting';
  $('#tradeStatusBadge').textContent = '대기중';
  $('#tradeNewsTicker').style.display = 'none';
  $('#tradeRoundNote').textContent = '턴이 시작됐습니다. 매수 후 매도 타이밍을 정하세요.';
  updateTradeRoundDots();
  updateTradeUi();
  drawTradeCanvas();
  const roundToken = t.round;
  showTradeCountdown(() => {
    if (state.trade !== t || t.round !== roundToken || t.status !== 'running') return;
    t.startAt = performance.now();
    addLocalTradeLog('turn_start', { scenario: scenario.key, trend: Number(t.trend.toFixed(3)), volatility: Number(t.volatility.toFixed(4)) });
    setTraderMsg(TRADE_TAUNTS[t.round].start);
    tickTradeGame();
    runTradeTimer();
    scheduleTradeTaunts();
    scheduleTradeNews();
  });
}

function tickTradeGame() {
  const t = state.trade;
  if (t.status !== 'running') return;
  const elapsed = performance.now() - t.startAt;
  if (elapsed >= t.timeLimitMs) {
    endTradeRound('timeout');
    return;
  }
  let change = (Math.random() - 0.5) * 2 * t.volatility;
  change += t.trend * 0.005;
  if (Math.random() < 0.03) change += (Math.random() - 0.5) * 0.04;
  t.currentPrice *= 1 + change;
  const deviation = (t.currentPrice - t.basePrice) / t.basePrice;
  const limit = t.round === 1 ? 0.15 : 0.30;
  const meanRevert = t.round === 1 ? 0.05 : 0.02;
  if (Math.abs(deviation) > limit) t.currentPrice -= (t.currentPrice - t.basePrice) * meanRevert;
  t.priceHistory.push(t.currentPrice);
  t.timeHistory.push(elapsed);
  if (t.priceHistory.length > 150) {
    t.priceHistory.shift();
    t.timeHistory.shift();
  }
  if (t.hasBought) {
    const pnl = ((t.currentPrice - t.buyPrice) / t.buyPrice) * 100;
    t.heartRate = Math.min(180, 72 + Math.abs(pnl) * 4);
  } else {
    t.heartRate = Math.min(180, 72 + Math.abs(deviation) * 200);
  }
  updateTradeUi();
  drawTradeCanvas();
  t.tickTimer = setTimeout(tickTradeGame, 80);
}

async function recordTradeEvent(action, context, signal) {
  const t = state.trade;
  try {
    const data = await api('/api/games/buy_sell/events', {
      method: 'POST',
      body: JSON.stringify({
        session_id: state.sessionId,
        turn: t.round,
        event_type: 'user_action',
        action,
        context,
        reaction_latency_ms: t.startAt ? Math.round(performance.now() - t.startAt) : null,
        signal,
        payload: {
          price: Math.round(t.currentPrice),
          buy_price: t.buyPrice ? Math.round(t.buyPrice) : null,
          round: t.round,
          source: 'interactive_trade_modal',
          scenario: t.scenario?.key || null,
        },
      }),
    });
    state.events.unshift(data.event);
    renderEvents();
    renderTraits();
  } catch (error) {
    addMessage('buy_sell', 'system', error.message, 'System');
  }
}

function runTradeTimer() {
  const t = state.trade;
  if (t.status !== 'running') return;
  const remaining = Math.max(0, t.timeLimitMs - (performance.now() - t.startAt));
  const progress = remaining / t.timeLimitMs;
  $('#tradeTimerText').textContent = (remaining / 1000).toFixed(1);
  const ring = $('#tradeTimerProgress');
  ring.style.strokeDashoffset = TRADE_TIMER_CIRC * (1 - progress);
  ring.style.stroke = progress < 0.3 ? '#ff3b5c' : progress < 0.6 ? '#ffb800' : '#00d68f';
  if (remaining > 0) t.timerTimer = setTimeout(runTradeTimer, 50);
}

function updateTradeUi() {
  const t = state.trade;
  const current = $('#tradeCurrentPrice');
  if (!current) return;
  current.textContent = tradeMoney(t.currentPrice);
  $('#tradeTotalAsset').textContent = tradeMoney(t.totalAsset);
  $('#tradeHeartRate').textContent = Math.floor(t.heartRate);
  if (t.hasBought && t.buyPrice) {
    const pnl = ((t.currentPrice - t.buyPrice) / t.buyPrice) * 100;
    const profit = $('#tradeProfitRate');
    profit.textContent = tradeRate(pnl);
    profit.style.color = pnl >= 0 ? '#00d68f' : '#ff3b5c';
  }
}

function updateTradeRoundDots() {
  const t = state.trade;
  const host = $('#tradeRoundDots');
  if (!host) return;
  host.innerHTML = '';
  for (let i = 0; i < t.maxRounds; i += 1) {
    const dot = document.createElement('i');
    const result = t.roundResults[i];
    if (result) dot.className = result.profitRate >= 0 ? 'win' : 'loss';
    else if (i === t.round - 1) dot.className = 'active';
    host.appendChild(dot);
  }
}

function drawTradeCanvas() {
  const canvas = $('#tradeChart');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width;
  const h = rect.height;
  const points = state.trade.priceHistory.length ? state.trade.priceHistory : [state.trade.currentPrice];
  const spread = state.trade.round === 1 ? 0.15 : 0.30;
  let min = Math.min(...points, state.trade.basePrice * (1 - spread));
  let max = Math.max(...points, state.trade.basePrice * (1 + spread));
  const rangePad = (max - min) * 0.1;
  min -= rangePad;
  max += rangePad;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(255,255,255,.10)';
  for (let i = 1; i < 4; i += 1) {
    const y = (h / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  const baseY = 10 + (h - 20) * (1 - (state.trade.basePrice - min) / (max - min || 1));
  ctx.strokeStyle = 'rgba(255,255,255,.22)';
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(10, baseY);
  ctx.lineTo(w - 10, baseY);
  ctx.stroke();
  ctx.setLineDash([]);
  if (state.trade.hasBought && state.trade.buyPrice) {
    const buyY = 10 + (h - 20) * (1 - (state.trade.buyPrice - min) / (max - min || 1));
    ctx.strokeStyle = '#4a90ff';
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(10, buyY);
    ctx.lineTo(w - 10, buyY);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#bfdbfe';
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText(`BUY ${tradeMoney(state.trade.buyPrice)}`, 16, buyY - 5);
  }
  ctx.beginPath();
  points.forEach((point, i) => {
    const x = 10 + (w - 20) * (i / Math.max(points.length - 1, 1));
    const y = 10 + (h - 20) * (1 - (point - min) / (max - min || 1));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = state.trade.currentPrice >= state.trade.basePrice ? '#4ade80' : '#fb7185';
  ctx.lineWidth = 2.4;
  ctx.stroke();
  const last = points[points.length - 1];
  const lastX = 10 + (w - 20);
  const lastY = 10 + (h - 20) * (1 - (last - min) / (max - min || 1));
  ctx.beginPath();
  ctx.arc(lastX, lastY, 5, 0, Math.PI * 2);
  ctx.fillStyle = state.trade.currentPrice >= state.trade.basePrice ? '#4ade80' : '#fb7185';
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2;
  ctx.stroke();
}

function addLocalTradeLog(type, payload = {}) {
  const t = state.trade;
  const deviation = t.basePrice ? ((t.currentPrice - t.basePrice) / t.basePrice) * 100 : 0;
  t.eventLog.push({
    turn: t.round,
    scenario: t.scenario?.key || null,
    type,
    elapsed_ms: t.startAt ? Math.round(performance.now() - t.startAt) : 0,
    price: Math.round(t.currentPrice),
    deviation_pct: Number(deviation.toFixed(2)),
    heart_rate: Math.round(t.heartRate),
    ...payload,
  });
}

function setTraderMsg(text) {
  const host = $('#aiTraderMsg');
  if (!host || !text) return;
  host.textContent = text;
  addLocalTradeLog('ai_taunt', { msg: text, while: state.trade.hasBought ? 'holding' : 'waiting' });
}

function scheduleTradeTaunts() {
  const t = state.trade;
  const emit = () => {
    if (t.status !== 'running' || t.hasSold) return;
    const deviation = (t.currentPrice - t.basePrice) / t.basePrice;
    let msg;
    if (t.hasBought) {
      const pnl = (t.currentPrice - t.buyPrice) / t.buyPrice;
      msg = pnl >= 0
        ? TRADE_TAUNTS.holdingProfit[Math.floor(Math.random() * TRADE_TAUNTS.holdingProfit.length)]
        : TRADE_TAUNTS.holdingLoss[Math.floor(Math.random() * TRADE_TAUNTS.holdingLoss.length)];
    } else {
      msg = deviation >= 0 ? TRADE_TAUNTS[t.round].rising : TRADE_TAUNTS[t.round].falling;
    }
    setTraderMsg(msg);
  };
  t.tauntTimers = [setTimeout(emit, 3500), setTimeout(emit, 7000)];
}

function scheduleTradeNews() {
  const t = state.trade;
  for (let i = 0; i < (t.scenario?.newsCount || 1); i += 1) {
    const delay = 1200 + Math.random() * 6500;
    const id = setTimeout(showTradeNews, delay);
    t.tauntTimers.push(id);
  }
}

function showTradeNews() {
  const t = state.trade;
  if (t.status !== 'running' || t.hasSold) return;
  const r = Math.random();
  let category = r < 0.34 ? 'surge' : r < 0.68 ? 'crash' : 'volatile';
  if (t.round === 2) category = r < 0.7 ? 'crash' : 'volatile';
  if (t.round === 3) category = r < 0.7 ? 'surge' : 'volatile';
  const isReal = Math.random() > (t.scenario?.fakeNewsRatio || 0.2);
  if (isReal) {
    if (category === 'surge') t.trend += 0.3;
    if (category === 'crash') t.trend -= 0.3;
    if (category === 'volatile') t.volatility *= 1.5;
  }
  const headline = fallbackTradeNews(t.stockName, category);
  t.lastNewsAt = performance.now();
  t.newsFiredCount += 1;
  addLocalTradeLog('news', { category, headline, is_real: isReal, fake: !isReal });
  $('#tradeNewsContent').textContent = `${headline}${isReal ? '' : ' (미확인 루머)'}`;
  $('#tradeNewsTicker').style.display = 'block';
  t.newsTimer = setTimeout(() => {
    const ticker = $('#tradeNewsTicker');
    if (ticker) ticker.style.display = 'none';
  }, 3000);
}

function showTradeCountdown(callback) {
  const overlay = document.createElement('div');
  overlay.className = 'trade-countdown-overlay';
  overlay.innerHTML = `<div class="trade-countdown-label">턴 ${state.trade.round} / ${state.trade.maxRounds}</div><div class="trade-countdown-num">3</div>`;
  document.body.appendChild(overlay);
  let count = 3;
  const timer = setInterval(() => {
    count -= 1;
    const num = overlay.querySelector('.trade-countdown-num');
    if (count > 0) num.textContent = count;
    else if (count === 0) num.textContent = 'GO';
    else {
      clearInterval(timer);
      overlay.remove();
      callback();
    }
  }, 650);
}

function executeTradeBuy() {
  const t = state.trade;
  if (t.status !== 'running' || t.hasBought || !t.startAt) return;
  t.hasBought = true;
  t.buyPrice = t.currentPrice;
  t.buyTime = performance.now();
  t.buyAtMs = performance.now() - t.startAt;
  t.phase = 'sell';
  const recent = t.priceHistory.slice(-6);
  const rising = recent.length >= 2 && recent[recent.length - 1] > recent[0];
  addLocalTradeLog('buy', {
    bought_while: rising ? 'rising' : 'falling',
    reaction_after_news_ms: t.lastNewsAt ? Math.round(performance.now() - t.lastNewsAt) : null,
  });
  recordTradeEvent('BUY', '손절·존버 미니게임에서 매수 선택', { risk_tolerance: 2, behavior_bias: rising ? 2 : 1, time_horizon: 2, stability_growth: rising ? 2 : 0 });
  $('#tradeBuyBtn').disabled = true;
  $('#tradeSellBtn').disabled = false;
  $('#tradeBuyPrice').textContent = tradeMoney(t.buyPrice);
  $('#tradeBuyPrice').style.color = '#4a90ff';
  $('#tradeStatusBadge').className = 'status-badge holding';
  $('#tradeStatusBadge').textContent = '보유중';
  $('#tradeInstruction').textContent = '매도 타이밍';
  $('#tradeSub').textContent = '익절과 손절 사이에서 실제 반응을 기록합니다.';
  $('#tradeRoundNote').textContent = '진입했습니다. 너무 오래 끌지, 너무 빨리 던질지 패턴을 봅니다.';
  setTraderMsg(rising ? '오를 때 올라탔네. 배짱 좋은데.' : '떨어질 때 줍줍? 역발상이군.');
}

function executeTradeSell() {
  const t = state.trade;
  if (t.status !== 'running' || !t.hasBought || t.hasSold) return;
  t.hasSold = true;
  $('#tradeSellBtn').disabled = true;
  $('#tradeStatusBadge').className = 'status-badge done';
  $('#tradeStatusBadge').textContent = '완료';
  $('#tradeInstruction').textContent = '거래 완료';
  $('#tradeSub').textContent = '다음 턴으로 넘어갑니다.';
  t.nextTimer = setTimeout(() => endTradeRound('manual'), 450);
}

function endTradeRound(reason = 'timeout') {
  const t = state.trade;
  if (t.roundEnding || t.status !== 'running') return;
  t.roundEnding = true;
  stopTradeGame(false);
  let profitRate = 0;
  let profit = 0;
  let holdTime = 0;
  let outcome = 'completed';
  if (t.hasBought) {
    profitRate = ((t.currentPrice - t.buyPrice) / t.buyPrice) * 100;
    profit = t.totalAsset * (profitRate / 100);
    holdTime = Math.max(0, (performance.now() - t.buyTime) / 1000);
    outcome = t.hasSold && reason === 'manual' ? 'completed' : 'timeout_autosell';
  } else {
    profitRate = -5;
    profit = -t.totalAsset * 0.05;
    outcome = 'no_trade';
  }
  const result = {
    round: t.round,
    intent: t.scenario?.key || null,
    profitRate,
    profit,
    holdTime,
    buyPrice: t.buyPrice,
    sellPrice: t.currentPrice,
    bought: t.hasBought,
    sold: t.hasSold,
    manualSell: reason === 'manual',
    autoSell: t.hasBought && !t.hasSold,
    noBuy: !t.hasBought,
    outcome,
    newsFired: t.newsFiredCount,
  };
  t.roundResults.push(result);
  t.results = t.roundResults;
  t.totalAsset += profit;
  addLocalTradeLog(outcome, { profit_rate: Number(profitRate.toFixed(2)), hold_sec: Number(holdTime.toFixed(1)) });
  const action = result.noBuy ? 'HOLD' : 'SELL';
  const context = result.noBuy
    ? '손절·존버 미니게임에서 제한시간 동안 매수하지 않고 관망'
    : result.autoSell
      ? '손절·존버 미니게임에서 제한시간 자동 청산'
      : `손절·존버 미니게임에서 ${profitRate >= 0 ? '익절' : '손절'} 선택`;
  recordTradeEvent(action, context, tradeSignal(action, result));
  updateTradeUi();
  updateTradeRoundDots();
  showTradeRoundNote(result);
  showTradeRoundToast(result);
  t.nextTimer = setTimeout(() => {
    if (t.round >= t.maxRounds) finishTradeGame();
    else startTradeRound();
  }, 1800);
}

function tradeSignal(action, result = null) {
  if (action === 'BUY') return { risk_tolerance: 2, behavior_bias: 1, time_horizon: 2, stability_growth: 2 };
  if (action === 'SELL') {
    const rate = Number(result?.profitRate) || 0;
    const shortHold = Number(result?.holdTime) < 2;
    return {
      risk_tolerance: rate < 0 ? -2 : 1,
      behavior_bias: shortHold || Math.abs(rate) > 4 ? 3 : 1,
      time_horizon: 4,
      stability_growth: rate >= 0 ? 2 : -1,
    };
  }
  return { risk_tolerance: -1, behavior_bias: 2, time_horizon: 3, stability_growth: -1 };
}

function showTradeRoundNote(result) {
  const note = $('#tradeRoundNote');
  if (!note) return;
  let title = '거래 완료';
  if (result.noBuy) title = '관망 패널티';
  else if (result.autoSell) title = '시간 초과 자동 청산';
  else if (result.profitRate > 0) title = '수익 실현';
  else title = '손실 확정';
  note.innerHTML = `<b>${title}</b><br><span style="color:${result.profitRate >= 0 ? '#00d68f' : '#ff3b5c'}">${tradeRate(result.profitRate)}</span> · ${result.holdTime ? `${result.holdTime.toFixed(1)}초 보유` : '매수하지 않음'} · ${tradeMoney(result.profit)}`;
}

function showTradeRoundToast(result) {
  const toast = document.createElement('div');
  toast.className = 'trade-toast';
  const title = result.noBuy ? '매매 미실행' : result.autoSell ? '시간 초과 자동 매도' : result.profitRate > 0 ? '수익 실현' : '손실 확정';
  toast.innerHTML = `<strong>${title}</strong><b class="${result.profitRate >= 0 ? 'win' : 'loss'}">${tradeRate(result.profitRate)}</b><span>${result.holdTime ? `${result.holdTime.toFixed(1)}초 보유` : '관망 기록'}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 1500);
}

function summarizeTrade(t) {
  const results = t.roundResults || [];
  const rates = results.map((r) => Number(r.profitRate) || 0);
  const wins = results.filter((r) => r.profitRate > 0).length;
  const totalReturn = ((t.totalAsset - t.initialAsset) / t.initialAsset) * 100;
  const bought = results.filter((r) => r.bought).length;
  const avgHold = results.reduce((sum, r) => sum + (Number(r.holdTime) || 0), 0) / Math.max(bought, 1);
  const noBuys = results.filter((r) => r.noBuy).length;
  const autoSells = results.filter((r) => r.autoSell).length;
  const bestRate = rates.length ? Math.max(...rates) : 0;
  const worstRate = rates.length ? Math.min(...rates) : 0;
  let type = '규칙 실행형';
  if (noBuys >= 2) type = '관망 지연형';
  else if (autoSells >= 2) type = '존버 고착 주의';
  else if (totalReturn < -8) type = '손절 규칙 보강형';
  else if (avgHold < 2.4 && bought >= 2) type = '충동 매매 주의';
  else if (totalReturn > 5) type = '순발 매매형';
  return { type, totalReturn, wins, avgHold, noBuys, autoSells, bestRate, worstRate };
}

async function finishTradeGame() {
  const t = state.trade;
  if (t.status === 'completed') return;
  stopTradeGame(false);
  t.status = 'completed';
  t.phase = 'done';
  t.results = t.roundResults;
  const summary = summarizeTrade(t);
  addMessage('buy_sell', 'system', `3턴 매매 본능 테스트 완료. ${summary.type}, 최종 수익률 ${summary.totalReturn.toFixed(2)}%가 로그에 기록됐습니다.`, 'Game Logger');
  renderTradeResult();
  renderTradeGameBoard();
  renderQuickChoices();
  renderChat();
  const prompt = `3턴 손절·존버 게임을 끝냈습니다. 결과는 ${summary.type}, 최종 수익률 ${summary.totalReturn.toFixed(2)}%, 수익 턴 ${summary.wins}/3, 평균 보유 ${summary.avgHold.toFixed(1)}초입니다. 제 행동을 해석해 주세요.`;
  await sendConversation(prompt, { behavior_bias: summary.totalReturn < 0 ? 2 : 1, time_horizon: 3 }, true);
  state.turnByGame.buy_sell = Math.max(state.turnByGame.buy_sell, 1);
}

function renderTradeResult() {
  const t = state.trade;
  const summary = summarizeTrade(t);
  const rows = [
    ['최종 수익률', tradeRate(summary.totalReturn), summary.totalReturn >= 0],
    ['수익 턴', `${summary.wins}/${t.maxRounds}`, true],
    ['평균 보유', `${summary.avgHold.toFixed(1)}초`, true],
    ['최악 손익', tradeRate(summary.worstRate), summary.worstRate >= 0],
  ];
  $('#tradeModal').innerHTML = `
    <div class="modal-head">
      <div>
        <span class="eyebrow">손절·존버 미니게임 결과</span>
        <h2>${escapeHtml(summary.type)}</h2>
      </div>
      <button class="modal-close" id="tradeCloseBtn" type="button">×</button>
    </div>
    <div class="modal-body">
      <div class="trade-result-card">
        <div class="trade-result-icon">${summary.totalReturn >= 0 ? '✨' : '📚'}</div>
        <strong>${escapeHtml(t.stockName || primaryTradeName())} · 3턴 완료</strong>
        <p>${summary.type} 패턴이 관찰됐습니다. 이 결과는 대화형 GM 해석과 위키 생성의 입력으로 사용됩니다.</p>
      </div>
      <div class="trade-result-grid">
        ${rows.map(([label, value, positive]) => `<div><span>${label}</span><b style="color:${positive ? 'var(--green)' : 'var(--red)'}">${value}</b></div>`).join('')}
      </div>
      <div class="trade-turn-list">
        ${(t.roundResults || []).map((r) => `<div><b>턴 ${r.round}</b><span>${escapeHtml(TRADE_SCENARIOS[r.round]?.label || '대응')} · ${r.bought ? `${r.holdTime.toFixed(1)}초 보유` : '관망'} · ${tradeRate(r.profitRate)}</span></div>`).join('')}
      </div>
      <div class="trade-result-actions">
        <button class="primary-action" id="tradeChatBtn" type="button">채팅으로 해석하기</button>
        <button class="secondary-action" id="tradeWikiBtn" type="button">위키 생성</button>
        <button class="secondary-action" id="tradeRetryBtn" type="button">다시하기</button>
      </div>
    </div>
  `;
  $('#tradeCloseBtn').addEventListener('click', closeTradeModal);
  $('#tradeChatBtn').addEventListener('click', () => {
    setTradeModal(false);
    $('#chatInput').focus();
  });
  $('#tradeRetryBtn').addEventListener('click', () => {
    state.trade = createTradeState();
    renderTradeIntro();
    renderTradeGameBoard();
    renderQuickChoices();
    renderChat();
  });
  $('#tradeWikiBtn').addEventListener('click', async () => {
    const button = $('#tradeWikiBtn');
    setBusy(button, true, '생성 중');
    await finishGame();
    setBusy(button, false, '위키 생성 완료');
  });
}

function renderDilemmaBoard() {
  const q = BALANCE_QUESTIONS[Math.min(state.turnByGame.balance, BALANCE_QUESTIONS.length - 1)];
  $('#visualSurface').innerHTML = `
    <div class="dilemma-board">
      <div><span class="eyebrow">Forced Choice</span><h2>${escapeHtml(q.title)}</h2></div>
      <div class="dilemma-pair">
        <div class="dilemma-card"><b>A. ${escapeHtml(q.left.label)}</b><span>분산과 규칙을 먼저 보는 선택입니다.</span></div>
        <div class="dilemma-card"><b>B. ${escapeHtml(q.right.label)}</b><span>확신과 성장 기회를 먼저 보는 선택입니다.</span></div>
      </div>
      <p class="muted">버튼을 누르거나 직접 이유를 입력하면 선택과 머뭇거림 시간이 로그에 남습니다.</p>
    </div>
  `;
}

function pillar(index) {
  return `${STEMS[((index % 10) + 10) % 10]}${BRANCHES[((index % 12) + 12) % 12]}`;
}

function elementOfPillar(value) {
  return value.split('').map((char) => FIVE_ELEMENTS[char]).filter(Boolean).join('/');
}

function computeMansae(dateText, timeText) {
  if (!dateText) return null;
  const [year, month, day] = dateText.split('-').map(Number);
  const [hour = 0] = String(timeText || '00:00').split(':').map(Number);
  if (!year || !month || !day) return null;
  const baseDate = Date.UTC(1984, 1, 2);
  const current = Date.UTC(year, month - 1, day);
  const dayIndex = Math.floor((current - baseDate) / 86400000);
  const yearIndex = year - 1984;
  const monthIndex = yearIndex * 12 + month + 1;
  const hourBranch = Math.floor(((hour + 1) % 24) / 2);
  const hourStem = ((dayIndex % 5) * 2 + hourBranch) % 10;
  return {
    year: pillar(yearIndex),
    month: pillar(monthIndex),
    day: pillar(dayIndex),
    hour: `${STEMS[hourStem]}${BRANCHES[hourBranch]}`,
  };
}

function choiceText(...parts) {
  return parts
    .map((part) => String(part || ''))
    .join(' ')
    .toLowerCase()
    .replace(/\s+/g, '');
}

function textHas(text, keywords) {
  return keywords.some((keyword) => text.includes(String(keyword).toLowerCase().replace(/\s+/g, '')));
}

function latestTurn(gameId = state.activeGame) {
  return state.lastTurns[gameId] || {};
}

function buySellQuickChoices() {
  const last = latestTurn('buy_sell');
  const text = choiceText(last.userMessage, last.reply, last.inferredAction);
  if (textHas(text, ['손절', '손실', '매도', '청산', 'sell'])) {
    return [
      { label: '손실 커지기 전에 잘랐어요', message: '손실이 더 커질까 봐 빠르게 청산했습니다. 저는 손실 확대를 보는 게 꽤 불편합니다.', signal: { risk_tolerance: -2, behavior_bias: 2, time_horizon: 3 } },
      { label: '남들이 팔 때 흔들렸어요', message: '가격보다 주변 분위기와 매도 압박에 흔들려서 팔았습니다. 군중 반응이 제 판단에 영향을 줬습니다.', signal: { risk_tolerance: -1, behavior_bias: 4, time_horizon: 3 } },
      { label: '규칙 없이 반응했어요', message: '사전에 정한 기준보다는 순간 감정으로 매도했습니다. 다음에는 기준이 있어야 할 것 같습니다.', signal: { risk_tolerance: -1, behavior_bias: 3, time_horizon: 4 } },
    ];
  }
  if (textHas(text, ['매수', '진입', '추격', '급등', 'buy'])) {
    return [
      { label: '놓칠까 봐 들어갔어요', message: '상승을 놓칠까 봐 바로 들어갔습니다. 기회 상실이 손실보다 더 크게 느껴졌습니다.', signal: { risk_tolerance: 3, behavior_bias: 4, time_horizon: 4, stability_growth: 3 } },
      { label: '흐름이 좋아 보여 샀어요', message: '가격 흐름이 좋아 보여서 진입했습니다. 지금은 추세가 계속될 것 같다는 판단이 컸습니다.', signal: { risk_tolerance: 2, behavior_bias: 2, time_horizon: 3, stability_growth: 3 } },
      { label: '계획한 진입이었어요', message: '순간 충동보다는 제가 생각한 구간에 가까워서 매수했습니다. 원칙에 맞는 진입이라고 느꼈습니다.', signal: { risk_tolerance: 1, behavior_bias: -2, time_horizon: -1 } },
    ];
  }
  if (textHas(text, ['관망', '존버', '보유', '기다', 'hold'])) {
    return [
      { label: '확신이 없어 기다렸어요', message: '확신이 부족해서 바로 움직이지 못했습니다. 정보가 더 있어야 결정할 수 있었습니다.', signal: { risk_tolerance: -1, behavior_bias: 3, time_horizon: 2 } },
      { label: '원칙대로 버텼어요', message: '가격이 흔들려도 제 원칙상 아직 팔 구간은 아니라고 봤습니다. 기다림은 의도적인 선택이었습니다.', signal: { risk_tolerance: 1, behavior_bias: -2, time_horizon: -3 } },
      { label: '결정을 미뤘어요', message: '사실은 판단이 어려워서 결정을 미뤘습니다. 자동 기준이 있으면 더 편할 것 같습니다.', signal: { risk_tolerance: -2, behavior_bias: 4, time_horizon: 2 } },
    ];
  }
  return [
    { label: '결과가 꽤 불안했어요', message: '게임 결과를 보니 제 매매 반응이 생각보다 불안정하게 느껴졌습니다.', signal: { risk_tolerance: -1, behavior_bias: 2 } },
    { label: 'AI 멘트에 흔들렸어요', message: '차트 자체보다 AI 멘트와 분위기 자극에 제 판단이 흔들린 것 같습니다.', signal: { behavior_bias: 4, time_horizon: 3 } },
    { label: '원칙을 세우고 싶어요', message: '제 반응을 보니 매수와 매도 전에 따를 원칙이 필요하다고 느꼈습니다.', signal: { behavior_bias: -2, diversification: -1 } },
  ];
}

function balanceQuickChoices() {
  const last = latestTurn('balance');
  const text = choiceText(last.userMessage, last.reply, last.inferredAction);
  if (textHas(text, ['분산', 'etf', '안정', '규칙', '기계적', '배당'])) {
    return [
      { label: '급락 때도 원칙 지킬래요', message: '급락장이 와도 분산과 안정 원칙을 지키는 쪽이 저에게 더 맞습니다.', signal: { diversification: -3, behavior_bias: -2, stability_growth: -2 } },
      { label: '성장 일부는 남길래요', message: '안정이 우선이지만 성장 기회를 완전히 버리지는 않고 일부만 남기고 싶습니다.', signal: { diversification: -1, stability_growth: 2, risk_tolerance: 1 } },
      { label: '큰 변동은 싫어요', message: '수익 기회가 줄어도 큰 변동성을 견디는 건 싫습니다. 마음 편한 구성이 더 중요합니다.', signal: { risk_tolerance: -3, diversification: -2, stability_growth: -3 } },
    ];
  }
  if (textHas(text, ['단일', '확신', '성장', '기회', '집중', '빠른', '수익'])) {
    return [
      { label: '집중 리스크 감수할래요', message: '확신 있는 자산이라면 어느 정도 집중 리스크를 감수할 수 있습니다.', signal: { diversification: 4, risk_tolerance: 2, stability_growth: 3 } },
      { label: '실패 신호면 줄일래요', message: '성장 기회는 잡고 싶지만 실패 신호가 보이면 비중을 줄이는 규칙은 필요합니다.', signal: { risk_tolerance: 1, behavior_bias: -1, stability_growth: 2 } },
      { label: '분산과 타협할래요', message: '집중을 완전히 버리지는 않되, 일부는 분산해서 흔들림을 낮추고 싶습니다.', signal: { diversification: 1, stability_growth: 1 } },
    ];
  }
  if (textHas(text, ['뉴스', '고민', '나중', '확인', '망설'])) {
    return [
      { label: '정보 더 보고 결정할래요', message: '결정 전에 정보를 더 확인하고 싶습니다. 지금 바로 움직이면 후회할 것 같습니다.', signal: { behavior_bias: 3, time_horizon: 2 } },
      { label: '사전 규칙대로 할래요', message: '계속 망설이기보다는 미리 정한 규칙대로 실행하는 편이 저에게 필요합니다.', signal: { behavior_bias: -2, diversification: -1 } },
      { label: '최악부터 확인할래요', message: '선택 전에 최악의 손실과 실패 시나리오를 먼저 확인해야 마음이 놓입니다.', signal: { risk_tolerance: -2, behavior_bias: 2 } },
    ];
  }
  const q = BALANCE_QUESTIONS[Math.min(state.turnByGame.balance, BALANCE_QUESTIONS.length - 1)];
  return [
    { label: q.left.label, message: `${q.title} 저는 ${q.left.label} 쪽을 고르겠습니다.`, signal: q.left.signal },
    { label: q.right.label, message: `${q.title} 저는 ${q.right.label} 쪽을 고르겠습니다.`, signal: q.right.signal },
    { label: '아직은 결정이 어려워요', message: '둘 중 하나를 고르기 어렵습니다. 지금은 확신보다 망설임이 더 큽니다.', signal: { behavior_bias: 3, risk_tolerance: -1 } },
  ];
}

function sajuQuickChoices() {
  const last = latestTurn('saju');
  const text = choiceText(last.userMessage, last.reply, last.inferredAction);
  if (textHas(text, ['장기', '가치', '원칙', '버핏', '느긋'])) {
    return [
      { label: '급등주에는 흔들려요', message: '저는 장기 투자자라고 생각하지만 급등주를 보면 마음이 흔들립니다.', signal: { time_horizon: -2, behavior_bias: 2, stability_growth: 1 } },
      { label: '원칙을 더 지키고 싶어요', message: '제 기질상 장기 원칙을 더 강하게 붙잡는 방식이 필요하다고 느낍니다.', signal: { time_horizon: -4, behavior_bias: -3 } },
      { label: '현재 포트가 걱정돼요', message: '제 기질과 현재 포트폴리오의 쏠림이 서로 맞는지 걱정됩니다.', signal: { diversification: -1, behavior_bias: -1 } },
    ];
  }
  if (textHas(text, ['기술', 'ai', '반도체', '성장', '급등', '추격', '한방'])) {
    return [
      { label: '성장 섹터에 끌려요', message: 'AI와 반도체 같은 성장 섹터를 보면 강하게 끌립니다.', signal: { risk_tolerance: 3, behavior_bias: 4, stability_growth: 4, sector_tags: ['기술/성장'] } },
      { label: '방어 규칙도 필요해요', message: '성장 기질은 유지하고 싶지만 급등 추격을 막는 방어 규칙도 필요합니다.', signal: { risk_tolerance: 1, behavior_bias: -2, stability_growth: 2 } },
      { label: '섹터 욕심이 있어요', message: 'AI와 반도체 같은 섹터에 대한 욕심이 제 판단을 자주 흔듭니다.', signal: { sector_tags: ['기술/성장'], stability_growth: 3, behavior_bias: 2 } },
    ];
  }
  if (textHas(text, ['배당', '금융', '현금', '채권', '방어', '안정'])) {
    return [
      { label: '안정이 제일 편해요', message: '저는 안정과 현금흐름을 먼저 보는 편이 가장 마음이 편합니다.', signal: { risk_tolerance: -3, stability_growth: -4, sector_tags: ['배당/방어'] } },
      { label: '성장도 조금은 원해요', message: '안정 성향이 강하지만 성장 기회도 일부는 넣고 싶습니다.', signal: { risk_tolerance: -1, stability_growth: -1 } },
      { label: '현재 보유가 불안해요', message: '제 안정 성향에 비해 현재 보유 종목의 변동성이 큰 것 같아 불안합니다.', signal: { risk_tolerance: -2, diversification: -1 } },
    ];
  }
  return SAJU_PROMPTS[Math.min(state.turnByGame.saju, SAJU_PROMPTS.length - 1)].choices;
}

function renderSajuBoard() {
  const prompt = SAJU_PROMPTS[Math.min(state.turnByGame.saju, SAJU_PROMPTS.length - 1)];
  const cal = state.saju.calendar;
  $('#visualSurface').innerHTML = `
    <div class="saju-board">
      <div>
        <span class="eyebrow">Investment Saju</span>
        <h2>${escapeHtml(prompt.title)}</h2>
      </div>
      <div class="saju-inputs">
        <input id="birthDateInput" type="date" value="${escapeHtml(state.saju.birthDate)}">
        <input id="birthTimeInput" type="time" value="${escapeHtml(state.saju.birthTime || '09:00')}">
        <button type="button" id="mansaeBtn">만세력 보기</button>
      </div>
      <div class="mansae-grid">
        ${['year', 'month', 'day', 'hour'].map((key) => `
          <div class="mansae-card"><span>${{ year: '년주', month: '월주', day: '일주', hour: '시주' }[key]}</span><b>${cal ? cal[key] : '-'}</b><em>${cal ? elementOfPillar(cal[key]) : '생년월일 입력'}</em></div>
        `).join('')}
      </div>
      <div class="saju-card"><b>도사의 질문</b><span>${escapeHtml(cal ? prompt.text : '생년월일과 시간을 입력하고 만세력을 먼저 확인해 주세요.')}</span></div>
    </div>
  `;
  $('#mansaeBtn').addEventListener('click', () => {
    state.saju.birthDate = $('#birthDateInput').value;
    state.saju.birthTime = $('#birthTimeInput').value || '09:00';
    state.saju.calendar = computeMansae(state.saju.birthDate, state.saju.birthTime);
    if (!state.saju.calendar) {
      addMessage('saju', 'system', '생년월일을 입력해야 만세력을 볼 수 있습니다.', 'System');
    } else {
      addMessage('saju', 'system', `간단 만세력: 년주 ${state.saju.calendar.year}, 월주 ${state.saju.calendar.month}, 일주 ${state.saju.calendar.day}, 시주 ${state.saju.calendar.hour}`, 'Mansae');
    }
    renderVisualSurface();
    renderQuickChoices();
    renderChat();
  });
}

function renderQuickChoices() {
  const host = $('#quickChoices');
  let choices = [];
  if (state.activeGame === 'buy_sell') {
    const locked = state.trade.status !== 'completed';
    host.innerHTML = locked
      ? '<div class="quick-lock">3턴 매매 게임을 먼저 완료하면 GM 채팅 해석이 열립니다.</div>'
      : buySellQuickChoices().map((choice, index) => `<button type="button" data-choice-index="${index}">${escapeHtml(choice.label)}</button>`).join('');
    host.querySelectorAll('[data-reflect]').forEach((button) => {
      button.addEventListener('click', () => sendConversation(button.dataset.reflect));
    });
    host.querySelectorAll('[data-choice-index]').forEach((button) => {
      button.addEventListener('click', () => {
        const choice = buySellQuickChoices()[Number(button.dataset.choiceIndex)];
        sendConversation(choice.message, choice.signal || null);
      });
    });
    return;
  }
  if (state.activeGame === 'balance') {
    choices = balanceQuickChoices();
  } else {
    if (!state.saju.calendar) {
      host.innerHTML = '<div class="quick-lock">생년월일과 시간을 입력하고 만세력을 먼저 확인해 주세요.</div>';
      return;
    }
    choices = sajuQuickChoices();
  }
  host.innerHTML = choices.map((choice, index) => `<button type="button" data-choice-index="${index}">${escapeHtml(choice.label)}</button>`).join('');
  host.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => {
      const choice = choices[Number(button.dataset.choiceIndex)];
      if (!choice.message) {
        $('#chatInput').focus();
        return;
      }
      sendConversation(choice.message, choice.signal || null);
    });
  });
}

function renderChat() {
  const messages = state.messages[state.activeGame];
  const host = $('#chatTranscript');
  const locked = state.activeGame === 'buy_sell' && state.trade.status !== 'completed';
  $('#chatInput').disabled = locked || !state.sessionId || (state.activeGame === 'saju' && !state.saju.calendar);
  $('#sendChatBtn').disabled = $('#chatInput').disabled;
  if (!messages.length) {
    host.innerHTML = '<div class="bubble system"><small>Logger</small>포트폴리오 연결 후 게임을 시작하면 캐릭터 GM이 먼저 말을 겁니다.</div>';
    return;
  }
  host.innerHTML = messages.map((message) => `
    <div class="bubble ${message.role}">
      ${message.label ? `<small>${escapeHtml(message.label)}</small>` : ''}
      ${escapeHtml(message.text)}
    </div>
  `).join('');
  host.scrollTop = host.scrollHeight;
}

function buildContext(signalOverride) {
  const elapsed = Math.round(performance.now() - state.startedAt);
  const history = (state.messages[state.activeGame] || []).slice(-8).map((item) => ({
    role: item.role,
    text: item.text,
    label: item.label,
  }));
  const common = {
    elapsed_ms: elapsed,
    portfolio_total: state.portfolioAnalysis?.total_value || null,
    max_exposure: state.portfolioAnalysis?.max_exposure || null,
    signal: signalOverride || undefined,
    last_turn: latestTurn(state.activeGame),
    recent_messages: history,
    instruction: '이미 나온 질문과 같은 선택지를 반복하지 말고, 사용자의 직전 답변을 다음 상황 판단으로 전개하세요.',
  };
  if (state.activeGame === 'balance') {
    const q = BALANCE_QUESTIONS[Math.min(state.turnByGame.balance, BALANCE_QUESTIONS.length - 1)];
    return {
      ...common,
      round: state.turnByGame.balance + 1,
      question: q.title,
      next_scene_hint: '안정성/수익성/분산 기준을 다시 묻지 말고 급락장 실행, 뉴스 확인 지연, 목표 비중 유지 여부 중 하나로 진행',
    };
  }
  if (state.activeGame === 'saju') {
    const prompt = SAJU_PROMPTS[Math.min(state.turnByGame.saju, SAJU_PROMPTS.length - 1)];
    return { ...common, round: state.turnByGame.saju + 1, question: prompt.text, mansae: state.saju.calendar, birth_time: state.saju.birthTime };
  }
  return {
    ...common,
    round: state.turnByGame.buy_sell + 1,
    trade_results: state.trade.roundResults || state.trade.results,
    trade_event_log: state.trade.eventLog || [],
    source: 'post_trade_chat',
  };
}

async function sendConversation(text, signalOverride = null, internal = false) {
  const message = String(text || '').trim();
  if (!message || !state.sessionId) return;
  if (state.activeGame === 'saju' && !state.saju.calendar) {
    addMessage('saju', 'system', '만세력을 먼저 확인해 주세요.', 'System');
    renderChat();
    return;
  }
  const gameId = state.activeGame;
  const turn = state.turnByGame[gameId] + 1;
  if (!internal) addMessage(gameId, 'user', message, 'You');
  addMessage(gameId, 'system', '응답을 분석하고 공통 로그에 기록 중입니다.', 'Logger');
  renderChat();
  setBusy($('#sendChatBtn'), true, '분석');
  try {
    const data = await api(`/api/games/${gameId}/conversation`, {
      method: 'POST',
      body: JSON.stringify({
        session_id: state.sessionId,
        turn,
        message,
        context: buildContext(signalOverride),
      }),
    });
    state.messages[gameId] = state.messages[gameId].filter((item) => item.text !== '응답을 분석하고 공통 로그에 기록 중입니다.');
    addMessage(gameId, 'gm', data.message, GAMES[gameId].title);
    state.lastTurns[gameId] = {
      userMessage: message,
      reply: data.message,
      inferredAction: data.inferred_action,
      signal: data.signal,
      turn,
    };
    state.events.unshift(data.gm_event);
    state.events.unshift(data.event);
    if (!internal) {
      const maxTurn = gameId === 'balance' ? BALANCE_QUESTIONS.length - 1 : gameId === 'saju' ? SAJU_PROMPTS.length - 1 : 8;
      state.turnByGame[gameId] = Math.min(state.turnByGame[gameId] + 1, maxTurn);
    }
    state.startedAt = performance.now();
    renderVisualSurface();
    renderQuickChoices();
    renderEvents();
    renderTraits();
    renderChat();
  } catch (error) {
    state.messages[gameId] = state.messages[gameId].filter((item) => item.text !== '응답을 분석하고 공통 로그에 기록 중입니다.');
    addMessage(gameId, 'system', error.message, 'System');
    renderChat();
  } finally {
    setBusy($('#sendChatBtn'), false, '전송');
  }
}

async function finishGame() {
  if (!state.sessionId) return;
  setBusy($('#finishGameBtn'), true, '생성 중...');
  try {
    const data = await api(`/api/games/${state.activeGame}/finish`, {
      method: 'POST',
      body: JSON.stringify({ session_id: state.sessionId }),
    });
    state.wikis[state.activeGame] = data.wiki;
    addMessage(state.activeGame, 'system', '현재 게임 로그가 표준 위키로 정리됐습니다.', 'Wiki Agent');
    renderWiki();
    renderChat();
    await refreshEvents();
  } catch (error) {
    addMessage(state.activeGame, 'system', error.message, 'System');
    renderChat();
  } finally {
    setBusy($('#finishGameBtn'), false, '현재 게임 위키 생성');
  }
}

async function createSynthesis() {
  if (!state.sessionId) return;
  setBusy($('#synthesisBtn'), true, '생성 중...');
  try {
    const data = await api('/api/reports/synthesis', {
      method: 'POST',
      body: JSON.stringify({ session_id: state.sessionId, include_backtest: true }),
    });
    state.report = data.report;
    renderReport();
  } catch (error) {
    setMarkdownPreview($('#reportBox'), '', error.message);
  } finally {
    setBusy($('#synthesisBtn'), false, '위키 종합 리포트 생성');
  }
}

async function refreshEvents() {
  if (!state.sessionId) return;
  const data = await api(`/api/games/sessions/${state.sessionId}/events`);
  state.events = [...data.events].reverse();
  renderEvents();
  renderTraits();
}

function renderEvents() {
  const host = $('#eventLog');
  if (!state.events.length) {
    host.innerHTML = '<div class="empty">아직 기록된 이벤트가 없습니다.</div>';
    return;
  }
  host.innerHTML = state.events.slice(0, 45).map((event) => `
    <div class="event-item">
      <strong>${escapeHtml(event.game_id)} · ${escapeHtml(event.event_type)}</strong>
      <span>${escapeHtml(event.action || '-')} · ${escapeHtml(event.context || '')}</span>
      <span>${event.reaction_latency_ms ? `${event.reaction_latency_ms}ms` : ''}</span>
    </div>
  `).join('');
}

function aggregateTraits() {
  const totals = { risk_tolerance: 0, diversification: 0, behavior_bias: 0, time_horizon: 0, stability_growth: 0 };
  const sectorTags = [];
  let count = 0;
  state.events.forEach((event) => {
    if (!event.signal || event.action === 'GM_MESSAGE') return;
    const hasSignal = Object.keys(totals).some((key) => Number(event.signal[key] || 0) !== 0) || (event.signal.sector_tags || []).length;
    if (!hasSignal) return;
    count += 1;
    Object.keys(totals).forEach((key) => {
      totals[key] += Number(event.signal[key] || 0);
    });
    sectorTags.push(...(event.signal.sector_tags || []));
  });
  Object.keys(totals).forEach((key) => {
    totals[key] = count ? Math.max(-5, Math.min(5, Math.round(totals[key] / count))) : 0;
  });
  const sectorCounts = sectorTags.reduce((acc, tag) => {
    acc[tag] = (acc[tag] || 0) + 1;
    return acc;
  }, {});
  return { ...totals, sector_tags: Object.entries(sectorCounts).sort((a, b) => b[1] - a[1]).map(([tag]) => tag).slice(0, 5) };
}

function renderTraits() {
  const labels = {
    risk_tolerance: '위험 감수',
    diversification: '분산 선호',
    behavior_bias: '행동 성향',
    time_horizon: '단기/장기',
    stability_growth: '안정/공격',
  };
  const traits = aggregateTraits();
  $('#traitGrid').innerHTML = Object.entries(labels).map(([key, label]) => {
    const value = traits[key];
    const width = Math.abs(value) * 10;
    const left = value < 0 ? 50 - width : 50;
    return `
      <div class="trait-row">
        <span>${label}</span>
        <span class="trait-track"><i class="trait-fill" style="left:${left}%;width:${width}%;background:${value >= 0 ? 'var(--blue)' : 'var(--green)'}"></i></span>
        <b>${value}</b>
      </div>
    `;
  }).join('') + `
    <div class="sector-tags">
      ${(traits.sector_tags.length ? traits.sector_tags : ['섹터 신호 대기']).map((tag) => `<span>${escapeHtml(tag)}</span>`).join('')}
    </div>
  `;
}

function renderWiki() {
  const wiki = state.wikis[state.activeGame] || Object.values(state.wikis)[0];
  setMarkdownPreview($('#wikiBox'), wiki?.markdown || '', '게임을 진행한 뒤 위키를 생성할 수 있습니다.');
}

function renderReport() {
  setMarkdownPreview($('#reportBox'), state.report?.markdown || '', '각 게임 위키만 읽어 종합 리포트를 만듭니다.');
}

function bindEvents() {
  $('#samplePortfolioBtn').addEventListener('click', loadSamplePortfolio);
  $('#addPositionBtn').addEventListener('click', addManualPosition);
  $('#initSessionBtn').addEventListener('click', () => initSession(true));
  $('#resetSessionBtn').addEventListener('click', resetSession);
  $('#finishGameBtn').addEventListener('click', finishGame);
  $('#synthesisBtn').addEventListener('click', createSynthesis);
  $('#tickerInput').addEventListener('input', (event) => {
    event.target.dataset.selectedSymbol = '';
    event.target.dataset.selectedName = '';
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => fetchSuggestions(event.target.value), 140);
  });
  $('#amountInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') addManualPosition();
  });
  const zone = $('#screenshotDropZone');
  const fileInput = $('#screenshotFileInput');
  zone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (event) => handleScreenshotFile(event.target.files && event.target.files[0]));
  zone.addEventListener('dragover', (event) => {
    event.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    zone.classList.remove('drag-over');
    handleScreenshotFile(event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0]);
  });
  document.addEventListener('paste', (event) => {
    const items = event.clipboardData?.items || [];
    for (let i = 0; i < items.length; i += 1) {
      if (items[i].type.startsWith('image/')) {
        handleScreenshotFile(items[i].getAsFile());
        break;
      }
    }
  });
  $('#chatForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = $('#chatInput');
    const message = input.value;
    input.value = '';
    sendConversation(message);
  });
  document.querySelectorAll('.game-tab').forEach((tab) => {
    tab.addEventListener('click', async () => {
      if (state.activeGame === 'buy_sell' && tab.dataset.game !== 'buy_sell') closeTradeModal();
      state.activeGame = tab.dataset.game;
      renderActiveGame();
      if (state.sessionId) await startActiveGame();
    });
  });
  $('#tradeModalBg').addEventListener('click', (event) => {
    if (event.target === $('#tradeModalBg')) closeTradeModal();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && $('#tradeModalBg').classList.contains('open')) closeTradeModal();
  });
}

window.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  renderPositions();
  renderActiveGame();
  renderTraits();
  renderEvents();
});
