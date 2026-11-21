# Abre um tunel Cloudflare (URL aleatoria) para o Postiz local e religa o Postiz com essa URL.
# ANTES: crie sua conta em http://localhost:4007 e ponha DISABLE_REGISTRATION: 'true' no compose,
# senao qualquer pessoa com a URL do tunel poderia criar a primeira conta (admin).
# Parar:  .\tunnel.ps1 -Stop   (fecha o tunel e volta o Postiz para localhost)
param([switch]$Stop)
Set-Location $PSScriptRoot
$cf = "C:\Users\joaot\tools\cloudflared\cloudflared.exe"
$log = Join-Path $env:TEMP "postiz-tunnel.log"

Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
  Where-Object { $_.CommandLine -match "127.0.0.1:4007" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

if ($Stop) {
  Remove-Item Env:POSTIZ_PUBLIC_URL -ErrorAction SilentlyContinue
  docker compose up -d
  "Tunel fechado; Postiz de volta em http://localhost:4007"; return
}

Remove-Item $log -ErrorAction SilentlyContinue
Start-Process -WindowStyle Hidden -FilePath $cf -ArgumentList "tunnel","--url","http://127.0.0.1:4007","--no-autoupdate" -RedirectStandardError $log
$url = $null
for ($i = 0; $i -lt 20 -and -not $url; $i++) {
  Start-Sleep 2
  if (Test-Path $log) { $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1; if ($m) { $url = $m.Matches[0].Value } }
}
if (-not $url) { "Nao consegui a URL do tunel; veja $log"; return }

$env:POSTIZ_PUBLIC_URL = $url
docker compose -f docker-compose.yaml -f docker-compose.tunnel.yaml up -d
"Postiz no celular: $url   (a URL muda a cada execucao; espere ~1 min o Postiz reiniciar)"
