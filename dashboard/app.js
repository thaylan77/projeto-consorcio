const API_URL = window.location.origin + '/api';

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

// ── Clientes ─────────────────────────────────────────────────────────────────
let clientesData = [];
let clientesOffset = 0;
const CLIENTES_LIMITE = 50;

async function fetchClientes(busca = '', offset = 0) {
    const tbody = document.getElementById('clientes-tbody');
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:var(--text-muted);">Carregando...</td></tr>`;
    try {
        const params = new URLSearchParams({ limite: CLIENTES_LIMITE, offset, q: busca });
        const res  = await fetch(`${API_URL}/clientes?${params}`);
        const data = await res.json();

        if (data.sem_csv) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:#f59e0b;">
                CSV da MicroWork ainda não disponível. Execute o pipeline primeiro.</td></tr>`;
            return;
        }

        clientesData = data.clientes || [];
        clientesOffset = offset;

        // Totais calculados no backend sobre todos os registros (não só a página)
        document.getElementById('cli-total').textContent      = data.total      || 0;
        document.getElementById('cli-disparados').textContent = data.disparados || 0;
        document.getElementById('cli-pendentes').textContent  = data.pendentes  || 0;
        document.getElementById('cli-pagos').textContent      = data.pagos      || 0;

        renderClientes(clientesData);
        renderPaginacaoClientes(total, offset, busca);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:#ef4444;">Erro ao carregar clientes.</td></tr>`;
    }
}

function statusClienteBadge(c) {
    if (c.pago) return '<span class="badge-pagto">Pago (IA)</span>';
    const map = {
        'Cobranca': '<span class="badge-cobranca">Cobrado D+2</span>',
        'D-1':      '<span class="badge-d1">Lembrete D-1</span>',
        'D-7':      '<span class="badge-d7">Aviso D-7</span>',
    };
    if (c.ultimo_tipo && map[c.ultimo_tipo]) return map[c.ultimo_tipo];
    if (c.ultimo_tipo) return `<span class="badge-erro">${c.ultimo_tipo}</span>`;
    return '<span style="color:var(--text-muted);font-size:0.8rem;">Pendente</span>';
}

function erroStatusBadge(status) {
    if (!status) return '';
    if (status === 'Enviado') return '<span class="badge badge-success" style="font-size:0.72rem;">Enviado</span>';
    return `<span class="badge-erro" style="font-size:0.72rem;">${status}</span>`;
}

function formatTel(tel) {
    if (!tel || tel.length < 10) return tel || '—';
    const n = tel.replace(/\D/g, '');
    if (n.length === 13) return `+${n.slice(0,2)} (${n.slice(2,4)}) ${n.slice(4,9)}-${n.slice(9)}`;
    if (n.length === 12) return `+${n.slice(0,2)} (${n.slice(2,4)}) ${n.slice(4,8)}-${n.slice(8)}`;
    return tel;
}

function formatMoeda(val) {
    if (!val || val === '—') return '—';
    const n = parseFloat(val);
    if (isNaN(n)) return val;
    return 'R$ ' + n.toLocaleString('pt-BR', { minimumFractionDigits: 2 });
}

function renderClientes(data) {
    const tbody = document.getElementById('clientes-tbody');
    if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center">Nenhum cliente encontrado.</td></tr>`;
        return;
    }
    tbody.innerHTML = '';
    data.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight:600;color:white;">${c.nome}</td>
            <td style="color:var(--text-muted);font-size:0.82rem;">
                <span style="background:rgba(255,255,255,0.05);padding:2px 6px;border-radius:4px;">${c.cpf}</span>
            </td>
            <td style="color:var(--text-muted);font-size:0.82rem;">${formatTel(c.telefone)}</td>
            <td style="font-size:0.82rem;">${c.contrato || c.proposta || '—'}</td>
            <td style="font-size:0.82rem;color:var(--text-muted);">${c.modelo || '—'}</td>
            <td style="font-size:0.82rem;color:var(--text-muted);">${c.datavenda || '—'}</td>
            <td style="font-size:0.82rem;">${formatMoeda(c.valorcredito)}</td>
            <td style="font-size:0.85rem;">${c.vencimento || '—'}</td>
            <td>${statusClienteBadge(c)}</td>`;
        tbody.appendChild(tr);
    });
}

function renderPaginacaoClientes(total, offset, busca) {
    const container = document.getElementById('clientes-paginacao');
    container.innerHTML = '';
    const totalPags = Math.ceil(total / CLIENTES_LIMITE);
    const pagAtual  = Math.floor(offset / CLIENTES_LIMITE);

    for (let i = 0; i < totalPags; i++) {
        const btn = document.createElement('button');
        btn.textContent = i + 1;
        btn.style.cssText = `padding:4px 10px;border-radius:5px;border:1px solid var(--border);
            background:${i === pagAtual ? 'var(--primary)' : 'transparent'};
            color:${i === pagAtual ? '#fff' : 'var(--text-muted)'};cursor:pointer;font-size:0.8rem;`;
        btn.onclick = () => fetchClientes(busca, i * CLIENTES_LIMITE);
        container.appendChild(btn);
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────
updateDashboard();
fetchLogs();
fetchClientes();
setInterval(updateDashboard, 30000);
setInterval(fetchLogs, 5000);

// Eventos — clientes
document.getElementById('clientes-search').addEventListener('input', e => {
    clearTimeout(window._cliSearchTimer);
    window._cliSearchTimer = setTimeout(() => fetchClientes(e.target.value.trim()), 400);
});
document.getElementById('clientes-refresh').addEventListener('click', () => {
    fetchClientes(document.getElementById('clientes-search').value.trim());
});
