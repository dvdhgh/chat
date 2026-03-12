# Production Deployment Script for LDN Chat

Write-Host "--- LOG: Starting Production Deployment to Cloud Run ---" -ForegroundColor Cyan
Write-Host "Project: gen-lang-client-0351290071" -ForegroundColor Gray
Write-Host "Region:  europe-west1" -ForegroundColor Gray

# Check if gcloud is installed
if (!(Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: gcloud CLI not found. Please install Google Cloud SDK." -ForegroundColor Red
    exit
}

# Run the deployment
# --quiet is added to skip interactive prompts
gcloud run deploy ldn-chat-prod `
    --source . `
    --project gen-lang-client-0351290071 `
    --region europe-west1 `
    --allow-unauthenticated `
    --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n--- LOG: Deployment Successful! ---" -ForegroundColor Green
    Write-Host "Your app is live at: https://ldn-chat-prod-535455457834.europe-west1.run.app" -ForegroundColor Cyan
} else {
    Write-Host "`n--- LOG: Deployment Failed with exit code $LASTEXITCODE ---" -ForegroundColor Red
}
