"""
utils.py — Funções utilitárias compartilhadas entre módulos

Centraliza lógica duplicada que existia em enviar.py, cobrador.py,
validador.py e corretor.py.
"""

import re
import unicodedata


def limpar_telefone(fone) -> str | None:
    """
    Normaliza um número de telefone para o formato internacional brasileiro.
    Retorna None se o número for inválido (< 8 dígitos).

    Regras:
      - Remove tudo que não for dígito
      - Prefixa com '55' se não começar com '55'
      - Insere o 9º dígito após o DDD quando o número tem 12 dígitos (55 + DDD + 8)
    """
    if not fone:
        return None
    limpo = re.sub(r"\D", "", str(fone))
    if len(limpo) < 8:
        return None
    if not limpo.startswith("55"):
        limpo = "55" + limpo
    if len(limpo) == 12:          # 55 + DDD(2) + numero(8) → insere 9 após DDD
        limpo = limpo[:4] + "9" + limpo[4:]
    return limpo


def normalizar(txt: str) -> str:
    """
    Remove acentos, converte para maiúsculas e elimina quebras de linha.
    Compatível com os usos de validador.py e corretor.py.
    """
    if not isinstance(txt, str):
        return ""
    return (
        unicodedata.normalize("NFKD", txt)
        .encode("ASCII", "ignore")
        .decode("ASCII")
        .upper()
        .replace("\n", " ")
        .strip()
    )
