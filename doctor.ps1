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

# 2. Python Version Check
$pythonExe = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
$pythonVersionStr = & $pythonExe --version 2>&1
if ($pythonVersionStr -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    $isPythonOk = ($major -eq 3 -and $minor -ge 10)
    Check-Result `
        -Success $isPythonOk `
        -Message "Python Version is compatible ($($Matches[0]))" `
        -FailMessage "Python Version is incompatible ($($Matches[0])). Required: 3.10+" `
        -Remediation "Install Python 3.10 or higher from https://www.python.org/"
} else {
    Check-Result -Success $false -Message "" -FailMessage "Could not determine Python version."
}

# 3. GitHub Credentials Check
$hasGithubToken = ($null -ne $env:GITHUB_PERSONAL_ACCESS_TOKEN -and $env:GITHUB_PERSONAL_ACCESS_TOKEN.Length -gt 10)
Check-Result `
    -Success $hasGithubToken `
    -Message "GitHub MCP Token is configured." `
    -FailMessage "GITHUB_PERSONAL_ACCESS_TOKEN is missing or too short." `
    -Remediation "Make sure to open a NEW terminal, or set it manually if you just created it."

# 4. Google Cloud Check
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

# 5. Firebase Config Check
$firebaseFiles = @("firebase.json", ".firebaserc")
$allFirebaseFilesFound = $true
foreach ($f in $firebaseFiles) {
    if (!(Test-Path $f)) {
        $allFirebaseFilesFound = $false
        Write-Host "       [ !! ] Missing $f" -ForegroundColor Red
    }
}
Check-Result `
    -Success $allFirebaseFilesFound `
    -Message "Firebase configuration files found." `
    -FailMessage "Missing Firebase configuration files." `
    -Remediation "Ensure firebase.json and .firebaserc are present in the root directory."

# 6. Java Check (for Emulators)
$javaInstalled = (Get-Command java -ErrorAction SilentlyContinue)
Check-Result `
    -Success ($null -ne $javaInstalled) `
    -Message "Java is installed (Required for Firebase Emulators)." `
    -FailMessage "Java is missing." `
    -Remediation "Install Java (JDK 11+) to use Firebase Emulators."

# 7. Node / NPX Check (for GitHub MCP)
$npxWorking = (npx -v 2>$null)
Check-Result `
    -Success ($null -ne $npxWorking) `
    -Message "NPX is available (Version $npxWorking). Required for GitHub MCP Server." `
    -FailMessage "NPX/Node.js is not found." `
    -Remediation "Install Node.js from https://nodejs.org/"

# 8. Port 9090 Check
$port9090Free = $true
$owningProcess = 0
try {
    $portUse = Get-NetTCPConnection -LocalPort 9090 -ErrorAction SilentlyContinue
    if ($portUse) {
        $port9090Free = $false
        $owningProcess = $portUse.OwningProcess
    }
} catch {}

Check-Result `
    -Success $port9090Free `
    -Message "Port 9090 is available for local testing." `
    -FailMessage "Port 9090 is ALREADY IN USE by process ID $owningProcess." `
    -Remediation "Kill the process or free up port 9090 before starting the app."

# 9. Network Check
Write-Host "Checking network connectivity to Google APIs..." -NoNewline -ForegroundColor Gray
$connected = $false
try {
    $response = Test-NetConnection -ComputerName "firestore.googleapis.com" -Port 443 -InformationLevel Quiet
    $connected = $response
} catch {}
Write-Host " "
Check-Result `
    -Success $connected `
    -Message "Connected to Google APIs." `
    -FailMessage "Could not reach firestore.googleapis.com." `
    -Remediation "Check your internet connection and firewall settings."

# 10. Python Dependency Check
Write-Host "`nChecking Python package health..." -ForegroundColor Gray
$pipList = & $pythonExe -m pip list --format json | ConvertFrom-Json

function Check-Package($Name, $ExpectedVersion = "") {
    $pkg = $pipList | Where-Object { $_.name -ieq $Name }
    if ($pkg) {
        if ($ExpectedVersion -and $pkg.version -ne $ExpectedVersion) {
            Check-Result -Success $false -Message "" -FailMessage "Package '$Name' has VERSION MISMATCH (Installed: $($pkg.version), Expected: $ExpectedVersion)" -Remediation "Run: .\.venv\Scripts\pip install $Name==$ExpectedVersion"
        } else {
            Check-Result -Success $true -Message "Package '$Name' is installed (Version $($pkg.version))" -FailMessage ""
        }
    } else {
        Check-Result -Success $false -Message "" -FailMessage "Package '$Name' is MISSING." -Remediation "Run: .\.venv\Scripts\pip install -r requirements.txt"
    }
}

Check-Package "flet" "0.82.0"
Check-Package "flet-web" "0.82.0"
Check-Package "flet-audio" "0.82.0"
Check-Package "google-cloud-firestore"
Check-Package "google-cloud-storage"
Check-Package "google-cloud-secret-manager"
Check-Package "google-genai"
Check-Package "mcp"

Write-Host "`n--- [ DOCTOR FINISHED ] ---`n" -ForegroundColor Cyan
