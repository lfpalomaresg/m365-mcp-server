param(
  [Parameter(Mandatory=$true)][ValidateSet('get','set')][string]$Action,
  [string]$Value
)

$file = "$env:USERPROFILE\.config\env-sync\bw-session.enc"
Add-Type -AssemblyName System.Security

switch ($Action) {
  'set' {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $enc = [System.Security.Cryptography.ProtectedData]::Protect(
      $bytes, $null,
      [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    [IO.File]::WriteAllBytes($file, $enc)
    Write-Host "OK: BW_SESSION guardada en DPAPI (solo tu usuario descifra)"
  }
  'get' {
    if (-not (Test-Path $file)) { exit 1 }
    $enc = [IO.File]::ReadAllBytes($file)
    $bytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
      $enc, $null,
      [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    [Text.Encoding]::UTF8.GetString($bytes)
  }
}