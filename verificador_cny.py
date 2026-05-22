"""
verificador_cny.py — Polling periódico do portal CNY para detectar pagamentos.

Verifica todos os boletos maduros (D-1 enviado há >= DIAS_APOS_VENC_PARA_COBRAR dias)
e registra o status na tabela status_cny do banco de dados.

Pode ser executado:
  • Pelo agendador automaticamente (manhã e tarde)
  • Sob demanda via dashboard (POST /api/run/verificador-cny)
  • Na linha de comando: python verificador_cny.py
"""

import re

import db
from cny_client import iniciar_sessao, encerrar_sessao, verificar_boleto_pago
from config import DIAS_APOS_VENC_PARA_COBRAR
from logger import log

MODULO = "VerifCNY"


def executar_verificacao() -> dict:
    """
    Verifica status de pagamento no CNY para todos os boletos maduros.
    Retorna resumo com contadores.
    """
    db.init_db()
    log("Verificacao periodica CNY iniciada.", modulo=MODULO)

    candidatos = db.disparos_d1_vencidos(DIAS_APOS_VENC_PARA_COBRAR)
    if not candidatos:
        log("Nenhum boleto maduro para verificar.", modulo=MODULO)
        return {"verificados": 0, "pagos": 0, "em_aberto": 0, "erros": 0}

    log(f"{len(candidatos)} boleto(s) para verificar no CNY.", modulo=MODULO)

    driver, wait = iniciar_sessao()
    if driver is None:
        log("Sessao CNY falhou. Verificacao abortada.", "ERROR", MODULO)
        return {"verificados": 0, "pagos": 0, "em_aberto": 0, "erros": 0,
                "erro": "Falha na sessao CNY"}

    verificados = pagos = em_aberto = erros = 0

    try:
        for entry in candidatos:
            arquivo    = entry.get("arquivo", "")
            vencimento = entry.get("vencimento", "")
            m   = re.search(r"Boleto_(\d+)_", arquivo)
            cpf = m.group(1) if m else re.sub(r"\D", "", entry.get("cpf", ""))

            if not cpf or not vencimento:
                continue

            try:
                pago   = verificar_boleto_pago(driver, wait, cpf, vencimento)
                status = "pago" if pago else "em_aberto"
                db.registrar_status_cny(cpf, vencimento, status)
                verificados += 1
                if pago:
                    pagos += 1
                    log(f"PAGO: CPF {cpf[:3]}***{cpf[-2:]} venc {vencimento}",
                        "SUCCESS", MODULO)
                else:
                    em_aberto += 1
            except Exception as e:
                log(f"Erro ao verificar CPF {cpf[:3]}***: {e}", "WARNING", MODULO)
                db.registrar_status_cny(cpf, vencimento, "erro")
                erros += 1

    finally:
        encerrar_sessao(driver)

    resumo = {"verificados": verificados, "pagos": pagos,
              "em_aberto": em_aberto, "erros": erros}
    log(f"Verificacao CNY concluida: {resumo}", "SUCCESS", MODULO)
    return resumo


if __name__ == "__main__":
    executar_verificacao()
