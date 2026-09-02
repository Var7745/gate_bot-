param (
    [ValidateSet("Register", "Unregister", "Status", "RunNow")]
    [string]$Action = "Register",
    [string]$Time = "19:00"
)

$TaskName = "GATE_2027_Daily_7PM_Dispatcher"
$ScriptPath = "C:\Users\goudv\.gemini\antigravity\scratch\gate-2027-companion\scripts\daily_dispatch.py"
$PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    $PythonExe = "python.exe"
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  GATE 2027 Windows Task Scheduler Manager" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

switch ($Action) {
    "Register" {
        Write-Host "[1/3] Target Task: $TaskName" -ForegroundColor Yellow
        Write-Host "[2/3] Schedule   : Daily at $Time (Evening 7:00 PM IST)" -ForegroundColor Yellow
        Write-Host "[3/3] Executable : $PythonExe `"$ScriptPath`" --notify" -ForegroundColor Yellow

        # Use schtasks.exe for wide compatibility without admin elevation requirements for user tasks
        $TaskCommand = "`"$PythonExe`" `"$ScriptPath`" --notify"
        
        # Unregister if already exists
        schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null

        # Create daily scheduled task
        $result = schtasks.exe /Create /TN $TaskName /TR $TaskCommand /SC DAILY /ST $Time /F
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n✅ SUCCESS: Daily 7:00 PM Windows Task registered successfully!" -ForegroundColor Green
            Write-Host "Every day at $Time, Windows will trigger your daily lecture notification." -ForegroundColor Green
            Write-Host "Next run info:" -ForegroundColor Gray
            schtasks.exe /Query /TN $TaskName /FO LIST | Select-String "TaskName|Next Run Time|Status"
        } else {
            Write-Host "`n⚠️ Warning: schtasks returned code $LASTEXITCODE. Result: $result" -ForegroundColor Red
        }
    }

    "Unregister" {
        Write-Host "Removing task $TaskName..." -ForegroundColor Yellow
        schtasks.exe /Delete /TN $TaskName /F
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Task $TaskName has been removed." -ForegroundColor Green
        }
    }

    "Status" {
        Write-Host "Checking status for $TaskName..." -ForegroundColor Cyan
        schtasks.exe /Query /TN $TaskName /FO LIST
    }

    "RunNow" {
        Write-Host "Executing task now for test..." -ForegroundColor Cyan
        schtasks.exe /Run /TN $TaskName
    }
}
