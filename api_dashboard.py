from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from functools import wraps
import os
import re
import glob
import subprocess
import sys
import threading
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


if __name__ == "__main__":
    print("API do Dashboard iniciada na porta 5000")
    print(f"Chave de API: {API_SECRET_KEY[:12]}...")
    print(f"Pipeline agendado: {HORA_PIPELINE} | Cobrador: {HORA_COBRADOR}")
    app.run(host="0.0.0.0", port=5000, debug=False)
