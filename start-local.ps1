$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    & '.venv/Scripts/python.exe' -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$env:DEBUG = 'true'
$env:LOCAL_ONLY = 'true'
$env:PUBLIC_ORIGIN = 'http://127.0.0.1:8000'
& '.venv/Scripts/python.exe' manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Database setup failed.' }
& '.venv/Scripts/python.exe' manage.py bootstrap
& '.venv/Scripts/python.exe' manage.py collectstatic --noinput
Write-Host 'Consumer website: http://127.0.0.1:8000/'
Write-Host 'Private staff login: http://127.0.0.1:8000/staff/login/'
$workerPython = (Resolve-Path '.venv/Scripts/python.exe').Path
$worker = Start-Process -FilePath $workerPython -ArgumentList @('manage.py','process_jobs','--loop') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
try {
    & '.venv/Scripts/python.exe' manage.py runserver 127.0.0.1:8000 --noreload
} finally {
    if (-not $worker.HasExited) { Stop-Process -Id $worker.Id }
}
