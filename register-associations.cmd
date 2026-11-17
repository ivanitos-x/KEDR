@echo off
pushd "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m viewers.associations
popd
pause
