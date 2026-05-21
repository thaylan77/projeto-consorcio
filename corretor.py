import pandas as pd
import os
import shutil
import re
import unicodedata
from pypdf import PdfReader

from config import PASTA_REJEITADOS, PASTA_VALIDADOS, PASTA_REVISAO_MANUAL
from utils import normalizar
from logger import log

ARQUIVO_CSV = "relatorio_microwork_consorcio.csv"
MODULO = "Corretor"


def carregar_clientes_nomes() -> dict:
    log("Carregando nomes do CSV...", modulo=MODULO)
    try:
        df = pd.read_csv(ARQUIVO_CSV)
    except Exception:
        log("Erro ao ler CSV.", "ERROR", MODULO)
        return {}
    dados = {}
    for _, row in df.iterrows():
        cpf = re.sub(r"\D", "", str(row["pessoacpfcnpj"]))
        nome_norm = normalizar(str(row["pessoa"]))
        if len(nome_norm) > 5:
            dados[nome_norm] = cpf
    return dados


def extrair_texto_pdf(caminho: str) -> str:
    try:
        reader = PdfReader(caminho)
        return normalizar("".join(p.extract_text() or "" for p in reader.pages))
    except Exception:
        return ""


def extrair_data_vencimento(texto: str) -> str | None:
    if not texto:
        return None
    padroes = [
        r"(?:VENCIMENTO|VCTO|VENC|PAGAVEL ATE|VALOR A PAGAR ATE)[\s:]*(\d{2}/\d{2}/\d{4})",
        r"(\d{2}/\d{2}/\d{4})",
    ]
    for p in padroes:
        match = re.search(p, texto)
        if match:
            return match.group(1).replace("/", "-")
    return None


def corrigir_arquivos():
    os.makedirs(PASTA_REVISAO_MANUAL, exist_ok=True)

    mapa_nomes = carregar_clientes_nomes()
    arquivos = [f for f in os.listdir(PASTA_REJEITADOS) if f.endswith(".pdf")]

    if not arquivos:
        log("Nenhum boleto na pasta Rejeitados.", modulo=MODULO)
        return

    log(f"Corrigindo {len(arquivos)} arquivos...", modulo=MODULO)
    corrigidos = 0
    manuais = 0

    for arquivo in arquivos:
        caminho_origem = os.path.join(PASTA_REJEITADOS, arquivo)
        texto_pdf = extrair_texto_pdf(caminho_origem)
        data_real = extrair_data_vencimento(texto_pdf)

        data_vencimento = f"Venc-{data_real}" if data_real else (
            "Venc-" + arquivo.split("Venc-")[1].replace(".pdf", "")
            if "Venc-" in arquivo else "Venc-Desconhecido"
        )

        dono_encontrado = None
        cpf_encontrado = None
        for nome_cliente, cpf_cliente in mapa_nomes.items():
            if nome_cliente in texto_pdf:
                dono_encontrado = nome_cliente
                cpf_encontrado = cpf_cliente
                break

        if dono_encontrado:
            novo_nome = f"Boleto_{cpf_encontrado}_{data_vencimento}.pdf"
            shutil.move(caminho_origem, os.path.join(PASTA_VALIDADOS, novo_nome))
            log(f"Corrigido: {dono_encontrado} -> {novo_nome}", "SUCCESS", MODULO)
            corrigidos += 1
        else:
            shutil.move(caminho_origem, os.path.join(PASTA_REVISAO_MANUAL, arquivo))
            log(f"Sem dono identificado: {arquivo} -> Revisao_Manual", "WARNING", MODULO)
            manuais += 1

    log(f"Corrigidos: {corrigidos} | Revisao manual: {manuais}", modulo=MODULO)


if __name__ == "__main__":
    corrigir_arquivos()
