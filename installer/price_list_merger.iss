; Установщик Price List Merger (Inno Setup 6).
; Собирается из build.ps1: ISCC /DAppVersion=1.0.0 installer\price_list_merger.iss
; На входе — папка dist\PriceListMerger после PyInstaller.
;
; Установка без прав администратора — в папку пользователя
; (%LOCALAPPDATA%\Programs\PriceListMerger). Профили поставщиков лежат
; отдельно (%APPDATA%\PriceListMerger) и при удалении не стираются.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Постоянный идентификатор: по нему Windows узнаёт программу при обновлении
AppId={{3C9E5A71-2B84-4F0D-A6E2-7D51C0B94F38}
AppName=Price List Merger
AppVersion={#AppVersion}
AppVerName=Price List Merger {#AppVersion}
AppPublisher=ZniKDK
AppPublisherURL=https://github.com/ZniKDK/price-list-merger
AppSupportURL=https://github.com/ZniKDK/price-list-merger/issues
DefaultDirName={autopf}\PriceListMerger
DefaultGroupName=Price List Merger
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=PriceListMerger-{#AppVersion}-Setup
SetupIconFile=..\src\price_list_merger\resources\app.ico
UninstallDisplayIcon={app}\PriceListMerger.exe
UninstallDisplayName=Price List Merger
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\PriceListMerger\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Price List Merger"; Filename: "{app}\PriceListMerger.exe"
Name: "{group}\Демо-прайсы"; Filename: "{app}\demo"
Name: "{group}\{cm:UninstallProgram,Price List Merger}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Price List Merger"; Filename: "{app}\PriceListMerger.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PriceListMerger.exe"; Description: "{cm:LaunchProgram,Price List Merger}"; Flags: nowait postinstall skipifsilent
