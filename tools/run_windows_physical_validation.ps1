param(
    [Parameter(Mandatory=$true)][string]$Apk,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][string]$Serial,
    [Parameter(Mandatory=$true)][string]$Evidence
)
$ErrorActionPreference='Continue'
$ProgressPreference='SilentlyContinue'
$adb=Join-Path $env:USERPROFILE 'nepa-android-tools\sdk\platform-tools\adb.exe'
$package='com.ampixa.nepakeyboard.ime.internal'
$component="$package/com.ampixa.nepakeyboard.ime.NepaInputMethodService"
$failureCount=0
$exitCode=1
$originalIme=$null
$enabledForTest=$false
if (Test-Path $Evidence) { throw "Evidence directory exists: $Evidence" }
New-Item -ItemType Directory -Path $Evidence | Out-Null
function Invoke-Adb([string[]]$Arguments) {
    $result=& $script:adb @Arguments 2>&1
    $script:adbExit=$LASTEXITCODE
    return ($result | Out-String).Trim()
}
function Run-Suite([string]$Class) {
    $out=Join-Path $script:Evidence "$Class.txt"
    $err=Join-Path $script:Evidence "$Class.stderr.txt"
    $name="$script:package/com.ampixa.nepakeyboard.ime.$Class"
    $process=Start-Process -FilePath $script:adb -ArgumentList @('-s',$script:Serial,'shell','am','instrument','-w','-r',$name) -NoNewWindow -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    if (!$process.WaitForExit(600000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Add-Content $err 'Timed out after 600 seconds'
        return $false
    }
    $process.WaitForExit()
    Add-Content $err "adb_exit_code=$($process.ExitCode)"
    $content=[IO.File]::ReadAllText($out)
    return ($content.Contains('INSTRUMENTATION_RESULT: status=ok') -and $content.Contains('INSTRUMENTATION_CODE: -1'))
}
try {
    if (!(Test-Path $Apk) -or !(Test-Path $adb)) { throw 'APK or ADB missing' }
    $actualSha=(Get-FileHash $Apk -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha -ne $ExpectedSha256) { throw "APK SHA mismatch: $actualSha" }
    "apk_sha256=$actualSha`napk=$Apk" | Set-Content (Join-Path $Evidence 'apk-sha256.txt')
    & $adb start-server *> $null
    if ($LASTEXITCODE -ne 0) { throw 'ADB server did not start' }
    $state=Invoke-Adb -Arguments @('-s',$Serial,'get-state')
    $state=($state -split '\r?\n' | Select-Object -Last 1).Trim()
    if ($state -ne 'device') { throw "Phone state is $state" }
    $model=Invoke-Adb -Arguments @('-s',$Serial,'shell','getprop','ro.product.model')
    $api=Invoke-Adb -Arguments @('-s',$Serial,'shell','getprop','ro.build.version.sdk')
    "serial=$Serial`nmodel=$model`napi=$api" | Set-Content (Join-Path $Evidence 'device-preflight.txt')
    if ($api -ne '34') { throw "Expected reference API 34 phone; got $api" }
    $battery=Invoke-Adb -Arguments @('-s',$Serial,'shell','dumpsys','battery')
    ($battery -split '\r?\n' | Where-Object { $_ -match 'level:|status:|USB powered:' }) | Set-Content (Join-Path $Evidence 'battery.txt')
    $originalIme=Invoke-Adb -Arguments @('-s',$Serial,'shell','settings','get','secure','default_input_method')
    $originalIme | Set-Content (Join-Path $Evidence 'original-default-ime.txt')
    if ($originalIme -notmatch '^com\.[A-Za-z0-9._]+/') { throw "Unrecognized original IME: $originalIme" }
    Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','list','-a','-s') | Set-Content (Join-Path $Evidence 'original-ime-list.txt')
    Invoke-Adb -Arguments @('-s',$Serial,'shell','input','keyevent','KEYCODE_WAKEUP') | Out-Null
    Invoke-Adb -Arguments @('-s',$Serial,'shell','wm','dismiss-keyguard') | Out-Null
    $install=Invoke-Adb -Arguments @('-s',$Serial,'install','--no-streaming','-r','-t',$Apk)
    $install | Set-Content (Join-Path $Evidence 'install.txt')
    if ($script:adbExit -ne 0 -or $install -notmatch 'Success') { throw "Install failed: $install" }
    $ready=$false
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        $imes=Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','list','-a','-s')
        $imes | Set-Content (Join-Path $Evidence 'available-imes.txt')
        if ($imes.Contains($component)) { $ready=$true; break }
        Start-Sleep -Seconds 2
    }
    if (!$ready) { throw 'Nepa IME did not register' }
    Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','enable',$component) | Set-Content (Join-Path $Evidence 'ime-enable.txt')
    if ($script:adbExit -ne 0) { throw 'Could not enable Nepa IME' }
    $enabledForTest=$true
    Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','set',$originalIme) | Set-Content (Join-Path $Evidence 'ime-original-before.txt')
    if ($script:adbExit -ne 0) { throw 'Could not select original IME' }
    $serviceOut=Join-Path $Evidence 'subtype-compatibility.txt'
    $serviceErr=Join-Path $Evidence 'subtype-compatibility.stderr.txt'
    $serviceName="$package/com.ampixa.nepakeyboard.ime.InternalSubtypeCompatibilityInstrumentation"
    $service=Start-Process -FilePath $adb -ArgumentList @('-s',$Serial,'shell','am','instrument','-w','-r',$serviceName) -NoNewWindow -RedirectStandardOutput $serviceOut -RedirectStandardError $serviceErr -PassThru
    $owner=$false
    for ($attempt=0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 250
        $pidResult=Invoke-Adb -Arguments @('-s',$Serial,'shell','pidof',$package)
        if ($pidResult -match '^\d+') { $owner=$true; break }
        if ($service.HasExited) { break }
    }
    if (!$owner) { throw 'Service instrumentation did not start' }
    Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','set',$component) | Set-Content (Join-Path $Evidence 'ime-rebind.txt')
    if ($script:adbExit -ne 0) { throw 'Could not select Nepa IME' }
    if (!$service.WaitForExit(600000)) {
        Stop-Process -Id $service.Id -Force -ErrorAction SilentlyContinue
        Add-Content $serviceErr 'Timed out after 600 seconds'
    }
    $service.WaitForExit()
    Add-Content $serviceErr "adb_exit_code=$($service.ExitCode)"
    $content=[IO.File]::ReadAllText($serviceOut)
    $required=@('INSTRUMENTATION_RESULT: status=ok','INSTRUMENTATION_CODE: -1','INSTRUMENTATION_RESULT: api_level=34','INSTRUMENTATION_RESULT: service_bound_picker_subtype_verified=true','INSTRUMENTATION_RESULT: service_bound_phonetic_emoji_editing_verified=true','INSTRUMENTATION_RESULT: no_personalized_learning_emoji_recents_suppressed_verified=true','INSTRUMENTATION_RESULT: service_bound_globe_subtype_verified=true','INSTRUMENTATION_RESULT: service_bound_held_delete_private_no_context_read_verified=true','INSTRUMENTATION_RESULT: private_context_read_count=0')
    $passed=$true
    foreach ($marker in $required) { if (!$content.Contains($marker)) { $passed=$false } }
    if (!$passed) { $failureCount++; Write-Output 'Service suite failed'; Invoke-Adb -Arguments @('-s',$Serial,'shell','dumpsys','input_method') | Set-Content (Join-Path $Evidence 'failure-input-method-dumpsys.txt') }
    else { Write-Output 'Service suite passed' }
    Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','set',$originalIme) | Set-Content (Join-Path $Evidence 'matrix-original-ime.txt')
    foreach ($class in @('EmojiPanelInstrumentation','TransliterationInstrumentation','ShellPreferenceInstrumentation','InternalScriptRenderingInstrumentation','InternalImeSmokeInstrumentation')) {
        $suitePassed=Run-Suite $class
        if (!$suitePassed) { $failureCount++; Write-Output "$class failed" } else { Write-Output "$class passed" }
    }
    "suite_failures=$failureCount" | Set-Content (Join-Path $Evidence 'suite-summary.txt')
    if ($failureCount -eq 0) { $exitCode=0 }
}
catch {
    $_ | Out-String | Set-Content (Join-Path $Evidence 'fatal-error.txt')
    Write-Output "Fatal: $_"
}
finally {
    if ($originalIme) {
        Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','set',$originalIme) | Set-Content (Join-Path $Evidence 'restored-default-ime-command.txt')
        if ($script:adbExit -ne 0) { $exitCode=1 }
    }
    if ($enabledForTest) {
        Invoke-Adb -Arguments @('-s',$Serial,'shell','ime','disable',$component) | Set-Content (Join-Path $Evidence 'ime-disable.txt')
        if ($script:adbExit -ne 0) { $exitCode=1 }
    }
    $restored=Invoke-Adb -Arguments @('-s',$Serial,'shell','settings','get','secure','default_input_method')
    $restored | Set-Content (Join-Path $Evidence 'restored-default-ime.txt')
    if ($restored -ne $originalIme) { $exitCode=1 }
    "remote_exit_status=$exitCode" | Set-Content (Join-Path $Evidence 'run-status.txt')
    Get-ChildItem $Evidence -File | Where-Object { $_.Name -ne 'final-sha256.txt' } | Sort-Object Name | ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(),$_.Name } | Set-Content (Join-Path $Evidence 'final-sha256.txt')
}
exit $exitCode
