import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
import os
import shutil
import glob
import re
import json

from config import (
    CNY_USUARIO, CNY_SENHA,
    PASTA_PARA_ENVIAR,
    VALOR_MINIMO_EMISSAO, MESES_RETROATIVOS,
)
from logger import log

MODULO = "Buscador"
arquivo_csv = "relatorio_microwork_consorcio.csv"
ARQUIVO_PROGRESSO = "progresso_buscador.json"


def _criar_options() -> webdriver.ChromeOptions:
    """Cria as opções do Chrome em tempo de execução (não em import)."""
    opts = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": PASTA_PARA_ENVIAR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_settings.popups": 0,
    }
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--log-level=3")

    # Necessário em servidores Linux sem interface gráfica (VPS/CI)
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    return opts


# =============================================================================
# PROGRESSO
# =============================================================================
def carregar_progresso() -> set:
    if os.path.exists(ARQUIVO_PROGRESSO):
        try:
            with open(ARQUIVO_PROGRESSO, "r", encoding="utf-8") as f:
                dados = json.load(f)
            hoje = datetime.now().strftime("%Y-%m-%d")
            if dados.get("data") == hoje:
                return set(dados.get("cpfs_processados", []))
        except Exception:
            pass
    return set()


def salvar_progresso(cpfs_processados: set) -> None:
    try:
        dados = {
            "data": datetime.now().strftime("%Y-%m-%d"),
            "cpfs_processados": list(cpfs_processados),
        }
        with open(ARQUIVO_PROGRESSO, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4)
    except Exception as e:
        log(f"Erro ao salvar progresso: {e}", "WARNING", MODULO)


# =============================================================================
# AUXILIARES
# =============================================================================
def limpar_valor(texto: str) -> float:
    apenas_numeros = re.sub(r"[^\d,]", "", texto)
    try:
        return float(apenas_numeros.replace(",", "."))
    except Exception:
        return 0.0


# =============================================================================
# LOGIN
# =============================================================================
def iniciar_e_logar():
    log("Iniciando Chrome e fazendo login...", modulo=MODULO)
    driver = webdriver.Chrome(options=_criar_options())
    wait = WebDriverWait(driver, 30)

    try:
        driver.get("https://newkey.cny.com.br/Intranet/")
        wait.until(EC.presence_of_element_located((By.ID, "edtUsuario"))).send_keys(CNY_USUARIO)
        wait.until(EC.presence_of_element_located((By.ID, "edtSenha"))).send_keys(CNY_SENHA)
        wait.until(EC.element_to_be_clickable((By.ID, "btnLogin"))).click()

        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="CO"]'))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="subs"]/ul/li[2]/a'))).click()
        wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_ctl00_tvwMenut2"))).click()

        log("Login e navegacao concluidos.", modulo=MODULO)
        return driver, wait
    except Exception as e:
        log(f"Erro no login: {e}", "ERROR", MODULO)
        try:
            driver.save_screenshot("erro_login.png")
        except Exception:
            pass
        try:
            driver.quit()
        except Exception:
            pass
        return None, None


# =============================================================================
# PROCESSAR CLIENTE
# =============================================================================
def processar_cliente(driver, wait, cpf: str, nome_cliente: str) -> bool:
    log(f"Iniciando: {nome_cliente} (CPF: {cpf})", modulo=MODULO)

    try:
        # --- RESET DE TELA ---
        try:
            try:
                driver.find_element(By.ID, "ctl00_Conteudo_ctl00_tvwMenut2").click()
            except Exception:
                wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="subs"]/ul/li[2]/a'))).click()
                wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_ctl00_tvwMenut2"))).click()
            wait.until(EC.element_to_be_clickable(
                (By.ID, "ctl00_Conteudo_identificacao_cota_btnBuscaAvancada")
            )).click()
        except Exception as e:
            log(f"Reset de tela falhou, recarregando: {e}", "WARNING", MODULO)
            driver.refresh()
            time.sleep(5)
            wait.until(EC.element_to_be_clickable(
                (By.ID, "ctl00_Conteudo_identificacao_cota_btnBuscaAvancada")
            )).click()

        # --- SELECIONAR CPF ---
        wait.until(EC.presence_of_element_located((By.ID, "ctl00_Conteudo_cbxCriterioBusca")))
        driver.execute_script(
            "var d=document.getElementById('ctl00_Conteudo_cbxCriterioBusca');"
            "d.value='F';"
            "__doPostBack('ctl00$Conteudo$cbxCriterioBusca','');"
        )
        wait.until(EC.presence_of_element_located((By.ID, "ctl00_Conteudo_edtContextoBusca")))

        # --- BUSCAR ---
        campo = wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_edtContextoBusca")))
        campo.clear()
        campo.send_keys(cpf)
        driver.find_element(By.ID, "ctl00_Conteudo_btnBuscar").click()
        wait.until(lambda d: (
            d.find_elements(By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkCD_Situacao_Cobranca")
            or d.find_elements(By.ID, "ctl00_Conteudo_lblMensagem")
        ))

        # --- STATUS ---
        try:
            situacao = wait.until(EC.presence_of_element_located(
                (By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkCD_Situacao_Cobranca")
            )).text.strip().upper()

            status_ruins = {"CAN", "CANCELADO", "QUI", "QUITADO", "EXCLUIDO", "CA2", "TRA", "SUS"}
            if situacao in status_ruins:
                log(f"Status '{situacao}' ignorado para {nome_cliente}.", modulo=MODULO)
                return True
        except Exception:
            log(f"CPF {cpf} nao retornou contrato.", modulo=MODULO)
            return True

        # --- ENTRAR NO CONTRATO ---
        try:
            driver.find_element(
                By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkID_Documento"
            ).click()
            wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_btnConfirma")))
        except Exception:
            log(f"Falha ao abrir contrato de {nome_cliente}.", "ERROR", MODULO)
            return False

        # --- CONFIRMAR E LOCALIZAR ---
        wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_btnConfirma"))).click()
        wait.until(EC.presence_of_element_located(
            (By.ID, "ctl00_Conteudo_identificacao_cota_btnLocaliza")
        ))
        for _ in range(3):
            try:
                btn = driver.find_element(By.ID, "ctl00_Conteudo_identificacao_cota_btnLocaliza")
                driver.execute_script("arguments[0].click();", btn)
                break
            except Exception:
                time.sleep(2)
        time.sleep(4)

        # --- PARCELAS ---
        tabela = wait.until(
            EC.presence_of_element_located((By.ID, "ctl00_Conteudo_grdBoleto_Avulso"))
        )
        linhas_iniciais = tabela.find_elements(By.TAG_NAME, "tr")
        indices_para_baixar = []

        for i, linha in enumerate(linhas_iniciais):
            colunas = linha.find_elements(By.TAG_NAME, "td")
            if len(colunas) > 5:
                valor_float = limpar_valor(colunas[5].text.strip())
                if valor_float >= VALOR_MINIMO_EMISSAO:
                    indices_para_baixar.append(i)
                elif valor_float > 0:
                    log(f"Parcela R$ {colunas[5].text.strip()} ignorada (abaixo do minimo).", modulo=MODULO)

        if not indices_para_baixar:
            log(f"Nenhuma parcela valida para {nome_cliente}.", modulo=MODULO)
            return True

        log(f"{len(indices_para_baixar)} parcelas validas para {nome_cliente}.", modulo=MODULO)

        for index_linha in indices_para_baixar:
            tabela = wait.until(
                EC.presence_of_element_located((By.ID, "ctl00_Conteudo_grdBoleto_Avulso"))
            )
            linha_atual = tabela.find_elements(By.TAG_NAME, "tr")[index_linha]
            colunas = linha_atual.find_elements(By.TAG_NAME, "td")
            vencimento = colunas[4].text.strip()
            valor = colunas[5].text.strip()
            log(f"Processando parcela {vencimento} (R$ {valor})", modulo=MODULO)

            # Marca checkbox
            try:
                icone = linha_atual.find_element(By.CSS_SELECTOR, "input[id*='imgEmite_Boleto']")
                if "ckUnchecked" in icone.get_attribute("src"):
                    icone.click()
                    time.sleep(2)
                    wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_btnEmitir")))
            except Exception as e:
                log(f"Erro ao marcar checkbox: {e}", "WARNING", MODULO)
                continue

            # Emite e aguarda download
            try:
                btn_emitir = wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_btnEmitir")))
                driver.execute_script("arguments[0].click();", btn_emitir)

                padrao_pdf = os.path.join(PASTA_PARA_ENVIAR, "*.pdf")
                arquivo_baixado = None
                for _ in range(60):
                    lista = glob.glob(padrao_pdf)
                    if lista and not glob.glob(os.path.join(PASTA_PARA_ENVIAR, "*.crdownload")):
                        arquivo_baixado = max(lista, key=os.path.getmtime)
                        break
                    time.sleep(1)

                if arquivo_baixado:
                    cpf_limpo = re.sub(r"[^\w\-_]", "", cpf)
                    venc_arquivo = vencimento.replace("/", "-")
                    nome_final = f"Boleto_{cpf_limpo}_Venc-{venc_arquivo}.pdf"
                    caminho_final = os.path.join(PASTA_PARA_ENVIAR, nome_final)
                    for _ in range(5):
                        try:
                            shutil.move(arquivo_baixado, caminho_final)
                            log(f"Salvo: {nome_final}", "SUCCESS", MODULO)
                            break
                        except PermissionError:
                            time.sleep(1)
                else:
                    log(f"Download falhou para parcela {vencimento}.", "ERROR", MODULO)

            except Exception as e:
                log(f"Erro na emissao: {e}", "ERROR", MODULO)

            # Reseta seleção para próxima parcela (página pode mudar após download)
            try:
                btn_localiza = driver.find_element(By.ID, "ctl00_Conteudo_identificacao_cota_btnLocaliza")
                driver.execute_script("arguments[0].click();", btn_localiza)
                time.sleep(5)
            except Exception:
                pass  # não crítico — só necessário quando há múltiplas parcelas

        return True

    except Exception as e:
        log(f"Erro geral em {nome_cliente}: {e}", "ERROR", MODULO)
        raise


# =============================================================================
# PRINCIPAL
# =============================================================================
def main():
    os.makedirs(PASTA_PARA_ENVIAR, exist_ok=True)
    log(f"Lendo CSV (ultimos {MESES_RETROATIVOS} meses)...", modulo=MODULO)
    try:
        df = pd.read_csv(arquivo_csv)
        df["datavenda"] = pd.to_datetime(df["datavenda"])
        data_corte = datetime.now() - relativedelta(months=MESES_RETROATIVOS)
        df_filtrado = df[df["datavenda"] >= data_corte]
        log(f"Total a processar: {len(df_filtrado)} clientes.", modulo=MODULO)
        if len(df_filtrado) == 0:
            return
    except Exception as e:
        log(f"Erro ao ler CSV: {e}", "CRITICAL", MODULO)
        return

    cpfs_ja_feitos = carregar_progresso()
    if cpfs_ja_feitos:
        log(f"Retomando: {len(cpfs_ja_feitos)} ja processados hoje.", modulo=MODULO)

    clientes_restantes = [
        linha
        for _, linha in df_filtrado.iterrows()
        if re.sub(r"\D", "", str(linha["pessoacpfcnpj"])) not in cpfs_ja_feitos
    ]

    if not clientes_restantes:
        log("Todos os clientes ja foram processados hoje.", modulo=MODULO)
        return

    log(f"Faltam {len(clientes_restantes)} clientes.", modulo=MODULO)

    max_relogin = 5
    tentativas = 0

    while tentativas < max_relogin and clientes_restantes:
        driver, wait = iniciar_e_logar()
        if not driver:
            tentativas += 1
            log(f"Falha ao iniciar Chrome. Tentativa {tentativas}/{max_relogin}.", "WARNING", MODULO)
            time.sleep(10)
            continue

        try:
            total = len(clientes_restantes)
            for i, linha in enumerate(clientes_restantes):
                nome = str(linha["pessoa"])
                cpf = re.sub(r"\D", "", str(linha["pessoacpfcnpj"]))
                data_venda = linha["datavenda"].strftime("%d/%m/%Y")
                log(f"[{i+1}/{total}] {nome} (Venda: {data_venda})", modulo=MODULO)

                try:
                    processar_cliente(driver, wait, cpf, nome)
                except Exception as e:
                    # Marca como processado ANTES de verificar o driver para
                    # evitar loop infinito no mesmo cliente após reconexão
                    cpfs_ja_feitos.add(cpf)
                    salvar_progresso(cpfs_ja_feitos)
                    log(f"Erro em {nome}, cliente marcado como pulado: {e}", "WARNING", MODULO)
                    # Verifica se o driver ainda responde
                    try:
                        _ = driver.current_url
                        continue  # driver vivo — pula este cliente e segue
                    except Exception:
                        raise  # driver morto — sai para reconectar

                cpfs_ja_feitos.add(cpf)
                salvar_progresso(cpfs_ja_feitos)

            log("Pipeline do buscador finalizado.", "SUCCESS", MODULO)
            driver.quit()
            return

        except Exception as e:
            log(f"Erro durante processamento, tentando reconectar: {e}", "WARNING", MODULO)
            tentativas += 1
            try:
                driver.quit()
            except Exception:
                pass
            clientes_restantes = [
                l for l in clientes_restantes
                if re.sub(r"\D", "", str(l["pessoacpfcnpj"])) not in cpfs_ja_feitos
            ]
            time.sleep(5)

    log("Limite de tentativas de re-login atingido.", "ERROR", MODULO)


if __name__ == "__main__":
    main()
