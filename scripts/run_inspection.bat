@echo off
cd /d "%~dp0.."
python -m src.runner --bot all --suite p0 --notify
if errorlevel 1 (
    py -3 -m src.runner --bot all --suite p0 --notify
)
exit /b %ERRORLEVEL%
