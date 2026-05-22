from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from functools import wraps
import os
import re
import glob
import subprocess
import sys
import threading
from datetime import datetime
from werkzeug.utils import safe_join

import db
from respostas_whatsapp import processar_resposta
from config import (
    API_SECRET_KEY,
    PASTA_PARA_ENVIAR, PASTA_VALIDADOS, PASTA_ENVIADOS,
    PASTA_REJEITADOS, PASTA_REVISAO_MANUAL,
    HORA_PIPELINE, HORA_COBRADOR, HORA_RESPOSTAS,
    JANELA_D7_MIN, JANELA_D7_MAX,
    JANELA_D1_MIN, JANELA_D1_MAX,
    DIAS_APOS_VENC_PARA_COBRAR,
    ANTHROPIC_API_KEY,
    SUNCHAT_WEBHOOK_SECRET,
)

_DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
_ARQUIVO_CSV   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relatorio_microwork_consorcio.csv")

app = Flask(__name__)
CORS(app)
db.init_db()

PASTA_BOLETOS = {
    "para_enviar":    PASTA_PARA_ENVIAR,
    "validados":      PASTA_VALIDADOS,
    "enviados":       PASTA_ENVIADOS,
    "rejeitados":     PASTA_REJEITADOS,
    "revisao_manual": PASTA_REVISAO_MANUAL,
}

ARQUIVO_LOG          = "app.log"
ORQUESTRADOR_SCRIPT  = "orquestrador.py"
COBRADOR_SCRIPT      = "cobrador.py"
AGENDADOR_SCRIPT     = "agendador.py"
RESPOSTAS_SCRIPT     = "respostas_whatsapp.py"


# =============================================================================
# AUTENTICAÇÃO
# =============================================================================
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("key", "")
        if key != API_SECRET_KEY:
            return jsonify({"error": "Nao autorizado. Informe a chave de API correta."}), 401
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# UTILITÁRIOS
# =============================================================================
def contar_pdf(pasta: str) -> int:
    if not os.path.exists(pasta):
        return 0
    return len(glob.glob(os.path.normpath(os.path.join(pasta, "*.pdf"))))


_SCRIPT_TIMEOUT = 2 * 60 * 60  # 2 horas — pipeline Selenium pode ser lento


def _run_background(script: str):
    try:
        subprocess.run([sys.executable, script], timeout=_SCRIPT_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass  # script excedeu o limite; thread é liberada normalmente


# =============================================================================
# ROTAS DE LEITURA (abertas)
# =============================================================================
@app.route("/api/stats", methods=["GET"])
def get_stats():
    return jsonify({k: contar_pdf(v) for k, v in PASTA_BOLETOS.items()})


@app.route("/api/history", methods=["GET"])
def get_history():
    try:
        limite = min(int(request.args.get("limite", 200)), 1000)
        offset = int(request.args.get("offset", 0))
        return jsonify(db.listar_disparos(limite, offset))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs", methods=["GET"])
def get_logs():
    if os.path.exists(ARQUIVO_LOG):
        try:
            with open(ARQUIVO_LOG, "r", encoding="utf-8", errors="replace") as f:
                return jsonify(f.readlines()[-100:])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify(["Aguardando inicio do log..."])


@app.route("/api/download/<pasta>/<nome_arquivo>", methods=["GET"])
def download_pdf(pasta, nome_arquivo):
    if pasta not in PASTA_BOLETOS:
        return jsonify({"error": "Pasta invalida."}), 400
    caminho = safe_join(PASTA_BOLETOS[pasta], nome_arquivo)
    if os.path.exists(caminho):
        return send_file(caminho, as_attachment=False)
    return jsonify({"error": "Arquivo nao encontrado."}), 404


def _carregar_clientes_csv():
    """Lê o CSV e retorna lista de dicts enriquecidos com status do banco."""
    import pandas as pd
    df = pd.read_csv(_ARQUIVO_CSV)
    mapa_status = db.status_por_cpf()
    mapa_score  = db.score_risco_por_cpf()
    pagamentos  = {p["telefone"] for p in db.listar_pagamentos()}

    clientes = []
    for _, row in df.iterrows():
        cpf_raw = re.sub(r"\D", "", str(row.get("pessoacpfcnpj", "")))
        nome    = str(row.get("pessoa", "")).strip().title()
        tel     = re.sub(r"\D", "", str(row.get("celularformatado", "")))

        if not cpf_raw or not nome or nome in ("", "Nan"):
            continue

        if tel and not tel.startswith("55"):
            tel = "55" + tel
        if len(tel) == 12:
            tel = tel[:4] + "9" + tel[4:]

        cpf_mask = (f"{cpf_raw[:3]}.***.***-{cpf_raw[-2:]}"
                    if len(cpf_raw) == 11 else cpf_raw)

        extras = {}
        for col in ("contrato", "proposta", "empresa", "modelo",
                    "administradorareduzida", "pontovenda", "vendedor",
                    "datavenda", "prazo", "valorprimeiraparcela", "valorcredito"):
            if col in df.columns:
                val = row.get(col, "")
                extras[col] = "" if str(val) in ("nan", "None", "") else str(val)

        disp  = mapa_status.get(cpf_raw, {})
        risco = mapa_score.get(cpf_raw, {})
        pago  = tel in pagamentos

        clientes.append({
            "nome":          nome,
            "cpf":           cpf_mask,
            "cpf_raw":       cpf_raw,
            "telefone":      tel,
            "ultimo_tipo":   disp.get("tipo_disparo", ""),
            "ultimo_status": disp.get("status", ""),
            "vencimento":    disp.get("vencimento", ""),
            "pago":          pago,
            "score_risco":   risco.get("score", "Novo"),
            **extras,
        })
    return clientes


@app.route("/api/clientes", methods=["GET"])
def get_clientes():
    """Retorna lista de clientes do CSV cruzada com status, score de risco e filial."""
    if not os.path.exists(_ARQUIVO_CSV):
        return jsonify({"clientes": [], "total": 0, "sem_csv": True}), 200
    try:
        busca   = request.args.get("q", "").lower().strip()
        empresa = request.args.get("empresa", "").strip()
        limite  = min(int(request.args.get("limite", 200)), 1000)
        offset  = int(request.args.get("offset", 0))

        clientes = _carregar_clientes_csv()

        # Filtros
        if empresa:
            clientes = [c for c in clientes if c.get("empresa", "") == empresa]
        if busca:
            clientes = [c for c in clientes if
                busca in c["nome"].lower() or
                busca in c["cpf"].lower() or
                busca in c["telefone"] or
                busca in c.get("contrato", "").lower() or
                busca in c.get("empresa", "").lower()]

        total      = len(clientes)
        disparados = sum(1 for c in clientes if c["ultimo_tipo"])
        pendentes  = sum(1 for c in clientes if not c["ultimo_tipo"] and not c["pago"])
        pagos      = sum(1 for c in clientes if c["pago"])
        por_score  = {}
        for c in clientes:
            s = c["score_risco"]
            por_score[s] = por_score.get(s, 0) + 1

        # Remove cpf_raw do retorno (não expor dado bruto)
        pagina = [{k: v for k, v in c.items() if k != "cpf_raw"}
                  for c in clientes[offset: offset + limite]]

        return jsonify({
            "total": total, "disparados": disparados,
            "pendentes": pendentes, "pagos": pagos,
            "por_score": por_score,
            "clientes":  pagina,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/empresas", methods=["GET"])
def get_empresas():
    """Retorna lista de filiais com totais de clientes, disparados e score de risco."""
    if not os.path.exists(_ARQUIVO_CSV):
        return jsonify([]), 200
    try:
        clientes = _carregar_clientes_csv()
        mapa: dict = {}
        for c in clientes:
            emp = c.get("empresa", "Sem filial") or "Sem filial"
            if emp not in mapa:
                mapa[emp] = {"empresa": emp, "total": 0, "disparados": 0,
                             "pendentes": 0, "alto_risco": 0}
            mapa[emp]["total"] += 1
            if c["ultimo_tipo"]:
                mapa[emp]["disparados"] += 1
            if not c["ultimo_tipo"] and not c["pago"]:
                mapa[emp]["pendentes"] += 1
            if c["score_risco"] in ("Alto", "Critico"):
                mapa[emp]["alto_risco"] += 1

        return jsonify(sorted(mapa.values(), key=lambda x: x["total"], reverse=True))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agenda", methods=["GET"])
def get_agenda():
    """Retorna configuração de agendamento para exibição no dashboard."""
    return jsonify({
        "hora_pipeline":  HORA_PIPELINE,
        "hora_cobrador":  HORA_COBRADOR,
        "hora_respostas": HORA_RESPOSTAS,
        "janela_d7":      f"{JANELA_D7_MIN}-{JANELA_D7_MAX} dias antes",
        "janela_d1":      f"{JANELA_D1_MIN}-{JANELA_D1_MAX} dias antes",
        "cobranca_apos":  f"{DIAS_APOS_VENC_PARA_COBRAR} dias apos o vencimento",
        "ia_ativa":       bool(ANTHROPIC_API_KEY),
    })


# =============================================================================
# ROTAS DE AÇÃO (protegidas por API key)
# =============================================================================
@app.route("/api/run", methods=["POST"])
@require_api_key
def run_system():
    threading.Thread(target=_run_background, args=(ORQUESTRADOR_SCRIPT,), daemon=True).start()
    return jsonify({"status": "Pipeline iniciado no servidor!"})


@app.route("/api/run/cobrador", methods=["POST"])
@require_api_key
def run_cobrador():
    threading.Thread(target=_run_background, args=(COBRADOR_SCRIPT,), daemon=True).start()
    return jsonify({"status": "Cobranca D+2 iniciada!"})


@app.route("/api/run/respostas", methods=["POST"])
@require_api_key
def run_respostas():
    threading.Thread(target=_run_background, args=(RESPOSTAS_SCRIPT,), daemon=True).start()
    return jsonify({"status": "Analise de respostas WhatsApp iniciada!"})


@app.route("/")
def index():
    return send_from_directory(_DASHBOARD_DIR, "index.html")


@app.route("/<path:filename>")
def static_dashboard(filename):
    return send_from_directory(_DASHBOARD_DIR, filename)


@app.route("/api/health", methods=["GET"])
def health():
    """Endpoint de health-check para monitoramento e deploys."""
    return jsonify({"status": "ok"}), 200


@app.route("/webhook/sunchat", methods=["POST"])
def webhook_sunchat():
    """Recebe mensagens de resposta de clientes via Sunchat e processa com IA."""
    # Verifica segredo compartilhado quando configurado
    if SUNCHAT_WEBHOOK_SECRET:
        recebido = request.headers.get("X-Sunchat-Secret", "")
        if recebido != SUNCHAT_WEBHOOK_SECRET:
            return jsonify({"error": "Nao autorizado."}), 401

    try:
        payload = request.get_json(force=True) or {}
        telefone = str(payload.get("number") or payload.get("from") or "").strip()
        mensagem = str(payload.get("message") or payload.get("body") or "").strip()
        if not telefone or not mensagem:
            return jsonify({"error": "Campos 'number' e 'message' obrigatorios."}), 400

        resultado = processar_resposta(telefone, mensagem)
        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# COBRANÇA OPERACIONAL
# =============================================================================
def _csv_get(dados, col: str, default: str = "") -> str:
    """Lê coluna de uma Series pandas ou dict, normalizando valores nulos."""
    v = dados.get(col, default) if hasattr(dados, "get") else default
    s = str(v) if v is not None else ""
    return "" if s.strip() in ("nan", "None", "NaN", "") else s.strip()


def _fmt_ultimo_contato(ts: str) -> str:
    """'20/05/2026 14:22:35' → '20/Mai 14:22'"""
    if not ts:
        return ""
    _M = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
          "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    try:
        partes = ts.split(" ")
        d, m, _ = partes[0].split("/")
        hora = partes[1][:5] if len(partes) > 1 else ""
        return f"{int(d)}/{_M[int(m)]} {hora}"
    except Exception:
        return ts


def _parse_valor(s: str) -> float:
    """Converte strings 'R$ 1.234,56' ou '1234.56' para float."""
    s = re.sub(r"[^\d,.]", "", s)
    if "," in s and "." in s:          # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                     # 1234,56
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def _construir_dados_cobranca() -> list[dict]:
    """
    Constrói a lista de clientes com boleto D-1 enviado e ainda não pagos.
    Cruza disparos com CSV para enriquecer com valor, parcela, modelo, etc.
    Retorna lista ordenada por maior atraso.
    """
    import pandas as pd

    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # ── CSV ────────────────────────────────────────────────────────────────────
    mapa_csv: dict = {}
    if os.path.exists(_ARQUIVO_CSV):
        try:
            df = pd.read_csv(_ARQUIVO_CSV)
            for _, row in df.iterrows():
                cpf = re.sub(r"\D", "", str(row.get("pessoacpfcnpj", "")))
                if cpf:
                    mapa_csv[cpf] = row
        except Exception:
            pass

    # ── Disparos ───────────────────────────────────────────────────────────────
    rows = db.listar_disparos_ativos()

    # Agrupa por arquivo (= um boleto único)
    por_arquivo: dict = {}
    for r in rows:
        arq = r["arquivo"]
        if arq not in por_arquivo:
            por_arquivo[arq] = {
                "arquivo":    arq,
                "nome":       r["nome"] or "",
                "cpf_db":     re.sub(r"\D", "", r["cpf"] or ""),
                "vencimento": r["vencimento"] or "",
                "envios":     {"D-7": 0, "D-1": 0, "Cobranca": 0},
                "ultimo_ts":  "",
            }
        e = por_arquivo[arq]
        if not e["nome"] and r["nome"]:
            e["nome"] = r["nome"]
        tipo = r["tipo_disparo"]
        if tipo in e["envios"]:
            e["envios"][tipo] += 1
        d = r["data_disparo"] or ""
        if d > e["ultimo_ts"]:
            e["ultimo_ts"] = d

    # ── Pagamentos confirmados via WhatsApp ────────────────────────────────────
    pagamentos_tel = {p["telefone"] for p in db.listar_pagamentos()}

    # ── Monta resultado ────────────────────────────────────────────────────────
    resultado = []
    for arq, entry in por_arquivo.items():
        if entry["envios"]["D-1"] == 0:
            continue  # ainda não recebeu D-1; não entra na cobrança ativa

        # CPF: preferência pelo nome do arquivo
        m = re.search(r"Boleto_(\d+)_", arq)
        cpf = m.group(1) if m else entry["cpf_db"]
        cpf = re.sub(r"\D", "", cpf)

        dados = mapa_csv.get(cpf, {})

        # Telefone
        tel_raw = _csv_get(dados, "celularformatado")
        tel = re.sub(r"\D", "", tel_raw)
        if tel and not tel.startswith("55"):
            tel = "55" + tel
        if len(tel) == 12:
            tel = tel[:4] + "9" + tel[4:]

        if tel and tel in pagamentos_tel:
            continue  # já confirmou pagamento via IA

        # Atraso
        venc_str = entry["vencimento"]
        try:
            venc_dt = datetime.strptime(venc_str, "%d/%m/%Y").replace(
                hour=0, minute=0, second=0, microsecond=0)
            dias_atraso = (hoje - venc_dt).days
        except Exception:
            dias_atraso = 0
        if dias_atraso < 0:
            continue  # ainda não venceu

        # Parcela atual e prazo
        prazo_str = _csv_get(dados, "prazo")
        try:
            prazo = int(float(prazo_str.replace(",", ".")))
        except Exception:
            prazo = 0

        datavenda_str = _csv_get(dados, "datavenda")
        parcela_atual = 0
        if datavenda_str:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    dv = datetime.strptime(datavenda_str[:10], fmt)
                    parcela_atual = max(1, (hoje.year - dv.year) * 12
                                       + (hoje.month - dv.month))
                    break
                except Exception:
                    continue

        historico_pct = (round(parcela_atual / prazo * 100)
                         if prazo > 0 and parcela_atual > 0 else 0)
        historico_pct = min(historico_pct, 99)

        # Valor
        valor = _parse_valor(_csv_get(dados, "valorprimeiraparcela"))

        # Outros campos
        nome     = (entry["nome"] or _csv_get(dados, "pessoa").title() or "—")
        modelo   = _csv_get(dados, "modelo") or "—"
        contrato = (_csv_get(dados, "contrato") or
                    _csv_get(dados, "proposta") or "")

        # CPF mascarado
        cpf_mask = (f"{cpf[:3]}.***.***-{cpf[-2:]}"
                    if len(cpf) == 11 else cpf)

        # Telefone formatado para exibição
        if len(tel) == 13:
            tel_fmt = f"+{tel[:2]} ({tel[2:4]}) {tel[4:9]}-{tel[9:]}"
        elif len(tel) == 12:
            tel_fmt = f"+{tel[:2]} ({tel[2:4]}) {tel[4:8]}-{tel[8:]}"
        else:
            tel_fmt = tel or "—"

        total_envios = sum(entry["envios"].values())

        resultado.append({
            "nome":          nome,
            "cpf":           cpf_mask,
            "telefone":      tel,
            "telefone_fmt":  tel_fmt,
            "contrato":      contrato,
            "modelo":        modelo,
            "parcela_atual": parcela_atual,
            "prazo":         prazo,
            "valor":         round(valor, 2),
            "dias_atraso":   dias_atraso,
            "vencimento":    venc_str,
            "envios":        entry["envios"],
            "total_envios":  total_envios,
            "historico_pct": historico_pct,
            "ultimo_contato": _fmt_ultimo_contato(entry["ultimo_ts"]),
        })

    resultado.sort(key=lambda x: x["dias_atraso"], reverse=True)
    return resultado


@app.route("/api/cobranca-operacional", methods=["GET"])
def get_cobranca_operacional():
    """Dados para a tela de cobrança operacional (abas de filtro + tabela)."""
    try:
        filtro = request.args.get("filtro", "todos")
        q      = request.args.get("q", "").lower().strip()
        limite = min(int(request.args.get("limite", 20)), 200)
        offset = int(request.args.get("offset", 0))

        clientes = _construir_dados_cobranca()

        # Contagens por aba (sobre o total, antes de filtrar)
        por_filtro = {
            "todos":   len(clientes),
            "hoje":    sum(1 for c in clientes if c["dias_atraso"] == 0),
            "ate7":    sum(1 for c in clientes if 1 <= c["dias_atraso"] <= 7),
            "8a30":    sum(1 for c in clientes if 8 <= c["dias_atraso"] <= 30),
            "30mais":  sum(1 for c in clientes if c["dias_atraso"] > 30),
            "risco":   sum(1 for c in clientes if c["total_envios"] >= 3),
        }

        valor_total   = sum(c["valor"] for c in clientes)
        enviados_hoje = db.stats_do_dia().get("enviados", 0)

        # Aplica filtro de aba
        if filtro == "hoje":
            clientes = [c for c in clientes if c["dias_atraso"] == 0]
        elif filtro == "ate7":
            clientes = [c for c in clientes if 1 <= c["dias_atraso"] <= 7]
        elif filtro == "8a30":
            clientes = [c for c in clientes if 8 <= c["dias_atraso"] <= 30]
        elif filtro == "30mais":
            clientes = [c for c in clientes if c["dias_atraso"] > 30]
        elif filtro == "risco":
            clientes = [c for c in clientes if c["total_envios"] >= 3]

        # Busca textual
        if q:
            clientes = [c for c in clientes if
                q in c["nome"].lower() or
                q in c["cpf"].lower() or
                q in c["telefone"] or
                q in c["contrato"].lower()]

        total  = len(clientes)
        pagina = clientes[offset: offset + limite]

        return jsonify({
            "total":         total,
            "valor_total":   round(valor_total, 2),
            "enviados_hoje": enviados_hoje,
            "por_filtro":    por_filtro,
            "clientes":      pagina,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("API do Dashboard iniciada na porta 5000")
    print(f"Chave de API: {API_SECRET_KEY[:12]}...")
    print(f"Pipeline agendado: {HORA_PIPELINE} | Cobrador: {HORA_COBRADOR}")
    app.run(host="0.0.0.0", port=5000, debug=False)
