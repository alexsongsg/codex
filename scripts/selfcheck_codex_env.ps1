param(
    [switch]$RequireHubspotToken
)

$ErrorActionPreference = "Stop"

function Pass($msg) { Write-Host "[PASS] $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$hasError = $false

Info "Checking runtime tools for Codex session..."

# python
try {
    $pythonCmd = Get-Command python -ErrorAction Stop
    $pythonVer = (& $pythonCmd.Source --version) 2>&1
    Pass "python available: $pythonVer ($($pythonCmd.Source))"
} catch {
    Fail "python not found in PATH."
    Info "Expected fallback shim: E:\\CodeX\\tools\\git\\cmd\\python.cmd"
    $hasError = $true
}

# gh
try {
    $ghCmd = Get-Command gh -ErrorAction Stop
    $ghVer = (& $ghCmd.Source --version | Select-Object -First 1)
    Pass "gh available: $ghVer ($($ghCmd.Source))"
} catch {
    Fail "gh not found in PATH."
    Info "Expected fallback shim: E:\\CodeX\\tools\\git\\cmd\\gh.cmd"
    $hasError = $true
}

# gh auth
try {
    gh auth status *> $null
    Pass "gh auth status: logged in"
} catch {
    Info "gh auth status: not logged in (run: gh auth login)"
}

# hubspot token
$token = [Environment]::GetEnvironmentVariable("HUBSPOT_PRIVATE_APP_TOKEN", "Process")
if (-not $token) {
    $token = [Environment]::GetEnvironmentVariable("HUBSPOT_PRIVATE_APP_TOKEN", "User")
}
if (-not $token) {
    $token = [Environment]::GetEnvironmentVariable("HUBSPOT_PRIVATE_APP_TOKEN", "Machine")
}

if ($token) {
    Pass "HUBSPOT_PRIVATE_APP_TOKEN available"
} else {
    $msg = "HUBSPOT_PRIVATE_APP_TOKEN missing"
    if ($RequireHubspotToken) {
        Fail $msg
        $hasError = $true
    } else {
        Info "$msg (optional for non-HubSpot tasks)"
    }
}

if ($hasError) {
    Fail "Codex environment check failed."
    exit 1
}

Pass "Codex environment check passed."
exit 0
