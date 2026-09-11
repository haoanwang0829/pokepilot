@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ==============================================
echo    PokePilot Portable Builder (Embedded Python)
echo ==============================================
echo.

:: ============================================================
:: Parse arguments
:: ============================================================
set "CLEAN_BUILD=0"
if /I "%~1"=="--clean" set "CLEAN_BUILD=1"
if /I "%~1"=="/clean" set "CLEAN_BUILD=1"

:: ============================================================
:: Configuration
:: ============================================================
set "PYTHON_VERSION=3.13.14"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"
set "BUILD_DIR=pokepilot-release"
set "PYTHON_DIR=%BUILD_DIR%\python"
set "SITE_PACKAGES=%PYTHON_DIR%\Lib\site-packages"

:: Track what was actually installed (for cleanup)
set "PIP_INSTALLED=0"
set "PACKAGES_INSTALLED=0"

:: ============================================================
:: Step 1: Clean previous build (only with --clean)
:: ============================================================
if "%CLEAN_BUILD%"=="1" (
    if exist "%BUILD_DIR%" (
        echo [1/9] Cleaning previous build...
        rmdir /s /q "%BUILD_DIR%"
    )
    echo [1/9] Full clean build mode
) else (
    if exist "%BUILD_DIR%\python\python.exe" (
        echo [1/9] Incremental build - existing Python detected
    ) else (
        echo [1/9] First build - will download everything
    )
)

:: ============================================================
:: Step 2: Create directory structure (safe: skip if exists)
:: ============================================================
echo [2/9] Creating directory structure...
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"
if not exist "%BUILD_DIR%\pokepilot" mkdir "%BUILD_DIR%\pokepilot"
if not exist "%BUILD_DIR%\data" mkdir "%BUILD_DIR%\data"
if not exist "%BUILD_DIR%\sprites" mkdir "%BUILD_DIR%\sprites"
if not exist "%BUILD_DIR%\models\torch\hub\checkpoints" mkdir "%BUILD_DIR%\models\torch\hub\checkpoints"
if not exist "%BUILD_DIR%\models\easyocr" mkdir "%BUILD_DIR%\models\easyocr"
if not exist "%SITE_PACKAGES%" mkdir "%SITE_PACKAGES%"

:: ============================================================
:: Step 3-5: Download & configure Python (skip if exists)
:: ============================================================
if exist "%PYTHON_DIR%\python.exe" (
    echo [3/9] Python already exists, skipping download
    echo [4/9] Skipping extraction
    echo [5/9] Skipping Python configuration
    goto :skip_python_setup
)

echo [3/9] Downloading Python %PYTHON_VERSION% embedded...
curl -L -o "%TEMP%\python-embed.zip" "%PYTHON_URL%"
if errorlevel 1 (
    echo ERROR: Failed to download Python
    pause
    exit /b 1
)

echo [4/9] Extracting Python...
powershell -Command "Expand-Archive -Path '%TEMP%\python-embed.zip' -DestinationPath '%PYTHON_DIR%' -Force"
del "%TEMP%\python-embed.zip"

echo [5/9] Configuring embedded Python...
(
    echo python313.zip
    echo .
    echo Lib/site-packages
    echo ..
    echo import site
) > "%PYTHON_DIR%\python313._pth"

:skip_python_setup

:: ============================================================
:: Step 6: Install pip (skip if exists)
:: ============================================================
if exist "%PYTHON_DIR%\Scripts\pip.exe" (
    echo [6/9] pip already exists, skipping installation
    goto :skip_pip_install
)

echo [6/9] Installing pip...
curl -L -o "%TEMP%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
if errorlevel 1 (
    echo ERROR: Failed to download pip
    pause
    exit /b 1
)
"%PYTHON_DIR%\python.exe" "%TEMP%\get-pip.py" --no-warn-script-location
del "%TEMP%\get-pip.py"
set "PIP_INSTALLED=1"

:skip_pip_install

:: ============================================================
:: Step 7: Install dependencies (skip if key packages exist)
:: ============================================================
if exist "%SITE_PACKAGES%\flask\__init__.py" (
    if exist "%SITE_packages%\torch\__init__.py" (
        echo [7/9] Python packages already installed, skipping
        goto :skip_packages_install
    )
)

echo [7/9] Installing Python packages (this may take 10-20 minutes)...
"%PYTHON_DIR%\python.exe" -m pip install --no-warn-script-location --target "%SITE_PACKAGES%" ^
    opencv-python>=4.9.0 ^
    numpy>=1.26.0 ^
    flask>=2.3.0 ^
    flask-cors>=4.0.0 ^
    pillow>=10.0.0 ^
    requests ^
    beautifulsoup4 ^
    easyocr

if errorlevel 1 (
    echo ERROR: Failed to install standard packages
    pause
    exit /b 1
)

echo   Installing PyTorch (CPU)...
"%PYTHON_DIR%\python.exe" -m pip install --no-warn-script-location --target "%SITE_PACKAGES%" ^
    torch>=2.1.0 torchvision>=0.16.0 ^
    --index-url https://download.pytorch.org/whl/cpu

if errorlevel 1 (
    echo ERROR: Failed to install PyTorch
    pause
    exit /b 1
)
set "PACKAGES_INSTALLED=1"

:skip_packages_install

:: ============================================================
:: Step 8: Copy ML models (existing caching logic)
:: ============================================================
echo [8/9] Copying ML models...

:: Remove leftover EasyOCR temp download (broken temp.zip forces EasyOCR to re-download)
if exist "%BUILD_DIR%\models\easyocr\temp.zip" del /q "%BUILD_DIR%\models\easyocr\temp.zip"

:: ResNet50 weights (torchvision looks in %%TORCH_HOME%%\hub\checkpoints)
call :get_model "%BUILD_DIR%\models\torch\hub\checkpoints\resnet50-0676ba61.pth" 50000000 "https://download.pytorch.org/models/resnet50-0676ba61.pth" "models\torch\hub\checkpoints\resnet50-0676ba61.pth" "%USERPROFILE%\.cache\torch\hub\checkpoints\resnet50-0676ba61.pth"

:: EasyOCR models (detection craft + ch_sim/en recognition)
call :get_easyocr_model "craft_mlt_25k.pth" 50000000 "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip" "models\easyocr\craft_mlt_25k.pth" "%USERPROFILE%\.EasyOCR\model\craft_mlt_25k.pth"
call :get_easyocr_model "zh_sim_g2.pth" 10000000 "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/zh_sim_g2.zip" "models\easyocr\zh_sim_g2.pth" "%USERPROFILE%\.EasyOCR\model\zh_sim_g2.pth"
call :get_easyocr_model "english_g2.pth" 5000000 "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip" "models\easyocr\english_g2.pth" "%USERPROFILE%\.EasyOCR\model\english_g2.pth"

if "%BUILD_FAILED%"=="1" (
    echo.
    echo ERROR: ML model acquisition failed, build aborted. Check network or local models\ dir.
    pause
    exit /b 1
)
echo   - All ML models verified

:: ============================================================
:: Step 9: Copy project files (xcopy is already incremental)
:: ============================================================
echo [9/9] Copying project files...
xcopy /E /I /Q "pokepilot" "%BUILD_DIR%\pokepilot"
xcopy /E /I /Q "data" "%BUILD_DIR%\data"
xcopy /E /I /Q "sprites" "%BUILD_DIR%\sprites"
copy "requirements.txt" "%BUILD_DIR%\" >nul
copy "LICENSE" "%BUILD_DIR%\" >nul
copy "pokepilot-release-README.md" "%BUILD_DIR%\README.md" >nul

:: Create start script
echo @echo off > "%BUILD_DIR%\start_pokepilot.bat"
echo chcp 65001 ^>nul >> "%BUILD_DIR%\start_pokepilot.bat"
echo title PokePilot >> "%BUILD_DIR%\start_pokepilot.bat"
echo. >> "%BUILD_DIR%\start_pokepilot.bat"
echo echo ============================================ >> "%BUILD_DIR%\start_pokepilot.bat"
echo echo          PokePilot is starting... >> "%BUILD_DIR%\start_pokepilot.bat"
echo echo ============================================ >> "%BUILD_DIR%\start_pokepilot.bat"
echo echo. >> "%BUILD_DIR%\start_pokepilot.bat"
echo cd /d "%%~dp0" >> "%BUILD_DIR%\start_pokepilot.bat"
echo. >> "%BUILD_DIR%\start_pokepilot.bat"
echo :: Set model paths for offline use >> "%BUILD_DIR%\start_pokepilot.bat"
echo set "TORCH_HOME=%%~dp0models\torch" >> "%BUILD_DIR%\start_pokepilot.bat"
echo set "EASYOCR_MODEL_DIR=%%~dp0models\easyocr" >> "%BUILD_DIR%\start_pokepilot.bat"
echo set PYTHONIOENCODING=utf-8 >> "%BUILD_DIR%\start_pokepilot.bat"
echo. >> "%BUILD_DIR%\start_pokepilot.bat"
echo :: Run with embedded Python (no installation needed) >> "%BUILD_DIR%\start_pokepilot.bat"
echo python\python.exe -m pokepilot.ui.ui_server >> "%BUILD_DIR%\start_pokepilot.bat"
echo. >> "%BUILD_DIR%\start_pokepilot.bat"
echo echo. >> "%BUILD_DIR%\start_pokepilot.bat"
echo echo Service stopped. Press any key to exit... >> "%BUILD_DIR%\start_pokepilot.bat"
echo pause ^>nul >> "%BUILD_DIR%\start_pokepilot.bat"

:: ============================================================
:: Cleanup: only if pip or packages were actually installed
:: ============================================================
if "%PACKAGES_INSTALLED%"=="1" (
    echo Cleaning up pip cache...
    "%PYTHON_DIR%\python.exe" -m pip cache purge 2>nul
)
if "%PIP_INSTALLED%"=="1" (
    if exist "%SITE_PACKAGES%\pip" rmdir /s /q "%SITE_PACKAGES%\pip"
    if exist "%SITE_PACKAGES%\pip-" rmdir /s /q "%SITE_PACKAGES%\pip-*"
    if exist "%SITE_PACKAGES%\setuptools" rmdir /s /q "%SITE_PACKAGES%\setuptools"
    if exist "%SITE_PACKAGES%\wheel" rmdir /s /q "%SITE_PACKAGES%\wheel"
)

echo.
echo ==============================================
echo    Build complete!
echo ==============================================
echo.
echo Output: %BUILD_DIR%\
echo.
echo To distribute:
echo   1. Zip the '%BUILD_DIR%' folder
echo   2. Users extract and double-click 'start_pokepilot.bat'
echo   3. No Python installation required!
echo.

pause

exit /b 0

:: ---------------------------------------------------------------
:: Subroutines: model fetch + verification (keep below exit /b 0)
:: ---------------------------------------------------------------

:check_size
:: %~1=file path  %~2=min bytes; sets SIZE_OK (1=OK)
set "SIZE_OK=0"
if exist "%~1" for %%A in ("%~1") do if %%~zA GEQ %~2 set "SIZE_OK=1"
goto :eof

:get_model
:: %~1=target  %~2=min bytes  %~3=download URL  %~4/%~5=local fallback sources
set "TARGET=%~1"
set "MIN_SIZE=%~2"
set "URL=%~3"
if exist "%TARGET%" (
    call :check_size "%TARGET%" "%MIN_SIZE%"
    if "!SIZE_OK!"=="1" ( echo   - OK: %TARGET% & goto :eof )
    echo   - %TARGET% exists but failed check, re-acquiring
    del /q "%TARGET%" 2>nul
)
for %%S in ("%~4" "%~5") do (
    if exist "%%~S" (
        copy "%%~S" "%TARGET%" >nul
        call :check_size "%TARGET%" "%MIN_SIZE%"
        if "!SIZE_OK!"=="1" ( echo   - OK: %TARGET% & goto :eof )
        del /q "%TARGET%" 2>nul
    )
)
echo   - %TARGET% not found locally, downloading...
curl -L -o "%TARGET%" "%URL%"
if errorlevel 1 goto :get_model_fail
call :check_size "%TARGET%" "%MIN_SIZE%"
if "%SIZE_OK%"=="1" ( echo   - OK: %TARGET% & goto :eof )
:get_model_fail
echo   ERROR: %TARGET% acquisition failed
set "BUILD_FAILED=1"
goto :eof

:get_easyocr_model
:: %~1=model file  %~2=min bytes  %~3=zip URL  %~4/%~5=local fallback sources
set "EZFNAME=%~1"
set "EZMIN=%~2"
set "EZZIP=%~3"
set "EZTDIR=%BUILD_DIR%\models\easyocr"
if exist "%EZTDIR%\%EZFNAME%" (
    call :check_size "%EZTDIR%\%EZFNAME%" "%EZMIN%"
    if "!SIZE_OK!"=="1" ( echo   - OK: %EZFNAME% & goto :eof )
    echo   - %EZFNAME% exists but failed check, re-acquiring
    del /q "%EZTDIR%\%EZFNAME%" 2>nul
)
for %%S in ("%~4" "%~5") do (
    if exist "%%~S" (
        copy "%%~S" "%EZTDIR%\%EZFNAME%" >nul
        call :check_size "%EZTDIR%\%EZFNAME%" "%EZMIN%"
        if "!SIZE_OK!"=="1" ( echo   - OK: %EZFNAME% & goto :eof )
        del /q "%EZTDIR%\%EZFNAME%" 2>nul
    )
)
echo   - %EZFNAME% not found locally, downloading...
curl -L -o "%TEMP%\easyocr_model.zip" "%EZZIP%"
if errorlevel 1 goto :ezfail
powershell -NoProfile -Command "Expand-Archive -Path '%TEMP%\easyocr_model.zip' -DestinationPath '%EZTDIR%' -Force"
del "%TEMP%\easyocr_model.zip" 2>nul
call :check_size "%EZTDIR%\%EZFNAME%" "%EZMIN%"
if "%SIZE_OK%"=="1" ( echo   - OK: %EZFNAME% & goto :eof )
:ezfail
echo   ERROR: %EZFNAME% acquisition failed
set "BUILD_FAILED=1"
goto :eof
