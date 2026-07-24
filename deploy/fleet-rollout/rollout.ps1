[CmdletBinding()]
param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [int]$Limit = 3,
    [switch]$All,
    [switch]$DryRun,
    [string[]]$StoreCode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundlePath = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\store-bootstrap"))
$storesPath = Join-Path $scriptRoot "stores.local.csv"
$credentialsPath = Join-Path $scriptRoot "credentials.local.psd1"
$logsPath = Join-Path $scriptRoot "logs"

function Find-BitviseTool {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Bitvise SSH Client\$Name.exe"),
        (Join-Path $env:ProgramFiles "Bitvise SSH Client\$Name.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    throw "Bitvise tool '$Name.exe' was not found."
}

function Invoke-Bitvise {
    param(
        [Parameter(Mandatory = $true)][string]$Tool,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )

    Write-Host "  $Description" -ForegroundColor DarkCyan
    & $Tool @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (!(Test-Path -LiteralPath $storesPath)) {
    throw "Missing private store list: $storesPath"
}
if (!(Test-Path -LiteralPath $credentialsPath)) {
    throw "Missing private credentials file: $credentialsPath"
}
if (!(Test-Path -LiteralPath (Join-Path $bundlePath "install.sh"))) {
    throw "Bootstrap bundle is missing: $bundlePath"
}

$credentials = Import-PowerShellDataFile -LiteralPath $credentialsPath
$stores = @(Import-Csv -LiteralPath $storesPath)
if ($StoreCode) {
    $wanted = @($StoreCode | ForEach-Object { [string]$_ })
    $stores = @($stores | Where-Object { $wanted -contains [string]$_.store_code })
}
elseif (!$All) {
    if ($Limit -lt 1) {
        throw "Limit must be at least 1."
    }
    $stores = @($stores | Select-Object -First $Limit)
}

if (!$stores.Count) {
    throw "No stores selected."
}

if (!$DryRun) {
    $sftpc = Find-BitviseTool -Name "sftpc"
    $sexec = Find-BitviseTool -Name "sexec"
}

New-Item -ItemType Directory -Path $logsPath -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$transcriptPath = Join-Path $logsPath "rollout-$stamp.log"
$resultsPath = Join-Path $logsPath "results-$stamp.csv"
$results = [System.Collections.Generic.List[object]]::new()

Start-Transcript -LiteralPath $transcriptPath | Out-Null
try {
    Write-Host "Selected stores: $($stores.Count)" -ForegroundColor Cyan
    Write-Host "Mode: $(if ($DryRun) { 'DRY RUN' } else { 'INSTALL' })" -ForegroundColor Cyan
    Write-Host ""

    foreach ($store in $stores) {
        $code = [string]$store.store_code
        $ip = [string]$store.ip
        $started = Get-Date
        $osInfo = ""
        $status = "FAILED"
        $message = ""

        Write-Host "[$code] $ip" -ForegroundColor Yellow
        try {
            if ($code -notmatch '^[A-Za-z0-9_-]+$') {
                throw "Invalid store code."
            }
            $parsedIp = $null
            if (![System.Net.IPAddress]::TryParse($ip, [ref]$parsedIp)) {
                throw "Invalid IP address."
            }

            $details = Invoke-RestMethod -Uri "$ApiBase/api/store/$code" -TimeoutSec 15
            $osInfo = [string]$details.store.os_info
            if ($osInfo -match '(?i)SUSE.*15|SLES.*15') {
                $password = [string]$credentials.Sles15Password
                $osFamily = "SLES15"
            }
            elseif ($osInfo -match '(?i)SUSE.*12|SLES.*12') {
                $password = [string]$credentials.Sles12Password
                $osFamily = "SLES12"
            }
            else {
                throw "Cannot determine SLES 12/15 from API os_info: '$osInfo'."
            }

            Write-Host "  Detected: $osFamily - $osInfo"
            if ($DryRun) {
                $status = "DRY_RUN_OK"
                $message = "Validated store, IP and OS family."
                continue
            }

            $connection = @("$($credentials.User)@$ip", "-pw=$password")
            Invoke-Bitvise -Tool $sexec -Arguments ($connection + @(
                "-exitZero",
                "-cmd=mkdir -p /SmartId/agent/tmp/store-bootstrap"
            )) -Description "Create remote bootstrap directory"

            $commandFile = Join-Path $env:TEMP "eod-sftpc-$code-$stamp.txt"
            @(
                "lcd `"$bundlePath`""
                "cd /SmartId/agent/tmp/store-bootstrap"
                "put *"
                "exit"
            ) | Set-Content -LiteralPath $commandFile -Encoding ASCII
            try {
                Invoke-Bitvise -Tool $sftpc -Arguments ($connection + @(
                    "-cmdFile=$commandFile"
                )) -Description "Upload bootstrap bundle"
            }
            finally {
                Remove-Item -LiteralPath $commandFile -Force -ErrorAction SilentlyContinue
            }

            $remoteCommand = "cd /SmartId/agent/tmp/store-bootstrap && sh install.sh $code"
            Invoke-Bitvise -Tool $sexec -Arguments ($connection + @(
                "-exitZero",
                "-cmd=$remoteCommand"
            )) -Description "Install and verify agent"

            $status = "SUCCESS"
            $message = "Agent and updater installed successfully."
        }
        catch {
            $message = $_.Exception.Message
            Write-Host "  ERROR: $message" -ForegroundColor Red
        }
        finally {
            $results.Add([pscustomobject]@{
                store_code = $code
                ip = $ip
                os_info = $osInfo
                status = $status
                message = $message
                duration_seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
            })
            Write-Host "  RESULT: $status" -ForegroundColor $(if ($status -in @("SUCCESS", "DRY_RUN_OK")) { "Green" } else { "Red" })
            Write-Host ""
        }
    }
}
finally {
    $results | Export-Csv -LiteralPath $resultsPath -NoTypeInformation -Encoding UTF8
    Stop-Transcript | Out-Null
}

$failed = @($results | Where-Object { $_.status -eq "FAILED" })
Write-Host "Results: $resultsPath" -ForegroundColor Cyan
Write-Host "Transcript: $transcriptPath" -ForegroundColor Cyan
Write-Host "Successful: $(@($results | Where-Object { $_.status -in @('SUCCESS', 'DRY_RUN_OK') }).Count)"
Write-Host "Failed: $($failed.Count)"

if ($failed.Count) {
    exit 1
}
