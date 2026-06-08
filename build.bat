@echo off
echo ============================================
echo   AGOL Updater - Build Script
echo ============================================
echo.

REM Ativa o venv
call "%~dp0venv\Scripts\activate.bat"

REM Instala PyInstaller se necessário
echo [1/3] Verificando PyInstaller...
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Instalando PyInstaller...
    pip install pyinstaller
) else (
    echo PyInstaller já instalado.
)

REM Instala Pillow para conversão do ícone
echo.
echo [2/3] Verificando Pillow ^(para icone^)...
pip show Pillow >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Instalando Pillow...
    pip install Pillow
) else (
    echo Pillow já instalado.
)

REM Converte o ícone PNG para ICO se necessário
if exist "%~dp0icon.png" (
    if not exist "%~dp0icon.ico" (
        echo Convertendo icon.png para icon.ico...
        python -c "from PIL import Image; img = Image.open('icon.png'); img.save('icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
    )
)

echo.
echo [3/3] Compilando executavel...
echo.

REM Determina flag de ícone
set ICON_FLAG=
if exist "%~dp0icon.ico" (
    set ICON_FLAG=--icon=icon.ico
)

REM Compila com PyInstaller (modo pasta - mais rápido para abrir)
pyinstaller --noconfirm --windowed --name "AGOL_Updater" ^
    %ICON_FLAG% ^
    --add-data "camadas_ids.json;." ^
    --add-data "tratamentos;tratamentos" ^
    --hidden-import=arcgis ^
    --hidden-import=pandas ^
    --hidden-import=openpyxl ^
    --collect-all arcgis ^
    Agol_Updater.py

echo.
echo ============================================
if %ERRORLEVEL% equ 0 (
    echo   BUILD CONCLUIDO COM SUCESSO!
    
    echo Copiando camadas_ids.json e tratamentos para dist\AGOL_Updater...
    copy /Y "camadas_ids.json" "dist\AGOL_Updater\camadas_ids.json" >nul
    xcopy /E /I /Y "tratamentos" "dist\AGOL_Updater\tratamentos" >nul

    echo   Executavel em: dist\AGOL_Updater\AGOL_Updater.exe
    echo.
    echo   Para distribuir, copie a pasta inteira:
    echo     dist\AGOL_Updater\
) else (
    echo   ERRO NA COMPILACAO! Verifique os logs acima.
)
echo ============================================
pause
