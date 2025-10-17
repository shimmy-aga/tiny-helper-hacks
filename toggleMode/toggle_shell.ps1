# Toggle Steam Big Picture shell <-> Explorer shell script
# Run as Administrator!

$regPathHKLM = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
$regPathHKCU = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
$steamExePath = "C:\Program Files (x86)\Steam\Steam.exe"
$steamShellValue = "`"$steamExePath`" -bigpicture"
$explorerShellValue = "explorer.exe"

$currentUser = $env:USERNAME
$currentDomain = $env:USERDOMAIN
$passwordPlain = "Mogooltje"  # Change this if needed

function Set-ShellValue {
    param (
        [string]$shellValue
    )
    Try {
        Set-ItemProperty -Path $regPathHKLM -Name "Shell" -Value $shellValue -ErrorAction Stop
        Set-ItemProperty -Path $regPathHKCU -Name "Shell" -Value $shellValue -ErrorAction Stop
        Write-Output "Shell set to '$shellValue' in HKLM and HKCU."
    } Catch {
        Write-Warning "Failed to set shell: $_"
        exit 1
    }
}

function ConfigureAutoLogin {
    param (
        [bool]$enable
    )
    Try {
        if ($enable) {
            Set-ItemProperty -Path $regPathHKLM -Name "AutoAdminLogon" -Value "1" -ErrorAction Stop
            Set-ItemProperty -Path $regPathHKLM -Name "DefaultUsername" -Value $currentUser -ErrorAction Stop
            Set-ItemProperty -Path $regPathHKLM -Name "DefaultPassword" -Value $passwordPlain -ErrorAction Stop
            Set-ItemProperty -Path $regPathHKLM -Name "DefaultDomainName" -Value $currentDomain -ErrorAction Stop
            Write-Output "Auto-login enabled for $currentDomain\$currentUser."
        } else {
            Set-ItemProperty -Path $regPathHKLM -Name "AutoAdminLogon" -Value "0" -ErrorAction Stop
            Remove-ItemProperty -Path $regPathHKLM -Name "DefaultPassword" -ErrorAction SilentlyContinue
            Remove-ItemProperty -Path $regPathHKLM -Name "DefaultUsername" -ErrorAction SilentlyContinue
            Remove-ItemProperty -Path $regPathHKLM -Name "DefaultDomainName" -ErrorAction SilentlyContinue
            Write-Output "Auto-login disabled."
        }
    } Catch {
        Write-Warning "Failed to configure auto-login: $_"
        exit 1
    }
}

function KillSteamProcesses {
    $steamProcs = @("steam","steamwebhelper","steambootstrapper")
    foreach ($procName in $steamProcs) {
        $procs = Get-Process -Name $procName -ErrorAction SilentlyContinue
        if ($procs) {
            foreach ($p in $procs) {
                try {
                    $p.Kill()
                    Write-Output "Killed Steam process $($p.Name) (PID: $($p.Id))"
                } catch {
                    Write-Warning "Failed to kill process $($p.Name): $_"
                }
            }
        }
    }
    # Wait until all Steam processes exit
    while (Get-Process -Name "steam" -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 500
    }
    Write-Output "All Steam processes terminated."
}

# Main logic: read current shell from HKLM (more authoritative)
$currentShell = (Get-ItemProperty -Path $regPathHKLM -Name "Shell" -ErrorAction SilentlyContinue).Shell

Write-Output "Current shell is: $currentShell"

if ($currentShell -like "*Steam.exe*") {
    # Currently Steam shell — switch to Explorer
    Write-Output "Switching shell from Steam to Explorer..."
    KillSteamProcesses
    Set-ShellValue -shellValue $explorerShellValue
    ConfigureAutoLogin -enable:$false
} else {
    # Currently Explorer shell (or other) — switch to Steam Big Picture
    Write-Output "Switching shell from Explorer to Steam Big Picture..."
    Set-ShellValue -shellValue $steamShellValue
    ConfigureAutoLogin -enable:$true
}

Write-Output "Rebooting in 5 seconds..."
Start-Sleep -Seconds 5

Restart-Computer -Force