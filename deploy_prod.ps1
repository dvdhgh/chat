# Production Deployment Script for LDN Chat
# NOTE: After deployment, remember to push changes to GitHub using the GitHub MCP server,
# as the local 'git' command may not be available or correctly configured.

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
    $REAL_URL = gcloud run services describe ldn-chat-prod --project gen-lang-client-0351290071 --region europe-west1 --format='value(status.url)'
    Write-Host "`n--- LOG: Deployment Successful! ---" -ForegroundColor Green
    Write-Host "Your app is live at: $REAL_URL" -ForegroundColor Cyan
} else {
    Write-Host "`n--- LOG: Deployment Failed with exit code $LASTEXITCODE ---" -ForegroundColor Red
}
