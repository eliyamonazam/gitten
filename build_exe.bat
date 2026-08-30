@echo off
REM Builds a single portable Gitten.exe with PyInstaller. Run on Windows.
setlocal

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -e .[dev] --quiet

pyinstaller --onefile --windowed --noconsole --name Gitten ^
    --paths src ^
    src\gitten\main.py

echo.
echo Done. Find the executable at dist\Gitten.exe
endlocal
