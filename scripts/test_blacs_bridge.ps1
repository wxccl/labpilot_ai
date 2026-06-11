Write-Host "Testing LabPilot BLACS bridge..."
curl.exe http://127.0.0.1:8765/status
Write-Host ""
curl.exe http://127.0.0.1:8765/channels
Write-Host ""
curl.exe http://127.0.0.1:8765/values
