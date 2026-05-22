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

// ── Empresas / Filiais ────────────────────────────────────────────────────────
async function fetchEmpresas() {
    try {
        const data = await fetch(`${API_URL}/empresas`).then(r => r.json());
        const select = document.getElementById('empresa-select');
        const cards  = document.getElementById('empresas-cards');

        // Popula select de filial
        select.innerHTML = '<option value="">Todas</option>';
        data.forEach(e => {
            const opt = document.createElement('option');
            opt.value = e.empresa;
            opt.textContent = `${e.empresa} (${e.total})`;
            select.appendChild(opt);
        });

        // Cards de resumo por filial
        cards.innerHTML = '';
        data.forEach(e => {
            const altoRiscoColor = e.alto_risco > 0 ? '#f87171' : '#64748b';
            cards.innerHTML += `
            <div style="background:rgba(30,41,59,0.7);border:1px solid var(--border);border-radius:8px;
                padding:10px 16px;font-size:0.78rem;cursor:pointer;min-width:160px;"
                onclick="filtrarPorEmpresa('${e.empresa}')">
                <div style="font-weight:600;color:white;margin-bottom:6px;">${e.empresa}</div>
                <div style="color:var(--text-muted);">Total: <strong style="color:#60a5fa;">${e.total}</strong></div>
                <div style="color:var(--text-muted);">Disparados: <strong style="color:#34d399;">${e.disparados}</strong></div>
                <div style="color:var(--text-muted);">Pendentes: <strong style="color:#fbbf24;">${e.pendentes}</strong></div>
                <div style="color:var(--text-muted);">Alto risco: <strong style="color:${altoRiscoColor};">${e.alto_risco}</strong></div>
            </div>`;
        });
    } catch(e) { console.error('fetchEmpresas', e); }
}

function filtrarPorEmpresa(nome) {
    document.getElementById('empresa-select').value = nome;
    fetchClientes('', 0);
}

// ── Clientes ─────────────────────────────────────────────────────────────────
let clientesData = [];
let clientesOffset = 0;
const CLIENTES_LIMITE = 50;

async function fetchClientes(busca = '', offset = 0) {
    const tbody = document.getElementById('clientes-tbody');
    tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="color:var(--text-muted);">Carregando...</td></tr>`;
    try {
        const empresa = document.getElementById('empresa-select')?.value || '';
        const params = new URLSearchParams({ limite: CLIENTES_LIMITE, offset, q: busca, empresa });
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
        const total = data.total || 0;
        document.getElementById('cli-total').textContent      = total;
        document.getElementById('cli-disparados').textContent = data.disparados || 0;
        document.getElementById('cli-pendentes').textContent  = data.pendentes  || 0;
        document.getElementById('cli-pagos').textContent      = data.pagos      || 0;
        const score = data.por_score || {};
        document.getElementById('cli-alto-risco').textContent =
            (score['Alto'] || 0) + (score['Critico'] || 0);

        renderClientes(clientesData);
        renderPaginacaoClientes(total, offset, busca);
    } catch (e) {
        console.error('fetchClientes error:', e);
        tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="color:#ef4444;">Erro: ${e.message}</td></tr>`;
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

const SCORE_BADGE = {
    'Critico': '<span style="background:rgba(239,68,68,0.2);color:#fca5a5;border:1px solid rgba(239,68,68,0.4);border-radius:5px;padding:2px 7px;font-size:0.72rem;font-weight:700;">Crítico</span>',
    'Alto':    '<span style="background:rgba(249,115,22,0.15);color:#fb923c;border:1px solid rgba(249,115,22,0.3);border-radius:5px;padding:2px 7px;font-size:0.72rem;font-weight:700;">Alto</span>',
    'Medio':   '<span style="background:rgba(245,158,11,0.12);color:#fbbf24;border:1px solid rgba(245,158,11,0.25);border-radius:5px;padding:2px 7px;font-size:0.72rem;">Médio</span>',
    'Baixo':   '<span style="background:rgba(16,185,129,0.12);color:#34d399;border:1px solid rgba(16,185,129,0.25);border-radius:5px;padding:2px 7px;font-size:0.72rem;">Baixo</span>',
    'Novo':    '<span style="color:#64748b;font-size:0.72rem;">Novo</span>',
};

function renderClientes(data) {
    const tbody = document.getElementById('clientes-tbody');
    if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center">Nenhum cliente encontrado.</td></tr>`;
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
            <td style="font-size:0.78rem;color:var(--text-muted);">${c.empresa || '—'}</td>
            <td style="font-size:0.82rem;">${c.contrato || c.proposta || '—'}</td>
            <td style="font-size:0.78rem;color:var(--text-muted);">${c.modelo || '—'}</td>
            <td style="font-size:0.82rem;">${formatMoeda(c.valorcredito)}</td>
            <td style="font-size:0.85rem;">${c.vencimento || '—'}</td>
            <td>${statusClienteBadge(c)}</td>
            <td>${SCORE_BADGE[c.score_risco] || SCORE_BADGE['Novo']}</td>`;
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
fetchEmpresas().then(() => fetchClientes());
setInterval(updateDashboard, 30000);
setInterval(fetchLogs, 5000);

// Eventos — clientes
document.getElementById('clientes-search').addEventListener('input', e => {
    clearTimeout(window._cliSearchTimer);
    window._cliSearchTimer = setTimeout(() => fetchClientes(e.target.value.trim()), 400);
});
document.getElementById('clientes-refresh').addEventListener('click', () => {
    fetchEmpresas().then(() =>
        fetchClientes(document.getElementById('clientes-search').value.trim())
    );
});
document.getElementById('empresa-select').addEventListener('change', () => {
    fetchClientes(document.getElementById('clientes-search').value.trim(), 0);
});

// =============================================================================
// COBRANÇA OPERACIONAL
// =============================================================================
let cobFiltro  = 'todos';
let cobOffset  = 0;
const COB_LIMITE = 20;

// ── Badges visuais ────────────────────────────────────────────────────────────
function atrasoBadge(dias) {
    if (dias === 0)
        return `<span style="background:rgba(16,185,129,.15);color:#34d399;border:1px solid rgba(16,185,129,.3);
            border-radius:20px;padding:3px 11px;font-size:.78rem;font-weight:700;">Hoje</span>`;
    if (dias <= 7)
        return `<span style="background:rgba(245,158,11,.15);color:#fbbf24;border:1px solid rgba(245,158,11,.3);
            border-radius:20px;padding:3px 11px;font-size:.78rem;font-weight:700;">${dias}d</span>`;
    if (dias <= 30)
        return `<span style="background:rgba(249,115,22,.15);color:#fb923c;border:1px solid rgba(249,115,22,.3);
            border-radius:20px;padding:3px 11px;font-size:.78rem;font-weight:700;">${dias}d</span>`;
    return `<span style="background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3);
        border-radius:20px;padding:3px 11px;font-size:.78rem;font-weight:700;">${dias}d</span>`;
}

function enviosBadges(envios) {
    const cfg = [
        { key: 'D-7',      cor: '#60a5fa', bg: 'rgba(59,130,246,.22)',  title: 'Aviso D-7'    },
        { key: 'D-1',      cor: '#fbbf24', bg: 'rgba(245,158,11,.22)', title: 'Lembrete D-1'  },
        { key: 'Cobranca', cor: '#f87171', bg: 'rgba(239,68,68,.22)',  title: 'Cobrança D+2'  },
    ];
    return cfg.map(b => {
        const n = (envios && envios[b.key]) || 0;
        return `<span title="${b.title}" style="
            display:inline-flex;align-items:center;justify-content:center;
            width:22px;height:22px;border-radius:50%;
            background:${b.bg};color:${b.cor};
            font-size:.7rem;font-weight:800;margin-right:2px;">${n}</span>`;
    }).join('');
}

function histBar(pct) {
    const cor = pct >= 80 ? '#34d399' : pct >= 50 ? '#fbbf24' : '#f87171';
    return `<div style="display:flex;align-items:center;gap:6px;">
        <div style="width:56px;height:5px;background:rgba(255,255,255,.08);
                    border-radius:3px;overflow:hidden;flex-shrink:0;">
            <div style="width:${pct}%;height:100%;background:${cor};border-radius:3px;"></div>
        </div>
        <span style="font-size:.72rem;color:var(--text-muted);">${pct}%</span>
    </div>`;
}

// ── Render da tabela ──────────────────────────────────────────────────────────
function renderCobranca(clientes) {
    const tbody = document.getElementById('cob-tbody');
    if (!clientes || clientes.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="color:var(--text-muted);">
            Nenhum cliente em cobrança ativa no momento.</td></tr>`;
        return;
    }
    tbody.innerHTML = '';
    clientes.forEach(c => {
        const parcelaStr = c.prazo > 0
            ? `Parcela ${c.parcela_atual}/${c.prazo}`
            : c.vencimento ? `Venc. ${c.vencimento}` : '—';

        const cnyCor = c.dias_atraso > 0 ? '#f87171' : '#34d399';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>
                <div style="font-weight:600;color:white;margin-bottom:3px;">${c.nome}</div>
                <div style="font-size:.73rem;color:var(--text-muted);">
                    <span style="background:rgba(255,255,255,.05);padding:1px 5px;border-radius:3px;">
                        ${c.cpf}</span>&nbsp;·&nbsp;${c.telefone_fmt || '—'}
                </div>
            </td>
            <td>
                <div style="font-size:.82rem;color:white;">${c.contrato || '—'}</div>
                <div style="font-size:.72rem;color:var(--text-muted);margin-top:3px;">
                    ${c.modelo} · ${parcelaStr}
                </div>
            </td>
            <td style="font-weight:700;color:white;white-space:nowrap;">
                R$&nbsp;${(c.valor || 0).toLocaleString('pt-BR', {minimumFractionDigits:2})}
            </td>
            <td>${atrasoBadge(c.dias_atraso)}</td>
            <td style="white-space:nowrap;">${enviosBadges(c.envios)}</td>
            <td>
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:.75rem;
                             color:var(--text-muted);">
                    <span style="width:7px;height:7px;border-radius:50%;display:inline-block;
                                 background:${cnyCor};flex-shrink:0;"></span>
                    Em aberto
                </span>
            </td>
            <td>${histBar(c.historico_pct)}</td>
            <td style="font-size:.75rem;color:var(--text-muted);white-space:nowrap;">
                ${c.ultimo_contato || '—'}
            </td>
            <td style="white-space:nowrap;">
                <a href="tel:${c.telefone}"
                   style="display:inline-flex;align-items:center;gap:4px;padding:4px 9px;
                          border:1px solid var(--border);border-radius:6px;color:var(--text-muted);
                          font-size:.73rem;text-decoration:none;margin-right:4px;transition:color .15s;"
                   onmouseover="this.style.color='#60a5fa';this.style.borderColor='#60a5fa'"
                   onmouseout="this.style.color='var(--text-muted)';this.style.borderColor='var(--border)'">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.11 11 19.79 19.79 0 0 1 1.08 2.18 2 2 0 0 1 3.05 0h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.09 7.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21 15z"/>
                    </svg>
                    Ligar
                </a>
                <span class="btn-2avia"
                    data-tel="${c.telefone}" data-venc="${c.vencimento}"
                    data-nome="${encodeURIComponent(c.nome)}"
                    style="display:inline-flex;align-items:center;gap:4px;padding:4px 9px;
                           border:1px solid rgba(245,158,11,.35);border-radius:6px;color:#fbbf24;
                           font-size:.73rem;cursor:pointer;transition:opacity .15s;"
                    onmouseover="this.style.opacity='.7'" onmouseout="this.style.opacity='1'">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 2L11 13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                    </svg>
                    2ª via
                </span>
            </td>`;
        tbody.appendChild(tr);
    });
}

// ── 2ª via via WhatsApp ───────────────────────────────────────────────────────
document.getElementById('cob-tbody').addEventListener('click', e => {
    const btn = e.target.closest('.btn-2avia');
    if (!btn) return;
    const tel  = btn.dataset.tel;
    const venc = btn.dataset.venc;
    const nome = decodeURIComponent(btn.dataset.nome);
    const msg  = encodeURIComponent(
        `Olá, ${nome}!\n\nIdentificamos que o seu boleto do consórcio com vencimento em ` +
        `*${venc}* ainda não foi liquidado em nosso sistema.\n\n` +
        `Caso já tenha realizado o pagamento, desconsidere esta mensagem.\n` +
        `Caso contrário, regularize para evitar juros e proteger seu contrato.\n\n` +
        `Estamos à disposição!\n\n*Socel Motos - Yamaha*`
    );
    window.open(`https://wa.me/${tel}?text=${msg}`, '_blank');
});

// ── Paginação ─────────────────────────────────────────────────────────────────
function renderPaginacaoCobranca(total, offset) {
    const container = document.getElementById('cob-paginacao');
    container.innerHTML = '';
    const totalPags = Math.ceil(total / COB_LIMITE);
    const pagAtual  = Math.floor(offset / COB_LIMITE);
    for (let i = 0; i < totalPags; i++) {
        const btn = document.createElement('button');
        btn.textContent = i + 1;
        btn.style.cssText = `padding:4px 10px;border-radius:5px;border:1px solid var(--border);
            background:${i === pagAtual ? 'var(--primary)' : 'transparent'};
            color:${i === pagAtual ? '#fff' : 'var(--text-muted)'};cursor:pointer;font-size:.8rem;`;
        btn.onclick = () => fetchCobranca(i * COB_LIMITE);
        container.appendChild(btn);
    }
}

// ── Fetch principal ───────────────────────────────────────────────────────────
async function fetchCobranca(offset = 0) {
    const tbody = document.getElementById('cob-tbody');
    tbody.innerHTML = `<tr><td colspan="9" class="text-center"
        style="color:var(--text-muted);">Carregando...</td></tr>`;
    try {
        const q = document.getElementById('cob-search')?.value?.trim() || '';
        const params = new URLSearchParams({
            filtro: cobFiltro, q, limite: COB_LIMITE, offset
        });
        const data = await fetch(`${API_URL}/cobranca-operacional?${params}`)
            .then(r => r.json());

        if (data.error) throw new Error(data.error);
        cobOffset = offset;

        // Subtítulo
        const vt = (data.valor_total || 0).toLocaleString('pt-BR',
            { minimumFractionDigits: 0, maximumFractionDigits: 0 });
        document.getElementById('cob-subtitle').textContent =
            `${data.total || 0} clientes inadimplentes · R$ ${vt} em atraso`;

        // Enviados hoje
        document.getElementById('cob-enviados-hoje').textContent =
            data.enviados_hoje ?? '—';

        // Contagens das abas
        const pf = data.por_filtro || {};
        document.getElementById('ct-todos').textContent   = pf.todos   ?? '—';
        document.getElementById('ct-hoje').textContent    = pf.hoje    ?? '—';
        document.getElementById('ct-ate7').textContent    = pf.ate7    ?? '—';
        document.getElementById('ct-8a30').textContent    = pf['8a30'] ?? '—';
        document.getElementById('ct-30mais').textContent  = pf['30mais'] ?? '—';
        document.getElementById('ct-risco').textContent   = pf.risco   ?? '—';

        renderCobranca(data.clientes || []);
        renderPaginacaoCobranca(data.total || 0, offset);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center"
            style="color:#ef4444;">Erro: ${e.message}</td></tr>`;
    }
}

// ── Event listeners das abas ──────────────────────────────────────────────────
document.getElementById('cob-tabs').addEventListener('click', e => {
    const btn = e.target.closest('.cob-tab');
    if (!btn) return;
    document.querySelectorAll('#cob-tabs .cob-tab').forEach(b => b.classList.remove('cob-active'));
    btn.classList.add('cob-active');
    cobFiltro = btn.dataset.filtro;
    fetchCobranca(0);
});

document.getElementById('cob-search').addEventListener('input', e => {
    clearTimeout(window._cobSearchTimer);
    window._cobSearchTimer = setTimeout(() => fetchCobranca(0), 400);
});

// Carrega junto com o dashboard
fetchCobranca();
