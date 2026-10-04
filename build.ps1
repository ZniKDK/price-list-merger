# Сборка Price List Merger для Windows. Результат в папке dist:
#   PriceListMerger\PriceListMerger.exe       — программа (папкой)
#   PriceListMerger-<версия>-portable.zip     — архив «распаковал и запустил»
#   PriceListMerger-<версия>-Setup.exe        — установщик (если есть Inno Setup)
#
# Запуск из папки проекта:  .\build.ps1
# (если PowerShell запрещает скрипты: powershell -ExecutionPolicy Bypass -File build.ps1)

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }  # на GitHub Actions

# Версия — из пакета, чтобы не дублировать её вручную
$version = & $python -c "import sys; sys.path.insert(0, 'src'); import price_list_merger; print(price_list_merger.__version__)"
Write-Host "Сборка Price List Merger $version"

& $python -m pip install --quiet -r requirements-dev.txt
& $python -m PyInstaller price_list_merger.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }

# Демо-прайсы кладём рядом с программой — их удобно открыть сразу
Copy-Item -Recurse -Force "demo" "dist\PriceListMerger\demo"

# Переносная версия — архивом
$zip = "dist\PriceListMerger-$version-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\PriceListMerger" -DestinationPath $zip
Write-Host "Архив: $zip"

# Установщик — если установлен Inno Setup (ищем компилятор ISCC)
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DAppVersion=$version" "installer\price_list_merger.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup завершился с ошибкой" }
    Write-Host "Установщик: dist\PriceListMerger-$version-Setup.exe"
} else {
    Write-Host "Inno Setup не найден — установщик пропущен"
}
