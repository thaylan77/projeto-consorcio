import subprocess
import sys
import os
import time

import db
from logger import log
from config import HORA_PIPELINE, HORA_COBRADOR

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
MODULO = "Orquestrador"

PIPELINE = [
    # critico=False → falha é avisada mas não interrompe o pipeline;
    # os passos seguintes ainda processam os arquivos já existentes nas pastas.
    {"name": "Extrator (API)",       "file": "extrator_api.py",  "critico": False},
    {"name": "Buscador (Crawler)",   "file": "buscador.py",      "critico": False},
    {"name": "Validador",            "file": "validador.py",     "critico": True},
    {"name": "Corretor",             "file": "corretor.py",      "critico": True},
    {"name": "Disparador (D-7/D-1)", "file": "enviar.py",        "critico": True},
]


def executar_script(nome: str, arquivo: str) -> bool:
    log(f"Iniciando: {nome}...", "START", MODULO)
    try:
        path = os.path.join(SCRIPTS_DIR, arquivo)
        proc = subprocess.Popen(
            [sys.executable, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        for linha in proc.stdout:
            msg = linha.strip()
            if msg:
                log(f"  > {msg}", "TRACE", MODULO)
        proc.wait()
        if proc.returncode == 0:
            log(f"Finalizado com sucesso: {nome}", "SUCCESS", MODULO)
            return True
        else:
            log(f"Erro em {nome}. Exit: {proc.returncode}", "ERROR", MODULO)
            return False
    except Exception as e:
        log(f"Falha critica em {nome}: {e}", "CRITICAL", MODULO)
        return False


def main():
    db.init_db()

    log("=" * 55, modulo=MODULO)
    log("INICIANDO PIPELINE CONSORCIO", modulo=MODULO)
    log(f"  Agendamento: pipeline {HORA_PIPELINE} | cobrador {HORA_COBRADOR}", modulo=MODULO)
    log("=" * 55, modulo=MODULO)

    sucessos = 0
    falhas   = 0
    inicio   = time.time()

    for item in PIPELINE:
        if executar_script(item["name"], item["file"]):
            sucessos += 1
        else:
            falhas += 1
            if item.get("critico", True):
                log(f"Pipeline interrompido em: {item['name']}.", "ABORT", MODULO)
                break
            else:
                log(
                    f"'{item['name']}' falhou mas nao e critico — continuando com arquivos existentes.",
                    "WARNING", MODULO,
                )

    duracao = int(time.time() - inicio)
    log("=" * 55, modulo=MODULO)
    log(
        f"Scripts: {len(PIPELINE)} | Sucessos: {sucessos} | "
        f"Falhas: {falhas} | Duracao: {duracao}s",
        modulo=MODULO,
    )
    log("=" * 55, modulo=MODULO)

    # Envia relatório por e-mail ao final do pipeline
    try:
        from relatorio import enviar_relatorio_diario
        enviar_relatorio_diario()
    except Exception as e:
        log(f"Aviso: falha ao enviar relatorio diario: {e}", "WARNING", MODULO)


if __name__ == "__main__":
    main()
