/* LUX-RU — Dashboard Rendering */

let chartInstances = {};

// 섹터 라벨은 백엔드(`backend/sector_labels.py`)에서 정규화된 한국어 라벨로 전달됩니다.
// 프런트는 별도 매핑 없이 받은 값을 그대로 사용합니다.
const SECTOR_COLORS = {
  '반도체': '#4f8df7',
  'IT': '#8a63d2',
  '바이오': '#e85d75',
  '금융': '#22a06b',
  '2차전지': '#f59f3a',
  '기타': '#8f8f8f',
};

function colorForLabel(label, index) {
  const key = String(label || '').trim();
  return SECTOR_COLORS[key] || CHART_COLORS[index % CHART_COLORS.length];
}

function renderDashboard(analysis) {
  const emptyEl = document.getElementById('dashboard-empty');
  const contentEl = document.getElementById('dashboard-content');
  emptyEl.classList.add('hidden');
  contentEl.classList.remove('hidden');

  const exp = analysis.exposure;

  // Stats
  document.getElementById('stat-total').textContent = formatKRW(exp.total_market_value);
  document.getElementById('stat-etf-count').textContent = (analysis.positions || []).length;
  document.getElementById('stat-stock-count').textContent = exp.top_holdings.length;
  document.getElementById('stat-grade').innerHTML = getGradeBadge(exp.data_grade);

  // Top Holdings Table
  renderTopHoldings(exp.top_holdings);

  // Donut Charts
  renderDonut('chart-sector', 'legend-sector', exp.by_sector, '섹터');
  renderDonut('chart-country', 'legend-country', exp.by_country, '국가');
  renderDonut('chart-currency', 'legend-currency', exp.by_currency, '통화');

  // Overlap Graph
  renderOverlapGraph(analysis.overlaps, analysis.positions);

  // FinLife
  renderFinLife(analysis.finlife_recommendations);
}

// ── Top Holdings ────────────────────────────────────

function renderTopHoldings(holdings) {
  const tbody = document.getElementById('top-holdings-body');
  const maxAmount = holdings.length > 0 ? parseFloat(holdings[0].exposure_amount) : 1;

  tbody.innerHTML = holdings.map((h, i) => {
    const pct = parseFloat(h.exposure_weight || 0);
    const amount = parseFloat(h.exposure_amount || 0);
    const barWidth = (amount / maxAmount) * 100;

    return `<tr>
      <td style="color:var(--text-muted)">${i + 1}</td>
      <td><strong>${h.instrument_name}</strong></td>
      <td style="color:var(--text-secondary)">${h.sector || '-'}</td>
      <td style="color:var(--text-secondary)">${h.country || '-'}</td>
      <td class="text-right text-mono">${formatKRW(amount)}</td>
      <td>
        <div class="exposure-bar">
          <div class="exposure-bar-fill">
            <div class="exposure-bar-inner" style="width:${barWidth}%"></div>
          </div>
          <span class="exposure-pct">${formatPercent(h.exposure_weight)}</span>
        </div>
      </td>
      <td>${getConfidenceBadge(h.confidence, h.coverage_min)}</td>
    </tr>`;
  }).join('');
}

// ── Donut Chart ─────────────────────────────────────

function renderDonut(canvasId, legendId, data, label) {
  // Destroy existing
  if (chartInstances[canvasId]) {
    chartInstances[canvasId].destroy();
  }

  const canvas = document.getElementById(canvasId);
  const legendEl = document.getElementById(legendId);

  // Sort by value desc
  const sorted = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const labels = sorted.map(([k]) => k);
  const values = sorted.map(([, v]) => v * 100);
  const colors = labels.map((labelName, i) => colorForLabel(labelName, i));

  chartInstances[canvasId] = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderWidth: 0,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(17, 24, 39, 0.95)',
          titleColor: '#f1f5f9',
          bodyColor: '#94a3b8',
          borderColor: 'rgba(99, 102, 241, 0.3)',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12,
          callbacks: {
            label: (ctx) => `${ctx.label}: ${ctx.parsed.toFixed(1)}%`,
          },
        },
      },
      animation: {
        animateRotate: true,
        duration: 1200,
      },
    },
  });

  // Custom legend
  legendEl.innerHTML = sorted.slice(0, 8).map(([k, v], i) => `
    <div class="legend-item">
      <div class="legend-color" style="background:${colors[i]}"></div>
      <span class="legend-label">${k}</span>
      <span class="legend-value">${(v * 100).toFixed(1)}%</span>
    </div>
  `).join('');
}

// ── Overlap Graph ───────────────────────────────────

function renderOverlapGraph(overlaps, positions) {
  const container = document.getElementById('overlap-graph');
  const detailsEl = document.getElementById('overlap-details');

  if (!overlaps || overlaps.length === 0) {
    container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-muted)">중복된 ETF가 없습니다</div>';
    return;
  }

  // Build graph elements
  const nodes = new Map();
  const edges = [];

  overlaps.forEach((ov, i) => {
    if (!nodes.has(ov.etf_a_id)) {
      nodes.set(ov.etf_a_id, {
        data: {
          id: ov.etf_a_id,
          label: ov.etf_a_name,
          value: ov.etf_a_value,
          size: Math.max(30, Math.sqrt(ov.etf_a_value / 10000)),
        }
      });
    }
    if (!nodes.has(ov.etf_b_id)) {
      nodes.set(ov.etf_b_id, {
        data: {
          id: ov.etf_b_id,
          label: ov.etf_b_name,
          value: ov.etf_b_value,
          size: Math.max(30, Math.sqrt(ov.etf_b_value / 10000)),
        }
      });
    }
    edges.push({
      data: {
        id: `e${i}`,
        source: ov.etf_a_id,
        target: ov.etf_b_id,
        overlap: ov.overlap_score,
        width: Math.max(2, ov.overlap_score * 10),
        label: `${(ov.overlap_score * 100).toFixed(0)}%`,
      }
    });
  });

  // Render with Cytoscape
  const cy = cytoscape({
    container,
    elements: [...nodes.values(), ...edges],
    style: [
      {
        selector: 'node',
        style: {
          'background-color': '#6366f1',
          'background-opacity': 0.8,
          'label': 'data(label)',
          'color': '#0f172a',
          'font-size': '11px',
          'font-family': 'Noto Sans KR, sans-serif',
          'text-valign': 'bottom',
          'text-margin-y': 8,
          'width': 'data(size)',
          'height': 'data(size)',
          'border-width': 2,
          'border-color': '#818cf8',
          'text-wrap': 'wrap',
          'text-max-width': '100px',
        }
      },
      {
        selector: 'edge',
        style: {
          'width': 'data(width)',
          'line-color': '#f87171',
          'line-opacity': 0.6,
          'curve-style': 'bezier',
          'label': 'data(label)',
          'font-size': '10px',
          'color': '#d97706',
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.9,
          'text-background-padding': '3px',
          'font-family': 'JetBrains Mono, monospace',
        }
      },
      {
        selector: 'node:hover',
        style: {
          'background-color': '#8b5cf6',
          'border-color': '#a78bfa',
          'border-width': 3,
        }
      }
    ],
    layout: {
      name: 'cose',
      idealEdgeLength: 150,
      nodeRepulsion: 8000,
      animate: true,
      animationDuration: 800,
    },
    userZoomingEnabled: false,
  });

  // Overlap details table
  detailsEl.innerHTML = `
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>ETF A</th>
            <th>ETF B</th>
            <th class="text-right">중복도</th>
            <th class="text-right">공통종목</th>
            <th>주요 공통 종목</th>
          </tr>
        </thead>
        <tbody>
          ${overlaps.map(ov => {
            const color = ov.overlap_score > 0.7 ? 'var(--danger)' :
                         ov.overlap_score > 0.4 ? 'var(--warning)' : 'var(--success)';
            const levelText = ov.overlap_score > 0.7 ? '⚠️ 사실상 동일' :
                             ov.overlap_score > 0.4 ? '⚡ 높은 중복' : '✅ 적정';
            return `<tr>
              <td><strong>${ov.etf_a_name}</strong></td>
              <td><strong>${ov.etf_b_name}</strong></td>
              <td class="text-right" style="color:${color}">
                <strong>${(ov.overlap_score * 100).toFixed(1)}%</strong>
                <br><span style="font-size:0.75rem">${levelText}</span>
              </td>
              <td class="text-right text-mono">${ov.common_count}개</td>
              <td style="font-size:0.8rem;color:var(--text-secondary)">${ov.common_holdings.slice(0, 5).join(', ')}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
}

// ── FinLife Cards ────────────────────────────────────

function renderFinLife(products) {
  const container = document.getElementById('finlife-cards');
  if (!products || products.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2rem;">추천 상품이 없습니다.</p>';
    return;
  }

  container.innerHTML = products.map(p => `
    <div class="finlife-card">
      <div class="finlife-company">${p.company}</div>
      <div class="finlife-name">${p.product_name}</div>
      <div class="flex items-center justify-between">
        <div>
          <div class="finlife-rate">${p.max_rate}%</div>
          <div class="finlife-rate-label">최고 우대금리</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:0.9rem;color:var(--text-secondary);">기본 ${p.base_rate}%</div>
          <div style="font-size:0.8rem;color:var(--text-muted);">${p.term_months > 0 ? p.term_months + '개월' : '기간제한없음'}</div>
        </div>
      </div>
      ${p.special_conditions ? `<div style="margin-top:0.75rem;font-size:0.8rem;color:var(--text-accent);background:rgba(99,102,241,0.08);padding:6px 10px;border-radius:6px;">💡 ${p.special_conditions}</div>` : ''}
    </div>
  `).join('');
}
