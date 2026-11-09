@echo off
rem Genera dist\ExamenSeguroPanel.exe (no requiere Python en la PC donde se use)
cd /d "%~dp0"
python -m pip install --quiet -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name ExamenSeguroPanel --add-data "web;web" panel_docente.py
echo Listo: dist\ExamenSeguroPanel.exe
pause
