# Fidelity Life Assurance WhatsApp Bot - Tunnel Launcher
# This script launches a public tunnel to expose http://localhost:8000 to Meta's Cloud API

$cloudflared = Join-Path $PSScriptRoot "cloudflared.exe"

if (Test-Path $cloudflared) {
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " Starting Cloudflare Tunnel for Fidelity Life Assurance WhatsApp Bot" -ForegroundColor Green
    Write-Host " Forwarding to http://localhost:8000" -ForegroundColor Cyan
    Write-Host " Look for your public URL ending with '.trycloudflare.com'" -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Cyan
    & $cloudflared tunnel --url http://127.0.0.1:8000
} else {
    Write-Host "Cloudflared binary not found at $cloudflared." -ForegroundColor Red
    Write-Host "Please ensure cloudflared.exe is in the project directory." -ForegroundColor Yellow
}
