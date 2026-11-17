# 청주교육지원청 수집을 이 PC의 Windows 예약 작업으로 등록한다 (다시 실행하면 덮어씀).
# 로그온할 때(2분 뒤) + 매일 12:00, 18:00. 꺼져 있어서 놓친 시간은 켜지면 바로 실행. 실패하면 10분 간격으로 3번 다시.
# 해제: Unregister-ScheduledTask -TaskName "kinder-job-monitor 청주 수집" -Confirm:$false
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "$root\.venv\Scripts\pythonw.exe" `
    -Argument "scripts\sync_cheongju.py --log" -WorkingDirectory $root
$logon = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$logon.Delay = "PT2M"
$triggers = @($logon, (New-ScheduledTaskTrigger -Daily -At 12:00), (New-ScheduledTaskTrigger -Daily -At 18:00))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable -RestartInterval (New-TimeSpan -Minutes 10) -RestartCount 3 `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "kinder-job-monitor 청주 수집" -Action $action -Trigger $triggers `
    -Settings $settings -Description "청주교육지원청 구인 게시판 수집 (해외 접속 차단이라 이 PC에서). 로그: .local\sync_cheongju.log" -Force | Out-Null
Write-Output "등록됨: kinder-job-monitor 청주 수집"
