$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& '.venv/Scripts/python.exe' -m pip install gdown opencv-python-headless
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.venv/Scripts/python.exe' -m gdown '1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK' -O 'apps/api/app/ml/cubicasa/model_best_val_loss_var.pkl'
if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Use the official CubiCasa5K README link.' }
