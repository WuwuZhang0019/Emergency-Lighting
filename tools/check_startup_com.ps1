# Date: 2026-10-14. Status: focused Windows COM check; native CAD timing is pending.
param([int]$PackageNo = 136)
$ErrorActionPreference = 'Stop'
$TaskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PackageName = '应急照明-' + $PackageNo.ToString('000')
$PackageRoot = Join-Path $TaskRoot ('output/' + $PackageName)
$CheckRoot = Join-Path $TaskRoot ('output/startup-' + $PackageNo.ToString('000') + '-check')
$CheckRun = Join-Path $CheckRoot ([guid]::NewGuid().ToString('N'))
[void][System.IO.Directory]::CreateDirectory($CheckRun)
$Startup = [System.IO.File]::ReadAllText((Join-Path $PackageRoot 'START-CAD2020.lsp'),
    [System.Text.Encoding]::GetEncoding(936))
# Inspect the generated immutable payloads; do not execute the LISP in PowerShell.
$Pattern = '\(EL:StartupResource ''EL:StartupWriteBase64 \(strcat root "([^"]+)"\)\s*''\(((?:"[A-Za-z0-9+/=]+"\s*)+)\)\)'
$Resources = [regex]::Matches($Startup, $Pattern)
if ($Resources.Count -lt 101) { throw 'Embedded resource payloads were not found' }
$FileCount = 0
$ByteCount = 0
$NativeMilliseconds = 0.0
$TextCount = 0
$AssetCount = 0
$CorruptionChecks = 0
foreach ($Resource in $Resources) {
    $Relative = $Resource.Groups[1].Value
    if ($Relative -notmatch '^(src|ui|assets/default-device-library)/' -or $Relative.Contains('..')) {
        throw ('Unexpected immutable resource path: ' + $Relative)
    }
    $Encoded = ([regex]::Matches($Resource.Groups[2].Value, '"([A-Za-z0-9+/=]+)"') |
        ForEach-Object { $_.Groups[1].Value }) -join ''
    $ExpectedBytes = [Convert]::FromBase64String($Encoded)
    $BinaryTarget = Join-Path $CheckRun $Relative
    $Stream = $null
    $Xml = $null
    $Node = $null
    $Clock = [Diagnostics.Stopwatch]::StartNew()
    try {
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($BinaryTarget))
        $Xml = New-Object -ComObject 'MSXML2.DOMDocument.6.0'
        $Node = $Xml.createElement('binary')
        $Node.dataType = 'bin.base64'
        $Node.text = $Encoded
        $Bytes = $Node.nodeTypedValue
        $Node.nodeTypedValue = $Bytes
        $ExpectedCanonical = $Node.text
        $Stream = New-Object -ComObject 'ADODB.Stream'
        $Stream.Type = 1
        $Stream.Open([Type]::Missing, 0, -1, '', '')
        $Stream.Write($Bytes)
        $Stream.SaveToFile($BinaryTarget, 2)
        $Stream.LoadFromFile($BinaryTarget)
        $Node.nodeTypedValue = $Stream.Read(-1)
        if ($Node.text -cne $ExpectedCanonical) { throw ('Canonical readback mismatch: ' + $Relative) }
        $Clock.Stop()
        $NativeMilliseconds += $Clock.Elapsed.TotalMilliseconds
        # Independent full byte check, outside the timed COM path.
        if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($BinaryTarget)) -cne $Encoded) {
            throw ('Independent byte mismatch: ' + $Relative)
        }
        if ($CorruptionChecks -eq 0 -and $ExpectedBytes.Length -gt 256) {
            $Damaged = [byte[]]$ExpectedBytes.Clone()
            $Damaged[$Damaged.Length - 1] = $Damaged[$Damaged.Length - 1] -bxor 1
            foreach ($BadBytes in @($Damaged, [byte[]]$ExpectedBytes[0..($ExpectedBytes.Length - 2)])) {
                [IO.File]::WriteAllBytes($BinaryTarget, $BadBytes)
                $Stream.LoadFromFile($BinaryTarget)
                $Node.nodeTypedValue = $Stream.Read(-1)
                if ($Node.text -ceq $ExpectedCanonical) { throw 'Corrupt/truncated bytes passed readback' }
                $CorruptionChecks++
            }
            [IO.File]::WriteAllBytes($BinaryTarget, $ExpectedBytes)
        }
        $FileCount++
        $ByteCount += $ExpectedBytes.Length
        if ($Relative.StartsWith('assets/')) { $AssetCount++ } else { $TextCount++ }
    } finally {
        if ($Stream) { $Stream.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Stream) }
        if ($Node) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Node) }
        if ($Xml) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Xml) }
    }
}
$Report = [ordered]@{
    date = '2026-10-14'; status = 'windows_com_passed'; package = $PackageNo
    resource_count = $FileCount; code_ui_count = $TextCount; device_resource_count = $AssetCount
    resource_bytes = $ByteCount; canonical_full_readback = $true; independent_byte_check = $true
    corruption_cases_rejected = $CorruptionChecks
    native_com_seconds = [Math]::Round($NativeMilliseconds / 1000, 3)
    native_cad_status = 'pending_user_validation'
    boundary = 'Windows MSXML/ADO only; excludes AutoLISP evaluation, Base64 chunk joining, COM release and CAD loading. This is not APPLOAD timing or proof of the two-second target.'
}
$ReportPath = Join-Path $TaskRoot ('tests/evidence/2026-10-14-startup-com-' + $PackageNo.ToString('000') + '.json')
$Utf8 = New-Object System.Text.UTF8Encoding($false, $true)
[IO.File]::WriteAllText($ReportPath, (($Report | ConvertTo-Json -Depth 4) + "`n"), $Utf8)
Write-Output ($Report | ConvertTo-Json -Depth 4)
