"""
test_api.py — Testes das rotas Flask da API do dashboard (api_dashboard.py)
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def client(tmp_db, monkeypatch, tmp_path):
    """Flask test client com banco isolado e pastas temporárias."""
    import api_dashboard as api
    monkeypatch.setattr(api, "db", tmp_db)

    # Aponta todas as pastas para diretórios temporários
    pastas_tmp = {k: str(tmp_path / k) for k in api.PASTA_BOLETOS}
    for p in pastas_tmp.values():
        os.makedirs(p, exist_ok=True)
    monkeypatch.setattr(api, "PASTA_BOLETOS", pastas_tmp)

    api.app.config["TESTING"] = True
    with api.app.test_client() as c:
        yield c


# ===========================================================================
# GET /api/stats
# ===========================================================================
class TestStats:
    def test_retorna_todas_as_chaves(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        for chave in ("para_enviar", "validados", "enviados", "rejeitados", "revisao_manual"):
            assert chave in data

    def test_contagem_zero_sem_arquivos(self, client):
        resp = client.get("/api/stats")
        data = resp.get_json()
        assert all(v == 0 for v in data.values())

    def test_conta_pdfs(self, client, tmp_path):
        import api_dashboard as api
        pasta = api.PASTA_BOLETOS["validados"]
        (os.path.join(pasta, "a.pdf") and open(os.path.join(pasta, "a.pdf"), "w").close())
        (os.path.join(pasta, "b.pdf") and open(os.path.join(pasta, "b.pdf"), "w").close())
        resp = client.get("/api/stats")
        assert resp.get_json()["validados"] == 2


# ===========================================================================
# GET /api/history
# ===========================================================================
class TestHistory:
    def test_retorna_lista_vazia(self, client):
        resp = client.get("/api/history")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_retorna_registros_do_banco(self, client, tmp_db):
        tmp_db.registrar_disparo("Joao", "111", "20/05/2026", "arq.pdf")
        resp = client.get("/api/history")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["nome"] == "Joao"

    def test_paginacao_limite(self, client, tmp_db):
        for i in range(10):
            tmp_db.registrar_disparo(f"C{i}", str(i), "20/05/2026", f"a{i}.pdf")
        resp = client.get("/api/history?limite=3")
        assert len(resp.get_json()) == 3

    def test_paginacao_offset(self, client, tmp_db):
        for i in range(5):
            tmp_db.registrar_disparo(f"C{i}", str(i), "20/05/2026", f"a{i}.pdf")
        todos  = client.get("/api/history?limite=5&offset=0").get_json()
        pagina2 = client.get("/api/history?limite=3&offset=3").get_json()
        assert len(pagina2) == 2
        assert todos[3]["nome"] == pagina2[0]["nome"]

    def test_limite_maximo_1000(self, client, tmp_db):
        # Deve aceitar limite=1000 sem erro
        resp = client.get("/api/history?limite=9999")
        assert resp.status_code == 200


# ===========================================================================
# GET /api/logs
# ===========================================================================
class TestLogs:
    def test_retorna_lista(self, client):
        resp = client.get("/api/logs")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_retorna_aguardando_quando_sem_log(self, client, monkeypatch, tmp_path):
        import api_dashboard as api
        monkeypatch.setattr(api, "ARQUIVO_LOG", str(tmp_path / "nao_existe.log"))
        resp = client.get("/api/logs")
        data = resp.get_json()
        assert any("Aguardando" in linha for linha in data)


# ===========================================================================
# GET /api/agenda
# ===========================================================================
class TestAgenda:
    def test_retorna_configuracoes(self, client):
        resp = client.get("/api/agenda")
        assert resp.status_code == 200
        data = resp.get_json()
        for chave in ("hora_pipeline", "hora_cobrador", "hora_respostas",
                       "janela_d7", "janela_d1", "cobranca_apos", "ia_ativa"):
            assert chave in data

    def test_ia_ativa_false_sem_api_key(self, client):
        resp = client.get("/api/agenda")
        assert resp.get_json()["ia_ativa"] is False


# ===========================================================================
# POST /api/run — autenticação
# ===========================================================================
class TestRunAuth:
    def test_sem_chave_retorna_401(self, client):
        resp = client.post("/api/run")
        assert resp.status_code == 401

    def test_chave_errada_retorna_401(self, client):
        resp = client.post("/api/run", headers={"X-API-Key": "chave_errada"})
        assert resp.status_code == 401

    def test_chave_correta_retorna_200(self, client):
        with patch("api_dashboard.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/api/run",
                               headers={"X-API-Key": "sk_test_key_12345"})
        assert resp.status_code == 200

    def test_chave_via_query_string(self, client):
        with patch("api_dashboard.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/api/run?key=sk_test_key_12345")
        assert resp.status_code == 200


# ===========================================================================
# POST /api/run/cobrador e /api/run/respostas
# ===========================================================================
class TestOutrosRuns:
    def test_cobrador_com_auth(self, client):
        with patch("api_dashboard.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/api/run/cobrador",
                               headers={"X-API-Key": "sk_test_key_12345"})
        assert resp.status_code == 200

    def test_respostas_com_auth(self, client):
        with patch("api_dashboard.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/api/run/respostas",
                               headers={"X-API-Key": "sk_test_key_12345"})
        assert resp.status_code == 200

    def test_cobrador_sem_auth_retorna_401(self, client):
        resp = client.post("/api/run/cobrador")
        assert resp.status_code == 401


# ===========================================================================
# GET /api/health
# ===========================================================================
class TestHealth:
    def test_retorna_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_retorna_status_ok(self, client):
        resp = client.get("/api/health")
        assert resp.get_json()["status"] == "ok"


# ===========================================================================
# POST /webhook/sunchat
# ===========================================================================
class TestWebhookSunchat:
    def test_campos_ausentes_retorna_400(self, client):
        resp = client.post("/webhook/sunchat",
                           data=json.dumps({}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_numero_sem_mensagem_retorna_400(self, client):
        resp = client.post("/webhook/sunchat",
                           data=json.dumps({"number": "5511999990001"}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_payload_valido_retorna_200(self, client):
        resultado_mock = {
            "telefone": "5511999990001",
            "nome": "Joao",
            "intencao": "OUTRO",
            "acao": "ignorado",
            "sucesso": True,
        }
        # processar_resposta agora é importada no topo do módulo
        with patch("api_dashboard.processar_resposta", return_value=resultado_mock):
            resp = client.post(
                "/webhook/sunchat",
                data=json.dumps({"number": "5511999990001", "message": "oi"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["intencao"] == "OUTRO"

    def test_segredo_errado_retorna_401(self, client, monkeypatch):
        import api_dashboard as api
        monkeypatch.setattr(api, "SUNCHAT_WEBHOOK_SECRET", "segredo_correto")
        resp = client.post(
            "/webhook/sunchat",
            data=json.dumps({"number": "5511999990001", "message": "oi"}),
            content_type="application/json",
            headers={"X-Sunchat-Secret": "segredo_errado"},
        )
        assert resp.status_code == 401

    def test_segredo_ausente_retorna_401(self, client, monkeypatch):
        import api_dashboard as api
        monkeypatch.setattr(api, "SUNCHAT_WEBHOOK_SECRET", "segredo_correto")
        resp = client.post(
            "/webhook/sunchat",
            data=json.dumps({"number": "5511999990001", "message": "oi"}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_segredo_correto_retorna_200(self, client, monkeypatch):
        import api_dashboard as api
        monkeypatch.setattr(api, "SUNCHAT_WEBHOOK_SECRET", "segredo_correto")
        resultado_mock = {
            "telefone": "5511999990001", "nome": "Joao",
            "intencao": "OUTRO", "acao": "ignorado", "sucesso": True,
        }
        with patch("api_dashboard.processar_resposta", return_value=resultado_mock):
            resp = client.post(
                "/webhook/sunchat",
                data=json.dumps({"number": "5511999990001", "message": "oi"}),
                content_type="application/json",
                headers={"X-Sunchat-Secret": "segredo_correto"},
            )
        assert resp.status_code == 200

    def test_sem_segredo_configurado_aceita_sem_header(self, client, monkeypatch):
        """Quando SUNCHAT_WEBHOOK_SECRET está vazio, nenhuma auth é exigida."""
        import api_dashboard as api
        monkeypatch.setattr(api, "SUNCHAT_WEBHOOK_SECRET", "")
        resultado_mock = {
            "telefone": "5511999990001", "nome": "Joao",
            "intencao": "OUTRO", "acao": "ignorado", "sucesso": True,
        }
        with patch("api_dashboard.processar_resposta", return_value=resultado_mock):
            resp = client.post(
                "/webhook/sunchat",
                data=json.dumps({"number": "5511999990001", "message": "oi"}),
                content_type="application/json",
            )
        assert resp.status_code == 200


# ===========================================================================
# GET /api/download
# ===========================================================================
class TestDownload:
    def test_pasta_invalida_retorna_400(self, client):
        resp = client.get("/api/download/pasta_inexistente/arquivo.pdf")
        assert resp.status_code == 400

    def test_arquivo_inexistente_retorna_404(self, client):
        resp = client.get("/api/download/validados/nao_existe.pdf")
        assert resp.status_code == 404

    def test_arquivo_existente_retorna_200(self, client):
        import api_dashboard as api
        pasta = api.PASTA_BOLETOS["validados"]
        caminho = os.path.join(pasta, "teste.pdf")
        with open(caminho, "wb") as f:
            f.write(b"%PDF-1.4 fake content")
        resp = client.get("/api/download/validados/teste.pdf")
        assert resp.status_code == 200
