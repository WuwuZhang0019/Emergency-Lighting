# Date: 2026-10-12. Verify the Windows COM byte/UTF-8 boundaries; this is not CAD acceptance.
param([int]$PackageNo = 110)
$ErrorActionPreference = 'Stop'
$TaskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$SeedRoot = Join-Path $TaskRoot 'assets/default-device-library'
$CheckRoot = Join-Path $TaskRoot 'output/default-library-com-check'
$CheckRun = Join-Path $CheckRoot ([guid]::NewGuid().ToString('N'))
[void][System.IO.Directory]::CreateDirectory($CheckRun)
$FileCount = 0
$ByteCount = 0
$Digests = @{}
foreach ($SeedFile in Get-ChildItem -LiteralPath $SeedRoot -Recurse -File) {
    $Relative = $SeedFile.FullName.Substring($SeedRoot.Length + 1).Replace('\', '/')
    $Expected = [System.IO.File]::ReadAllBytes($SeedFile.FullName)
    $BinaryTarget = Join-Path $CheckRun ('asset-' + $FileCount.ToString('000') + '.bin')
    $Stream = $null
    try {
        $Stream = New-Object -ComObject 'ADODB.Stream'
        $Stream.Type = 1
        # Match all five AutoLISP slots: nil, adModeUnknown, unspecified, empty credentials.
        # PowerShell null is not a missing COM argument: use Type.Missing here.
        $Stream.Open([Type]::Missing, 0, -1, '', '')
        $Encoded = [Convert]::ToBase64String($Expected)
        for ($Offset = 0; $Offset -lt $Encoded.Length; $Offset += 192) {
            $Chunk = $Encoded.Substring($Offset, [Math]::Min(192, $Encoded.Length - $Offset))
            $Stream.Write([Convert]::FromBase64String($Chunk))
        }
        $Stream.SaveToFile($BinaryTarget, 2)
        $ExpectedHash = (Get-FileHash -LiteralPath $SeedFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ((Get-FileHash -LiteralPath $BinaryTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) {
            throw ('Binary roundtrip mismatch: ' + $Relative)
        }
        $Digests[$Relative] = $ExpectedHash
        $FileCount++
        $ByteCount += $Expected.Length
    } finally {
        if ($Stream) { $Stream.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Stream) }
    }
}
$Catalog = Join-Path $SeedRoot 'catalog.eld'
$Utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$Raw = [System.IO.File]::ReadAllBytes($Catalog)
$ExpectedText = $Utf8.GetString($Raw).TrimStart([char]0xfeff)
$BomCatalog = Join-Path $CheckRun 'catalog-bom.eld'
[System.IO.File]::WriteAllBytes($BomCatalog, ([byte[]](239, 187, 191) + $Utf8.GetBytes($ExpectedText)))
foreach ($Utf8File in ($Catalog, $BomCatalog)) {
    $Stream = New-Object -ComObject 'ADODB.Stream'
    try {
        $Stream.Type = 1
        $Stream.Open([Type]::Missing, 0, -1, '', '')
        $Stream.LoadFromFile($Utf8File)
        $Bytes = [byte[]]$Stream.Read(-1)
        $Stream.Position = 0
        $Stream.Type = 2
        $Stream.Charset = 'utf-8'
        if ($Bytes.Length -ge 3 -and $Bytes[0] -eq 239 -and $Bytes[1] -eq 187 -and $Bytes[2] -eq 191) {
            $Stream.Position = 3
        }
        if ($Stream.ReadText(-1) -cne $ExpectedText) { throw 'UTF-8 text roundtrip mismatch' }
    } finally { $Stream.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Stream) }
}
$TextTarget = Join-Path $CheckRun 'written-catalog.eld'
$Stream = New-Object -ComObject 'ADODB.Stream'
try {
    $Stream.Type = 2
    $Stream.Charset = 'utf-8'
    $Stream.Open([Type]::Missing, 0, -1, '', '')
    $Stream.WriteText($ExpectedText, 0)
    $Stream.SaveToFile($TextTarget, 1)
    if ([System.IO.File]::ReadAllText($TextTarget, $Utf8) -cne $ExpectedText) {
        throw 'Explicit WriteText roundtrip mismatch'
    }
} finally { $Stream.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Stream) }
$Report = [ordered]@{
    date = (Get-Date -Format 'yyyy-MM-dd'); status = 'windows_com_passed'; package = $PackageNo
    binary_file_count = $FileCount; binary_bytes = $ByteCount; utf8_with_and_without_bom = $true
    native_cad_status = 'pending_user_validation'
    explicit_open_argument_count = 5; explicit_write_text_argument_count = 2
    utf8_write_roundtrip = $true
    boundary = 'Real Windows ADODB calls with explicit optional slots and 192-character Base64 chunks; AutoLISP binding, DCL, CAD2020 and real drawings are not exercised'
    default_sha256 = $Digests
}
$ReportPath = Join-Path $TaskRoot ('tests/evidence/2026-10-12-default-library-com-' + $PackageNo.ToString('000') + '.json')
[System.IO.File]::WriteAllText($ReportPath, (($Report | ConvertTo-Json -Depth 4) + "`n"), $Utf8)
Write-Output ('Windows COM checks passed: ' + $FileCount + ' original files; UTF-8 with and without BOM')
