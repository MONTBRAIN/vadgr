# The O1 lifecycle, performed inside an isolated offline snapshot.
#
# This script runs as the logon command of a Windows Sandbox session whose
# configuration declares no network adapter. The snapshot is therefore offline
# before this script starts, and no host firewall, DNS, route or VPN setting is
# read or changed anywhere in this pass. The sandbox is discarded when it
# closes, so every file this script writes to the mapped folder is the only
# evidence that survives.
#
# It drives the registered installation vehicle through its own window, because
# a new installation refuses a quiet install by design: the current terms must
# be shown and accepted. It then launches the CLI and the console, reads the
# bundled legal notices, restarts the daemon twice, repairs, reads the rollback
# state and uninstalls with owner data deletion.
#
# Every step records what it observed. A step that cannot run records that
# instead, because a missing observation is a result and a guessed one is not.
[CmdletBinding()]
param(
    [string] $Shared = 'C:\o1'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$script:record = [ordered]@{
    started = (Get-Date).ToUniversalTime().ToString('o')
    machine = @{
        os = (Get-CimInstance Win32_OperatingSystem).Caption
        user = $env:USERNAME
        computer = $env:COMPUTERNAME
    }
    steps = New-Object System.Collections.ArrayList
}
$recordPath = Join-Path $Shared 'o1-record.json'
$transcript = Join-Path $Shared 'o1-transcript.txt'
Start-Transcript -LiteralPath $transcript -Force | Out-Null

function Save-Record {
    $script:record.finished = (Get-Date).ToUniversalTime().ToString('o')
    $script:record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $recordPath -Encoding utf8
}

function Add-Step {
    param(
        [Parameter(Mandatory)][string] $Name,
        [Parameter(Mandatory)][ValidateSet('pass', 'fail', 'observed', 'blocked')][string] $Result,
        $Detail
    )
    $entry = [ordered]@{
        name = $Name
        result = $Result
        at = (Get-Date).ToUniversalTime().ToString('o')
        detail = $Detail
    }
    [void]$script:record.steps.Add($entry)
    Write-Output ("[{0}] {1}" -f $Result.ToUpperInvariant(), $Name)
    if ($Detail) {
        # The transcript gets the shape, not the bulk. One run wrote 47 MB of
        # transcript and a 4.5 MB record, almost all of it window trees printed
        # twice, which buries the one line a reader needs.
        $line = $Detail | ConvertTo-Json -Depth 6 -Compress
        if ($line.Length -gt 2000) {
            $line = $line.Substring(0, 2000) + ("... [{0} more characters, kept in the record]" -f ($line.Length - 2000))
        }
        Write-Output $line
    }
    Write-Heartbeat ("recorded: $Name")
    # The snapshot can be closed at any moment, so the record is written after
    # every step rather than at the end.
    Save-Record
}

# Nothing in this driver waits without a bound, and it says so when a bound is
# reached. The snapshot is discarded when it closes, so a wait that never ends
# destroys the only evidence the cell would have produced. This cost the pass
# twice: an installer prompt nobody answered for eleven minutes, and a command
# that had already exited while its caller held a pipe open for thirty six.
$script:CommandBudgetSeconds = 420

function Invoke-Capture {
    param(
        [Parameter(Mandatory)][string] $Command,
        [string[]] $Arguments = @(),
        [int] $BudgetSeconds = $script:CommandBudgetSeconds
    )
    # The streams go to files rather than through a pipeline. A pipeline ends
    # when every writer closes it, which is not the same question as whether
    # the command finished, and the difference is exactly what hung this cell.
    Write-Heartbeat ("running: $Command " + ($Arguments -join ' '))
    $stamp = [guid]::NewGuid().ToString('N')
    $outPath = Join-Path $Shared "capture-$stamp.out"
    $errPath = Join-Path $Shared "capture-$stamp.err"
    $started = Get-Date
    $process = Start-Process -FilePath $Command -ArgumentList $Arguments -PassThru `
        -NoNewWindow -RedirectStandardOutput $outPath -RedirectStandardError $errPath
    # Reading the handle here caches it. Without that the exit code reads back
    # empty once the process ends, and an empty exit code is worse than none:
    # a failed command then looks like a successful one.
    $null = $process.Handle
    $finished = $process.WaitForExit($BudgetSeconds * 1000)
    if (-not $finished) {
        Write-Heartbeat ("budget reached: $Command after $BudgetSeconds seconds")
        # The whole tree, because a child of the command keeps the redirected
        # files open and the command's own death does not release them.
        & taskkill.exe /T /F /PID $process.Id 2>&1 | Out-Null
        [void]$process.WaitForExit(15000)
    }
    # The bounded wait returns before the exit code is readable, so the
    # unbounded one follows it. The process has already ended either way, so
    # this cannot reintroduce a wait: it only finishes reading what happened.
    # Without it every captured command reports an empty exit code, which is
    # worse than no capture, because a failure then reads as a success.
    $process.WaitForExit()
    $exitCode = $null
    try { $exitCode = $process.ExitCode } catch { $exitCode = $null }

    $output = @()
    foreach ($path in @($outPath, $errPath)) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $output += @(Get-Content -LiteralPath $path -ErrorAction SilentlyContinue)
        # A killed process can still hold its redirect file for a moment.
        foreach ($attempt in 1..10) {
            try { Remove-Item -LiteralPath $path -Force -ErrorAction Stop; break }
            catch { Start-Sleep -Milliseconds 200 }
        }
    }
    return @{
        exit_code = $exitCode
        timed_out = (-not $finished)
        seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
        output = (($output | ForEach-Object { "$_" }) -join "`n")
    }
}

# A snapshot the host cannot see inside needs a pulse it can. The host reads
# this file, so a stalled step is visible within seconds instead of looking
# exactly like a slow one.
function Write-Heartbeat {
    param([Parameter(Mandatory)][string] $What)
    $line = "{0}  {1}" -f (Get-Date).ToUniversalTime().ToString('o'), $What
    try { Set-Content -LiteralPath (Join-Path $Shared 'o1-heartbeat.txt') -Value $line -Encoding utf8 }
    catch { }
}

# --- the isolation this cell starts from -----------------------------------

function Measure-Isolation {
    $adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    $addresses = @(Get-NetIPAddress -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -ne '::1' } |
        ForEach-Object { $_.IPAddress })
    $dns = 'not attempted'
    try {
        Resolve-DnsName -Name 'github.com' -QuickTimeout -ErrorAction Stop | Out-Null
        $dns = 'RESOLVED, which means this snapshot is not offline'
    }
    catch { $dns = "refused: $($_.Exception.Message)" }
    $http = 'not attempted'
    try {
        Invoke-WebRequest -Uri 'https://github.com' -TimeoutSec 5 -UseBasicParsing | Out-Null
        $http = 'ANSWERED, which means this snapshot is not offline'
    }
    catch { $http = "refused: $($_.Exception.Message)" }
    return @{ adapters = $adapters; routable_addresses = $addresses; dns = $dns; http = $http }
}

# --- the installer window ---------------------------------------------------

function Get-SetupWindow {
    param([int] $TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'Vadgr setup')
    while ((Get-Date) -lt $deadline) {
        $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
            [System.Windows.Automation.TreeScope]::Children, $condition)
        if ($window) {
            # The element is reached again from the window handle, so every
            # pattern call below is delivered to this window and can never
            # reach another application.
            $handle = [IntPtr]$window.Current.NativeWindowHandle
            if ($handle -ne [IntPtr]::Zero) {
                $owned = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
                $process = Get-Process -Id $owned.Current.ProcessId -ErrorAction Stop
                return @{ element = $owned; handle = $handle; process = $process }
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "no window named 'Vadgr setup' appeared within $TimeoutSeconds seconds"
}

function Find-Control {
    param(
        [Parameter(Mandatory)] $Window,
        [Parameter(Mandatory)][string] $Name,
        [int] $TimeoutSeconds = 60,
        # Every window has a title bar Close button with the same accessible
        # name as the page button beside it. Driving by name alone closes the
        # window instead of pressing the button, and the run then reads as
        # finished.
        #
        # The discriminator is the shape of the automation id, not its
        # presence. Measured on this theme on 2026-11-06: the title bar button
        # reports the id `Close`, so requiring an id at all admits exactly the
        # control this switch exists to refuse. Minimize, Maximize and the four
        # scroll buttons report names as ids too.
        #
        # Every page control carries the dialog control id as a number:
        # Install Vadgr 32768, Decline 111, the page Close 132 and
        # Uninstall 32773.
        [switch] $PageControl
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, $Name)
    while ((Get-Date) -lt $deadline) {
        $matches = $Window.element.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants, $condition)
        foreach ($element in $matches) {
            if (-not $element.Current.IsEnabled -or $element.Current.IsOffscreen) { continue }
            if ($element.Current.ProcessId -ne $Window.element.Current.ProcessId) {
                throw "the control named '$Name' belongs to another process"
            }
            if ($PageControl -and ($element.Current.AutomationId -notmatch '^\d+$')) { continue }
            return $element
        }
        Start-Sleep -Milliseconds 400
    }
    throw "no enabled control named '$Name' within $TimeoutSeconds seconds"
}

function Answer-FilesInUse {
    # Windows Installer asks about held files in a task dialog of its own, not
    # in the setup window, so a driver that watches only the setup window waits
    # for an answer nobody gives. Measured on 2026-10-27: an unanswered prompt
    # ends the package after about eleven minutes with 0x80070642 and a full
    # rollback, and the only visible sign is a window the driver never looked
    # at.
    #
    # The process check is not a formality. Any application can own a dialog of
    # this class, including the owner's own tools, so the dialog is answered
    # only when it belongs to the process that owns the setup window.
    param([Parameter(Mandatory)] $Window)
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty, '#32770')
    $dialogs = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Children, $condition)
    foreach ($dialog in $dialogs) {
        if ($dialog.Current.ProcessId -ne $Window.element.Current.ProcessId) { continue }
        $owned = [System.Windows.Automation.AutomationElement]::FromHandle(
            [IntPtr]$dialog.Current.NativeWindowHandle)
        $names = @()
        $all = $owned.FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($element in $all) { $names += $element.Current.Name }
        $radio = $null
        $ok = $null
        foreach ($element in $all) {
            if ($element.Current.ControlType -eq [System.Windows.Automation.ControlType]::RadioButton -and
                $element.Current.Name -like 'Close the applications*') { $radio = $element }
            if ($element.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
                $element.Current.Name -eq 'OK') { $ok = $element }
        }
        if (-not $radio -or -not $ok) { continue }
        $radio.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        $ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        Add-Step -Name 'the installer asked about held files and the driver answered it' `
            -Result 'observed' -Detail @{ title = $owned.Current.Name; elements = $names }
        return $true
    }
    return $false
}

function Wait-ForText {
    # Wait until the window's own tree carries one of these strings.
    param(
        [Parameter(Mandatory)] $Window,
        [Parameter(Mandatory)][string[]] $AnyOf,
        [int] $TimeoutSeconds = 1500
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $names = @(Read-WindowTree -Window $Window | ForEach-Object { $_.name })
        foreach ($wanted in $AnyOf) {
            if ($names -contains $wanted) { return $wanted }
        }
        [void](Answer-FilesInUse -Window $Window)
        Start-Sleep -Seconds 5
    }
    throw ("none of these appeared within $TimeoutSeconds seconds: " + ($AnyOf -join ', '))
}

function Read-WindowTree {
    param([Parameter(Mandatory)] $Window)
    $rows = @()
    $all = $Window.element.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($element in $all) {
        $rows += @{
            name = $element.Current.Name
            control_type = $element.Current.ControlType.ProgrammaticName
            enabled = [bool]$element.Current.IsEnabled
            offscreen = [bool]$element.Current.IsOffscreen
        }
    }
    return $rows
}

function Invoke-Control {
    param([Parameter(Mandatory)] $Element)
    $pattern = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
}

function Toggle-Control {
    param([Parameter(Mandatory)] $Element)
    $pattern = $Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    $pattern.Toggle()
    return $pattern.Current.ToggleState.ToString()
}

# --- the daemon -------------------------------------------------------------

$installRoot = Join-Path $env:LOCALAPPDATA 'Programs\Vadgr'
$cli = Join-Path $installRoot 'vadgr.exe'
$app = Join-Path $installRoot 'vadgr-app.exe'

function Measure-Health {
    param([int] $TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $started = Get-Date
            $answer = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' `
                -TimeoutSec 5 -UseBasicParsing
            return @{
                status = [int]$answer.StatusCode
                milliseconds = [math]::Round(((Get-Date) - $started).TotalMilliseconds, 1)
                body = $answer.Content
            }
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    return @{ status = 0; error = "no answer on loopback within $TimeoutSeconds seconds" }
}

function Get-DaemonProcesses {
    return @(Get-Process -Name 'vadgr' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($installRoot, 'OrdinalIgnoreCase') } |
        ForEach-Object { @{ id = $_.Id; path = $_.Path } })
}

# --- the pass ---------------------------------------------------------------

try {
    Add-Step -Name 'the snapshot is offline before anything is installed' `
        -Result 'observed' -Detail (Measure-Isolation)

    $setup = Join-Path $Shared 'Vadgr-0.5.0-windows-x64-setup.exe'
    if (-not (Test-Path -LiteralPath $setup)) { throw "no vehicle at $setup" }
    Add-Step -Name 'the vehicle under test' -Result 'observed' -Detail @{
        path = $setup
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $setup).Hash.ToLowerInvariant()
        bytes = (Get-Item -LiteralPath $setup).Length
    }

    $log = Join-Path $Shared 'o1-install.log'
    $started = Start-Process -FilePath $setup -ArgumentList @('/log', $log) -PassThru
    $window = Get-SetupWindow
    Add-Step -Name 'the installer shows its own window, as a new installation must' `
        -Result 'pass' -Detail @{
            launched_process = $started.Id
            window_process = $window.process.Id
            window_process_name = $window.process.ProcessName
            handle = [int64]$window.handle
        }

    $terms = Find-Control -Window $window -Name 'I have read and accept these terms'
    $state = Toggle-Control -Element $terms
    Add-Step -Name 'the terms are accepted through the checkbox the reader uses' `
        -Result $(if ($state -eq 'On') { 'pass' } else { 'fail' }) `
        -Detail @{ toggle_state = $state }

    $install = Find-Control -Window $window -Name 'Install Vadgr' -PageControl
    Invoke-Control -Element $install
    Add-Step -Name 'the installation starts from the window' -Result 'pass' -Detail @{
        invoked = 'Install Vadgr'
    }

    $reached = Wait-ForText -Window $window -AnyOf @('Vadgr is ready.', 'Open the setup log')
    $tree = Read-WindowTree -Window $window
    $close = Find-Control -Window $window -Name 'Close' -PageControl
    Add-Step -Name 'the installer reports a finished installation' `
        -Result $(if ($reached -eq 'Vadgr is ready.') { 'pass' } else { 'fail' }) `
        -Detail @{ reached = $reached; tree = $tree }
    Invoke-Control -Element $close
    Start-Sleep -Seconds 3

    $inventory = @()
    foreach ($name in @('vadgr.exe', 'vadgr-app.exe', 'install-receipt.json',
            'development-receipt.json', 'README-OFFLINE.txt')) {
        $path = Join-Path $installRoot $name
        $inventory += @{
            name = $name
            present = (Test-Path -LiteralPath $path -PathType Leaf)
            sha256 = $(if (Test-Path -LiteralPath $path -PathType Leaf) {
                (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() } else { $null })
        }
    }
    $missing = @($inventory | Where-Object { -not $_.present }).Count
    Add-Step -Name 'the installed payload carries its own receipts offline' `
        -Result $(if ($missing -eq 0) { 'pass' } else { 'fail' }) `
        -Detail @{ root = $installRoot; files = $inventory }

    $legal = @(Get-ChildItem -LiteralPath (Join-Path $installRoot 'legal') -File -ErrorAction SilentlyContinue |
        ForEach-Object { @{ name = $_.Name; bytes = $_.Length } })
    $terms_text = Join-Path $installRoot 'legal\TERMS.txt'
    Add-Step -Name 'the bundled legal notices are readable with no repository' `
        -Result $(if ($legal.Count -ge 6 -and (Test-Path -LiteralPath $terms_text)) { 'pass' } else { 'fail' }) `
        -Detail @{
            files = $legal
            terms_first_line = $(if (Test-Path -LiteralPath $terms_text) {
                (Get-Content -LiteralPath $terms_text -TotalCount 1) } else { $null })
        }

    Add-Step -Name 'the CLI answers from the installed package' -Result 'observed' `
        -Detail (Invoke-Capture -Command $cli -Arguments @('--version'))

    $start = Invoke-Capture -Command $cli -Arguments @('start')
    $health = Measure-Health
    $daemons = Get-DaemonProcesses
    Add-Step -Name 'the daemon starts and answers on loopback with no network' `
        -Result $(if ($health.status -eq 200 -and $daemons.Count -eq 1) { 'pass' } else { 'fail' }) `
        -Detail @{ start = $start; health = $health; daemons = $daemons }

    foreach ($round in 1, 2) {
        $stop = Invoke-Capture -Command $cli -Arguments @('stop')
        Start-Sleep -Seconds 2
        $restart = Invoke-Capture -Command $cli -Arguments @('start')
        $after = Measure-Health
        $running = Get-DaemonProcesses
        Add-Step -Name "restart $round leaves exactly one healthy daemon" `
            -Result $(if ($after.status -eq 200 -and $running.Count -eq 1) { 'pass' } else { 'fail' }) `
            -Detail @{ stop = $stop; start = $restart; health = $after; daemons = $running }
    }

    # W12, against the installed package rather than a development build. A
    # script reads a command by capturing its output, and capturing it is what
    # exposed the daemon holding its caller's pipe: the caller waited for the
    # daemon's whole life on a command that had already returned. The capture
    # runs in a job, so a return of that defect fails this step instead of
    # ending the run, and the job is the only place a pipeline is used here.
    $stopBefore = Invoke-Capture -Command $cli -Arguments @('stop')
    Start-Sleep -Seconds 2
    $capture = Start-Job -ScriptBlock {
        param($cli)
        $started = Get-Date
        $output = & $cli start 2>&1 | ForEach-Object { "$_" }
        @{
            exit_code = $LASTEXITCODE
            seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
            output = ($output -join "`n")
        }
    } -ArgumentList $cli
    $returned = $null -ne (Wait-Job -Job $capture -Timeout 120)
    $captured = $(if ($returned) { Receive-Job -Job $capture } else { $null })
    Remove-Job -Job $capture -Force
    $healthAfterCapture = Measure-Health
    Add-Step -Name 'capturing the output of start does not hold the caller open' `
        -Result $(if ($returned -and $healthAfterCapture.status -eq 200) { 'pass' } else { 'fail' }) `
        -Detail @{
            stopped_first = $stopBefore
            returned = $returned
            seconds = $(if ($captured) { $captured.seconds } else { 'over the 120 second budget' })
            exit_code = $(if ($captured) { $captured.exit_code } else { $null })
            health = $healthAfterCapture
            daemons = Get-DaemonProcesses
        }

    $console = Start-Process -FilePath $app -PassThru
    Start-Sleep -Seconds 6
    $consoleCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'Vadgr')
    $consoleWindow = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
        [System.Windows.Automation.TreeScope]::Children, $consoleCondition)
    $consoleRows = @()
    if ($consoleWindow) {
        $handle = [IntPtr]$consoleWindow.Current.NativeWindowHandle
        $owned = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
        $consoleRows = @($owned.FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition) |
            ForEach-Object { @{ name = $_.Current.Name
                                control_type = $_.Current.ControlType.ProgrammaticName
                                enabled = [bool]$_.Current.IsEnabled } })
    }
    Add-Step -Name 'the console opens on an offline machine' `
        -Result $(if ($consoleRows.Count -gt 0) { 'pass' } else { 'fail' }) `
        -Detail @{ process = $console.Id; elements = $consoleRows.Count
                   rollback_rows = @($consoleRows | Where-Object { $_.name -like '*oll back*' }) }

    Get-Process -Id $console.Id -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2

    $repairLog = Join-Path $Shared 'o1-repair.log'
    $repair = Start-Process -FilePath $setup -ArgumentList @('/log', $repairLog) -PassThru
    $modify = Get-SetupWindow
    $repairButton = Find-Control -Window $modify -Name 'Repair' -PageControl
    Invoke-Control -Element $repairButton
    $repairReached = Wait-ForText -Window $modify -AnyOf @('Vadgr was repaired.', 'Open the setup log')
    $repairTree = Read-WindowTree -Window $modify
    $repairClose = Find-Control -Window $modify -Name 'Close' -PageControl
    Add-Step -Name 'repair completes from the installed package with no network' `
        -Result $(if ($repairReached -eq 'Vadgr was repaired.') { 'pass' } else { 'fail' }) `
        -Detail @{ reached = $repairReached; tree = $repairTree }
    Invoke-Control -Element $repairClose
    Start-Sleep -Seconds 3
    $healthAfterRepair = Measure-Health
    Add-Step -Name 'the daemon is healthy after the repair' `
        -Result $(if ($healthAfterRepair.status -eq 200) { 'pass' } else { 'fail' }) `
        -Detail @{ health = $healthAfterRepair; daemons = Get-DaemonProcesses }

    $rollback = Invoke-Capture -Command $cli -Arguments @('rollback')
    Add-Step -Name 'rollback states the truth on a first installation' -Result 'observed' `
        -Detail $rollback

    Invoke-Capture -Command $cli -Arguments @('stop') | Out-Null
    Start-Sleep -Seconds 2
    $uninstallLog = Join-Path $Shared 'o1-uninstall.log'
    $uninstall = Start-Process -FilePath $setup -ArgumentList @('/log', $uninstallLog) -PassThru
    $removeWindow = Get-SetupWindow
    $uninstallButton = Find-Control -Window $removeWindow -Name 'Uninstall' -PageControl
    Invoke-Control -Element $uninstallButton
    $uninstallReached = Wait-ForText -Window $removeWindow `
        -AnyOf @('Vadgr was removed. Owner data was preserved.', 'Open the setup log')
    $uninstallTree = Read-WindowTree -Window $removeWindow
    $uninstallClose = Find-Control -Window $removeWindow -Name 'Close' -PageControl
    Invoke-Control -Element $uninstallClose
    Start-Sleep -Seconds 5
    Add-Step -Name 'uninstall completes and says what it kept' `
        -Result $(if (-not (Test-Path -LiteralPath $installRoot)) { 'pass' } else { 'fail' }) `
        -Detail @{
            install_root_present = (Test-Path -LiteralPath $installRoot)
            tree = $uninstallTree
            remaining_daemons = Get-DaemonProcesses
        }

    $profileState = @()
    foreach ($path in @((Join-Path $env:LOCALAPPDATA 'Vadgr'), (Join-Path $env:APPDATA 'Vadgr'),
            (Join-Path $env:USERPROFILE '.vadgr-cua'))) {
        $profileState += @{ path = $path; present = (Test-Path -LiteralPath $path) }
    }
    Add-Step -Name 'the owner data the uninstall promised to keep is named' -Result 'observed' `
        -Detail @{ paths = $profileState }

    Add-Step -Name 'the snapshot was offline for the whole lifecycle' -Result 'observed' `
        -Detail (Measure-Isolation)

    $failures = @($script:record.steps | Where-Object { $_.result -eq 'fail' }).Count
    Add-Step -Name 'the O1 lifecycle result' `
        -Result $(if ($failures -eq 0) { 'pass' } else { 'fail' }) `
        -Detail @{ failing_steps = $failures }
}
catch {
    Add-Step -Name 'the pass stopped on an error' -Result 'fail' -Detail @{
        message = $_.Exception.Message
        position = $_.InvocationInfo.PositionMessage
    }
}
finally {
    Save-Record
    Stop-Transcript | Out-Null
    # A marker file tells the host that the record is complete, because the
    # host cannot see inside the snapshot and a partial file looks finished.
    "done $((Get-Date).ToUniversalTime().ToString('o'))" |
        Set-Content -LiteralPath (Join-Path $Shared 'o1-done.txt') -Encoding utf8
}
