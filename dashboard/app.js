const API_URL = 'http://localhost:5000/api';

// ── Chave de API ─────────────────────────────────────────────────────────────
function getApiKey() { return localStorage.getItem('consorcio_api_key') || ''; }
function setApiKey(k) { localStorage.setItem('consorcio_api_key', k); }
function apiHeaders() { return { 'X-API-Key': getApiKey(), 'Content-Type': 'application/json' }; }

// ── Elementos ─────────────────────────────────────────────────────────────────
const domStats = {
    para_enviar:    document.getElementById('stat-para-enviar'),
    validados:      document.getElementById('stat-validados'),
    enviados:       document.getElementById('stat-enviados'),
    rejeitados:     document.getElementById('stat-rejeitados'),
    revisao_manual: document.getElementById('stat-revisao'),
};
const historyTbody   = document.getElementById('history-tbody');
const refreshBtn     = document.getElementById('refresh-btn');
const runBtn         = document.getElementById('run-btn');
const cobradorBtn    = document.getElementById('cobrador-btn');
const iaBtn          = document.getElementById('ia-btn');
const searchInput    = document.getElementById('search-input');
const terminalOutput = document.getElementById('terminal-output');
const logContainer   = document.querySelector('.terminal-container');

let allHistory = [];

// ── Stats ─────────────────────────────────────────────────────────────────────
async function fetchStats() {
    try {
        const data = await fetch(`${API_URL}/stats`).then(r => r.json());
        animateValue(domStats.para_enviar,    0, data.para_enviar,    800);
        animateValue(domStats.validados,      0, data.validados,      800);
        animateValue(domStats.enviados,       0, data.enviados,       800);
        animateValue(domStats.rejeitados,     0, data.rejeitados,     800);
        animateValue(domStats.revisao_manual, 0, data.revisao_manual, 800);
    } catch (e) { console.error('Stats', e); }
}

// ── Agenda ────────────────────────────────────────────────────────────────────
async function fetchAgenda() {
    try {
        const ag = await fetch(`${API_URL}/agenda`).then(r => r.json());
        document.getElementById('ag-pipeline').textContent = ag.hora_pipeline  || '—';
        document.getElementById('ag-cobrador').textContent = ag.hora_cobrador  || '—';
        document.getElementById('ag-d7').textContent       = ag.janela_d7      || '—';
        document.getElementById('ag-d1').textContent       = ag.janela_d1      || '—';
        document.getElementById('ag-cobr').textContent     = ag.cobranca_apos  || '—';
    } catch (e) { console.error('Agenda', e); }
}

// ── Histórico ─────────────────────────────────────────────────────────────────
async function fetchHistory() {
    try {
        const res = await fetch(`${API_URL}/history`);
        allHistory = await res.json();
        renderHistory(allHistory);
    } catch (e) {
        historyTbody.innerHTML =
            `<tr><td colspan="7" class="text-center" style="color:#ef4444;">
             Falha ao carregar dados. Verifique se a API está em execução.</td></tr>`;
    }
}

function tipoBadge(tipo) {
    if (!tipo) return '<span class="badge badge-success">Enviado</span>';
    const map = {
        'D-7':      '<span class="badge-d7">D-7 Aviso</span>',
        'D-1':      '<span class="badge-d1">D-1 Lembrete</span>',
        'Cobranca': '<span class="badge-cobranca">Cobrança D+2</span>',
        'PagtoConfirmado': '<span class="badge-pagto">Pago ✓</span>',
    };
    return map[tipo] || `<span class="badge-erro">${tipo}</span>`;
}

function statusBadge(status) {
    if (status === 'Enviado') return '<span class="badge badge-success">Enviado</span>';
    return `<span class="badge-erro">${status}</span>`;
}

function renderHistory(data) {
    if (!data || data.length === 0) {
        historyTbody.innerHTML =
            `<tr><td colspan="7" class="text-center">Nenhum disparo registrado ainda.</td></tr>`;
        return;
    }
    historyTbody.innerHTML = '';
    data.forEach(item => {
        const fileUrl = `${API_URL}/download/enviados/${encodeURIComponent(item.arquivo)}`;
        const [dataPart, horaPart] = (item.data_disparo || '').split(' ');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>
                <span style="font-weight:500;">${dataPart || ''}</span>
                <span style="color:var(--text-muted);font-size:0.82em;margin-left:5px;">${horaPart || ''}</span>
            </td>
            <td>${tipoBadge(item.tipo_disparo)}</td>
            <td style="font-weight:600;color:white;">${item.nome || ''}</td>
            <td style="color:var(--text-muted);">
                <span style="background:rgba(255,255,255,0.05);padding:3px 7px;border-radius:4px;">${item.cpf || ''}</span>
            </td>
            <td>${item.vencimento || ''}</td>
            <td>${statusBadge(item.status)}</td>
            <td>
                <a href="${fileUrl}" target="_blank" class="action-link" title="Ver PDF">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="12" y1="18" x2="12" y2="12"/>
                        <line x1="9" y1="15" x2="15" y2="15"/>
                    </svg>
                </a>
            </td>`;
        historyTbody.appendChild(tr);
    });
}

// ── Logs ──────────────────────────────────────────────────────────────────────
async function fetchLogs() {
    try {
        const logs = await fetch(`${API_URL}/logs`).then(r => r.json());
        const atBottom = logContainer.scrollHeight - logContainer.clientHeight
                         <= logContainer.scrollTop + 50;
        terminalOutput.innerHTML = logs.map(line => {
            let color = 'inherit';
            if (line.includes('[ERROR]') || line.includes('[CRITICAL]')) color = '#ef4444';
            else if (line.includes('[SUCCESS]'))  color = '#10b981';
            else if (line.includes('[START]'))    color = '#3b82f6';
            else if (line.includes('[ABORT]'))    color = '#f59e0b';
            else if (line.includes('[IA-'))       color = '#a78bfa';
            return `<div style="color:${color};margin-bottom:2px;">${line}</div>`;
        }).join('');
        if (atBottom) logContainer.scrollTop = logContainer.scrollHeight;
    } catch (e) { /* silently fail */ }
}

// ── Ações autenticadas ────────────────────────────────────────────────────────
async function _acaoAutenticada(endpoint, label, btn) {
    let key = getApiKey();
    if (!key) {
        key = prompt(`Informe a chave de API para executar "${label}":\n(encontre em .env → API_SECRET_KEY)`);
        if (!key) return;
        setApiKey(key.trim());
    }
    btn.disabled = true;
    try {
        const res = await fetch(`${API_URL}/${endpoint}`, { method: 'POST', headers: apiHeaders() });
        if (res.status === 401) {
            alert('Chave inválida. Tente novamente.');
            localStorage.removeItem('consorcio_api_key');
            return;
        }
        const data = await res.json();
        alert(`${data.icon || ''} ${data.status}`);
        // log mais frequente por 1 minuto
        const t = setInterval(fetchLogs, 1500);
        setTimeout(() => clearInterval(t), 60000);
    } catch (e) {
        alert(`Erro ao executar "${label}".`);
    } finally {
        btn.disabled = false;
    }
}

async function runSystem()   {
    if (!confirm('Iniciar o pipeline completo agora?')) return;
    await _acaoAutenticada('run', 'Pipeline', runBtn);
}
async function runCobrador() {
    if (!confirm('Iniciar cobrança D+2 manualmente agora?')) return;
    await _acaoAutenticada('run/cobrador', 'Cobrador D+2', cobradorBtn);
}
async function runIA() {
    if (!confirm('Analisar respostas recebidas no WhatsApp com IA agora?')) return;
    await _acaoAutenticada('run/respostas', 'IA Respostas', iaBtn);
}

// ── Filtro ────────────────────────────────────────────────────────────────────
searchInput.addEventListener('input', e => {
    const term = e.target.value.toLowerCase();
    renderHistory(allHistory.filter(item =>
        (item.nome       || '').toLowerCase().includes(term) ||
        (item.cpf        || '').toLowerCase().includes(term) ||
        (item.tipo_disparo || '').toLowerCase().includes(term) ||
        (item.data_disparo || '').toLowerCase().includes(term)
    ));
});

// ── Animação numérica ─────────────────────────────────────────────────────────
function animateValue(obj, start, end, duration) {
    if (!obj) return;
    let t0 = null;
    const step = ts => {
        if (!t0) t0 = ts;
        const p = Math.min((ts - t0) / duration, 1);
        obj.innerHTML = Math.floor(p * (end - start) + start);
        if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

// ── Dashboard refresh ─────────────────────────────────────────────────────────
async function updateDashboard() {
    refreshBtn.classList.add('loading');
    refreshBtn.style.opacity = '0.8';
    await Promise.all([fetchStats(), fetchHistory(), fetchAgenda()]);
    setTimeout(() => { refreshBtn.classList.remove('loading'); refreshBtn.style.opacity = '1'; }, 500);
}

// ── Eventos ───────────────────────────────────────────────────────────────────
refreshBtn.addEventListener('click', updateDashboard);
runBtn.addEventListener('click', runSystem);
cobradorBtn.addEventListener('click', runCobrador);
iaBtn.addEventListener('click', runIA);

// ── Init ──────────────────────────────────────────────────────────────────────
updateDashboard();
fetchLogs();
setInterval(updateDashboard, 30000);
setInterval(fetchLogs, 5000);
