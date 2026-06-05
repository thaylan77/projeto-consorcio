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
PASTA_DIAGNOSTICO = "diagnostico_buscador"

# Reinicia o driver a cada N clientes para evitar vazamento de memória
# do Chrome headless em execuções longas.
RESTART_INTERVAL = 50


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
def processar_cliente(driver, wait, cpf: str, nome_cliente: str) -> dict:
    """
    Processa um cliente no CNY. Retorna dict com a categoria do resultado
    para fins de telemetria:
      categoria ∈ {quitado_cancelado, sem_contrato, abrir_contrato_falhou,
                   sem_parcela_valida, baixou}
      baixados  : nº de PDFs efetivamente salvos
      ignoradas : nº de parcelas vistas mas com valor < mínimo
    """
    log(f"Iniciando: {nome_cliente} (CPF: {cpf})", modulo=MODULO)
    parcelas_ignoradas = 0
    # Rastreia em qual etapa estávamos quando der erro, e quanto tempo cada uma levou.
    etapa_atual = "inicio"
    etapa_inicio = time.monotonic()
    etapas_log: list[str] = []

    def _marcar(nome_etapa: str):
        nonlocal etapa_atual, etapa_inicio
        dur = time.monotonic() - etapa_inicio
        etapas_log.append(f"{etapa_atual}={dur:.1f}s")
        etapa_atual = nome_etapa
        etapa_inicio = time.monotonic()

    try:
        # --- RESET DE TELA ---
        etapa_atual = "reset_tela"
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
        _marcar("selecionar_cpf")
        wait.until(EC.presence_of_element_located((By.ID, "ctl00_Conteudo_cbxCriterioBusca")))
        driver.execute_script(
            "var d=document.getElementById('ctl00_Conteudo_cbxCriterioBusca');"
            "d.value='F';"
            "__doPostBack('ctl00$Conteudo$cbxCriterioBusca','');"
        )
        wait.until(EC.presence_of_element_located((By.ID, "ctl00_Conteudo_edtContextoBusca")))

        # --- BUSCAR ---
        _marcar("buscar")
        campo = wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_edtContextoBusca")))
        campo.clear()
        campo.send_keys(cpf)
        driver.find_element(By.ID, "ctl00_Conteudo_btnBuscar").click()
        wait.until(lambda d: (
            d.find_elements(By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkCD_Situacao_Cobranca")
            or d.find_elements(By.ID, "ctl00_Conteudo_lblMensagem")
        ))

        # --- STATUS ---
        _marcar("ler_status")
        try:
            situacao = wait.until(EC.presence_of_element_located(
                (By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkCD_Situacao_Cobranca")
            )).text.strip().upper()

            status_ruins = {"CAN", "CANCELADO", "QUI", "QUITADO", "EXCLUIDO", "CA2", "TRA", "SUS"}
            if situacao in status_ruins:
                log(f"Status '{situacao}' ignorado para {nome_cliente}.", modulo=MODULO)
                return {"categoria": "quitado_cancelado", "baixados": 0,
                        "ignoradas": 0, "status": situacao}
        except Exception:
            log(f"CPF {cpf} nao retornou contrato.", modulo=MODULO)
            return {"categoria": "sem_contrato", "baixados": 0, "ignoradas": 0}

        # --- ENTRAR NO CONTRATO ---
        _marcar("abrir_contrato")
        try:
            driver.find_element(
                By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkID_Documento"
            ).click()
            wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_btnConfirma")))
        except Exception:
            log(f"Falha ao abrir contrato de {nome_cliente}.", "ERROR", MODULO)
            return {"categoria": "abrir_contrato_falhou", "baixados": 0, "ignoradas": 0}

        # --- CONFIRMAR E LOCALIZAR ---
        _marcar("confirmar_localizar")
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
        _marcar("ler_tabela")
        tabela = wait.until(
            EC.presence_of_element_located((By.ID, "ctl00_Conteudo_grdBoleto_Avulso"))
        )
        linhas_iniciais = tabela.find_elements(By.TAG_NAME, "tr")
        indices_para_baixar = []

        # Inspeção detalhada da tabela — TODAS as linhas com TODAS as colunas
        # Layout confirmado por screenshot: # Cota | Pcl | Histórico | Vencimento |
        # Valor | Multa | Juros | Vl. devido | Vl. receber
        # Critério correto: usar "Vl. receber" (última coluna não-vazia), não "Valor".
        log(f"Tabela com {len(linhas_iniciais)} linhas para {nome_cliente}:", modulo=MODULO)
        for i, linha in enumerate(linhas_iniciais):
            colunas = linha.find_elements(By.TAG_NAME, "td")
            if len(colunas) <= 5:
                continue

            textos = [c.text.strip() for c in colunas]
            venc_str = textos[4] if len(textos) > 4 else ""
            valor_str = textos[5] if len(textos) > 5 else ""

            # "Vl. receber" tipicamente é a última coluna numérica. Pegamos o último
            # texto que parece valor monetário.
            vl_receber_str = ""
            for t in reversed(textos):
                if re.match(r"^[\d\.,]+$", t.replace(",", "").replace(".", "")):
                    vl_receber_str = t
                    break
            vl_receber = limpar_valor(vl_receber_str)
            valor_float = limpar_valor(valor_str)

            checkboxes = linha.find_elements(By.CSS_SELECTOR, "input[id*='imgEmite_Boleto']")
            if checkboxes:
                src = checkboxes[0].get_attribute("src") or ""
                if "ckUnchecked" in src:
                    chk_estado = "checkbox:vazio"
                elif "ckChecked" in src:
                    chk_estado = "checkbox:marcado"
                else:
                    chk_estado = "checkbox:?"
            else:
                chk_estado = "SEM_CHECKBOX"

            # Log compacto: índice, vencimento, valor, vl_receber e estado
            log(f"  linha[{i:>2}] venc={venc_str:>10} valor={valor_str:>10} "
                f"vl_receber={vl_receber_str:>10} {chk_estado}", modulo=MODULO)
            # Log completo das colunas, útil pra debug inicial
            log(f"    colunas={textos}", modulo=MODULO)

            # NOVO critério: só baixa se (a) vl_receber > 0 — há de fato algo pra cobrar
            # AND (b) checkbox disponível — CNY permite emitir
            # AND (c) valor da parcela acima do mínimo
            if (vl_receber > 0 and checkboxes
                    and valor_float >= VALOR_MINIMO_EMISSAO):
                indices_para_baixar.append(i)
            elif vl_receber <= 0:
                log(f"    -> pulada (Vl.receber=R$ {vl_receber_str or '0'} — nada a cobrar)",
                    modulo=MODULO)
            elif valor_float < VALOR_MINIMO_EMISSAO:
                parcelas_ignoradas += 1
                log(f"    -> ignorada (valor abaixo do minimo R$ {VALOR_MINIMO_EMISSAO})",
                    modulo=MODULO)
            elif not checkboxes:
                log(f"    -> ATENCAO: vl_receber ok mas sem checkbox", "WARNING", MODULO)

        if not indices_para_baixar:
            log(f"Nenhuma parcela valida para {nome_cliente}.", modulo=MODULO)
            return {"categoria": "sem_parcela_valida", "baixados": 0,
                    "ignoradas": parcelas_ignoradas}

        log(f"{len(indices_para_baixar)} parcelas validas para {nome_cliente}.", modulo=MODULO)
        baixados_aqui = 0

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
                            baixados_aqui += 1
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

        return {"categoria": "baixou", "baixados": baixados_aqui,
                "ignoradas": parcelas_ignoradas}

    except Exception as e:
        tipo_erro = type(e).__name__
        msg = str(e).strip() or "(mensagem vazia)"
        # Marca a etapa que falhou também na linha do tempo
        dur_atual = time.monotonic() - etapa_inicio
        etapas_log.append(f"{etapa_atual}=FALHOU_apos_{dur_atual:.1f}s")
        log(f"Erro em {nome_cliente} [{tipo_erro}] na etapa '{etapa_atual}' "
            f"({msg[:120]})", "ERROR", MODULO)
        log(f"  Linha do tempo: {' | '.join(etapas_log)}", modulo=MODULO)
        # Screenshot pra diagnóstico (nome inclui etapa pra facilitar grep)
        try:
            os.makedirs(PASTA_DIAGNOSTICO, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"{ts}_{cpf}_{etapa_atual}_{tipo_erro}.png"
            driver.save_screenshot(os.path.join(PASTA_DIAGNOSTICO, fname))
            log(f"Screenshot salvo: {fname}", modulo=MODULO)
        except Exception:
            pass
        # Anota a etapa que falhou pro main agregar
        try:
            e._etapa_falha = etapa_atual  # type: ignore[attr-defined]
        except Exception:
            pass
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
    erros_por_tipo: dict[str, int] = {}
    erros_por_etapa: dict[str, int] = {}   # qual passo gerou o timeout/erro
    categorias: dict[str, int] = {
        "baixou": 0, "quitado_cancelado": 0, "sem_contrato": 0,
        "abrir_contrato_falhou": 0, "sem_parcela_valida": 0,
    }
    status_breakdown: dict[str, int] = {}  # CAN/QUI/SUS/TRA... separados
    total_pdfs   = 0
    total_ignor  = 0
    sucessos     = 0

    while tentativas < max_relogin and clientes_restantes:
        driver, wait = iniciar_e_logar()
        if not driver:
            tentativas += 1
            log(f"Falha ao iniciar Chrome. Tentativa {tentativas}/{max_relogin}.", "WARNING", MODULO)
            time.sleep(10)
            continue

        try:
            total = len(clientes_restantes)
            processados_nesta_sessao = 0

            for i, linha in enumerate(clientes_restantes):
                nome = str(linha["pessoa"])
                cpf = re.sub(r"\D", "", str(linha["pessoacpfcnpj"]))
                data_venda = linha["datavenda"].strftime("%d/%m/%Y")
                log(f"[{i+1}/{total}] {nome} (Venda: {data_venda})", modulo=MODULO)

                try:
                    res = processar_cliente(driver, wait, cpf, nome)
                    sucessos += 1
                    cat = res.get("categoria", "?") if isinstance(res, dict) else "?"
                    categorias[cat] = categorias.get(cat, 0) + 1
                    if cat == "quitado_cancelado":
                        st = res.get("status", "?")
                        status_breakdown[st] = status_breakdown.get(st, 0) + 1
                    total_pdfs  += res.get("baixados", 0) if isinstance(res, dict) else 0
                    total_ignor += res.get("ignoradas", 0) if isinstance(res, dict) else 0
                except Exception as e:
                    tipo_erro = type(e).__name__
                    erros_por_tipo[tipo_erro] = erros_por_tipo.get(tipo_erro, 0) + 1
                    etapa_falha = getattr(e, "_etapa_falha", "?")
                    erros_por_etapa[etapa_falha] = erros_por_etapa.get(etapa_falha, 0) + 1
                    # Marca como processado ANTES de verificar o driver para
                    # evitar loop infinito no mesmo cliente após reconexão
                    cpfs_ja_feitos.add(cpf)
                    salvar_progresso(cpfs_ja_feitos)
                    log(f"Erro em {nome} [{tipo_erro} @ {etapa_falha}], "
                        f"cliente marcado como pulado.", "WARNING", MODULO)
                    try:
                        _ = driver.current_url
                        # driver vivo — pula este cliente e segue
                    except Exception:
                        raise  # driver morto — sai para reconectar
                else:
                    cpfs_ja_feitos.add(cpf)
                    salvar_progresso(cpfs_ja_feitos)

                processados_nesta_sessao += 1

                # Restart preventivo: Chrome headless vaza memória em execuções longas.
                # Reinicia o driver a cada RESTART_INTERVAL clientes (mas não no último).
                if (processados_nesta_sessao % RESTART_INTERVAL == 0
                        and i < total - 1):
                    log(f"Restart preventivo do Chrome apos {processados_nesta_sessao} clientes.",
                        modulo=MODULO)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver, wait = iniciar_e_logar()
                    if not driver:
                        log("Falha ao reiniciar Chrome durante restart preventivo.",
                            "ERROR", MODULO)
                        tentativas += 1
                        break  # sai do for, while reabre o driver

            log("Pipeline do buscador finalizado.", "SUCCESS", MODULO)
            log("=" * 55, modulo=MODULO)
            log("RESUMO DO BUSCADOR", modulo=MODULO)
            log(f"  Sucessos      : {sucessos}", modulo=MODULO)
            log(f"  PDFs baixados : {total_pdfs}", modulo=MODULO)
            log(f"  Parcelas abaixo do minimo (ignoradas): {total_ignor}",
                modulo=MODULO)
            log("  Categorias de saida:", modulo=MODULO)
            for cat, n in sorted(categorias.items(), key=lambda x: -x[1]):
                if n > 0:
                    log(f"    {cat:25s}: {n}", modulo=MODULO)
            if status_breakdown:
                log("  Status (breakdown de quitado_cancelado):", modulo=MODULO)
                for st, n in sorted(status_breakdown.items(), key=lambda x: -x[1]):
                    log(f"    {st:25s}: {n}", modulo=MODULO)
            if erros_por_tipo:
                log("  Erros por tipo:", modulo=MODULO)
                for tp, n in sorted(erros_por_tipo.items(), key=lambda x: -x[1]):
                    log(f"    {tp:25s}: {n}", modulo=MODULO)
            if erros_por_etapa:
                log("  Erros por etapa:", modulo=MODULO)
                for ep, n in sorted(erros_por_etapa.items(), key=lambda x: -x[1]):
                    log(f"    {ep:25s}: {n}", modulo=MODULO)
            log("=" * 55, modulo=MODULO)
            try:
                driver.quit()
            except Exception:
                pass
            return

        except Exception as e:
            tipo_erro = type(e).__name__
            log(f"Erro durante processamento [{tipo_erro}], tentando reconectar: {e}",
                "WARNING", MODULO)
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

    log(f"Limite de tentativas de re-login atingido. "
        f"Sucessos: {sucessos} | PDFs: {total_pdfs} | "
        f"categorias: {categorias} | erros: {erros_por_tipo or '{}'}",
        "ERROR", MODULO)


if __name__ == "__main__":
    main()
