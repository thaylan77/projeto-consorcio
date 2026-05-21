@echo off
title Sistema Consorcio Yamaha
echo ===================================================
echo   Sistema Consorcio Yamaha - Iniciando...
echo ===================================================
echo.

echo [1/3] Iniciando API do Dashboard...
start /B python api_dashboard.py

echo [2/3] Iniciando Agendador Autonomo (pipeline diario + cobranca D+2)...
start /B python agendador.py

echo [3/3] Aguardando servicos subirem...
timeout /t 3 /nobreak > NUL

echo.
echo Abrindo painel no navegador...
start dashboard\index.html

echo.
echo ===================================================
echo  SISTEMA ATIVO
echo  - Dashboard: http://localhost:5000
echo  - Pipeline: executa diariamente (ver .env HORA_PIPELINE)
echo  - Cobranca D+2: executa diariamente (ver .env HORA_COBRADOR)
echo  - Para encerrar tudo: feche esta janela
echo ===================================================
echo.
echo Pressione CTRL+C para encerrar todos os servicos.
pause > NUL
