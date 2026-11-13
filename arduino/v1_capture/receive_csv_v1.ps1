# [repo note] v1 - Windows-only, no-install serial logger. Saves every line exactly as received.
# Usage: powershell -ExecutionPolicy Bypass -File receive_csv_v1.ps1 -Port COM3 -Tag test
#        (COM3 is an example - use the port shown in Arduino IDE > Tools > Port)
# receive_csv v1 (2026-09-11)
# Windows PowerShell serial logger - no installation required.
# Console messages are ASCII only so it works on any codepage.

param(
    [Parameter(Mandatory=$true)][string]$Port,
    [string]$Tag = "",
    [int]$Baud = 500000
)

$outDir = Join-Path $PSScriptRoot "output"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$name  = if ($Tag) { "piezo_${Tag}_${stamp}.csv" } else { "piezo_${stamp}.csv" }
$path  = Join-Path $outDir $name

$sp = New-Object System.IO.Ports.SerialPort($Port, $Baud, 'None', 8, 'One')
$sp.NewLine     = "`n"
$sp.ReadTimeout = 2000
$sp.DtrEnable   = $true

try {
    $sp.Open()
} catch {
    Write-Host "ERROR: cannot open $Port"
    Write-Host "  - Close the Arduino IDE Serial Monitor first."
    Write-Host "  - Check the port name in Arduino IDE: Tools > Port"
    exit 1
}

Write-Host "Recording -> $path"
Write-Host "Press any key to stop."
Write-Host ""

$writer = New-Object System.IO.StreamWriter($path, $false, [System.Text.Encoding]::UTF8)
$rows = 0
$events = 0

try {
    while ($true) {
        if ([Console]::KeyAvailable) { [Console]::ReadKey($true) | Out-Null; break }

        try { $line = $sp.ReadLine() } catch { continue }

        $line = $line.Trim()
        if ($line -eq "") { continue }

        if ($line.StartsWith("#")) {
            Write-Host $line
            if ($line.StartsWith("# event")) { $events++ }
        } else {
            $rows++
        }

        $writer.WriteLine($line)
        $writer.Flush()
    }
}
finally {
    $writer.Close()
    $sp.Close()
    Write-Host ""
    Write-Host "Saved: $path"
    Write-Host "  events: $events   rows: $rows"
}
