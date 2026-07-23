param(
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(Mandatory = $true)][string]$WorkDir
)

$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$icon = Join-Path $env:SystemRoot "System32\shell32.dll,21"

$paths = @(
    (Join-Path $desktop "LocReach.lnk"),
    (Join-Path $startMenu "LocReach.lnk")
)

$ws = New-Object -ComObject WScript.Shell
foreach ($p in $paths) {
    $s = $ws.CreateShortcut($p)
    $s.TargetPath = $Target
    $s.WorkingDirectory = $WorkDir
    $s.WindowStyle = 1
    $s.Description = "Start LocReach (SearXNG + OpenSERP + app)"
    $s.IconLocation = $icon
    $s.Save()
    Write-Host "  [OK] $p"
}

# Best-effort taskbar pin (often blocked on modern Windows)
$desktopLnk = Join-Path $desktop "LocReach.lnk"
try {
    $shell = New-Object -ComObject Shell.Application
    $folder = $shell.Namespace((Split-Path $desktopLnk))
    $item = $folder.ParseName((Split-Path $desktopLnk -Leaf))
    $verbs = @($item.Verbs() | ForEach-Object { $_.Name -replace "&", "" })
    $pin = $item.Verbs() | Where-Object { ($_.Name -replace "&", "") -match "Pin to taskbar|Pin to Tas" }
    if ($pin) {
        $pin.DoVerb()
        Write-Host "  [OK] Pinned to taskbar"
    } else {
        Write-Host "  [!] Auto-pin not available. Right-click Desktop LocReach -> Pin to taskbar."
    }
} catch {
    Write-Host "  [!] Auto-pin not available. Right-click Desktop LocReach -> Pin to taskbar."
}
