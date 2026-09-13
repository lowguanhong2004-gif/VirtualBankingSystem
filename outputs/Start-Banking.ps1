$ErrorActionPreference = 'Stop'
$bankProject = Split-Path -Parent $PSScriptRoot
$bankPython = 'C:\Users\lowgu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$bankPackages = Join-Path $bankProject 'work\python-packages'
if ((Test-Path -LiteralPath $bankPython) -and (Test-Path -LiteralPath (Join-Path $bankPackages 'streamlit'))) {
    & $bankPython (Join-Path $bankProject 'work\serve.py')
} else {
    Write-Host 'Install dependencies first: python -m pip install -r requirements.txt'
    python -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --server.port 8501
}
