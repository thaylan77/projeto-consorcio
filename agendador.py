"""
agendador.py — Daemon autônomo do sistema de consórcio

Executa automaticamente todos os dias:
  • HORA_PIPELINE  → roda o pipeline completo (extrator → buscador → validador → corretor → enviar)
  • HORA_COBRADOR  → verifica boletos vencidos há >= 2 dias e envia cobrança

O disparador (enviar.py) cuida das janelas D-7 e D-1 automaticamente.
O cobrador (cobrador.py) cuida do follow-up D+2.

Como usar:
  python agendador.py          (inicia o daemon — mantenha o terminal aberto)
  Ctrl+C para parar.
"""

import subprocess
import sys
import os
import time
import threading
from datetime import datetime

import schedule

from config import HORA_PIPELINE, HORA_COBRADOR, HORA_VERIF_CNY
from logger import log

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
MODULO = "Agendador"

# Locks independentes — cada job só bloqueia a si mesmo
_lock_pipeline  = threading.Lock()
_lock_cobrador  = threading.Lock()
_lock_verif_cny = threading.Lock()
_lock_snapshot  = threading.Lock()


# =============================================================================
# RUNNERS
# =============================================================================
def _rodar_script(nome: str, arquivo: str, lock: threading.Lock) -> None:
    if not lock.acquire(blocking=False):
        log(f"'{nome}' ja em execucao, ignorando disparo.", "WARNING", MODULO)
        return
    try:
        log(f"Iniciando: {nome}", "START", MODULO)
        path = os.path.join(SCRIPTS_DIR, arquivo)
        proc = subprocess.Popen(
            [sys.executable, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for linha in proc.stdout:
            msg = linha.strip()
            if msg:
                log(f"  > {msg}", "TRACE", MODULO)
        proc.wait()
        nivel = "SUCCESS" if proc.returncode == 0 else "ERROR"
        log(f"Finalizado '{nome}' (exit {proc.returncode})", nivel, MODULO)
    except Exception as e:
        log(f"Erro ao rodar '{nome}': {e}", "CRITICAL", MODULO)
    finally:
        lock.release()


def job_pipeline():
    threading.Thread(
        target=_rodar_script,
        args=("Pipeline completo", "orquestrador.py", _lock_pipeline),
        daemon=True,
    ).start()


def job_cobrador():
    threading.Thread(
        target=_rodar_script,
        args=("Cobranca D+2", "cobrador.py", _lock_cobrador),
        daemon=True,
    ).start()


def job_verif_cny():
    threading.Thread(
        target=_rodar_script,
        args=("Verificacao CNY", "verificador_cny.py", _lock_verif_cny),
        daemon=True,
    ).start()


def _rodar_snapshot_mensal() -> None:
    """Captura snapshot de KPIs mensais — só executa de fato no dia 1."""
    if datetime.now().day != 1:
        return
    if not _lock_snapshot.acquire(blocking=False):
        log("Snapshot mensal ja em execucao, ignorando disparo.", "WARNING", MODULO)
        return
    try:
        import db as _db
        from api_dashboard import _calcular_kpis_gerente
        log("Capturando snapshot mensal de KPIs...", "START", MODULO)
        k = _calcular_kpis_gerente()
        _db.salvar_snapshot_mensal(
            mes=k["mes"],
            inadimplencia_pct=k["inadimplencia_pct"],
            recebido=k["recebido"],
            a_receber=k["a_receber"],
            atrasado=k["atrasado"],
            em_risco=k["em_risco"],
            adimplentes=k["adimplentes"],
            carteira=k["carteira"],
        )
        log(f"Snapshot mensal salvo para {k['mes']} "
            f"(inadimpl={k['inadimplencia_pct']}% recebido=R$ {k['recebido']:.2f})",
            "SUCCESS", MODULO)
    except Exception as e:
        log(f"Erro no snapshot mensal: {e}", "ERROR", MODULO)
    finally:
        _lock_snapshot.release()


def job_snapshot_mensal():
    threading.Thread(target=_rodar_snapshot_mensal, daemon=True).start()


# =============================================================================
# AGENDA
# =============================================================================
def configurar_agenda():
    schedule.every().day.at(HORA_PIPELINE).do(job_pipeline)
    schedule.every().day.at(HORA_COBRADOR).do(job_cobrador)
    schedule.every().day.at(HORA_VERIF_CNY).do(job_verif_cny)
    schedule.every().day.at("16:00").do(job_verif_cny)   # 2ª verificação da tarde
    schedule.every().day.at("02:00").do(job_snapshot_mensal)  # roda só dia 1

    log("=" * 55, modulo=MODULO)
    log("AGENDADOR INICIADO", modulo=MODULO)
    log(f"  Pipeline completo      : todos os dias as {HORA_PIPELINE}", modulo=MODULO)
    log(f"  Cobranca D+2           : todos os dias as {HORA_COBRADOR}", modulo=MODULO)
    log(f"  Verificacao CNY        : {HORA_VERIF_CNY} e 16:00", modulo=MODULO)
    log("  Snapshot mensal KPIs   : todo dia 1, as 02:00", modulo=MODULO)
    log("  Respostas WhatsApp     : via webhook /webhook/sunchat (push)", modulo=MODULO)
    log("  Pressione Ctrl+C para encerrar.", modulo=MODULO)
    log("=" * 55, modulo=MODULO)


def proximas_execucoes() -> str:
    jobs = schedule.get_jobs()
    if not jobs:
        return "Sem jobs agendados."
    linhas = []
    for j in jobs:
        proximo = j.next_run.strftime("%d/%m/%Y %H:%M") if j.next_run else "N/A"
        linhas.append(f"  [{j.job_func.__name__}] proximo: {proximo}")
    return "\n".join(linhas)


# =============================================================================
# MAIN
# =============================================================================
def main():
    configurar_agenda()

    ultimo_status = datetime.now()

    while True:
        schedule.run_pending()

        # A cada hora, imprime os próximos horários
        agora = datetime.now()
        if (agora - ultimo_status).total_seconds() >= 3600:
            log(f"Agendador ativo. Proximas execucoes:\n{proximas_execucoes()}", modulo=MODULO)
            ultimo_status = agora

        time.sleep(30)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Agendador encerrado pelo usuario.", modulo=MODULO)
