# LDN Chat Project Doctor
# This script verifies your local development environment.

$ErrorActionPreference = "SilentlyContinue"
$PROJECT_ID = "gen-lang-client-0351290071"

Write-Host "`n--- [ PROJECT DOCTOR: LDN CHAT ] ---" -ForegroundColor Cyan

function Check-Result($Success, $Message, $FailMessage, $Remediation = "") {
    if ($Success) {
        Write-Host "[ OK ] " -NoNewline -ForegroundColor Green
        Write-Host $Message
    } else {
        Write-Host "[ !! ] " -NoNewline -ForegroundColor Red
        Write-Host $FailMessage
        if ($Remediation) {
            Write-Host "       -> Fix: $Remediation" -ForegroundColor Yellow
        }
    }
}

# 1. Virtual Environment Check
$isInVenv = ($env:VIRTUAL_ENV -match ".venv")
Check-Result `
    -Success $isInVenv `
    -Message "Active Virtual Environment detected ($env:VIRTUAL_ENV)" `
    -FailMessage "No active .venv detected in current session." `
    -Remediation "Run: .\.venv\Scripts\Activate.ps1"

# 2. GitHub Credentials Check
$hasGithubToken = ($null -ne $env:GITHUB_PERSONAL_ACCESS_TOKEN -and $env:GITHUB_PERSONAL_ACCESS_TOKEN.Length -gt 10)
Check-Result `
    -Success $hasGithubToken `
    -Message "GitHub MCP Token is configured." `
    -FailMessage "GITHUB_PERSONAL_ACCESS_TOKEN is missing or too short." `
    -Remediation "Make sure to open a NEW terminal, or set it manually if you just created it."

# 3. Google Cloud Check
$gcloudInstalled = (Get-Command gcloud -ErrorAction SilentlyContinue)
if ($gcloudInstalled) {
    $currentProject = gcloud config get-value project 2>$null
    $isCorrectProject = ($currentProject -eq $PROJECT_ID)
    Check-Result `
        -Success $isCorrectProject `
        -Message "GCloud configured correctly for project: $PROJECT_ID" `
        -FailMessage "GCloud project is set to '$currentProject' (Expected: $PROJECT_ID)" `
        -Remediation "Run: gcloud config set project $PROJECT_ID"
} else {
    Check-Result `
        -Success $false `
        -Message "" `
        -FailMessage "gcloud CLI is not installed." `
        -Remediation "Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
}

# 4. Node / NPX Check (for GitHub MCP)
$npxWorking = (npx -v 2>$null)
Check-Result `
    -Success ($null -ne $npxWorking) `
    -Message "NPX is available (Version $npxWorking). Required for GitHub MCP Server." `
    -FailMessage "NPX/Node.js is not found." `
    -Remediation "Install Node.js from https://nodejs.org/"

# 5. Python Dependency Check
Write-Host "`nChecking Python package health..." -ForegroundColor Gray
$pythonExe = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
$pipList = & $pythonExe -m pip list --format json | ConvertFrom-Json

function Check-Package($Name, $ExpectedVersion = "") {
    $pkg = $pipList | Where-Object { $_.name -ieq $Name }
    if ($pkg) {
        Check-Result -Success $true -Message "Package '$Name' is installed (Version $($pkg.version))" -FailMessage ""
    } else {
        Check-Result -Success $false -Message "" -FailMessage "Package '$Name' is MISSING." -Remediation "Run: .\.venv\Scripts\pip install -r requirements.txt"
    }
}

Check-Package "flet"
Check-Package "mcp"
Check-Package "google-cloud-firestore"

Write-Host "`n--- [ DOCTOR FINISHED ] ---`n" -ForegroundColor Cyan
