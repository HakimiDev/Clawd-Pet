@echo off
REM Builds a single portable Clawd.exe into dist\ (settings are saved in "Clawd Data" next to the exe)
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name Clawd --icon assets\clawd.ico ^
  --add-data "assets\clawd.ico;assets" ^
  --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 ^
  --exclude-module matplotlib --exclude-module numpy --exclude-module pandas --exclude-module scipy ^
  --exclude-module IPython --exclude-module torch --exclude-module cv2 ^
  clawd_pet.pyw
echo.
echo Done: dist\Clawd.exe
