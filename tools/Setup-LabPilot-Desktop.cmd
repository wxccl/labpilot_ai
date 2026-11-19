@echo off
setlocal
set "LABPILOT_PY=%CONDA_PREFIX%\python.exe"
if not exist "%LABPILOT_PY%" set "LABPILOT_PY=D:\anaconda\envs\labscript\python.exe"
if not exist "%LABPILOT_PY%" goto environment
"%LABPILOT_PY%" -c "from importlib.metadata import version; print('Runmanager',version('runmanager')); import PyQt5" || goto environment
"%LABPILOT_PY%" -m pip install --no-index --no-deps --find-links "%~dp0wheelhouse" labpilot-ai==0.3.6rc3 || goto failed
set "SITE=%~1"
if not defined SITE set "SITE=%LABPILOT_PROFILE%"
if not defined SITE set "SITE=D:\LabPilot\controller\profile.json"
if not exist "%SITE%" goto choose
"%LABPILOT_PY%" -c "from labpilot_ai.desktop_shortcut import create; import sys; print(create(sys.argv[1]))" "%SITE%" || goto failed
goto done
:choose
echo Choose the site profile in LabPilot. Then select Settings - Create desktop shortcut.
"%LABPILOT_PY%" -m labpilot_ai
goto done
:environment
echo Open the existing labscript Anaconda Prompt and run this file again.
:failed
pause
exit /b 1
:done
pause
