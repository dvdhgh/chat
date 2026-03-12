# LDN Chat Dev Startup Script

# 1. Set Environment Variables for Emulators
# We are currently bypassing emulators to mirror production behavior exactly.
# $env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8081"
# $env:STORAGE_EMULATOR_HOST = "127.0.0.1:9199"
$env:GCLOUD_PROJECT = "gen-lang-client-0351290071"

# 1.5 Cleanup lingering processes on ports
Write-Host "--- LOG: Cleaning up ports ---" -ForegroundColor Yellow
$ports = @(8081, 9199, 9090)
foreach ($port in $ports) {
    try {
        $processId = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue).OwningProcess
        if ($processId) {
            Write-Host "Killing process $processId on port $port"
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

# Ensure Java is in the Path for this session
$env:Path += ";C:\Program Files\Microsoft\jdk-21.0.10.7-hotspot\bin"

Write-Host "--- LOG: Environment Set (Project: $env:GCLOUD_PROJECT) ---" -ForegroundColor Cyan

# 2. Check for Java (Required for Emulators)
if (!(Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Java is not installed. Emulators require JRE." -ForegroundColor Red
    # exit # Commenting out exit since we aren't enforcing emulators
}

# 3. Start Emulators in Background
# Write-Host "--- LOG: Starting Firebase Emulators ---" -ForegroundColor Cyan
# Start-Process npx -ArgumentList "-y", "firebase-tools", "emulators:start", "--only", "firestore,storage" -WindowStyle Minimized

# 4. Wait for Emulators (Simple Sleep)
# Write-Host "--- LOG: Waiting for Emulators to warm up (15s) ---" -ForegroundColor Yellow
# Start-Sleep -Seconds 15

# 5. Ensure Dependencies are correct
Write-Host "--- LOG: Checking dependencies (pinned to 0.82.0) ---" -ForegroundColor Yellow
$pythonExe = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
& $pythonExe -m pip install -r requirements.txt --quiet

# 6. Start Flet App
Write-Host "--- LOG: Starting LDN Chat App in Web Mode ---" -ForegroundColor Green
& $pythonExe main.py
