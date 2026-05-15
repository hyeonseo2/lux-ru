/* LUX-RU — Upload Page Logic */

let uploadedPositions = [];

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Drag & Drop ─────────────────────────────────────

const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');

uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', () => {
  uploadZone.classList.remove('drag-over');
});

uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

fileInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) handleFile(file);
});

// ── File Handler ────────────────────────────────────

async function handleFile(file) {
  if (!file.name.endsWith('.csv')) {
    alert('CSV 파일만 지원합니다.');
    return;
  }

  showLoading('CSV 파싱 중...');

  const broker = document.getElementById('broker-select').value;
  const formData = new FormData();
  formData.append('file', file);
  formData.append('broker', broker);
  formData.append('session_id', SESSION_ID);

  try {
    const resp = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await resp.json();

    if (!data.success) {
      alert('파싱 실패: ' + (data.message || '알 수 없는 오류'));
      return;
    }

    uploadedPositions = data.positions;
    renderPreview(data);
  } catch (err) {
    alert('업로드 오류: ' + err.message);
  } finally {
    hideLoading();
  }
}

// ── Render Preview ──────────────────────────────────

function renderPreview(data) {
  const preview = document.getElementById('upload-preview');
  const stats = document.getElementById('upload-stats');
  const tbody = document.getElementById('upload-table-body');
  const warningsEl = document.getElementById('upload-warnings');

  preview.classList.remove('hidden');
  stats.textContent = `${data.rows_parsed}건 파싱 성공 / ${data.rows_failed}건 실패`;

  // Warnings
  if (data.warnings && data.warnings.length > 0) {
    warningsEl.style.display = 'block';
    warningsEl.innerHTML = data.warnings.map(w =>
      `<div style="color:var(--warning);font-size:0.85rem;padding:4px 0;">⚠️ ${escapeHtml(w)}</div>`
    ).join('');
  } else {
    warningsEl.style.display = 'none';
  }

  // Table
  tbody.innerHTML = data.positions.map(p => {
    const accountLabels = {
      taxable: '일반계좌', isa: 'ISA', pension_saving: '연금저축',
      irp: 'IRP', deposit: '예금', etc: '기타'
    };
    const accountLabel = accountLabels[p.account_type] || p.account_type;
    const broker = p.broker || '-';
    const instrumentName = p.instrument_name || '-';
    const currency = p.currency || '-';

    return `<tr>
      <td>${escapeHtml(accountLabel)}</td>
      <td>${escapeHtml(broker)}</td>
      <td><strong>${escapeHtml(instrumentName)}</strong></td>
      <td class="text-right text-mono">${parseFloat(p.quantity).toLocaleString()}</td>
      <td class="text-right text-mono">${formatKRW(p.market_value)}</td>
      <td>${escapeHtml(currency)}</td>
    </tr>`;
  }).join('');

  // Scroll to preview
  preview.scrollIntoView({ behavior: 'smooth' });
}

// ── Run Analysis ────────────────────────────────────

async function runAnalysis() {
  if (!uploadedPositions.length) {
    alert('먼저 CSV를 업로드해주세요.');
    return;
  }

  showLoading('LUX-RU 분석 중...');

  try {
    const resp = await fetch('/api/portfolio/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: SESSION_ID,
        positions: uploadedPositions,
      }),
    });
    const data = await resp.json();

    if (data.success) {
      currentAnalysis = data.data;
      renderDashboard(currentAnalysis);
      navigate('dashboard');
    } else {
      alert('분석 실패: ' + data.message);
    }
  } catch (err) {
    alert('분석 오류: ' + err.message);
  } finally {
    hideLoading();
  }
}
