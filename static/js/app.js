/* LUX-RU — SPA Router & Utilities */

const SESSION_ID = 'luxru-' + Math.random().toString(36).slice(2, 10);
let currentAnalysis = null;

// ── SPA Router ──────────────────────────────────────

function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));

  const el = document.getElementById(`page-${page}`);
  if (el) el.classList.add('active');

  const link = document.querySelector(`.nav-links a[data-page="${page}"]`);
  if (link) link.classList.add('active');

  // If navigating to dashboard with no data
  if (page === 'dashboard' && !currentAnalysis) {
    document.getElementById('dashboard-empty').classList.remove('hidden');
    document.getElementById('dashboard-content').classList.add('hidden');
  }
}

// ── Formatting ──────────────────────────────────────

function formatKRW(amount) {
  const n = parseFloat(amount) || 0;
  if (n >= 100000000) return `₩${(n / 100000000).toFixed(1)}억`;
  if (n >= 10000) return `₩${(n / 10000).toFixed(0)}만`;
  return `₩${n.toLocaleString('ko-KR')}`;
}

function formatPercent(weight) {
  return `${(parseFloat(weight) * 100).toFixed(2)}%`;
}

function getGradeBadge(grade) {
  const labels = { A: '공식 전체', B: '운용사 자료', C: '공시 상위', D: '벤치마크 추정', E: '미확인' };
  return `<span class="badge badge-${grade.toLowerCase()}">${grade} · ${labels[grade] || '미확인'}</span>`;
}

function getConfidenceBadge(confidence, coverage) {
  const conf = parseFloat(confidence);
  let grade = 'A';
  if (conf < 0.5) grade = 'E';
  else if (conf < 0.7) grade = 'D';
  else if (conf < 0.85) grade = 'C';
  else if (conf < 0.95) grade = 'B';
  return getGradeBadge(grade);
}

// ── Loading ─────────────────────────────────────────

function showLoading(text = '분석 중...') {
  document.getElementById('loading-text').textContent = text;
  document.getElementById('loading-overlay').classList.remove('hidden');
}

function hideLoading() {
  document.getElementById('loading-overlay').classList.add('hidden');
}

// ── Sample Data ─────────────────────────────────────

async function loadSampleData() {
  showLoading('샘플 데이터 로딩 중...');
  try {
    const resp = await fetch('/static/assets/sample.csv');
    const text = await resp.text();

    // Upload sample
    const formData = new FormData();
    formData.append('file', new Blob([text], { type: 'text/csv' }), 'sample.csv');
    formData.append('broker', 'auto');
    formData.append('session_id', SESSION_ID);

    const uploadResp = await fetch('/api/upload', { method: 'POST', body: formData });
    const uploadData = await uploadResp.json();

    if (!uploadData.success || !uploadData.positions.length) {
      hideLoading();
      alert('샘플 데이터 파싱 실패');
      return;
    }

    showLoading('LUX-RU 분석 중...');

    // Run analysis
    const analyzeResp = await fetch('/api/portfolio/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: SESSION_ID,
        positions: uploadData.positions,
      }),
    });
    const analyzeData = await analyzeResp.json();

    if (analyzeData.success) {
      currentAnalysis = analyzeData.data;
      renderDashboard(currentAnalysis);
      navigate('dashboard');
    }
  } catch (err) {
    console.error(err);
    alert('오류가 발생했습니다: ' + err.message);
  } finally {
    hideLoading();
  }
}

// Chart color palette
const CHART_COLORS = [
  '#6366f1', '#8b5cf6', '#a78bfa', '#34d399', '#fbbf24',
  '#f87171', '#60a5fa', '#f472b6', '#2dd4bf', '#fb923c',
  '#a3e635', '#e879f9', '#22d3ee', '#facc15', '#818cf8',
];
