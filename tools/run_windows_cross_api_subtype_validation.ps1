param(
    [Parameter(Mandatory=$true)][string]$Apk,
    [Parameter(Mandatory=$true)][int]$Api,
    [Parameter(Mandatory=$true)][string]$Avd,
    [Parameter(Mandatory=$true)][string]$Evidence,
    [switch]$RequireNoPersonalizedLearning,
    [switch]$PreselectIme
)
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$root = Join-Path $env:USERPROFILE 'nepa-android-tools'
$adb = Join-Path $root 'sdk\platform-tools\adb.exe'
$emulator = Join-Path $root 'sdk\emulator\emulator.exe'
$serial = 'emulator-5556'
$package = 'com.ampixa.nepakeyboard.ime.internal'
$component = "$package/com.ampixa.nepakeyboard.ime.NepaInputMethodService"
$failureCount = 0
$exitCode = 1
$emuProcess = $null
if (Test-Path $Evidence) { throw "Evidence directory already exists: $Evidence" }
New-Item -ItemType Directory -Path $Evidence | Out-Null
function Invoke-Adb([string[]]$Arguments) {
    $result = & $script:adb @Arguments 2>&1
    $script:adbExit = $LASTEXITCODE
    return ($result | Out-String).Trim()
}
function Run-Suite([string]$Class, [int]$TimeoutSeconds = 600) {
    $out = Join-Path $script:Evidence "$Class.txt"
    $err = Join-Path $script:Evidence "$Class.stderr.txt"
    $name = "$script:package/com.ampixa.nepakeyboard.ime.$Class"
    $process = Start-Process -FilePath $script:adb -ArgumentList @('-s',$script:serial,'shell','am','instrument','-w','-r',$name) -NoNewWindow -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    if (!$process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Add-Content $err "Timed out after $TimeoutSeconds seconds"
        return $false
    }
    $process.WaitForExit()
    Add-Content $err "adb_exit_code=$($process.ExitCode)"
    $content = [IO.File]::ReadAllText($out)
    return ($content.Contains('INSTRUMENTATION_RESULT: status=ok') -and $content.Contains('INSTRUMENTATION_CODE: -1'))
}
try {
    if (!(Test-Path $Apk) -or !(Test-Path $adb) -or !(Test-Path $emulator)) { throw 'Missing APK or Android tools' }
    if ($Api -notin @(26,27,34,36)) { throw "Unsupported API $Api" }
    $os = Get-CimInstance Win32_OperatingSystem
    $freeRam = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    $freeDisk = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
    "free_ram_gib=$freeRam`nfree_disk_gib=$freeDisk" | Set-Content (Join-Path $Evidence 'host-preflight.txt')
    if ($freeRam -lt 6 -or $freeDisk -lt 8) { throw 'Insufficient emulator headroom' }
    $apkSha = (Get-FileHash $Apk -Algorithm SHA256).Hash.ToLowerInvariant()
    "apk_sha256=$apkSha`napk=$Apk" | Set-Content (Join-Path $Evidence 'apk-sha256.txt')
    $devices = Invoke-Adb -Arguments @('devices')
    if ($devices -match 'emulator-\d+') { throw "An emulator is already present: $devices" }
    $avds = & $emulator -list-avds 2>&1 | Out-String
    if (($avds -split '\r?\n') -notcontains $Avd) { throw "AVD missing: $Avd" }
    $guestMemory = if ($Api -ge 36) { '4096' } else { '2048' }
    $guestCores = if ($Api -ge 36) { '4' } else { '2' }
    $args = @('-avd',$Avd,'-port','5556','-cores',$guestCores,'-memory',$guestMemory,'-gpu','swiftshader','-no-window','-no-audio','-no-boot-anim','-no-snapshot','-wipe-data')
    $emuProcess = Start-Process -FilePath $emulator -ArgumentList $args -NoNewWindow -RedirectStandardOutput (Join-Path $Evidence 'emulator.stdout.log') -RedirectStandardError (Join-Path $Evidence 'emulator.stderr.log') -PassThru
    $ready = $false
    for ($attempt=0; $attempt -lt 180; $attempt++) {
        Start-Sleep -Seconds 5
        $boot = Invoke-Adb -Arguments @('-s',$serial,'shell','getprop','sys.boot_completed')
        if ($boot -eq '1') { $ready = $true; break }
    }
    if (!$ready) { throw "API $Api emulator did not boot" }
    $actualApi = Invoke-Adb -Arguments @('-s',$serial,'shell','getprop','ro.build.version.sdk')
    $actualApi | Set-Content (Join-Path $Evidence 'api-level.txt')
    if ($actualApi -ne "$Api") { throw "Wrong API: $actualApi" }
    Write-Output "API $Api booted"
    Invoke-Adb -Arguments @('-s',$serial,'shell','input','keyevent','KEYCODE_WAKEUP') | Out-Null
    Invoke-Adb -Arguments @('-s',$serial,'shell','wm','dismiss-keyguard') | Out-Null
    $install = Invoke-Adb -Arguments @('-s',$serial,'install','--no-streaming','-r','-t',$Apk)
    $install | Set-Content (Join-Path $Evidence 'install.txt')
    if ($script:adbExit -ne 0 -or $install -notmatch 'Success') { throw "APK install failed: $install" }
    $imeReady = $false
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        $imes = Invoke-Adb -Arguments @('-s',$serial,'shell','ime','list','-a','-s')
        $imes | Set-Content (Join-Path $Evidence 'available-imes.txt')
        if ($imes.Contains($component)) { $imeReady = $true; break }
        Start-Sleep -Seconds 2
    }
    if (!$imeReady) { throw 'Installed IME is absent from platform list after 120 seconds' }
    $alternate = (($imes -split '\r?\n') | Where-Object { $_ -match '^(com.google.android.inputmethod.latin|com.android.inputmethod.latin)/' } | Select-Object -First 1).Trim()
    if (!$alternate) { throw 'No system Latin IME found' }
    Invoke-Adb -Arguments @('-s',$serial,'shell','ime','enable',$component) | Set-Content (Join-Path $Evidence 'ime-enable.txt')
    if ($script:adbExit -ne 0) { throw 'Could not enable IME' }
    if ($PreselectIme) {
        Invoke-Adb -Arguments @('-s',$serial,'shell','ime','set',$component) | Set-Content (Join-Path $Evidence 'ime-preselect.txt')
        if ($script:adbExit -ne 0) { throw 'Could not preselect Nepa IME' }
        $selected = Invoke-Adb -Arguments @('-s',$serial,'shell','settings','get','secure','default_input_method')
        $selected | Set-Content (Join-Path $Evidence 'preselected-default-ime.txt')
        if ($selected -ne $component) { throw "Default IME is $selected" }
    } else {
        Invoke-Adb -Arguments @('-s',$serial,'shell','ime','set',$alternate) | Set-Content (Join-Path $Evidence 'ime-alternate.txt')
        if ($script:adbExit -ne 0) { throw 'Could not select alternate IME' }
    }
    $serviceClass = 'InternalSubtypeCompatibilityInstrumentation'
    $serviceOut = Join-Path $Evidence 'subtype-compatibility.txt'
    $serviceErr = Join-Path $Evidence 'subtype-compatibility.stderr.txt'
    $serviceName = "$package/com.ampixa.nepakeyboard.ime.$serviceClass"
    $service = Start-Process -FilePath $adb -ArgumentList @('-s',$serial,'shell','am','instrument','-w','-r',$serviceName) -NoNewWindow -RedirectStandardOutput $serviceOut -RedirectStandardError $serviceErr -PassThru
    $owner = $false
    for ($attempt=0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 250
        $pidResult = Invoke-Adb -Arguments @('-s',$serial,'shell','pidof',$package)
        if ($pidResult -match '^\d+') { $owner = $true; break }
        if ($service.HasExited) { break }
    }
    if (!$owner) { throw 'Service instrumentation did not acquire the app process' }
    if (!$PreselectIme) {
        Invoke-Adb -Arguments @('-s',$serial,'shell','ime','set',$component) | Set-Content (Join-Path $Evidence 'ime-rebind.txt')
        if ($script:adbExit -ne 0) { throw 'Could not rebind Nepa IME' }
    }
    if (!$service.WaitForExit(600000)) {
        Stop-Process -Id $service.Id -Force -ErrorAction SilentlyContinue
        Add-Content $serviceErr 'Timed out after 600 seconds'
    }
    $service.WaitForExit()
    Add-Content $serviceErr "adb_exit_code=$($service.ExitCode)"
    $serviceText = [IO.File]::ReadAllText($serviceOut)
    $required = @('INSTRUMENTATION_RESULT: status=ok','INSTRUMENTATION_CODE: -1',"INSTRUMENTATION_RESULT: api_level=$Api",'INSTRUMENTATION_RESULT: service_bound_picker_subtype_verified=true','INSTRUMENTATION_RESULT: service_bound_phonetic_emoji_editing_verified=true','INSTRUMENTATION_RESULT: private_emoji_recents_suppressed_verified=true','INSTRUMENTATION_RESULT: service_bound_globe_subtype_verified=true','INSTRUMENTATION_RESULT: platform_subtype_confirmation_verified=true','INSTRUMENTATION_RESULT: service_bound_held_delete_private_no_context_read_verified=true','INSTRUMENTATION_RESULT: private_context_read_count=0')
    if ($RequireNoPersonalizedLearning) { $required += 'INSTRUMENTATION_RESULT: no_personalized_learning_emoji_recents_suppressed_verified=true' }
    $servicePass = $true
    foreach ($marker in $required) { if (!$serviceText.Contains($marker)) { $servicePass = $false } }
    if (!$servicePass) { $failureCount++; Write-Output 'Service suite failed'; Invoke-Adb -Arguments @('-s',$serial,'shell','dumpsys','input_method') | Set-Content (Join-Path $Evidence 'failure-input-method-dumpsys.txt') }
    else { Write-Output 'Service suite passed' }
    Invoke-Adb -Arguments @('-s',$serial,'shell','ime','set',$alternate) | Set-Content (Join-Path $Evidence 'matrix-alternate-ime.txt')
    foreach ($class in @('EmojiPanelInstrumentation','TransliterationInstrumentation','ShellPreferenceInstrumentation','InternalScriptRenderingInstrumentation','InternalImeSmokeInstrumentation')) {
        $passed = Run-Suite $class
        if (!$passed) { $failureCount++; Write-Output "$class failed" } else { Write-Output "$class passed" }
    }
    "suite_failures=$failureCount" | Set-Content (Join-Path $Evidence 'suite-summary.txt')
    if ($failureCount -eq 0) { $exitCode = 0 }
    else { Invoke-Adb -Arguments @('-s',$serial,'logcat','-d','-v','threadtime') | Set-Content (Join-Path $Evidence 'failure-logcat.txt') }
}
catch {
    $_ | Out-String | Set-Content (Join-Path $Evidence 'fatal-error.txt')
    Write-Output "Fatal: $_"
    try { Invoke-Adb -Arguments @('-s',$serial,'logcat','-d','-v','threadtime') | Set-Content (Join-Path $Evidence 'failure-logcat.txt') } catch {}
}
finally {
    try { Invoke-Adb -Arguments @('-s',$serial,'emu','kill') | Out-Null } catch {}
    if ($emuProcess -and !$emuProcess.HasExited) {
        if (!$emuProcess.WaitForExit(30000)) { try { Stop-Process -Id $emuProcess.Id -Force } catch {} }
    }
    Start-Sleep -Seconds 5
    $after = Invoke-Adb -Arguments @('devices')
    $after | Set-Content (Join-Path $Evidence 'post-cleanup-adb.txt')
    if ($after -match 'emulator-5556') { $exitCode = 1 }
    "remote_exit_status=$exitCode" | Set-Content (Join-Path $Evidence 'run-status.txt')
    $manifest = @()
    foreach ($file in (Get-ChildItem $Evidence -File | Where-Object { $_.Name -ne 'final-sha256.txt' } | Sort-Object Name)) {
        $hash = $null
        for ($attempt=0; $attempt -lt 15; $attempt++) {
            try { $hash = (Get-FileHash $file.FullName -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant(); break }
            catch { Start-Sleep -Seconds 1 }
        }
        if (!$hash) { $exitCode = 1; continue }
        $manifest += "$hash  $($file.Name)"
    }
    $manifest | Set-Content (Join-Path $Evidence 'final-sha256.txt')
}
exit $exitCode
