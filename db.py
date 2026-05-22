"""
db.py — Camada de persistência SQLite

Substitui historico_envios.json e pagamentos_informados.json por um banco
SQLite com WAL mode para acesso concorrente seguro entre processos.
Na primeira execução migra automaticamente os JSON existentes.
"""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import ARQUIVO_HISTORICO

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "consorcio.db"))
ARQUIVO_PAGAMENTOS_JSON = "pagamentos_informados.json"

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS disparos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    data_disparo TEXT    NOT NULL,
    nome         TEXT    NOT NULL,
    cpf          TEXT    NOT NULL DEFAULT '',
    vencimento   TEXT    NOT NULL DEFAULT '',
    arquivo      TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'Enviado',
    tipo_disparo TEXT    NOT NULL DEFAULT 'D-1',
    erro         TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_disparos_arquivo       ON disparos(arquivo);
CREATE INDEX IF NOT EXISTS idx_disparos_tipo_status   ON disparos(tipo_disparo, status);
CREATE INDEX IF NOT EXISTS idx_disparos_cpf           ON disparos(cpf);

CREATE TABLE IF NOT EXISTS pagamentos_informados (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    telefone TEXT    NOT NULL UNIQUE,
    nome     TEXT    NOT NULL DEFAULT '',
    mensagem TEXT    NOT NULL DEFAULT '',
    data     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pagamentos_telefone ON pagamentos_informados(telefone);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# =============================================================================
# INICIALIZAÇÃO E MIGRAÇÃO
# =============================================================================
def init_db() -> None:
    with _conn() as con:
        con.executescript(_DDL)
    _migrar_json()


def _migrar_json() -> None:
    """Importa dados dos JSON legados uma única vez."""
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM disparos").fetchone()[0]

    if total > 0:
        return  # já foi migrado

    # Migra historico_envios.json
    if os.path.exists(ARQUIVO_HISTORICO):
        try:
            with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
                registros = json.load(f)
            with _conn() as con:
                for r in registros:
                    con.execute(
                        "INSERT OR IGNORE INTO disparos "
                        "(data_disparo, nome, cpf, vencimento, arquivo, status, tipo_disparo, erro) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (
                            r.get("data_disparo", ""),
                            r.get("nome", ""),
                            r.get("cpf", ""),
                            r.get("vencimento", ""),
                            r.get("arquivo", ""),
                            r.get("status", "Enviado"),
                            r.get("tipo_disparo", "D-1"),
                            r.get("erro", ""),
                        ),
                    )
            print(f"[db] Migrados {len(registros)} registros de historico_envios.json")
        except Exception as e:
            print(f"[db] Aviso na migracao do historico: {e}")

    # Migra pagamentos_informados.json
    if os.path.exists(ARQUIVO_PAGAMENTOS_JSON):
        try:
            with open(ARQUIVO_PAGAMENTOS_JSON, "r", encoding="utf-8") as f:
                pagamentos = json.load(f)
            with _conn() as con:
                for p in pagamentos:
                    con.execute(
                        "INSERT OR IGNORE INTO pagamentos_informados "
                        "(telefone, nome, mensagem, data) VALUES (?,?,?,?)",
                        (
                            p.get("telefone", ""),
                            p.get("nome", ""),
                            p.get("mensagem", ""),
                            p.get("data", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
                        ),
                    )
            print(f"[db] Migrados {len(pagamentos)} pagamentos de pagamentos_informados.json")
        except Exception as e:
            print(f"[db] Aviso na migracao de pagamentos: {e}")


# =============================================================================
# DISPAROS
# =============================================================================
def registrar_disparo(nome: str, cpf: str, vencimento: str, arquivo: str,
                       status: str = "Enviado", erro: str = "",
                       tipo_disparo: str = "D-1") -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO disparos (data_disparo, nome, cpf, vencimento, arquivo, status, tipo_disparo, erro) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), nome, cpf,
             vencimento, arquivo, status, tipo_disparo, erro),
        )


def ja_enviado_tipo(arquivo: str, tipo: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM disparos WHERE arquivo=? AND tipo_disparo=? AND status='Enviado' LIMIT 1",
            (arquivo, tipo),
        ).fetchone()
    return row is not None


def listar_disparos(limite: int = 200, offset: int = 0) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM disparos ORDER BY id DESC LIMIT ? OFFSET ?", (limite, offset)
        ).fetchall()
    return [dict(r) for r in rows]


def disparos_d1_vencidos(dias_apos: int) -> list[dict]:
    """Retorna disparos D-1 cujo vencimento passou ha >= dias_apos dias e ainda nao foram cobrados."""
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    candidatos_q = """
        SELECT * FROM disparos
        WHERE tipo_disparo='D-1' AND status='Enviado'
          AND arquivo NOT IN (SELECT arquivo FROM disparos WHERE tipo_disparo='Cobranca' AND status='Enviado')
        GROUP BY arquivo
        HAVING MAX(id)=id
    """

    with _conn() as con:
        rows = con.execute(candidatos_q).fetchall()

    pendentes = []
    for r in rows:
        try:
            data_venc = datetime.strptime(r["vencimento"], "%d/%m/%Y").replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if (hoje - data_venc).days >= dias_apos:
                pendentes.append(dict(r))
        except Exception:
            continue
    return pendentes


def stats_do_dia() -> dict:
    hoje = datetime.now().strftime("%d/%m/%Y")
    with _conn() as con:
        total = con.execute(
            "SELECT COUNT(*) FROM disparos WHERE data_disparo LIKE ?", (f"{hoje}%",)
        ).fetchone()[0]
        enviados = con.execute(
            "SELECT COUNT(*) FROM disparos WHERE data_disparo LIKE ? AND status='Enviado'",
            (f"{hoje}%",)
        ).fetchone()[0]
        erros = con.execute(
            "SELECT COUNT(*) FROM disparos WHERE data_disparo LIKE ? AND status='Erro'",
            (f"{hoje}%",)
        ).fetchone()[0]
        por_tipo = con.execute(
            "SELECT tipo_disparo, COUNT(*) as n FROM disparos "
            "WHERE data_disparo LIKE ? AND status='Enviado' GROUP BY tipo_disparo",
            (f"{hoje}%",)
        ).fetchall()
    return {
        "total": total,
        "enviados": enviados,
        "erros": erros,
        "por_tipo": {r["tipo_disparo"]: r["n"] for r in por_tipo},
    }


def score_risco_por_cpf() -> dict:
    """
    Calcula score de risco de inadimplência por CPF com base no histórico de disparos.

    Lógica:
      - Crítico  : teve Cobrança D+2 com status Erro (não pagou mesmo após cobrança)
      - Alto     : teve Cobrança D+2 enviada com sucesso
      - Médio    : recebeu D-1 mas não precisou de cobrança (pagou no prazo)
      - Baixo    : só recebeu D-7, pagou antes do lembrete final
      - Novo     : sem histórico ainda

    Retorna {cpf: {"score": str, "contagem": {tipo: n}}}
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT arquivo, tipo_disparo, status FROM disparos"
        ).fetchall()

    historico: dict[str, dict] = {}
    for r in rows:
        m = re.search(r"Boleto_(\d+)_", r["arquivo"])
        if not m:
            continue
        cpf = m.group(1)
        if cpf not in historico:
            historico[cpf] = {}
        tipo = r["tipo_disparo"]
        status = r["status"]
        chave = f"{tipo}_{status}"
        historico[cpf][chave] = historico[cpf].get(chave, 0) + 1

    resultado = {}
    for cpf, contagem in historico.items():
        tipos_enviados = {k.split("_")[0] for k, v in contagem.items() if "Enviado" in k}
        teve_cobranca_erro = contagem.get("Cobranca_Erro", 0) > 0

        if teve_cobranca_erro:
            score = "Critico"
        elif "Cobranca" in tipos_enviados:
            score = "Alto"
        elif "D-1" in tipos_enviados:
            score = "Medio"
        elif "D-7" in tipos_enviados:
            score = "Baixo"
        else:
            score = "Novo"

        resultado[cpf] = {"score": score, "contagem": contagem}

    return resultado


def status_por_cpf() -> dict:
    """
    Retorna {cpf: {tipo_disparo, status, vencimento}} com o último disparo
    de cada cliente, extraindo o CPF do campo arquivo (Boleto_{CPF}_Venc-...).
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT arquivo, tipo_disparo, status, vencimento "
            "FROM disparos WHERE id IN "
            "(SELECT MAX(id) FROM disparos GROUP BY arquivo)"
        ).fetchall()
    resultado = {}
    for r in rows:
        m = re.search(r"Boleto_(\d+)_", r["arquivo"])
        if m:
            cpf = m.group(1)
            resultado[cpf] = {
                "tipo_disparo": r["tipo_disparo"],
                "status":       r["status"],
                "vencimento":   r["vencimento"],
            }
    return resultado


# =============================================================================
# PAGAMENTOS INFORMADOS (IA WhatsApp)
# =============================================================================
def registrar_pagamento(telefone: str, nome: str = "", mensagem: str = "") -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO pagamentos_informados (telefone, nome, mensagem, data) "
            "VALUES (?,?,?,?)",
            (telefone, nome, mensagem, datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
        )


def telefone_ja_pagou(telefone: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM pagamentos_informados WHERE telefone=? LIMIT 1", (telefone,)
        ).fetchone()
    return row is not None


def listar_pagamentos() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM pagamentos_informados ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]
