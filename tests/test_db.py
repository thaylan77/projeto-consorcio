"""
test_db.py — Testes da camada de persistência SQLite (db.py)
"""

import json
import os
from datetime import datetime, timedelta


# ===========================================================================
# INICIALIZAÇÃO
# ===========================================================================
class TestInitDb:
    def test_cria_tabela_disparos(self, tmp_db):
        import sqlite3
        con = sqlite3.connect(tmp_db.DB_PATH)
        tabelas = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        con.close()
        assert "disparos" in tabelas

    def test_cria_tabela_pagamentos(self, tmp_db):
        import sqlite3
        con = sqlite3.connect(tmp_db.DB_PATH)
        tabelas = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        con.close()
        assert "pagamentos_informados" in tabelas

    def test_idempotente(self, tmp_db):
        """Chamar init_db() duas vezes não deve lançar exceção."""
        tmp_db.init_db()
        tmp_db.init_db()

    def test_migra_historico_json(self, tmp_db, tmp_path, monkeypatch):
        """Deve importar registros de historico_envios.json na primeira execução."""
        import db

        historico = [
            {
                "data_disparo": "01/05/2026 08:00:00",
                "nome": "Joao Silva",
                "cpf": "123.***.***-45",
                "vencimento": "10/05/2026",
                "arquivo": "Boleto_12345678901_Venc-10-05-2026.pdf",
                "status": "Enviado",
                "tipo_disparo": "D-1",
                "erro": "",
            }
        ]
        json_path = tmp_path / "hist.json"
        json_path.write_text(json.dumps(historico), encoding="utf-8")

        # Aponta ARQUIVO_HISTORICO para o JSON temporário e usa banco vazio
        db_novo = str(tmp_path / "novo.db")
        monkeypatch.setattr(db, "DB_PATH", db_novo)
        monkeypatch.setattr(db, "ARQUIVO_HISTORICO", str(json_path), raising=False)
        # Garante banco vazio e força migração
        db.init_db()

        registros = db.listar_disparos()
        assert len(registros) == 1
        assert registros[0]["nome"] == "Joao Silva"


# ===========================================================================
# DISPAROS
# ===========================================================================
class TestRegistrarDisparo:
    def test_insere_registro(self, tmp_db):
        tmp_db.registrar_disparo("Maria", "111", "20/05/2026",
                                  "Boleto_111_Venc-20-05-2026.pdf")
        registros = tmp_db.listar_disparos()
        assert len(registros) == 1
        assert registros[0]["nome"] == "Maria"

    def test_valores_padrao(self, tmp_db):
        tmp_db.registrar_disparo("Ana", "222", "21/05/2026", "arq.pdf")
        r = tmp_db.listar_disparos()[0]
        assert r["status"] == "Enviado"
        assert r["tipo_disparo"] == "D-1"
        assert r["erro"] == ""

    def test_registra_erro(self, tmp_db):
        tmp_db.registrar_disparo("Pedro", "333", "22/05/2026", "arq.pdf",
                                   status="Erro", erro="Timeout", tipo_disparo="D-7")
        r = tmp_db.listar_disparos()[0]
        assert r["status"] == "Erro"
        assert r["erro"] == "Timeout"
        assert r["tipo_disparo"] == "D-7"

    def test_data_disparo_preenchida(self, tmp_db):
        tmp_db.registrar_disparo("Carlos", "444", "23/05/2026", "arq.pdf")
        r = tmp_db.listar_disparos()[0]
        assert r["data_disparo"] != ""


class TestJaEnviadoTipo:
    def test_retorna_true_quando_existe(self, tmp_db):
        tmp_db.registrar_disparo("A", "1", "20/05/2026", "arq.pdf",
                                   status="Enviado", tipo_disparo="D-7")
        assert tmp_db.ja_enviado_tipo("arq.pdf", "D-7") is True

    def test_retorna_false_quando_nao_existe(self, tmp_db):
        assert tmp_db.ja_enviado_tipo("arq_inexistente.pdf", "D-7") is False

    def test_ignora_status_erro(self, tmp_db):
        """Status='Erro' não conta como já enviado."""
        tmp_db.registrar_disparo("B", "2", "20/05/2026", "arq.pdf",
                                   status="Erro", tipo_disparo="D-1")
        assert tmp_db.ja_enviado_tipo("arq.pdf", "D-1") is False

    def test_diferencia_tipo(self, tmp_db):
        """D-7 enviado não bloqueia D-1."""
        tmp_db.registrar_disparo("C", "3", "20/05/2026", "arq.pdf",
                                   status="Enviado", tipo_disparo="D-7")
        assert tmp_db.ja_enviado_tipo("arq.pdf", "D-1") is False


class TestListarDisparos:
    def test_retorna_mais_recente_primeiro(self, tmp_db):
        tmp_db.registrar_disparo("Primeiro", "1", "20/05/2026", "a.pdf")
        tmp_db.registrar_disparo("Segundo",  "2", "21/05/2026", "b.pdf")
        lista = tmp_db.listar_disparos()
        assert lista[0]["nome"] == "Segundo"
        assert lista[1]["nome"] == "Primeiro"

    def test_respeita_limite(self, tmp_db):
        for i in range(10):
            tmp_db.registrar_disparo(f"Cliente{i}", str(i), "20/05/2026", f"arq{i}.pdf")
        assert len(tmp_db.listar_disparos(limite=3)) == 3

    def test_retorna_lista_vazia(self, tmp_db):
        assert tmp_db.listar_disparos() == []


class TestDisparosD1Vencidos:
    def _data(self, delta_dias: int) -> str:
        return (datetime.now() + timedelta(days=delta_dias)).strftime("%d/%m/%Y")

    def test_retorna_vencido(self, tmp_db):
        venc = self._data(-5)  # venceu há 5 dias
        tmp_db.registrar_disparo("X", "9", venc, "boleto_9.pdf",
                                   status="Enviado", tipo_disparo="D-1")
        resultado = tmp_db.disparos_d1_vencidos(2)
        assert len(resultado) == 1
        assert resultado[0]["arquivo"] == "boleto_9.pdf"

    def test_exclui_nao_vencido(self, tmp_db):
        venc = self._data(1)  # vence amanhã
        tmp_db.registrar_disparo("Y", "8", venc, "boleto_8.pdf",
                                   status="Enviado", tipo_disparo="D-1")
        assert tmp_db.disparos_d1_vencidos(2) == []

    def test_exclui_ja_cobrado(self, tmp_db):
        venc = self._data(-5)
        arquivo = "boleto_cobrado.pdf"
        tmp_db.registrar_disparo("Z", "7", venc, arquivo,
                                   status="Enviado", tipo_disparo="D-1")
        tmp_db.registrar_disparo("Z", "7", venc, arquivo,
                                   status="Enviado", tipo_disparo="Cobranca")
        assert tmp_db.disparos_d1_vencidos(2) == []

    def test_exclui_status_erro(self, tmp_db):
        venc = self._data(-5)
        tmp_db.registrar_disparo("W", "6", venc, "err.pdf",
                                   status="Erro", tipo_disparo="D-1")
        assert tmp_db.disparos_d1_vencidos(2) == []


class TestStatsDodia:
    def test_conta_zero_sem_registros(self, tmp_db):
        s = tmp_db.stats_do_dia()
        assert s["total"] == 0
        assert s["enviados"] == 0
        assert s["erros"] == 0
        assert s["por_tipo"] == {}

    def test_conta_enviados_e_erros(self, tmp_db):
        venc = datetime.now().strftime("%d/%m/%Y")
        tmp_db.registrar_disparo("A", "1", venc, "a.pdf", status="Enviado", tipo_disparo="D-7")
        tmp_db.registrar_disparo("B", "2", venc, "b.pdf", status="Enviado", tipo_disparo="D-1")
        tmp_db.registrar_disparo("C", "3", venc, "c.pdf", status="Erro",    tipo_disparo="D-1")
        s = tmp_db.stats_do_dia()
        assert s["total"] == 3
        assert s["enviados"] == 2
        assert s["erros"] == 1
        assert s["por_tipo"]["D-7"] == 1
        assert s["por_tipo"]["D-1"] == 1


# ===========================================================================
# PAGAMENTOS
# ===========================================================================
class TestPagamentos:
    def test_registrar_e_consultar(self, tmp_db):
        tmp_db.registrar_pagamento("5511999990001", "Joao", "ja paguei")
        assert tmp_db.telefone_ja_pagou("5511999990001") is True

    def test_retorna_false_nao_cadastrado(self, tmp_db):
        assert tmp_db.telefone_ja_pagou("5500000000000") is False

    def test_upsert_nao_duplica(self, tmp_db):
        tmp_db.registrar_pagamento("5511999990002", "Maria", "msg1")
        tmp_db.registrar_pagamento("5511999990002", "Maria", "msg2")
        pagamentos = tmp_db.listar_pagamentos()
        assert len(pagamentos) == 1
        assert pagamentos[0]["mensagem"] == "msg2"

    def test_listar_pagamentos_retorna_lista(self, tmp_db):
        tmp_db.registrar_pagamento("5511111111111", "A", "")
        tmp_db.registrar_pagamento("5522222222222", "B", "")
        assert len(tmp_db.listar_pagamentos()) == 2
