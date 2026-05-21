import pandas as pd
import requests
import base64
import os
import shutil
import re
import time
from datetime import datetime

from config import (
    TOKEN_SUNCHAT,
    PASTA_VALIDADOS, PASTA_ENVIADOS,
    JANELA_D7_MIN, JANELA_D7_MAX,
    JANELA_D1_MIN, JANELA_D1_MAX,
)
import db
from utils import limpar_telefone
from logger import log

ARQUIVO_CSV = "relatorio_microwork_consorcio.csv"
MODULO = "Disparador"

URL_TEXTO = "https://api.sunchat.com.br/core/v2/api/chats/send-text"
URL_MEDIA  = "https://api.sunchat.com.br/core/v2/api/chats/send-media"



# =============================================================================
# HISTÓRICO (delegado ao db)
# =============================================================================
def ja_enviado_tipo(nome_arquivo: str, tipo: str) -> bool:
    return db.ja_enviado_tipo(nome_arquivo, tipo)


def registrar_historico(nome: str, cpf: str, vencimento: str, arquivo: str,
                         status: str = "Enviado", erro: str = "",
                         tipo_disparo: str = "D-1") -> None:
    nome_fmt = nome.title() if nome else "Desconhecido"
    cpf_fmt  = cpf[:3] + ".***.***-" + cpf[-2:] if len(cpf) >= 11 else cpf
    db.registrar_disparo(nome_fmt, cpf_fmt, vencimento, arquivo, status, erro, tipo_disparo)


# =============================================================================
# MAPA DE CLIENTES
# =============================================================================
def carregar_mapa_clientes() -> dict:
    log("Mapeando clientes do CSV...", modulo=MODULO)
    try:
        df = pd.read_csv(ARQUIVO_CSV)
    except Exception:
        return {}
    mapa = {}
    for _, row in df.iterrows():
        cpf = re.sub(r"\D", "", str(row["pessoacpfcnpj"]))
        telefone = limpar_telefone(row["celularformatado"])
        if telefone:
            mapa[cpf] = {"nome": str(row["pessoa"]), "telefone": telefone}
    return mapa


# =============================================================================
# ENVIO
# =============================================================================
def _montar_mensagem(nome: str, data_vencimento_str: str, tipo: str) -> str:
    if tipo == "D-7":
        return (
            f"Ola, {nome}!\n\n"
            f"Passando para avisar que o seu boleto do consorcio vence em *{data_vencimento_str}*.\n"
            f"Segue o PDF em anexo para facilitar o pagamento.\n\n"
            f"Atenciosamente,\n*Socel Motos - Concessionarias Yamaha*"
        )
    else:  # D-1
        return (
            f"Ola, {nome}!\n\n"
            f"Lembrete importante: o seu boleto do consorcio vence *amanha ({data_vencimento_str})*.\n"
            f"Segue o PDF novamente em anexo. Se ja pagou, desconsidere.\n\n"
            f"Atenciosamente,\n*Socel Motos - Yamaha*"
        )


def enviar_whatsapp(dados_cliente: dict, caminho_arquivo: str,
                     data_vencimento_str: str, tipo: str) -> bool:
    nome        = dados_cliente["nome"].title()
    telefone    = dados_cliente["telefone"]
    nome_arquivo = os.path.basename(caminho_arquivo)

    try:
        cpf_log = nome_arquivo.split("_")[1]
    except Exception:
        cpf_log = "00000000000"

    mensagem = _montar_mensagem(nome, data_vencimento_str, tipo)
    log(f"[{tipo}] {nome} ({telefone}) | venc {data_vencimento_str}", modulo=MODULO)

    headers = {"access-token": TOKEN_SUNCHAT, "Content-Type": "application/json"}

    # Envia texto
    try:
        resp = requests.post(URL_TEXTO, json={
            "number": telefone, "message": mensagem,
            "forceSend": True, "verifyContact": True,
        }, headers=headers, timeout=20)
        if resp.status_code not in (200, 201, 202):
            erro = f"Erro texto: {resp.text[:80]}"
            log(erro, "ERROR", MODULO)
            registrar_historico(nome, cpf_log, data_vencimento_str, nome_arquivo,
                                "Erro", erro, tipo)
            return False
    except Exception as e:
        log(f"Falha de conexao (texto): {e}", "ERROR", MODULO)
        return False

    time.sleep(1)

    # Envia PDF — até 3 tentativas com back-off
    _MAX_TENTATIVAS = 3
    try:
        with open(caminho_arquivo, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        erro = f"Erro ao ler PDF: {str(e)[:80]}"
        log(erro, "ERROR", MODULO)
        registrar_historico(nome, cpf_log, data_vencimento_str, nome_arquivo,
                            "Erro", erro, tipo)
        return False

    for tentativa in range(1, _MAX_TENTATIVAS + 1):
        try:
            resp = requests.post(URL_MEDIA, json={
                "number": telefone, "base64": encoded, "extension": ".pdf",
                "fileName": nome_arquivo, "forceSend": True, "verifyContact": True,
            }, headers=headers, timeout=40)
            if resp.status_code in (200, 201, 202):
                log(f"[{tipo}] Enviado: {nome_arquivo}", "SUCCESS", MODULO)
                registrar_historico(nome, cpf_log, data_vencimento_str, nome_arquivo,
                                    "Enviado", "", tipo)
                return True
            erro = f"Erro PDF (tentativa {tentativa}): {resp.text[:60]}"
            log(erro, "WARNING", MODULO)
        except Exception as e:
            erro = f"Falha conexao PDF (tentativa {tentativa}): {str(e)[:60]}"
            log(erro, "WARNING", MODULO)
        if tentativa < _MAX_TENTATIVAS:
            time.sleep(5 * tentativa)   # 5s, 10s

    log(f"PDF nao enviado apos {_MAX_TENTATIVAS} tentativas: {nome_arquivo}", "ERROR", MODULO)
    registrar_historico(nome, cpf_log, data_vencimento_str, nome_arquivo,
                        "Erro", erro, tipo)
    return False


# =============================================================================
# LÓGICA DE JANELAS DE ENVIO
# =============================================================================
def calcular_dias_restantes(data_str: str) -> int:
    data_venc = datetime.strptime(data_str, "%d/%m/%Y").replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return (data_venc - hoje).days


def classificar_envio(dias: int) -> str | None:
    """Retorna o tipo de disparo ('D-7', 'D-1') ou None se não for hora de enviar."""
    if JANELA_D7_MIN <= dias <= JANELA_D7_MAX:
        return "D-7"
    if JANELA_D1_MIN <= dias <= JANELA_D1_MAX:
        return "D-1"
    return None


# =============================================================================
# LOOP PRINCIPAL
# =============================================================================
def iniciar_disparador():
    db.init_db()
    os.makedirs(PASTA_ENVIADOS, exist_ok=True)

    mapa_clientes = carregar_mapa_clientes()

    if not os.path.exists(PASTA_VALIDADOS):
        log("Pasta Validados nao existe.", "WARNING", MODULO)
        return

    arquivos = [f for f in os.listdir(PASTA_VALIDADOS) if f.endswith(".pdf")]
    log(f"{len(arquivos)} boletos em Validados.", modulo=MODULO)
    enviados_sessao = 0
    aguardando = 0
    ja_feitos  = 0

    for arquivo in arquivos:
        if not (arquivo.startswith("Boleto_") or arquivo.startswith("BOLETO_")):
            continue

        try:
            partes   = arquivo.split("_")
            cpf      = partes[1]
            data_fmt = partes[2].replace("Venc-", "").replace(".pdf", "").replace("-", "/")
            dias     = calcular_dias_restantes(data_fmt)
            tipo     = classificar_envio(dias)

        except Exception as e:
            log(f"Nome invalido {arquivo}: {e}", "WARNING", MODULO)
            continue

        if tipo is None:
            if dias > JANELA_D7_MAX:
                aguardando += 1
                log(f"Aguardando ({dias}d restantes): {arquivo}", modulo=MODULO)
            # dias < JANELA_D1_MIN → vencido, cobrador trata
            continue

        if ja_enviado_tipo(arquivo, tipo):
            ja_feitos += 1
            continue

        if cpf not in mapa_clientes:
            log(f"CPF {cpf} sem cadastro/celular.", "WARNING", MODULO)
            registrar_historico("Desconhecido", cpf, data_fmt, arquivo,
                                "Erro", "Cadastro s/ Celular", tipo)
            continue

        caminho = os.path.join(PASTA_VALIDADOS, arquivo)
        if enviar_whatsapp(mapa_clientes[cpf], caminho, data_fmt, tipo):
            enviados_sessao += 1
            # Só move para Enviados após o envio final (D-1)
            if tipo == "D-1":
                destino = os.path.join(PASTA_ENVIADOS, arquivo)
                for _ in range(3):
                    try:
                        shutil.move(caminho, destino)
                        break
                    except Exception:
                        time.sleep(2)
            time.sleep(3)

    log(
        f"Sessao concluida | Enviados: {enviados_sessao} | "
        f"Ja feitos: {ja_feitos} | Aguardando janela: {aguardando}",
        "SUCCESS", MODULO,
    )


if __name__ == "__main__":
    iniciar_disparador()
