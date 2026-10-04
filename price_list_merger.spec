# Сборка PriceListMerger.exe (окно) и PriceListMerger-cli.exe (консоль)
# через PyInstaller.
# Запуск: .\build.ps1  (или: pyinstaller price_list_merger.spec --noconfirm)
#
# Сборка «папкой» (onedir): exe + папка _internal с Python, Qt и pandas.
# Такой вариант запускается быстрее, чем один большой exe, который
# каждый раз распаковывается во временную папку.

EXCLUDES = [
    "tkinter", "pytest", "IPython", "matplotlib", "scipy", "PIL",
    "PyQt6.QtWebEngineCore", "PyQt6.QtMultimedia", "PyQt6.QtQml", "PyQt6.QtQuick",
    "PyQt6.Qt3DCore", "PyQt6.QtBluetooth", "PyQt6.QtNetwork", "PyQt6.QtPdf",
]

analysis = Analysis(
    ["main.py"],
    pathex=["src"],
    # Иконка окна нужна программе во время работы
    datas=[("src/price_list_merger/resources", "price_list_merger/resources")],
    hiddenimports=[],
    # Модули, которые программе не нужны, — меньше размер сборки
    excludes=EXCLUDES,
    noarchive=False,
)

# Консольная версия: тот же код без окна, для планировщика задач и скриптов
cli_analysis = Analysis(["cli_main.py"], pathex=["src"], excludes=EXCLUDES + ["PyQt6"])

pyz = PYZ(analysis.pure)
cli_pyz = PYZ(cli_analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="PriceListMerger",
    icon="src/price_list_merger/resources/app.ico",
    console=False,  # без чёрного окна консоли
    upx=False,
)

cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name="PriceListMerger-cli",
    icon="src/price_list_merger/resources/app.ico",
    console=True,
    upx=False,
)

# Обе программы — в одной папке и с общими библиотеками
coll = COLLECT(
    exe,
    cli_exe,
    analysis.binaries,
    analysis.datas,
    cli_analysis.binaries,
    cli_analysis.datas,
    name="PriceListMerger",
    upx=False,
)
