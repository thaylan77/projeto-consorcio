import requests
import pandas as pd
from datetime import datetime
from config import BEARER_TOKEN
from logger import log

API_URL = "https://microworkcloud.com.br/api/integracao/terceiro"
OUTPUT_FILENAME = "relatorio_microwork_consorcio.csv"
MODULO = "Extrator API"


def extrair_dados():
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Expect": "",
    }

    # DataFinal sempre apontada para o final do próximo ano (nunca expira)
    ano_proximo = datetime.now().year + 1

    payload = {
        "idrelatorioconfiguracao": 194,
        "idrelatorioconsulta": 97,
        "idrelatorioconfiguracaoleiaute": 194,
        "idrelatoriousuarioleiaute": 285,
        "ididioma": 1,
        "listaempresas": [1, 2, 3, 4, 5, 6, 7, 8],
        "filtros": (
            "Reposicao=True;"
            "PontoVenda=null;"
            "SituacaoContrato=null;"
            "Novo=True;"
            "NaoRecebidoPrimeiraParcela=True;"
            "PrimeiraParcelaRecebida=True;"
            "RecebidoCartaoAdm=True;"
            "Vendedor=null;"
            "Supervisor=null;"
            "Gerente=null;"
            "Modelo=null;"
            "Administradora=null;"
            "DataInicial=2020-01-01;"
            f"DataFinal={ano_proximo}-12-31;"
            "NaoRecebidoCartaoAdm=True;"
            "NaoRemessa=True;"
            "Remessa=True;"
            "NaoPagamentoAdministradora=True;"
            "PagamentoAdministradora=True;"
            "Municipio=null"
        ),
    }

    log(f"Iniciando requisicao para a API: {API_URL}", modulo=MODULO)

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=300)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data)
                df.to_csv(OUTPUT_FILENAME, index=False, encoding="utf-8-sig")
                log(f"Sucesso! {len(df)} registros salvos em '{OUTPUT_FILENAME}'", "SUCCESS", MODULO)
                return True
            else:
                log("API retornou sucesso, mas a lista de dados esta vazia.", "WARNING", MODULO)
                return False
        else:
            log(f"Falha na API. Status: {response.status_code} - {response.reason}", "ERROR", MODULO)
            log(f"Resposta: {response.text}", "TRACE", MODULO)
            return False

    except Exception as e:
        log(f"Erro de conexao: {e}", "CRITICAL", MODULO)
        return False


if __name__ == "__main__":
    extrair_dados()
