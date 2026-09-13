param (
    [string]$Title = "🎯 GATE 2027 Evening 7:00 PM Mission",
    [string]$Message = "Tonight's Topic: Propositional & First Order Logic",
    [string]$Subtext = "Click to launch your curated YouTube class!",
    [string]$Url = "https://www.youtube.com/watch?v=xlUFkM7A2s8"
)

# Attempt 1: Modern Windows 10/11 WinRT Toast Notification
$toastSuccess = $false
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    # Escape XML special chars
    $safeTitle = [System.Security.SecurityElement]::Escape($Title)
    $safeMessage = [System.Security.SecurityElement]::Escape($Message)
    $safeSubtext = [System.Security.SecurityElement]::Escape($Subtext)
    $safeUrl = [System.Security.SecurityElement]::Escape($Url)

    $toastXml = @"
<toast launch="$safeUrl" activationType="protocol">
    <visual>
        <binding template="ToastGeneric">
            <text>$safeTitle</text>
            <text>$safeMessage</text>
            <text>$safeSubtext</text>
        </binding>
    </visual>
    <actions>
        <action content="🚀 Watch Class Now" arguments="$safeUrl" activationType="protocol" />
    </actions>
    <audio src="ms-winsoundevent:Notification.Reminder" />
</toast>
"@

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($toastXml)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
    
    # Use standard Windows PowerShell AppID or custom AppID
    $appId = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
    $toastSuccess = $true
} catch {
    # Fallback if WinRT is unavailable
    $toastSuccess = $false
}

# Fallback: Windows Forms Balloon Notification
if (-not $toastSuccess) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.BalloonTipTitle = $Title
        $notify.BalloonTipText = "$Message`n$Subtext"
        $notify.Visible = $true
        $notify.ShowBalloonTip(10000)
    } catch {
        # Silent pass if running headlessly
    }
}

Write-Host "Notification triggered: $Title - $Message"
