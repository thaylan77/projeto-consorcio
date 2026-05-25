"""
respostas_whatsapp.py — Processamento inteligente de respostas via WhatsApp

Fluxo:
  1. Sunchat envia um POST para /webhook/sunchat quando um cliente responde
  2. Claude Haiku classifica a intenção em milissegundos
  3. O sistema age automaticamente:
     - JA_PAGOU      → marca boleto como pago, para cobranças futuras
     - PEDIR_BOLETO  → reenvia o PDF mais recente do cliente
     - PEDIR_PRAZO   → registra e enfileira para revisão humana
     - RECLAMACAO    → idem
     - OUTRO         → apenas loga

Configuração Sunchat:
  No painel da Sunchat, configure o Webhook URL para:
    http://<IP_DA_MAQUINA>:5000/webhook/sunchat
"""

import os
import re
import glob
import base64
import time
from datetime import datetime

import requests
import anthropic

from config import TOKEN_SUNCHAT, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, PASTA_ENVIADOS, PASTA_VALIDADOS
import db
from logger import log

MODULO = "IA-Respostas"

URL_TEXTO = "https://api.sunchat.com.br/core/v2/api/chats/send-text"
URL_MEDIA  = "https://api.sunchat.com.br/core/v2/api/chats/send-media"


# =============================================================================
# CLASSIFICAÇÃO COM CLAUDE
# =============================================================================
def classificar_intencao(mensagem: str, nome_cliente: str) -> str:
    """
    Retorna uma das categorias:
      JA_PAGOU | PEDIR_BOLETO | PEDIR_PRAZO | RECLAMACAO | OUTRO
    """
    if not ANTHROPIC_API_KEY:
        log("ANTHROPIC_API_KEY nao configurada. Classificando como OUTRO.", "WARNING", MODULO)
        return "OUTRO"

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resposta = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=15,
            messages=[{
                "role": "user",
                "content": (
                    f"Cliente de consorcio '{nome_cliente}' respondeu a uma mensagem de cobranca:\n"
                    f'"{mensagem}"\n\n'
                    "Classifique a intencao em UMA palavra:\n"
                    "JA_PAGOU — afirma que ja pagou\n"
                    "PEDIR_BOLETO — quer receber o boleto/PDF\n"
                    "PEDIR_PRAZO — pede prazo ou renegociacao\n"
                    "RECLAMACAO — reclama ou esta aborrecido\n"
                    "OUTRO — qualquer outra coisa\n\n"
                    "Responda SOMENTE com a palavra da categoria."
                ),
            }],
        )
        categoria = resposta.content[0].text.strip().upper()
        # Garante que só retorna categorias válidas
        validas = {"JA_PAGOU", "PEDIR_BOLETO", "PEDIR_PRAZO", "RECLAMACAO", "OUTRO"}
        return categoria if categoria in validas else "OUTRO"

    except Exception as e:
        log(f"Erro na API Claude: {e}", "ERROR", MODULO)
        return "OUTRO"


# =============================================================================
# PAGAMENTOS INFORMADOS (delegado ao db)
# =============================================================================
def marcar_como_pago(telefone: str, nome: str, mensagem_original: str) -> None:
    db.registrar_pagamento(telefone, nome, mensagem_original)


def telefone_ja_pagou(telefone: str) -> bool:
    return db.telefone_ja_pagou(telefone)


# =============================================================================
# AÇÕES
# =============================================================================
def _carregar_mapa_clientes() -> dict:
    """Retorna {telefone: {nome, cpf}} a partir do CSV."""
    try:
        import pandas as pd
        df = pd.read_csv("relatorio_microwork_consorcio.csv")
        mapa = {}
        for _, row in df.iterrows():
            cpf = re.sub(r"\D", "", str(row["pessoacpfcnpj"]))
            tel_limpo = re.sub(r"\D", "", str(row["celularformatado"]))
            if tel_limpo and len(tel_limpo) >= 8:
                if not tel_limpo.startswith("55"):
                    tel_limpo = "55" + tel_limpo
                if len(tel_limpo) == 12:
                    tel_limpo = tel_limpo[:4] + "9" + tel_limpo[4:]
                mapa[tel_limpo] = {"nome": str(row["pessoa"]).title(), "cpf": cpf}
        return mapa
    except Exception:
        return {}


def _ultimo_boleto_do_cliente(cpf: str) -> str | None:
    """Procura o PDF mais recente do CPF nas pastas Validados e Enviados."""
    padrao = f"Boleto_{cpf}_Venc-*.pdf"
    candidatos = (
        glob.glob(os.path.join(PASTA_VALIDADOS, padrao)) +
        glob.glob(os.path.join(PASTA_ENVIADOS,  padrao))
    )
    if not candidatos:
        return None
    return max(candidatos, key=os.path.getmtime)


def _enviar_texto(telefone: str, mensagem: str) -> bool:
    headers = {"access-token": TOKEN_SUNCHAT, "Content-Type": "application/json"}
    try:
        resp = requests.post(URL_TEXTO, json={
            "number": telefone, "message": mensagem,
            "forceSend": True, "verifyContact": True,
        }, headers=headers, timeout=20)
        return resp.status_code in (200, 201, 202)
    except Exception:
        return False


def _reenviar_boleto(telefone: str, nome: str, cpf: str) -> bool:
    caminho = _ultimo_boleto_do_cliente(cpf)
    if not caminho:
        log(f"Nenhum boleto encontrado para CPF {cpf}.", "WARNING", MODULO)
        return False

    nome_arquivo = os.path.basename(caminho)
    headers = {"access-token": TOKEN_SUNCHAT, "Content-Type": "application/json"}
    try:
        with open(caminho, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        resp = requests.post(URL_MEDIA, json={
            "number": telefone, "base64": encoded, "extension": ".pdf",
            "fileName": nome_arquivo, "forceSend": True, "verifyContact": True,
        }, headers=headers, timeout=40)
        return resp.status_code in (200, 201, 202)
    except Exception as e:
        log(f"Erro ao reenviar boleto: {e}", "ERROR", MODULO)
        return False


# =============================================================================
# PROCESSADOR PRINCIPAL
# =============================================================================
def processar_resposta(telefone: str, mensagem: str) -> dict:
    """
    Ponto de entrada para processar uma mensagem recebida.
    Retorna um dict com {telefone, nome, intencao, acao, sucesso}.
    """
    mapa = _carregar_mapa_clientes()
    cliente = mapa.get(telefone, {})
    nome = cliente.get("nome", "Cliente")
    cpf  = cliente.get("cpf", "")

    log(f"Resposta recebida de {telefone} ({nome}): '{mensagem[:80]}'", modulo=MODULO)

    intencao = classificar_intencao(mensagem, nome)
    log(f"Classificacao IA → {intencao}", modulo=MODULO)

    acao    = "nenhuma"
    sucesso = True

    if intencao == "JA_PAGOU":
        marcar_como_pago(telefone, nome, mensagem)
        _enviar_texto(telefone,
            f"Perfeito, {nome}! Obrigado pela confirmacao. "
            f"Ficamos a disposicao. *Socel Motos - Yamaha*"
        )
        acao = "pagamento_marcado"
        log(f"Pagamento informado por {nome} ({telefone}).", "SUCCESS", MODULO)

    elif intencao == "PEDIR_BOLETO":
        ok = _reenviar_boleto(telefone, nome, cpf)
        if ok:
            _enviar_texto(telefone,
                f"Ola, {nome}! Segue o boleto novamente em anexo. "
                f"Qualquer duvida estamos a disposicao. *Socel Motos*"
            )
            acao = "boleto_reenviado"
            log(f"Boleto reenviado para {nome}.", "SUCCESS", MODULO)
        else:
            acao = "boleto_nao_encontrado"
            sucesso = False

    elif intencao in ("PEDIR_PRAZO", "RECLAMACAO"):
        _enviar_texto(telefone,
            f"Ola, {nome}! Recebemos sua mensagem e um de nossos "
            f"atendentes entrara em contato em breve. *Socel Motos*"
        )
        acao = "encaminhado_humano"
        log(f"Mensagem de {nome} encaminhada para revisao humana ({intencao}).", "WARNING", MODULO)

    else:
        acao = "ignorado"
        log(f"Mensagem de {nome} classificada como OUTRO — sem acao.", modulo=MODULO)

    return {
        "telefone": telefone,
        "nome": nome,
        "intencao": intencao,
        "acao": acao,
        "sucesso": sucesso,
    }


# =============================================================================
# NOTA: a Sunchat NÃO oferece endpoint de polling de mensagens recebidas.
# A integração funciona 100% por webhook push:
#   Sunchat → POST /webhook/sunchat → processar_resposta()
# Por isso esse módulo não tem mais uma rotina de "varredura em lote".
# Mantemos apenas o ponto de entrada manual para teste rápido pela linha de comando.
# =============================================================================

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        _tel, _txt = sys.argv[1], " ".join(sys.argv[2:])
        log(f"Modo teste manual: telefone={_tel} texto={_txt!r}", modulo=MODULO)
        print(processar_resposta(_tel, _txt))
    else:
        log("Modo daemon: nada a fazer. Respostas chegam via webhook /webhook/sunchat.", modulo=MODULO)
