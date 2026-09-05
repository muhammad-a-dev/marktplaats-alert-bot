@echo off
REM ===================================================================
REM  MarketPlats Alert Bot - starts the Discord bot and the scraper.
REM  Double-click this file, or run it from a terminal.
REM  Press Ctrl+C in the window to stop everything.
REM ===================================================================

title MarketPlats Alert Bot

REM Always work from the folder this file lives in.
cd /d "%~dp0"

REM Find Python. "py" is the standard Windows launcher, "python" is the fallback.
set PYTHON=py
where py >nul 2>&1
if errorlevel 1 set PYTHON=python

where %PYTHON% >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERROR: Python was not found.
    echo   Install it from https://www.python.org/downloads/
    echo   and tick "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

REM Install the two dependencies the first time, then remember it was done.
if not exist ".deps-installed" (
    echo Installing dependencies, this only happens once...
    %PYTHON% -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   ERROR: Could not install the dependencies.
        echo   Try running this by hand:  %PYTHON% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo done > ".deps-installed"
)

echo.
echo   Starting the Discord bot and the scraper...
echo   Press Ctrl+C to stop.
echo.

%PYTHON% run.py %*

REM Keep the window open so any error message stays readable.
echo.
echo   Stopped.
pause
