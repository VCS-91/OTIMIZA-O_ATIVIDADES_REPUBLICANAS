@echo off
REM Envia as alteracoes do projeto para o GitHub (commit + push).
REM Uso: dois cliques neste arquivo, ou no terminal:  atualizar_github.bat "mensagem do commit"
setlocal
cd /d "%~dp0"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Esta pasta nao e um repositorio git.
    goto fim
)

echo === Arquivos alterados ===
git status --short
echo.

set "MSG=%~1"
if "%MSG%"=="" set /p "MSG=Mensagem do commit (Enter = 'Atualizacao do projeto'): "
if "%MSG%"=="" set "MSG=Atualizacao do projeto"

git add -A
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "%MSG%"
    if errorlevel 1 (
        echo [ERRO] O commit falhou. Veja a mensagem acima.
        goto fim
    )
) else (
    echo Nada novo para commitar. Vou so enviar o que ainda nao foi enviado.
)

echo.
echo === Baixando alteracoes dos colegas (git pull --rebase) ===
git pull --rebase
if errorlevel 1 (
    echo [ERRO] Conflito ao juntar com o GitHub. Resolva os conflitos e rode de novo.
    goto fim
)

echo.
echo === Enviando para o GitHub (git push) ===
git push
if errorlevel 1 (
    echo [ERRO] O push falhou. Verifique a internet e o login do GitHub.
    goto fim
)

echo.
echo Pronto! O GitHub esta atualizado.

:fim
echo.
pause
endlocal
