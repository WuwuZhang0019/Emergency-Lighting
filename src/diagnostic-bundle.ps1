# Date: 2026-10-15. Status: implemented; invoked only by explicit diagnostic export.
param([Parameter(Mandatory = $true)][string]$SourceDirectory)
$ErrorActionPreference = 'Stop'
$stage = $null
$partial = $null
$published = $false
try {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $stage = [IO.Path]::GetFullPath($SourceDirectory).TrimEnd('\', '/')
    if (-not [IO.Directory]::Exists($stage) -or
        [IO.Path]::GetFileName($stage) -notmatch '^ELDIAG-[0-9.-]+$') {
        throw 'Invalid diagnostic staging directory.'
    }
    $zipPath = $stage + '.zip'
    $partial = $zipPath + '.partial'
    if ([IO.File]::Exists($zipPath) -or [IO.File]::Exists($partial)) {
        throw 'Diagnostic archive already exists; nothing was overwritten.'
    }
    $files = @([IO.Directory]::GetFiles($stage) | Sort-Object)
    if ($files.Count -eq 0 -or [IO.Directory]::GetDirectories($stage).Length -ne 0 -or
        -not [IO.File]::Exists([IO.Path]::Combine($stage, 'README.md'))) {
        throw 'Incomplete diagnostic staging directory.'
    }
    # The source is a dedicated snapshot, never the package root or a recursive scan.
    $stream = [IO.File]::Open($partial, [IO.FileMode]::CreateNew)
    try {
        $archive = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
        try {
            foreach ($file in $files) {
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file,
                    [IO.Path]::GetFileName($file), [IO.Compression.CompressionLevel]::Optimal) | Out-Null
            }
        } finally { $archive.Dispose() }
    } finally { $stream.Dispose() }
    # Read every archived byte and compare SHA256 before publishing the final ZIP.
    $archive = [IO.Compression.ZipFile]::OpenRead($partial)
    try {
        if ($archive.Entries.Count -ne $files.Count) { throw 'Archive entry count mismatch.' }
        foreach ($file in $files) {
            $entry = $archive.GetEntry([IO.Path]::GetFileName($file))
            if ($null -eq $entry -or $entry.Length -ne (Get-Item -LiteralPath $file).Length) {
                throw 'Archive entry length mismatch.'
            }
            $sha = [Security.Cryptography.SHA256]::Create()
            $original = [IO.File]::OpenRead($file)
            try { $expected = [Convert]::ToBase64String($sha.ComputeHash($original)) }
            finally { $original.Dispose() }
            $packed = $entry.Open()
            try { $actual = [Convert]::ToBase64String($sha.ComputeHash($packed)) }
            finally { $packed.Dispose(); $sha.Dispose() }
            if ($expected -ne $actual) { throw 'Archive entry hash mismatch.' }
        }
    } finally { $archive.Dispose() }
    [IO.File]::Move($partial, $zipPath)
    $published = $true
    # Remove only the known files after publication. No recursive deletion.
    foreach ($file in $files) { [IO.File]::Delete($file) }
    [IO.Directory]::Delete($stage, $false)
    exit 0
} catch {
    # A completed verified ZIP is still successful if snapshot cleanup was blocked.
    if ($published) { exit 0 }
    if ($stage -and [IO.Directory]::Exists($stage)) {
        [IO.File]::WriteAllText([IO.Path]::Combine($stage, 'bundle-error.txt'),
            $_.Exception.ToString(), (New-Object Text.UTF8Encoding($false)))
    }
    exit 1
}
