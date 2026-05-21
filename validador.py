import pandas as pd
import os
import shutil
import re
import unicodedata
from pypdf import PdfReader

from config import PASTA_PARA_ENVIAR, PASTA_VALIDADOS, PASTA_REJEITADOS
from utils import normalizar
from logger import log

ARQUIVO_CSV = "relatorio_microwork_consorcio.csv"
MODULO = "Validador"


def carregar_dados() -> dict:
    df = pd.read_csv(ARQUIVO_CSV)
    dados = {}
    for _, row in df.iterrows():
        cpf = re.sub(r"\D", "", str(row["pessoacpfcnpj"]))
        nome = normalizar(str(row["pessoa"]))
        dados[cpf] = nome
    return dados


def validar():
    for p in [PASTA_VALIDADOS, PASTA_REJEITADOS]:
        os.makedirs(p, exist_ok=True)

    mapa = carregar_dados()
    arquivos = [f for f in os.listdir(PASTA_PARA_ENVIAR) if f.endswith(".pdf")]
    log(f"Auditando {len(arquivos)} arquivos...", modulo=MODULO)

    for arq in arquivos:
        origem = os.path.join(PASTA_PARA_ENVIAR, arq)
        try:
            cpf_arq = arq.split("_")[1]
            nome_esperado = mapa.get(cpf_arq, "DESCONHECIDO")

            reader = PdfReader(origem)
            texto = "".join(p.extract_text() or "" for p in reader.pages)
            texto_limpo = re.sub(r"\D", "", texto)
            texto_norm = normalizar(texto)

            aprovado = cpf_arq in texto_limpo or nome_esperado in texto_norm

            if aprovado:
                shutil.move(origem, os.path.join(PASTA_VALIDADOS, arq))
                log(f"VALIDADO: {arq}", "SUCCESS", MODULO)
            else:
                shutil.move(origem, os.path.join(PASTA_REJEITADOS, arq))
                log(f"REJEITADO: {arq}", "WARNING", MODULO)

        except Exception as e:
            log(f"Erro ao ler {arq}: {e}", "ERROR", MODULO)


if __name__ == "__main__":
    validar()
