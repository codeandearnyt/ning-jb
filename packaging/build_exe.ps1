#Requires -Version 5.1
<#
.SYNOPSIS
    Build dist\NingX-Optimizer.exe with PyInstaller.

.DESCRIPTION
    The executable is windowed: double-clicking it opens the UI. When it is
    started from a console with --check or --version, it attaches to that
    console and prints there. The build is unsigned; Windows SmartScreen will
    warn on first run until a signed release exists.

    Requires PyInstaller in the project venv:
        .\.venv\Scripts\python.exe -m pip install pyinstaller
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Create it with: uv venv --system-site-packages .venv"
}

Push-Location $root
try {
    & $python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not installed. Run: .\.venv\Scripts\python.exe -m pip install pyinstaller"
    }

    & $python "packaging\make_icon.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Icon generation failed with exit code $LASTEXITCODE."
    }

    $version = (& $python -c "import ningx; print(ningx.__version__)").Trim()
    $numbers = @($version.Split(".") | ForEach-Object { [int]($_ -replace "[^0-9]", "") })
    while ($numbers.Count -lt 4) { $numbers += 0 }
    $quad = ($numbers[0..3] -join ", ")
    $version4 = ($numbers[0..3] -join ".")

    $work = Join-Path $root "build\pyinstaller"
    $dist = Join-Path $root "dist"
    New-Item -ItemType Directory -Force -Path $work | Out-Null

    $template = Get-Content (Join-Path $root "packaging\version_info.txt") -Raw
    $template = $template.Replace("@FILEVERS@", $quad).Replace("@VERSION4@", $version4)
    $versionFile = Join-Path $work "version_info.txt"
    Set-Content -Path $versionFile -Value $template -Encoding ascii

    Write-Host "Building NingX-Optimizer $version ..."
    $arguments = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "NingX-Optimizer",
        "--icon", (Join-Path $root "packaging\ningx.ico"),
        "--version-file", $versionFile,
        "--distpath", $dist,
        "--workpath", $work,
        "--specpath", $work,
        "--paths", (Join-Path $root "src"),
        "--exclude-module", "tkinter",
        "--hidden-import", "win32cred",
        "--hidden-import", "win32pdh",
        "--hidden-import", "win32ts",
        # CredRead decodes the LastWritten FILETIME through win32timezone, which
        # pywin32 imports dynamically and PyInstaller therefore cannot see.
        "--hidden-import", "win32timezone",
        (Join-Path $root "src\ningx\__main__.py")
    )
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $exe = Join-Path $dist "NingX-Optimizer.exe"
    if (-not (Test-Path $exe)) {
        throw "Expected $exe, but it was not produced."
    }
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "Built $exe ($size MB)"
}
finally {
    Pop-Location
}
