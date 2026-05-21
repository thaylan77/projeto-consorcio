"""
cobrador.py — Cobrança automática D+2

Regras:
  • Consulta o banco SQLite por disparos D-1 cujo vencimento passou >= DIAS_APOS_VENC_PARA_COBRAR dias.
  • Para cada um que ainda não recebeu cobrança e não informou pagamento via IA, envia follow-up.
  • Registra o envio com tipo_disparo "Cobranca" para evitar duplicatas.
"""

import pandas as pd
import requests
import os
import re
import time
from datetime import datetime

from config import TOKEN_SUNCHAT, DIAS_APOS_VENC_PARA_COBRAR
import db
from utils import limpar_telefone
from logger import log

ARQUIVO_CSV = "relatorio_microwork_consorcio.csv"
MODULO = "Cobrador"

URL_TEXTO = "https://api.sunchat.com.br/core/v2/api/chats/send-text"


# =============================================================================
# HISTÓRICO (delegado ao db)
# =============================================================================
def registrar_cobranca(nome: str, cpf: str, vencimento: str, arquivo: str,
                        status: str = "Enviado", erro: str = "") -> None:
    db.registrar_disparo(nome, cpf, vencimento, arquivo, status, erro, "Cobranca")


# =============================================================================
# CLIENTES
# =============================================================================
def carregar_mapa_clientes() -> dict:
    try:
        df = pd.read_csv(ARQUIVO_CSV)
    except Exception:
        return {}
    mapa = {}
    for _, row in df.iterrows():
        cpf = re.sub(r"\D", "", str(row["pessoacpfcnpj"]))
        tel = limpar_telefone(row["celularformatado"])
        if tel:
            mapa[cpf] = {"nome": str(row["pessoa"]).title(), "telefone": tel}
    return mapa


# =============================================================================
# IDENTIFICAR BOLETOS A COBRAR
# =============================================================================
def encontrar_boletos_a_cobrar() -> list[dict]:
    return db.disparos_d1_vencidos(DIAS_APOS_VENC_PARA_COBRAR)


# =============================================================================
# ENVIO DA COBRANÇA
# =============================================================================
def enviar_cobranca(telefone: str, nome: str, data_vencimento: str) -> bool:
    mensagem = (
        f"Ola, {nome}!\n\n"
        f"Identificamos que o seu boleto do consorcio com vencimento em "
        f"*{data_vencimento}* ainda nao foi liquidado em nosso sistema.\n\n"
        f"Caso ja tenha realizado o pagamento, desconsidere esta mensagem e "
        f"agradecemos pela atencao.\n"
        f"Caso contrario, quitando agora voce evita juros e protege seu contrato.\n\n"
        f"Precisando de ajuda, estamos a disposicao!\n\n"
        f"Atenciosamente,\n*Socel Motos - Yamaha*"
    )

    headers = {"access-token": TOKEN_SUNCHAT, "Content-Type": "application/json"}
    try:
        resp = requests.post(URL_TEXTO, json={
            "number": telefone, "message": mensagem,
            "forceSend": True, "verifyContact": True,
        }, headers=headers, timeout=20)
        return resp.status_code in (200, 201, 202)
    except Exception as e:
        log(f"Erro ao enviar cobranca: {e}", "ERROR", MODULO)
        return False


# =============================================================================
# PRINCIPAL
# =============================================================================
def executar_cobranca():
    db.init_db()
    log("Verificando boletos vencidos para cobranca...", modulo=MODULO)
    pendentes = encontrar_boletos_a_cobrar()

    if not pendentes:
        log("Nenhum boleto requer cobranca no momento.", modulo=MODULO)
        return

    log(f"{len(pendentes)} boleto(s) elegivel(is) para cobranca.", modulo=MODULO)
    mapa_clientes = carregar_mapa_clientes()

    cobrados = 0
    erros    = 0

    for entrada in pendentes:
        arquivo    = entrada.get("arquivo", "")
        vencimento = entrada.get("vencimento", "")
        nome_hist  = entrada.get("nome", "Cliente")
        cpf_hist   = entrada.get("cpf", "")

        try:
            cpf_limpo = arquivo.split("_")[1]
        except Exception:
            cpf_limpo = ""

        dados = mapa_clientes.get(cpf_limpo)
        if not dados:
            log(f"CPF sem cadastro/celular para cobranca: {arquivo}", "WARNING", MODULO)
            registrar_cobranca(nome_hist, cpf_hist, vencimento, arquivo,
                               "Erro", "Sem cadastro/celular")
            erros += 1
            continue

        nome     = dados["nome"]
        telefone = dados["telefone"]

        # Pula se cliente já informou pagamento via WhatsApp (IA)
        if db.telefone_ja_pagou(telefone):
            log(f"Cliente ja informou pagamento via WhatsApp, pulando: {nome}", modulo=MODULO)
            continue

        log(f"Cobrando {nome} ({telefone}) | venc {vencimento}", modulo=MODULO)

        if enviar_cobranca(telefone, nome, vencimento):
            log(f"Cobranca enviada: {arquivo}", "SUCCESS", MODULO)
            registrar_cobranca(nome, cpf_hist, vencimento, arquivo, "Enviado")
            cobrados += 1
        else:
            log(f"Falha na cobranca: {arquivo}", "ERROR", MODULO)
            registrar_cobranca(nome, cpf_hist, vencimento, arquivo, "Erro", "Falha no envio")
            erros += 1

        time.sleep(3)

    log(f"Cobrancas enviadas: {cobrados} | Erros: {erros}", "SUCCESS", MODULO)


if __name__ == "__main__":
    executar_cobranca()
