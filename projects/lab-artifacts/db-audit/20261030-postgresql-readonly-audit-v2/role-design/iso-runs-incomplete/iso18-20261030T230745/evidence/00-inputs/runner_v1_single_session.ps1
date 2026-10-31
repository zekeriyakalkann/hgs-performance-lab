param([Parameter(Mandatory = $true)][string]$ConfirmFile,
      [Parameter(Mandatory = $true)][string]$TranscriptFile,
      [Parameter(Mandatory = $true)][string]$ConsoleLog)
# =============================================================================
# HGS2 V1 - tek oturumlu calistirici (runbook 0.7: "Tum asamalar ayni pencerede, sirayla")
# Kaynak: role-design\EXECUTION_RUNBOOK_V1.md powershell bloklari, AYNEN ve AYNI SIRAYLA.
# Runbook'ta OLMAYAN satirlar yalnizca "# [Axx]" ile isaretli EK bloklardadir:
#   [A0]   Asama 0 "Beklenen cikti" tablosunun kapiya donusturulmesi (yalnizca okuma)
#   [LC]   Her runbook blogundan sonra canli servis + 5432 dinleyici kontrol noktasi (yalnizca okuma)
#   [A2.1] Calistirici kopyasi, blok kaynak hash'leri ve arac surumleri kanita
#   [A2.5] / [A10.1] port/PID kanit dosyalari
#   [A10.4] Read-Host (etkilesimsiz surecte calismaz) yerine onay dosyasi; kapi hatasinda erteleme kaydi
#   [A-TS] Transcript ve konsol gunlugunde test parolasi / ozel anahtar taramasi
#   [A-ERR] Herhangi bir GUARD/hata: DUR, kayit, yalnizca test kumesini durdur
# Gevsetilen veya cikarilan runbook kapisi YOKTUR.
# =============================================================================
if (Test-Path -LiteralPath $ConfirmFile) { throw "GUARD: onay dosyasi onceden var (bayat onay kabul edilmez): $ConfirmFile" }
Start-Transcript -LiteralPath $TranscriptFile | Out-Null
$__failed = $false
try {


# ======== RUNBOOK BLOK 0 (S0) - EXECUTION_RUNBOOK_V1.md L95-L115 - AYNEN ========
'===== S0 ====='

$PSVersionTable.PSVersion.ToString()
$Host.Name
$Base = 'C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\db-audit\20261030-postgresql-readonly-audit-v2'
Set-Location -LiteralPath $Base

$IntegrityFiles = @(
    (Join-Path $Base 'asama3-final\postgresql_readonly_audit_v2.sql'),
    (Join-Path $Base 'role-design\ISOLATED_CLUSTER_TEST_PLAN.md'),
    (Join-Path $Base 'role-design\AUDIT_ROLE_PRIVILEGE_MATRIX.md'))
$Hash0 = @{}
foreach ($f in $IntegrityFiles) { $Hash0[$f] = (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLower() }
$Hash0.GetEnumerator() | Format-Table -AutoSize Value, Name

& 'C:\Program Files\PostgreSQL\18\bin\postgres.exe' --version
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' --version
& py -3.13 --version
& 'C:\Program Files\Git\ucrt64\bin\openssl.exe' version
netsh int ipv4 show excludedportrange protocol=tcp
netsh int ipv6 show excludedportrange protocol=tcp
Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'hgs2-iso')
Test-Path -LiteralPath (Join-Path $Base 'role-design\iso-runs')

# [A0] ---- Asama 0 beklenen degerleri -> kapilar (ek, yalnizca okuma) ----
function __G0([bool]$c, [string]$m) { if (-not $c) { throw "GUARD: S0 $m" } }
$__exp = @{}
$__exp[(Join-Path $Base 'asama3-final\postgresql_readonly_audit_v2.sql')] = '5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b'
$__exp[(Join-Path $Base 'role-design\ISOLATED_CLUSTER_TEST_PLAN.md')]    = '398889d315187e965bb555f2fa72ba92f7bfcb341d5cca50dfdaa96a822cf389'
$__exp[(Join-Path $Base 'role-design\AUDIT_ROLE_PRIVILEGE_MATRIX.md')]   = '5733d45fa265309089a417c2e2653d2564f63783df854b78316447c11694bd7b'
__G0 (($PSVersionTable.PSVersion.Major -eq 5) -and ($PSVersionTable.PSVersion.Minor -eq 1)) 'PSVersion 5.1 degil'
__G0 ($Host.Name -eq 'ConsoleHost') 'Host ConsoleHost degil'
foreach ($f in $IntegrityFiles) { __G0 ($Hash0[$f] -eq $__exp[$f]) "hash beklenen degil: $f" }
$__tool = New-Object System.Collections.Generic.List[string]
$__tool.Add('PSVersion: ' + $PSVersionTable.PSVersion.ToString()); $__tool.Add('Host: ' + $Host.Name)
$__tool.Add('Kullanici: ' + $env:USERDOMAIN + '\' + $env:USERNAME)
foreach ($x in 'postgres', 'psql', 'initdb', 'pg_ctl', 'pg_controldata') {
    $v = [string](& "C:\Program Files\PostgreSQL\18\bin\$x.exe" --version)
    __G0 ($v -match '\(PostgreSQL\) 18\.6$') "$x surumu 18.6 degil: $v"
    $__tool.Add("$x.exe: $v")
}
$v = [string](& py -3.13 --version); __G0 ($v -match '^Python 3\.13\.\d+$') "py -3.13 yok: $v"; $__tool.Add("py -3.13: $v")
$v = [string](& 'C:\Program Files\Git\ucrt64\bin\openssl.exe' version); __G0 ($v -match '^OpenSSL (1\.1\.1|3\.)') "openssl: $v"; $__tool.Add("openssl: $v")
foreach ($proto in 'ipv4', 'ipv6') {
    foreach ($l in @(netsh int $proto show excludedportrange protocol=tcp)) {
        if ($l -match '^\s*(\d+)\s+(\d+)') { __G0 (-not (([int]$Matches[1] -le 55438) -and (55438 -le [int]$Matches[2]))) "55438 $proto ayrilmis aralikta: $l" }
    }
}
$__tool.Add('excludedportrange ipv4/ipv6: 55438 kapsanmiyor')
$__tool.Add('runbook sha256: ' + (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Base 'role-design\EXECUTION_RUNBOOK_V1.md')).Hash.ToLower())
$__tool.Add('validator sha256: ' + (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Base 'asama3-final\tools\validate_audit_result.py')).Hash.ToLower())
$__tool
'S0 kapilari: PASS'


# ======== RUNBOOK BLOK 1 (S1) - EXECUTION_RUNBOOK_V1.md L157-L225 - AYNEN ========
'===== S1 ====='

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- Sabitler ---
$PgBin     = 'C:\Program Files\PostgreSQL\18\bin'
$LiveData  = 'C:\Program Files\PostgreSQL\18\data'     # DOKUNULMAZ: yalnizca kapilarda karsilastirma
$LiveSvc   = 'postgresql-x64-18'
$LivePort  = 5432
$TestPort  = 55438
$RunId     = 'iso18-' + (Get-Date -Format 'yyyyMMddTHHmmss')
$Root      = Join-Path $env:LOCALAPPDATA "hgs2-iso\$RunId"
$Data      = Join-Path $Root 'data'
$LogFile   = Join-Path $Root 'log\postgres.log'
$Certs     = Join-Path $Root 'certs'
$Cfg       = Join-Path $Root 'cfg'
$Evidence  = Join-Path $Root 'evidence'
$OpenSsl   = 'C:\Program Files\Git\ucrt64\bin\openssl.exe'
$Base      = 'C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\db-audit\20261030-postgresql-readonly-audit-v2'
$AuditSql  = Join-Path $Base 'asama3-final\postgresql_readonly_audit_v2.sql'
$AuditSha  = '5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b'
$Validator = Join-Path $Base 'asama3-final\tools\validate_audit_result.py'

function Assert-Guard([bool]$Cond, [string]$Msg) { if (-not $Cond) { throw "GUARD: $Msg" } }
function Assert-UnderRoot([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    Assert-Guard ($full.StartsWith([IO.Path]::GetFullPath($Root) + '\', [StringComparison]::OrdinalIgnoreCase)) "yol test koku disinda: $full"
    Assert-Guard (-not $full.StartsWith([IO.Path]::GetFullPath($LiveData), [StringComparison]::OrdinalIgnoreCase)) "yol canli veri dizini: $full"
    Assert-Guard (-not $full.StartsWith('C:\Program Files', [StringComparison]::OrdinalIgnoreCase)) "yol Program Files altinda: $full"
}

# G1: yonetici olmayan oturum
$me = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
Assert-Guard (-not $me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'elevated olmayan PowerShell gerekli'
# G2: port
Assert-Guard ($TestPort -ne $LivePort) 'test portu 5432 olamaz'
Assert-Guard ($null -eq (Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue)) "port $TestPort dinleniyor"
# G3: yollar
Assert-Guard (-not (Test-Path -LiteralPath $Root)) 'test koku zaten var'
Assert-UnderRoot $Data
# G4: ikili surum ve denetim dosyasi butunlugu
Assert-Guard ((& "$PgBin\postgres.exe" --version) -match '\b18\.6\b') 'ikili surum 18.6 degil'
Assert-Guard ((Get-FileHash -Algorithm SHA256 -LiteralPath $AuditSql).Hash.ToLower() -eq $AuditSha) 'denetim SQL hash uyusmuyor'
Assert-Guard (Test-Path -LiteralPath $OpenSsl) 'openssl bulunamadi'
# G5: canli servis anlik goruntusu (yalnizca okuma; veritabanina baglanmaz)
function Get-LiveSnapshot {
    $s = Get-CimInstance Win32_Service -Filter "Name='$LiveSvc'"
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($s.ProcessId)"
    [pscustomobject]@{ State = $s.State; Pid = $s.ProcessId; Created = $p.CreationDate.ToString('o'); PathName = $s.PathName }
}
$Live0 = Get-LiveSnapshot
function Assert-LiveUnchanged {
    $now = Get-LiveSnapshot
    Assert-Guard (($now.State -eq $Live0.State) -and ($now.Pid -eq $Live0.Pid) -and ($now.Created -eq $Live0.Created) -and ($now.PathName -eq $Live0.PathName)) 'CANLI SERVIS DEGISTI - DUR, MUDAHALE ETME, RAPORLA'
}

# --- V1 eki (yalnizca okuma): 5432 dinleyicileri ve ek kapilar ---
function Get-Live5432 {
    @(Get-NetTCPConnection -LocalPort $LivePort -State Listen -ErrorAction SilentlyContinue |
      Sort-Object LocalAddress |
      ForEach-Object { '{0}:{1} pid={2}' -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess }) -join '; '
}
$Live5432_0 = Get-Live5432
Assert-Guard ($Live0.State -eq 'Running') 'canli servis Running degil - DUR'
Assert-Guard ($Live0.PathName -like "*$LiveData*") 'canli servis yolu beklenen data dizinini gostermiyor - DUR'
Assert-Guard ($Live5432_0 -ne '') 'canli 5432 dinleyicisi yok - DUR'
$Live0 | Format-List
"5432 dinleyicileri: $Live5432_0"
"RunId: $RunId"
"Test koku: $Root"

# [LC] ---- canli servis + 5432 dinleyici kontrol noktasi (ek, yalnizca okuma) ----
function Save-LiveCheckpoint([string]$Label) {
    Assert-LiveUnchanged
    $l = Get-Live5432
    Assert-Guard ($l -eq $Live5432_0) "5432 DINLEYICILERI DEGISTI ($Label) - DUR, MUDAHALE ETME, RAPORLA"
    $line = '{0} {1} live_service=unchanged(State={2} Pid={3}) 5432=unchanged({4})' -f (Get-Date -Format 'o'), $Label, $Live0.State, $Live0.Pid, $l
    $__av = Get-Variable -Name Archive -ValueOnly -ErrorAction SilentlyContinue
    if ($__av -and (Test-Path -LiteralPath (Join-Path $__av 'evidence'))) { Add-Content -LiteralPath (Join-Path $__av 'evidence\live-checks.txt') -Encoding ASCII -Value $line }
    elseif (Test-Path -LiteralPath $Evidence) { Add-Content -LiteralPath (Join-Path $Evidence 'live-checks.txt') -Encoding ASCII -Value $line }
    $line
}
Save-LiveCheckpoint 'after-S1'


# ======== RUNBOOK BLOK 2 (S2.1) - EXECUTION_RUNBOOK_V1.md L261-L304 - AYNEN ========
'===== S2.1 ====='

foreach ($v in 'PGHOST','PGHOSTADDR','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','PGPASSFILE','PGSERVICE',
               'PGSERVICEFILE','PGSYSCONFDIR','PGOPTIONS','PGSSLMODE','PGSSLROOTCERT','PGAPPNAME',
               'PGCLIENTENCODING','PGDATA','PSQLRC','PGCHANNELBINDING','PGTARGETSESSIONATTRS') {
    Remove-Item -LiteralPath "Env:$v" -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $Root, (Split-Path $LogFile), $Certs, $Cfg, $Evidence | Out-Null
# Test kokunu yalnizca gecerli kullaniciya ac
& icacls $Root /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(OI)(CI)F" | Out-Null
Assert-Guard ($LASTEXITCODE -eq 0) 'icacls basarisiz'          # V1 eki
$env:PGSYSCONFDIR  = $Cfg
$env:PGSERVICEFILE = Join-Path $Cfg 'none.conf'
$env:PGPASSFILE    = Join-Path $Cfg 'pgpass.conf'
$env:PSQLRC        = Join-Path $Cfg 'none.psqlrc'
$env:PGCONNECT_TIMEOUT = '5'

function New-TestSecret { $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ([Convert]::ToBase64String($b)) -replace '[+/=]', 'x' }
function Add-TestPgpass([string]$Role, [string]$Secret) {
    # Port kapsamli: 5432'ye karsi asla kullanilmaz. Parola yalnizca [A-Za-z0-9x] icerir (kacis gerekmez).
    Add-Content -LiteralPath $env:PGPASSFILE -Value "*:${TestPort}:*:${Role}:$Secret" -Encoding ASCII
}

# --- V1 yardimcilari ---
$Inputs = Join-Path $Evidence '00-inputs'
New-Item -ItemType Directory -Force -Path $Inputs | Out-Null
$TestSecrets = @{}
function Write-TestFile([string]$Path, [string]$Text) {
    Assert-UnderRoot $Path
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))   # BOM yok (psql icin zorunlu)
}
function Write-Stage([string]$Stage, [string]$Result) {
    Add-Content -LiteralPath (Join-Path $Evidence 'stage-results.txt') -Encoding ASCII -Value ('{0} {1} {2}' -f (Get-Date -Format 'o'), $Stage, $Result)
}
function Get-EvidenceText([string]$Id, [string]$Name) {
    $f = Join-Path (Join-Path $Evidence $Id) $Name
    if (Test-Path -LiteralPath $f) { [string](Get-Content -LiteralPath $f -Raw) } else { '' }
}

# --- Asama 1 kaydinin kanita yazilmasi ---
$Live0 | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Evidence 'live-start.json') -Encoding ASCII
Set-Content -LiteralPath (Join-Path $Evidence 'live-start-5432.txt') -Encoding ASCII -Value $Live5432_0
$Hash0.GetEnumerator() | ForEach-Object { '{0}  {1}' -f $_.Value, $_.Key } |
    Set-Content -LiteralPath (Join-Path $Evidence 'integrity-start.sha256') -Encoding ASCII
Write-Stage 'S1-live-snapshot' 'RECORDED'
Get-ChildItem -LiteralPath $Root | Format-Table Name

# [A2.1] ---- calistirici, blok kaynaklari ve arac surumleri kanita (ek) ----
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $Inputs 'runner_v1_single_session.ps1')
Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $PSCommandPath) 'runner_provenance.txt') -Destination (Join-Path $Inputs 'runner_provenance.txt')
Write-TestFile (Join-Path $Inputs 'toolchain.txt') (($__tool -join "`n") + "`n")


Save-LiveCheckpoint 'after-S2.1'   # [LC]


# ======== RUNBOOK BLOK 3 (S2.2) - EXECUTION_RUNBOOK_V1.md L316-L333 - AYNEN ========
'===== S2.2 ====='

Assert-Guard (-not (Test-Path -LiteralPath $Data)) 'test data dizini zaten var'      # V1 eki
$SuperPw = New-TestSecret
$TestSecrets['postgres'] = $SuperPw                                                    # V1 eki (bitis taramasi icin)
$PwFile  = Join-Path $Cfg 'initdb.pw'
Assert-UnderRoot $PwFile                                                               # V1 eki
[IO.File]::WriteAllText($PwFile, $SuperPw)          # BOM ve satir sonu yok
& "$PgBin\initdb.exe" -D $Data -U postgres --pwfile=$PwFile --auth-host=scram-sha-256 --auth-local=scram-sha-256 -E UTF8 --locale=C
$rc = $LASTEXITCODE
Remove-Item -LiteralPath $PwFile -Force             # YIKICI (sinirli): yalnizca test kokundeki gecici parola dosyasi
Assert-Guard ($rc -eq 0) "initdb cikis $rc"
Add-TestPgpass 'postgres' $SuperPw

# Sistem kimligi: bagimsiz kanal (pg_controldata), plan 5.7
$SysId = ((& "$PgBin\pg_controldata.exe" -D $Data) | Select-String 'Database system identifier:\s+(\d+)').Matches[0].Groups[1].Value
Assert-Guard ($SysId -match '^\d+$') 'system identifier okunamadi'                    # V1 eki
Set-Content -LiteralPath (Join-Path $Evidence 'test-system-identifier.txt') -Encoding ASCII -Value $SysId
Write-Stage 'S2.2-initdb' 'PASS'
"SysId: $SysId"

Save-LiveCheckpoint 'after-S2.2'   # [LC]


# ======== RUNBOOK BLOK 4 (S2.3) - EXECUTION_RUNBOOK_V1.md L346-L359 - AYNEN ========
'===== S2.3 ====='

$ext = Join-Path $Certs 'server_ext.cnf'
Set-Content -LiteralPath $ext -Encoding ASCII -Value @(
  'subjectAltName=DNS:hgs2-test.local,IP:127.0.0.1,IP:::1',
  'basicConstraints=CA:FALSE',
  'keyUsage=digitalSignature,keyEncipherment',
  'extendedKeyUsage=serverAuth')
& $OpenSsl req -x509 -newkey rsa:3072 -nodes -days 7 -subj '/CN=hgs2-iso-test-CA' -keyout "$Certs\ca.key" -out "$Certs\ca.crt" -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
Assert-Guard ($LASTEXITCODE -eq 0) 'openssl CA'
& $OpenSsl req -newkey rsa:3072 -nodes -subj '/CN=hgs2-test.local' -keyout "$Certs\server.key" -out "$Certs\server.csr"
Assert-Guard ($LASTEXITCODE -eq 0) 'openssl CSR'
& $OpenSsl x509 -req -in "$Certs\server.csr" -CA "$Certs\ca.crt" -CAkey "$Certs\ca.key" -CAcreateserial -days 7 -extfile $ext -out "$Certs\server.crt"
Assert-Guard ($LASTEXITCODE -eq 0) 'openssl x509'
Get-ChildItem -LiteralPath $Certs | Format-Table Name, Length
Write-Stage 'S2.3-certs' 'PASS'

Save-LiveCheckpoint 'after-S2.3'   # [LC]


# ======== RUNBOOK BLOK 5 (S2.4) - EXECUTION_RUNBOOK_V1.md L369-L390 - AYNEN ========
'===== S2.4 ====='

Assert-UnderRoot (Join-Path $Data 'postgresql.conf')                                    # V1 eki
$crt = (Join-Path $Certs 'server.crt') -replace '\\','/'
$key = (Join-Path $Certs 'server.key') -replace '\\','/'
$conf = @"

# --- HGS2 isolated test cluster ($RunId) - gecici, izole ---
port = $TestPort
listen_addresses = '127.0.0.1,::1'
unix_socket_directories = ''
cluster_name = 'hgs2iso18'
max_connections = 20
password_encryption = 'scram-sha-256'
ssl = on
ssl_cert_file = '$crt'
ssl_key_file = '$key'
log_connections = on
log_disconnections = on
log_statement = 'all'
log_line_prefix = '%m [%p] %e user=%u db=%d host=%h app=%a '
"@
Add-Content -LiteralPath (Join-Path $Data 'postgresql.conf') -Value $conf -Encoding ASCII
Write-Stage 'S2.4-conf' 'PASS'

Save-LiveCheckpoint 'after-S2.4'   # [LC]


# ======== RUNBOOK BLOK 6 (S2.5) - EXECUTION_RUNBOOK_V1.md L398-L460 - AYNEN ========
'===== S2.5 ====='

$Hba = @{}
$Hba['A'] = @(   # TLS istege bagli (AUDIT_ROLE_PRIVILEGE_MATRIX 10.1)
 'host    hgs2_perftest_db  hgs2_audit  127.0.0.1/32  scram-sha-256',
 'host    hgs2_perftest_db  hgs2_audit  ::1/128       scram-sha-256',
 'host    all               hgs2_audit  all           reject',
 'host    replication       hgs2_audit  all           reject',
 'local   all               hgs2_audit                reject',
 'local   replication       hgs2_audit                reject',
 'host    all               all         127.0.0.1/32  scram-sha-256',
 'host    all               all         ::1/128       scram-sha-256')
function Set-TestHba([string]$Variant) {
    $target = Join-Path $Data 'pg_hba.conf'; Assert-UnderRoot $target
    Set-Content -LiteralPath $target -Encoding ASCII -Value (@("# HGS2 iso test - variant $Variant") + $Hba[$Variant])
}
function Start-TestCluster { Assert-UnderRoot $Data; & "$PgBin\pg_ctl.exe" -D $Data -l $LogFile -w -t 60 start; Assert-Guard ($LASTEXITCODE -eq 0) 'pg_ctl start'; Assert-LiveUnchanged }
function Stop-TestCluster  { Assert-UnderRoot $Data; & "$PgBin\pg_ctl.exe" -D $Data -m fast -w stop;  Assert-Guard ($LASTEXITCODE -eq 0) 'pg_ctl stop';  Assert-LiveUnchanged }

Set-TestHba 'A'
Start-TestCluster
# Ayri surec kaniti: komut satirinda test data directory gecen postgres.exe var, canli servis PID'i ayni
Assert-Guard (@(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count -ge 1) 'test postmaster bulunamadi'

# --- Plan 5.7: korumali psql calistirici ---
function ConvertTo-ArgString([string[]]$A) { ($A | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' ' }
function Assert-TestConn([string]$Conn) {
    Assert-Guard ($Conn -match "(^|\s)port=$TestPort(\s|$)") 'yalnizca test portu'
    Assert-Guard ($Conn -notmatch '(^|\s)port=5432(\s|$)') '5432 yasak'
    Assert-Guard ($Conn -match '(^|\s)(host|hostaddr)=(127\.0\.0\.1|::1)(\s|$)') 'yalnizca loopback hostaddr/host'
}
# Tek komut; stdout/stderr ayri dosyalara (PS 5.1 yerel stderr yonlendirmesi icerigi bozdugu icin Start-Process)
function Invoke-TestPsql([string]$Id, [string]$Conn, [string[]]$Extra) {
    Assert-TestConn $Conn
    $d = Join-Path $Evidence $Id; New-Item -ItemType Directory -Force -Path $d | Out-Null
    $argv = @('-X', '-v', 'ON_ERROR_STOP=1', '-d', $Conn) + $Extra
    Set-Content -LiteralPath "$d\args.txt" -Value (ConvertTo-ArgString $argv) -Encoding UTF8
    $p = Start-Process -FilePath "$PgBin\psql.exe" -ArgumentList (ConvertTo-ArgString $argv) -NoNewWindow -Wait -PassThru `
         -RedirectStandardOutput "$d\stdout.txt" -RedirectStandardError "$d\stderr.txt"
    Set-Content -LiteralPath "$d\exit.txt" -Value $p.ExitCode -Encoding ASCII
    Assert-LiveUnchanged
    return $p.ExitCode
}

# --- V1: kume kimligi ve arguman tirnaklama dogrulamasi (plan R-N7) ---
$SuperConnPg   = "host=127.0.0.1 port=$TestPort dbname=postgres user=postgres sslmode=require"
$rc  = Invoke-TestPsql 'S2-identity' $SuperConnPg @('-w', '-At', '-c', "select version(), current_setting('port'), current_setting('cluster_name'), current_setting('ssl'), current_setting('data_directory')")
$out = Get-EvidenceText 'S2-identity' 'stdout.txt'
$out
Get-Content -LiteralPath (Join-Path $Evidence 'S2-identity\args.txt')
Assert-Guard ($rc -eq 0) "S2-identity psql cikis $rc"
Assert-Guard ($out -match 'PostgreSQL 18\.6\b') 'sunucu 18.6 degil'
Assert-Guard ($out -match '\|55438\|hgs2iso18\|on\|') 'port / cluster_name / ssl beklenen degil'
Assert-Guard ($out -match 'hgs2-iso') 'data_directory test kokunu gostermiyor'

# --- V1: 55438 dinleyicilerinin yalnizca test postmaster'a ait oldugu ---
$listen = @(Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue)
$listen | Format-Table LocalAddress, LocalPort, OwningProcess
Assert-Guard ($listen.Count -ge 1) "port $TestPort dinlenmiyor"
foreach ($l in $listen) {
    $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$($l.OwningProcess)").CommandLine
    Assert-Guard ($cl -like "*$Data*") "55438 dinleyicisi test postmaster degil (pid $($l.OwningProcess))"
}
Get-Content -LiteralPath $LogFile -Tail 15
Write-Stage 'S2-cluster' 'PASS'

# [A2.5] ---- 55438 port/PID kaniti (ek) ----
$__pp = foreach ($l in $listen) {
    $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$($l.OwningProcess)").CommandLine
    '{0}:{1} pid={2} test_postmaster={3}' -f $l.LocalAddress, $l.LocalPort, $l.OwningProcess, ($cl -like "*$Data*")
}
Write-TestFile (Join-Path $Evidence 'S2-port-pid.txt') ((@($__pp) + "live_5432: $(Get-Live5432)" + "live_service_pid: $($Live0.Pid)") -join "`n")


Save-LiveCheckpoint 'after-S2.5'   # [LC]


# ======== RUNBOOK BLOK 7 (S3) - EXECUTION_RUNBOOK_V1.md L506-L606 - AYNEN ========
'===== S3 ====='

# --- 3.1 Global fixture (postgres DB, super kullanici) ---
$FixGlobal = Join-Path $Inputs 'fixture_global_v1.sql'
$txt = @'
-- HGS2 V1 - global fixture (yalnizca izole test kumesi). Gercek veri YOK.
\set ON_ERROR_STOP on
SELECT current_setting('port') = '55438'
   AND current_setting('cluster_name') = 'hgs2iso18'
   AND current_database() = 'postgres' AS iso_ok \gset
\if :iso_ok
\else
  \echo 'DUR: izole test kumesi degil'
  SELECT 1/0;
\endif
CREATE ROLE hgs2_perftest LOGIN;
CREATE DATABASE hgs2_perftest_db OWNER hgs2_perftest;
CREATE DATABASE hibrit_giris_db OWNER postgres;
CREATE DATABASE other_db;
REVOKE CONNECT ON DATABASE hibrit_giris_db FROM PUBLIC;
SELECT datname, pg_get_userbyid(datdba) AS owner, datacl FROM pg_database ORDER BY 1;
'@
Write-TestFile $FixGlobal $txt

# --- 3.2 hgs2_perftest_db fixture (tablolar hgs2_perftest sahipliginde) ---
$FixDb = Join-Path $Inputs 'fixture_db_v1.sql'
$txt = @'
-- HGS2 V1 - sentetik sema (kaynak: asama3-final\kanit\harness\fixture_db.sql L8-21). Gercek veri YOK.
\set ON_ERROR_STOP on
SELECT current_setting('port') = '55438'
   AND current_setting('cluster_name') = 'hgs2iso18'
   AND current_database() = 'hgs2_perftest_db' AS iso_ok \gset
\if :iso_ok
\else
  \echo 'DUR: izole test kumesi / hedef DB degil'
  SELECT 1/0;
\endif
SET ROLE hgs2_perftest;
CREATE TABLE public.admins  (id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                             kullanici_adi varchar(100) NOT NULL UNIQUE, sifre_ozeti varchar(255) NOT NULL);
CREATE TABLE public.devices (id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, cihaz_adi varchar(100) NOT NULL);
CREATE TABLE public.users   (id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                             kart_no varchar(50) UNIQUE, ogrenci_no varchar(50) UNIQUE,
                             ad_soyad varchar(200), parmak_izi_sablonu oid);
CREATE TABLE public.logs    (id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                             device_id bigint REFERENCES public.devices(id),
                             user_id bigint REFERENCES public.users(id),
                             zaman timestamptz NOT NULL DEFAULT now());
INSERT INTO public.admins (kullanici_adi, sifre_ozeti) VALUES ('test_admin', 'SENTETIK-OZET-YOK');
INSERT INTO public.devices (cihaz_adi) VALUES ('test-cihaz-1');
INSERT INTO public.users (kart_no, ogrenci_no, ad_soyad) VALUES ('TEST-KART-0001', 'TEST-0001', 'Sentetik Kisi 1');
INSERT INTO public.logs (device_id, user_id) VALUES (1, 1);
RESET ROLE;
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, c.relacl
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1;
'@
Write-TestFile $FixDb $txt

# --- 3.3 Test parolasi atama dosyasi (parola ICERMEZ; surec ortamindan okunur) ---
$SetPwSql = Join-Path $Inputs 'set_password_v1.sql'
$txt = @'
-- HGS2 V1 - test rolune rastgele test parolasi (plan 3.3 test kumesi yolu b). Parola bu dosyada YOK.
\set ON_ERROR_STOP on
SELECT current_setting('port') = '55438'
   AND current_setting('cluster_name') = 'hgs2iso18' AS iso_ok \gset
\if :iso_ok
\else
  \echo 'DUR: izole test kumesi degil'
  SELECT 1/0;
\endif
\getenv pw HGS2_ISO_PW
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
ALTER ROLE :"target_role" PASSWORD :'pw';
RESET log_min_error_statement;
RESET log_statement;
\unset pw
'@
Write-TestFile $SetPwSql $txt

function Set-TestRolePassword([string]$Id, [string]$Role) {
    $secret = New-TestSecret
    $env:HGS2_ISO_PW = $secret                        # yalnizca bu surec ve psql alt sureci
    try     { $rc = Invoke-TestPsql $Id $SuperConnPg @('-w', '-v', "target_role=$Role", '-f', $SetPwSql) }
    finally { Remove-Item -LiteralPath 'Env:HGS2_ISO_PW' -ErrorAction SilentlyContinue }
    Assert-Guard ($rc -eq 0) "$Id parola atama cikis $rc"
    $TestSecrets[$Role] = $secret
    Add-TestPgpass $Role $secret
}

# --- 3.4 Calistirma ---
$rc = Invoke-TestPsql 'S3-fixture-global' $SuperConnPg @('-w', '-f', $FixGlobal)
Get-EvidenceText 'S3-fixture-global' 'stdout.txt'
Assert-Guard ($rc -eq 0) "S3-fixture-global cikis $rc"

$SuperConnPerf = "host=127.0.0.1 port=$TestPort dbname=hgs2_perftest_db user=postgres sslmode=require"
$rc = Invoke-TestPsql 'S3-fixture-db' $SuperConnPerf @('-w', '-f', $FixDb)
Get-EvidenceText 'S3-fixture-db' 'stdout.txt'
Assert-Guard ($rc -eq 0) "S3-fixture-db cikis $rc"

Set-TestRolePassword 'S3-perftest-password' 'hgs2_perftest'
Write-Stage 'S3-fixture' 'PASS'

Save-LiveCheckpoint 'after-S3'   # [LC]


# ======== RUNBOOK BLOK 8 (S4) - EXECUTION_RUNBOOK_V1.md L647-L696 - AYNEN ========
'===== S4 ====='

# --- 4.1 Matris 11 SQL blogunun cikarilmasi (matris dosyasi DEGISTIRILMEZ) ---
$Matrix = Join-Path $Base 'role-design\AUDIT_ROLE_PRIVILEGE_MATRIX.md'
$fence  = ([string][char]96) * 3
$ml = [IO.File]::ReadAllLines($Matrix, [Text.Encoding]::UTF8)
$h = -1; for ($i = 0; $i -lt $ml.Length; $i++) { if ($ml[$i] -eq '## 11. Proposed SQL Draft (NOT EXECUTED)') { $h = $i; break } }
Assert-Guard ($h -ge 0) 'matris 11. bolum basligi bulunamadi'
$s = -1; for ($i = $h + 1; $i -lt $ml.Length; $i++) { if ($ml[$i] -eq ($fence + 'sql')) { $s = $i; break } }
Assert-Guard ($s -gt $h) 'SQL blogu baslangici bulunamadi'
$e = -1; for ($i = $s + 1; $i -lt $ml.Length; $i++) { if ($ml[$i] -eq $fence) { $e = $i; break } }
Assert-Guard ($e -gt $s) 'SQL blogu sonu bulunamadi'
$draft = $ml[($s + 1)..($e - 1)]
Assert-Guard ($draft[0] -eq "\echo 'HGS2_ROLE_DRAFT: NOT EXECUTED - bu taslak calistirilmaz'") 'taslak ilk satiri beklenmedik'
Assert-Guard ($draft[1] -eq '\quit') 'taslak ikinci satiri \quit degil'
$approved = $draft[2..($draft.Length - 1)]
Assert-Guard (@($approved | Where-Object { $_ -eq '\quit' }).Count -eq 0) 'onayli kopyada sutun-0 \quit kaldi'
Assert-Guard (@($approved | Where-Object { $_ -match '^CREATE ROLE hgs2_audit$' }).Count -eq 1) 'CREATE ROLE satiri bulunamadi'

# --- 4.2 Onay kaydi (plan 3.1: onayli kopyanin SHA-256'si + change_ref kapisi) ---
$ChangeRef = "ISO-TEST-$RunId"
Assert-Guard ($ChangeRef -match '^ISO-TEST-iso18-\d{8}T\d{6}$') 'change_ref gecersiz'
$RoleSql = Join-Path $Inputs 'role_draft_approved_iso.sql'
Write-TestFile $RoleSql (($approved -join "`n") + "`n")
$RoleSqlSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $RoleSql).Hash.ToLower()
$approvalLine = '{0}  role_draft_approved_iso.sql  change_ref={1}  kaynak=AUDIT_ROLE_PRIVILEGE_MATRIX.md 11 (sha256 {2})' -f $RoleSqlSha, $ChangeRef, $Hash0[$IntegrityFiles[2]]
Set-Content -LiteralPath (Join-Path $Inputs 'role_draft_approved_iso.sha256') -Encoding ASCII -Value $approvalLine
"Onayli kopya SHA-256: $RoleSqlSha"

# --- 4.3 Rol olusturma (super kullanici, hgs2_perftest_db, tek transaction) ---
$rc  = Invoke-TestPsql 'S4-role-create' $SuperConnPerf @('-w', '-v', "change_ref=$ChangeRef", '-f', $RoleSql)
$out = @(Get-Content -LiteralPath (Join-Path $Evidence 'S4-role-create\stdout.txt'))
$err = Get-EvidenceText 'S4-role-create' 'stderr.txt'
$out
Assert-Guard ($rc -eq 0) "S4-role-create psql cikis $rc"
Assert-Guard ([string]::IsNullOrWhiteSpace($err)) 'S4-role-create stderr bos degil'
Assert-Guard (@($out | Where-Object { $_ -like 'DUR:*' -or $_ -like 'HGS2_ROLE_DESIGN_FAIL*' }).Count -eq 0) 'taslak DUR/FAIL yazdi (ROLLBACK, rol olusmadi)'
Assert-Guard (@($out | Where-Object { $_ -like 'HGS2_ROLE_DESIGN_OK*' }).Count -eq 1) 'HGS2_ROLE_DESIGN_OK yok'
Assert-Guard (@($out | Where-Object { $_ -like 'BILGI:*GRANT uretilmedi.' }).Count -eq 3) 'stok kumede hic GRANT uretilmemeliydi (3 BILGI satiri beklenir)'

# --- 4.4 hgs2_audit test parolasi ---
Set-TestRolePassword 'S4-audit-password' 'hgs2_audit'

# --- 4.5 Parola bicimi ve gunluk kontrolu (parola degeri GOSTERILMEZ) ---
$rc  = Invoke-TestPsql 'S4-password-check' $SuperConnPg @('-w', '-At', '-c', "select rolname, left(rolpassword, 14) from pg_authid where rolname in ('hgs2_audit','hgs2_perftest') order by 1")
$out = Get-EvidenceText 'S4-password-check' 'stdout.txt'
$out
Assert-Guard ($rc -eq 0) "S4-password-check cikis $rc"
Assert-Guard ($out -match '(?m)^hgs2_audit\|SCRAM-SHA-256\$\r?$') 'hgs2_audit SCRAM ozeti yok'
Assert-Guard ($out -match '(?m)^hgs2_perftest\|SCRAM-SHA-256\$\r?$') 'hgs2_perftest SCRAM ozeti yok'
Assert-Guard (@(Select-String -LiteralPath $LogFile -Pattern 'ALTER ROLE .*PASSWORD').Count -eq 0) 'ALTER ROLE ... PASSWORD sunucu gunlugune dusmus'
Write-Stage 'S4-role-create' "PASS approved_sha256=$RoleSqlSha"

Save-LiveCheckpoint 'after-S4'   # [LC]


# ======== RUNBOOK BLOK 9 (S5) - EXECUTION_RUNBOOK_V1.md L752-L1001 - AYNEN ========
'===== S5 ====='

# --- 5.1 Bagimsiz dogrulama SQL'i ---
$VerifySql = Join-Path $Inputs 'role_verify_v1.sql'
$txt = @'
-- HGS2 V1 - hgs2_audit bagimsiz yetki dogrulamasi (SALT OKUNUR)
-- Olcutler: AUDIT_ROLE_PRIVILEGE_MATRIX.md 11 (6-9, 10 all_ok) + ISOLATED_CLUSTER_TEST_PLAN.md T1 kontrol sorgusu
-- Yalnizca izole test kumesinde (port 55438, cluster_name hgs2iso18), super kullaniciyla, hgs2_perftest_db icinde.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL search_path = pg_catalog, pg_temp;

SELECT current_setting('port') = '55438'
   AND current_setting('cluster_name') = 'hgs2iso18'
   AND current_database() = 'hgs2_perftest_db'
   AND EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname = 'hgs2_audit') AS iso_ok
\gset
\if :iso_ok
\else
  \echo 'HGS2_V1_ROLE_VERIFY_FAIL: izole kume / hedef DB / hgs2_audit kosulu saglanmadi'
  SELECT 1/0;
\endif

-- A. Oznitelikler: SUPERUSER yok; CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS/INHERIT yok
SELECT NOT r.rolsuper AS not_superuser,
       (NOT r.rolcreatedb AND NOT r.rolcreaterole AND NOT r.rolreplication
        AND NOT r.rolbypassrls AND NOT r.rolinherit
        AND r.rolcanlogin AND r.rolconnlimit = 2) AS attrs_ok
FROM pg_roles r WHERE r.rolname = 'hgs2_audit'
\gset

-- B. Rol uyeligi yok (matris 7)
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT (SELECT count(*) FROM pg_auth_members m WHERE m.member = a.oid) = 0  AS no_member_of,
       (SELECT count(*) FROM pg_auth_members m WHERE m.roleid = a.oid) = 0  AS no_members_in_audit,
       NOT EXISTS (SELECT 1 FROM pg_roles r
                    WHERE r.oid <> a.oid
                      AND pg_has_role(a.oid, r.oid, 'MEMBER'))              AS no_effective_membership,
       NOT pg_has_role(a.oid, 'hgs2_perftest', 'MEMBER')                    AS not_member_perftest,
       NOT pg_has_role(a.oid, 'postgres', 'MEMBER')                         AS not_member_postgres
FROM a
\gset

-- C. Sahiplik yok (matris 8). Her olcutun KAPSAMI ayridir:
--    no_owned_db, no_owned_tablespace : pg_database / pg_tablespace paylasilan katalog -> kume geneli, dogrudan.
--    no_owned_schema_this_db          : pg_namespace -> YALNIZCA bu oturumun DB'si (hgs2_perftest_db), dogrudan.
--    no_owner_shdep_records           : pg_shdepend 'o' KAYITLARI (matristeki adi: no_owned_objects_any_db).
--      Bu yalnizca paylasilan bagimlilik kaydinin yoklugunu olcer; diger DB'lerin pg_namespace/pg_class
--      kataloglari bu oturumdan OKUNMAZ ve oradaki nesneler dogrudan dogrulanmaz.
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT (SELECT count(*) FROM pg_database d WHERE d.datdba = a.oid) = 0     AS no_owned_db,
       (SELECT count(*) FROM pg_namespace n WHERE n.nspowner = a.oid) = 0  AS no_owned_schema_this_db,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype = 'o') = 0                  AS no_owner_shdep_records,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype NOT IN ('o', 'a')) = 0      AS no_other_shdeps,
       (SELECT count(*) FROM pg_tablespace t WHERE t.spcowner = a.oid) = 0 AS no_owned_tablespace
FROM a
\gset

-- D. Kullanici tablosu / sequence / LO / default ACL erisimi yok (matris 6)
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT (SELECT count(*) FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
           AND ((c.relkind IN ('r', 'p', 'v', 'm', 'f')
                 AND (has_table_privilege(a.oid, c.oid,
                        'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN')
                      OR has_any_column_privilege(a.oid, c.oid,
                        'SELECT, INSERT, UPDATE, REFERENCES')))
             OR (c.relkind = 'S'
                 AND has_sequence_privilege(a.oid, c.oid, 'USAGE, SELECT, UPDATE')))
       )                                                                    AS user_rel_access_count,
       NOT has_table_privilege(a.oid, 'public.users'::regclass, 'SELECT')   AS no_select_users,
       (SELECT count(*) FROM pg_largeobject_metadata m
          CROSS JOIN LATERAL aclexplode(m.lomacl) x
         WHERE x.privilege_type IN ('SELECT', 'UPDATE')
           AND x.grantee IN (0, a.oid))                                     AS lo_public_or_audit_count,
       (SELECT count(*) FROM pg_default_acl da
          CROSS JOIN LATERAL aclexplode(da.defaclacl) x
         WHERE x.grantee = a.oid
            OR (x.grantee = 0 AND da.defaclobjtype IN ('r', 'S', 'L')))      AS defacl_risk_count
FROM a
\gset

-- E. Gereksiz CREATE yok (tum DB'ler + bu DB'nin semalari); TEMPORARY yalnizca kayit
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT NOT EXISTS (SELECT 1 FROM pg_database d
                    WHERE has_database_privilege(a.oid, d.oid, 'CREATE'))   AS no_db_create_any,
       NOT EXISTS (SELECT 1 FROM pg_namespace n
                    WHERE has_schema_privilege(a.oid, n.oid, 'CREATE'))     AS no_schema_create,
       has_database_privilege(a.oid, 'hgs2_perftest_db', 'TEMPORARY')       AS has_db_temporary
FROM a
\gset

-- F. Yalnizca gerekli baglanti ve katalog okuma yetkileri (matris 2-5; stokta hepsi PUBLIC'ten)
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT has_database_privilege(a.oid, 'hgs2_perftest_db', 'CONNECT')          AS connect_target,
       NOT has_database_privilege(a.oid, 'hibrit_giris_db', 'CONNECT')       AS hibrit_acl_closed,
       has_schema_privilege(a.oid, 'pg_catalog', 'USAGE')                    AS usage_pg_catalog,
       has_schema_privilege(a.oid, 'public', 'USAGE')                        AS usage_public,
       has_function_privilege(a.oid, 'pg_catalog.pg_control_system()', 'EXECUTE') AS ctrl_exec,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype = 'a')                      AS acl_ref_count,
       (SELECT count(*) FROM pg_db_role_setting s WHERE s.setrole = a.oid)  AS role_setting_count,
       (SELECT count(*) FROM pg_parameter_acl pa
          CROSS JOIN LATERAL aclexplode(pa.paracl) x
         WHERE x.grantee = a.oid)                                           AS parameter_acl_count,
       current_setting('lo_compat_privileges') = 'off'                      AS lo_compat_off,
       (SELECT count(*) FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE p.prosecdef
           AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
           AND has_schema_privilege(a.oid, n.oid, 'USAGE')
           AND has_function_privilege(a.oid, p.oid, 'EXECUTE'))             AS secdef_callable_count
FROM a
\gset

SELECT count(*) = 0                         AS catalogs_ok,
       COALESCE(string_agg(v.rel, ', '), '-') AS catalogs_missing
FROM (VALUES ('pg_roles'), ('pg_auth_members'), ('pg_database'), ('pg_db_role_setting'),
             ('pg_namespace'), ('pg_class'), ('pg_attribute'), ('pg_depend'),
             ('pg_constraint'), ('pg_type'), ('pg_proc'), ('pg_trigger'),
             ('pg_event_trigger'), ('pg_extension'), ('pg_foreign_server'),
             ('pg_foreign_data_wrapper'), ('pg_user_mappings'), ('pg_policy'),
             ('pg_default_acl'), ('pg_largeobject_metadata'), ('pg_stat_ssl')) AS v(rel)
WHERE NOT has_table_privilege('hgs2_audit', 'pg_catalog.' || v.rel, 'SELECT')
\gset

SELECT count(*) = 0                          AS functions_ok,
       COALESCE(string_agg(v.sig, ', '), '-') AS functions_missing
FROM (VALUES
  ('pg_catalog.now()'), ('pg_catalog.statement_timestamp()'),
  ('pg_catalog.pg_current_xact_id_if_assigned()'),
  ('pg_catalog.current_setting(text)'), ('pg_catalog.current_database()'),
  ('pg_catalog.regexp_replace(text,text,text,text)'), ('pg_catalog.host(inet)'),
  ('pg_catalog.inet_server_addr()'), ('pg_catalog.inet_server_port()'),
  ('pg_catalog.pg_is_in_recovery()'), ('pg_catalog.pg_backend_pid()'),
  ('pg_catalog.lower(text)'),
  ('pg_catalog.has_function_privilege(text,text)'),
  ('pg_catalog.has_function_privilege(oid,oid,text)'),
  ('pg_catalog.pg_control_system()'),
  ('pg_catalog.pg_has_role(name,oid,text)'), ('pg_catalog.pg_has_role(oid,oid,text)'),
  ('pg_catalog.pg_get_userbyid(oid)'),
  ('pg_catalog.has_database_privilege(oid,oid,text)'),
  ('pg_catalog.aclexplode(aclitem[])'), ('pg_catalog.acldefault("char",oid)'),
  ('pg_catalog.has_schema_privilege(oid,oid,text)'), ('pg_catalog.to_regnamespace(text)'),
  ('pg_catalog.has_table_privilege(oid,oid,text)'),
  ('pg_catalog.has_any_column_privilege(oid,oid,text)'),
  ('pg_catalog.has_sequence_privilege(oid,oid,text)'),
  ('pg_catalog.unnest(anyarray)'), ('pg_catalog.split_part(text,text,integer)'),
  ('pg_catalog.substr(text,integer)'), ('pg_catalog.strpos(text,text)'),
  ('pg_catalog.string_agg(text,text)'), ('pg_catalog.count()'),
  ('pg_catalog.bool_or(boolean)'), ('pg_catalog.bool_and(boolean)'),
  ('pg_catalog.pg_get_constraintdef(oid)'), ('pg_catalog.format_type(oid,integer)'),
  ('pg_catalog.to_regclass(text)'),
  ('pg_catalog.pg_get_function_identity_arguments(oid)'),
  ('pg_catalog.pg_get_expr(pg_node_tree,oid)'),
  ('pg_catalog.pg_stat_get_activity(integer)'), ('pg_catalog.pg_has_role(oid,text)'),
  ('pg_catalog.has_server_privilege(oid,text)')
) AS v(sig)
WHERE to_regprocedure(v.sig) IS NULL
   OR NOT has_function_privilege('hgs2_audit', to_regprocedure(v.sig)::oid, 'EXECUTE')
\gset

-- G. pg_hba katmani (matris 9.2)
SELECT NOT EXISTS (SELECT 1 FROM pg_hba_file_rules r WHERE r.error IS NOT NULL) AS hba_no_errors,
       COALESCE((SELECT r.auth_method FROM pg_hba_file_rules r
                  WHERE r.error IS NULL
                    AND r.type IN ('host', 'hostssl', 'hostnossl', 'hostgssenc', 'hostnogssenc')
                    AND ('hgs2_audit' = ANY (r.user_name) OR 'all' = ANY (r.user_name))
                    AND ('hibrit_giris_db' = ANY (r.database) OR 'all' = ANY (r.database))
                  ORDER BY r.line_number LIMIT 1) = 'reject', false)            AS hba_hibrit_rejected
\gset

-- Rapor: veritabani bazinda ACL CONNECT (matris 9.1; hgs2_perftest_db disindaki 't' satirlari yalnizca pg_hba ile kapali)
SELECT d.datname, d.datallowconn,
       has_database_privilege('hgs2_audit', d.oid, 'CONNECT') AS acl_connect,
       (d.datname = 'hgs2_perftest_db')                      AS expected_connect
FROM pg_database d ORDER BY d.datname;

\echo 'A not_superuser=' :not_superuser ' attrs_ok=' :attrs_ok
\echo 'B no_member_of=' :no_member_of ' no_members_in_audit=' :no_members_in_audit ' no_effective_membership=' :no_effective_membership ' not_member_perftest=' :not_member_perftest ' not_member_postgres=' :not_member_postgres
\echo 'C no_owned_db=' :no_owned_db ' no_owned_schema_this_db=' :no_owned_schema_this_db ' no_owner_shdep_records=' :no_owner_shdep_records ' no_other_shdeps=' :no_other_shdeps ' no_owned_tablespace=' :no_owned_tablespace
\echo 'D user_rel_access_count=' :user_rel_access_count ' no_select_users=' :no_select_users ' lo_public_or_audit_count=' :lo_public_or_audit_count ' defacl_risk_count=' :defacl_risk_count
\echo 'E no_db_create_any=' :no_db_create_any ' no_schema_create=' :no_schema_create ' has_db_temporary(kayit)=' :has_db_temporary
\echo 'F connect_target=' :connect_target ' hibrit_acl_closed=' :hibrit_acl_closed ' usage_pg_catalog=' :usage_pg_catalog ' usage_public=' :usage_public ' ctrl_exec=' :ctrl_exec
\echo 'F acl_ref_count=' :acl_ref_count ' role_setting_count=' :role_setting_count ' parameter_acl_count=' :parameter_acl_count ' lo_compat_off=' :lo_compat_off ' secdef_callable_count(kayit)=' :secdef_callable_count
\echo 'F catalogs_ok=' :catalogs_ok ' eksik:' :catalogs_missing
\echo 'F functions_ok=' :functions_ok ' eksik:' :functions_missing
\echo 'G hba_no_errors=' :hba_no_errors ' hba_hibrit_rejected=' :hba_hibrit_rejected

SELECT (:'not_superuser')::boolean AND (:'attrs_ok')::boolean
   AND (:'no_member_of')::boolean AND (:'no_members_in_audit')::boolean
   AND (:'no_effective_membership')::boolean AND (:'not_member_perftest')::boolean
   AND (:'not_member_postgres')::boolean
   AND (:'no_owned_db')::boolean AND (:'no_owned_schema_this_db')::boolean
   AND (:'no_owner_shdep_records')::boolean AND (:'no_other_shdeps')::boolean
   AND (:'no_owned_tablespace')::boolean
   AND :user_rel_access_count = 0 AND (:'no_select_users')::boolean
   AND :lo_public_or_audit_count = 0 AND :defacl_risk_count = 0
   AND (:'no_db_create_any')::boolean AND (:'no_schema_create')::boolean
   AND (:'connect_target')::boolean AND (:'hibrit_acl_closed')::boolean
   AND (:'usage_pg_catalog')::boolean AND (:'usage_public')::boolean
   AND (:'ctrl_exec')::boolean AND (:'catalogs_ok')::boolean AND (:'functions_ok')::boolean
   AND :acl_ref_count = 0 AND :role_setting_count = 0 AND :parameter_acl_count = 0
   AND (:'lo_compat_off')::boolean
   AND (:'hba_no_errors')::boolean AND (:'hba_hibrit_rejected')::boolean AS v1_role_ok
\gset
\if :v1_role_ok
  \echo 'HGS2_V1_ROLE_VERIFY_OK'
\else
  \echo 'HGS2_V1_ROLE_VERIFY_FAIL'
  SELECT 1/0;
\endif
ROLLBACK;
'@
Write-TestFile $VerifySql $txt

# --- 5.2 Calistirma (super kullanici, hgs2_perftest_db, salt okunur) ---
$rc  = Invoke-TestPsql 'S5-role-verify' $SuperConnPerf @('-w', '-f', $VerifySql)
$out = Get-EvidenceText 'S5-role-verify' 'stdout.txt'
$err = Get-EvidenceText 'S5-role-verify' 'stderr.txt'
$out
Assert-Guard ($rc -eq 0) "S5-role-verify cikis $rc"
Assert-Guard ([string]::IsNullOrWhiteSpace($err)) 'S5-role-verify stderr bos degil'
Assert-Guard ([regex]::Matches($out, '(?m)^HGS2_V1_ROLE_VERIFY_OK\r?$').Count -eq 1) 'HGS2_V1_ROLE_VERIFY_OK yok'
Assert-Guard ($out -notmatch '(?m)^HGS2_V1_ROLE_VERIFY_FAIL') 'dogrulama FAIL'

# --- 5.3 Oturum duzeyi kontroller (hgs2_audit ile) ---
$AuditConn = "host=127.0.0.1 port=$TestPort dbname=hgs2_perftest_db user=hgs2_audit sslmode=require"
$rc  = Invoke-TestPsql 'S5-pos-connect' $AuditConn @('-w', '-At', '-c', 'select current_user, session_user, current_database(), (select ssl from pg_stat_ssl where pid = pg_backend_pid())')
$out = Get-EvidenceText 'S5-pos-connect' 'stdout.txt'
$out
Assert-Guard ($rc -eq 0) "S5-pos-connect cikis $rc"
Assert-Guard ($out -match '(?m)^hgs2_audit\|hgs2_audit\|hgs2_perftest_db\|t\r?$') 'hgs2_audit hedefe TLS ile baglanamadi'

$neg = [ordered]@{
    'S5-neg-set-role'     = 'SET ROLE hgs2_perftest'
    'S5-neg-select-users' = 'SELECT 1 FROM public.users LIMIT 1'
    'S5-neg-create-table' = 'CREATE TABLE public.v1_probe(i int)'
}
foreach ($k in $neg.Keys) {
    $rc  = Invoke-TestPsql $k $AuditConn @('-w', '-v', 'VERBOSITY=verbose', '-c', $neg[$k])
    $err = Get-EvidenceText $k 'stderr.txt'
    '{0}: cikis={1}  {2}' -f $k, $rc, (($err -split "`r?`n") | Select-Object -First 1)
    Assert-Guard (($rc -ne 0) -and ($err -match 'ERROR:\s+42501:')) "${k}: beklenen 42501 reddi alinmadi"
}
Write-Stage 'S5-role-verify' 'PASS'

Save-LiveCheckpoint 'after-S5'   # [LC]


# ======== RUNBOOK BLOK 10 (S6) - EXECUTION_RUNBOOK_V1.md L1074-L1098 - AYNEN ========
'===== S6 ====='

# --- 6.1 Butunluk (calistirmadan hemen once) ---
$ShaNow = (Get-FileHash -Algorithm SHA256 -LiteralPath $AuditSql).Hash.ToLower()
"Final SQL SHA-256: $ShaNow"
Assert-Guard ($ShaNow -eq $AuditSha) 'denetim SQL hash uyusmuyor'

# --- 6.2 Plan 5.7 Invoke-Audit (degistirilmeden) ---
function Invoke-Audit([string]$Id, [string]$HostArg, [string]$ServerAddr, [string]$SslPart, [string[]]$Extra) {
    $conn = "host=$HostArg port=$TestPort dbname=hgs2_perftest_db user=hgs2_audit $SslPart".Trim()
    $argv = @('-v', "expected_host=$HostArg", '-v', "expected_port=$TestPort", '-v', "expected_server_addr=$ServerAddr",
              '-v', "expected_server_port=$TestPort", '-v', "expected_system_identifier=$SysId", '-f', $AuditSql) + $Extra
    $rc = Invoke-TestPsql $Id $conn $argv
    $d = Join-Path $Evidence $Id
    & py -3.13 -I $Validator --exit-code $rc --stdout "$d\stdout.txt" --stderr "$d\stderr.txt" | Set-Content -LiteralPath "$d\verdict.txt" -Encoding UTF8
    return $rc
}

# --- 6.3 Denetim ---
$AuditId = 'S6-audit-hgs2_audit'
$AuditRc = Invoke-Audit $AuditId '127.0.0.1' '127.0.0.1' 'sslmode=require' @('-w')
$AuditDir = Join-Path $Evidence $AuditId
"psql cikis: $AuditRc"
Get-Content -LiteralPath "$AuditDir\args.txt"
Select-String -LiteralPath "$AuditDir\stdout.txt" -Pattern '^HGS2_AUDIT_|^tasima=' | ForEach-Object { $_.Line }
Set-Content -LiteralPath "$AuditDir\audit_sql.sha256" -Encoding ASCII -Value "$ShaNow  asama3-final\postgresql_readonly_audit_v2.sql"
Write-Stage 'S6-audit-run' "EXIT=$AuditRc"

Save-LiveCheckpoint 'after-S6'   # [LC]


# ======== RUNBOOK BLOK 11 (S7) - EXECUTION_RUNBOOK_V1.md L1142-L1153 - AYNEN ========
'===== S7 ====='

$ValOut = & py -3.13 -I $Validator --exit-code $AuditRc --stdout "$AuditDir\stdout.txt" --stderr "$AuditDir\stderr.txt"
$ValRc  = $LASTEXITCODE
$ValOut
"validator cikis: $ValRc"
Set-Content -LiteralPath "$AuditDir\verdict-explicit.txt" -Encoding UTF8 -Value (@($ValOut) + "validator_exit=$ValRc")
Get-Content -LiteralPath "$AuditDir\verdict.txt"
$StdErrText = Get-EvidenceText $AuditId 'stderr.txt'
Assert-Guard ($ValRc -eq 0) 'validator PASS vermedi'
Assert-Guard ((@($ValOut))[0] -eq 'PASS') 'validator ilk satiri PASS degil'
Assert-Guard ((Get-Content -LiteralPath "$AuditDir\verdict.txt" -TotalCount 1) -eq 'PASS') 'verdict.txt PASS degil'
Assert-Guard ([string]::IsNullOrWhiteSpace($StdErrText)) 'denetim stderr bos degil'
Write-Stage 'S7-validator' 'PASS'

Save-LiveCheckpoint 'after-S7'   # [LC]


# ======== RUNBOOK BLOK 12 (S8) - EXECUTION_RUNBOOK_V1.md L1185-L1202 - AYNEN ========
'===== S8 ====='

foreach ($m in 'disable', 'require') {
    $id  = "S8-audit-hibrit-$m"
    $rc  = Invoke-TestPsql $id "host=127.0.0.1 port=$TestPort dbname=hibrit_giris_db user=hgs2_audit sslmode=$m" @('-w', '-c', 'select 1')
    $err = Get-EvidenceText $id 'stderr.txt'
    '{0}: cikis={1}' -f $id, $rc
    $err
    Assert-Guard ($rc -eq 2) "${id}: cikis $rc (beklenen 2)"
    Assert-Guard ($err -match 'pg_hba\.conf rejects connection for host "127\.0\.0\.1", user "hgs2_audit", database "hibrit_giris_db"') "${id}: pg_hba reddi mesaji yok"
    Assert-Guard (-not (Test-Path -LiteralPath (Join-Path $Evidence "$id\stdout.txt")) -or [string]::IsNullOrWhiteSpace((Get-EvidenceText $id 'stdout.txt'))) "${id}: stdout bos degil (sorgu calismis olabilir)"
}
# Sunucu gunlugu: SQLSTATE 28000 ve oturum acilmamis olmasi
$hbaLines = @(Select-String -LiteralPath $LogFile -Pattern '\] 28000 user=hgs2_audit db=hibrit_giris_db .*FATAL:\s+pg_hba\.conf rejects connection')
$hbaLines | ForEach-Object { $_.Line } | Set-Content -LiteralPath (Join-Path $Evidence 'S8-log-28000.txt') -Encoding UTF8
$authLines = @(Select-String -LiteralPath $LogFile -Pattern 'user=hgs2_audit db=hibrit_giris_db .*connection (authenticated|authorized)')
"28000 satirlari: $($hbaLines.Count)   oturum acilis satirlari: $($authLines.Count)"
Assert-Guard ($hbaLines.Count -ge 2) 'gunlukte 28000 pg_hba reddi beklenen sayida yok'
Assert-Guard ($authLines.Count -eq 0) 'hgs2_audit hibrit_giris_db icin kimlik dogrulamasi/oturum gecmis'
Write-Stage 'S8-audit-hibrit-blocked' 'PASS'

Save-LiveCheckpoint 'after-S8'   # [LC]


# ======== RUNBOOK BLOK 13 (S9) - EXECUTION_RUNBOOK_V1.md L1236-L1259 - AYNEN ========
'===== S9 ====='

# (a) C10: hgs2_perftest kendi DB'sine baglanir (kimlik dogrulamasi calisiyor)
$rc  = Invoke-TestPsql 'S9-perftest-own-db' "host=127.0.0.1 port=$TestPort dbname=hgs2_perftest_db user=hgs2_perftest sslmode=require" @('-w', '-At', '-c', 'select current_user, current_database()')
$out = Get-EvidenceText 'S9-perftest-own-db' 'stdout.txt'
$out
Assert-Guard ($rc -eq 0) "S9-perftest-own-db cikis $rc"
Assert-Guard ($out -match '(?m)^hgs2_perftest\|hgs2_perftest_db\r?$') 'hgs2_perftest kendi DB''sine baglanamadi'

# (b) C11: hgs2_perftest -> hibrit_giris_db = 42501 (28000 / 28P01 DEGIL)
$rc  = Invoke-TestPsql 'S9-perftest-hibrit' "host=127.0.0.1 port=$TestPort dbname=hibrit_giris_db user=hgs2_perftest sslmode=require" @('-w', '-c', 'select 1')
$err = Get-EvidenceText 'S9-perftest-hibrit' 'stderr.txt'
"S9-perftest-hibrit: cikis=$rc"
$err
Assert-Guard ($rc -eq 2) "S9-perftest-hibrit cikis $rc (beklenen 2)"
Assert-Guard ($err -match 'permission denied for database "hibrit_giris_db"') 'beklenen 42501 mesaji yok'
Assert-Guard ($err -notmatch 'pg_hba\.conf rejects') 'hgs2_perftest pg_hba ile reddedildi (28000) - PerfTestSafetyGuard kirilir'
Assert-Guard ($err -notmatch 'password authentication failed') 'hgs2_perftest kimlik dogrulamasi basarisiz (28P01)'

$l42501 = @(Select-String -LiteralPath $LogFile -Pattern '\] 42501 user=hgs2_perftest db=hibrit_giris_db .*FATAL:\s+permission denied for database')
$l28    = @(Select-String -LiteralPath $LogFile -Pattern '\] 28(000|P01) user=hgs2_perftest ')
($l42501 + $l28) | ForEach-Object { $_.Line } | Set-Content -LiteralPath (Join-Path $Evidence 'S9-log-sqlstate.txt') -Encoding UTF8
"42501 satirlari: $($l42501.Count)   28000/28P01 satirlari: $($l28.Count)"
Assert-Guard ($l42501.Count -ge 1) 'gunlukte 42501 satiri yok'
Assert-Guard ($l28.Count -eq 0) 'gunlukte hgs2_perftest icin 28000/28P01 var'
Write-Stage 'S9-perftest-42501' 'PASS'

Save-LiveCheckpoint 'after-S9'   # [LC]


# ======== RUNBOOK BLOK 14 (S10.1) - EXECUTION_RUNBOOK_V1.md L1296-L1300 - AYNEN ========
'===== S10.1 ====='

Stop-TestCluster
Assert-Guard (@(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count -eq 0) 'test postmaster hala calisiyor'
Assert-Guard ($null -eq (Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue)) "port $TestPort hala dinleniyor"
Assert-LiveUnchanged
Write-Stage 'S10.1-cluster-stopped' 'PASS'

# [A10.1] ---- port/surec serbest kaniti (ek) ----
$__pf1 = @(Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue).Count
$__pf2 = @(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count
Write-TestFile (Join-Path $Evidence 'S10.1-port-free.txt') (@("port_${TestPort}_listen_count: $__pf1", "test_postmaster_count: $__pf2", "live_5432: $(Get-Live5432)") -join "`n")


# ======== RUNBOOK BLOK 15 (S10.2) - EXECUTION_RUNBOOK_V1.md L1313-L1321 - AYNEN ========
'===== S10.2 ====='

$scanFiles = @(Get-ChildItem -LiteralPath $Evidence -Recurse -File) + @(Get-Item -LiteralPath $LogFile)
foreach ($k in @($TestSecrets.Keys)) {
    $hits = @($scanFiles | Select-String -SimpleMatch -Pattern $TestSecrets[$k])
    "parola taramasi ${k}: $($hits.Count) eslesme"
    Assert-Guard ($hits.Count -eq 0) "test parolasi ($k) kanit veya gunluk icinde bulundu - ARSIVLEME YAPMA"
}
$keyHits = @($scanFiles | Select-String -SimpleMatch -Pattern 'PRIVATE KEY')
Assert-Guard ($keyHits.Count -eq 0) 'kanitta ozel anahtar icerigi var - ARSIVLEME YAPMA'
Write-Stage 'S10.2-secret-scan' 'PASS'

Save-LiveCheckpoint 'after-S10.2'   # [LC]


# ======== RUNBOOK BLOK 16 (S10.3) - EXECUTION_RUNBOOK_V1.md L1331-L1344 - AYNEN ========
'===== S10.3 ====='

$Archive = Join-Path $Base "role-design\iso-runs\$RunId"
Assert-Guard (-not (Test-Path -LiteralPath $Archive)) 'arsiv klasoru zaten var'
Assert-Guard ([IO.Path]::GetFullPath($Archive).StartsWith([IO.Path]::GetFullPath((Join-Path $Base 'role-design\iso-runs')) + '\', [StringComparison]::OrdinalIgnoreCase)) 'arsiv hedefi iso-runs altinda degil'
New-Item -ItemType Directory -Force -Path $Archive, (Join-Path $Archive 'log') | Out-Null
Copy-Item -LiteralPath $Evidence -Destination (Join-Path $Archive 'evidence') -Recurse
Copy-Item -LiteralPath $LogFile  -Destination (Join-Path $Archive 'log\postgres.log')

# Kopya dogrulamasi (dosya sayisi + hash kumesi)
$srcH = @(Get-ChildItem -LiteralPath $Evidence -Recurse -File | ForEach-Object { (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash } | Sort-Object)
$dstH = @(Get-ChildItem -LiteralPath (Join-Path $Archive 'evidence') -Recurse -File | ForEach-Object { (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash } | Sort-Object)
Assert-Guard (($srcH.Count -eq $dstH.Count) -and (@(Compare-Object $srcH $dstH).Count -eq 0)) 'arsiv kopyasi kaynakla ayni degil'
Assert-Guard ((Get-FileHash -Algorithm SHA256 -LiteralPath $LogFile).Hash -eq (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Archive 'log\postgres.log')).Hash) 'gunluk kopyasi farkli'
Add-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt') -Encoding ASCII -Value ('{0} S10.3-archive PASS files={1}' -f (Get-Date -Format 'o'), $srcH.Count)
"Arsiv: $Archive  dosya: $($srcH.Count)"

Save-LiveCheckpoint 'after-S10.3'   # [LC]


# [A10.4] ---- Read-Host yerine onay dosyasi (etkilesimsiz surec). Onay = RunId'nin birebir yazilmasi ----
function Wait-DeleteConfirmation {
    $t0 = Get-Date
    Write-Host "ONAY BEKLENIYOR: silme icin RunId su dosyaya yazilmali: $ConfirmFile (en fazla 30 dk)"
    while (((Get-Date) - $t0).TotalMinutes -lt 30) {
        if (Test-Path -LiteralPath $ConfirmFile) { Start-Sleep -Milliseconds 500; return ([IO.File]::ReadAllText($ConfirmFile)).Trim() }
        Start-Sleep -Seconds 2
    }
    Write-Host 'ONAY ZAMAN ASIMI'
    return ''
}
$__delOk = $false
try {


# ======== RUNBOOK BLOK 17 (S10.4) - EXECUTION_RUNBOOK_V1.md L1363-L1381 - AYNEN ========
'===== S10.4 ====='

$RootFull  = [IO.Path]::GetFullPath($Root)
$IsoParent = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hgs2-iso'))
Assert-Guard ($RootFull -match '\\hgs2-iso\\iso18-\d{8}T\d{6}$') 'silme hedefi RunId bicimine uymuyor'
Assert-Guard ([IO.Path]::GetDirectoryName($RootFull) -eq $IsoParent) 'silme hedefi hgs2-iso altinda degil'
Assert-Guard (-not $RootFull.StartsWith('C:\Program Files', [StringComparison]::OrdinalIgnoreCase)) 'silme hedefi Program Files altinda'
Assert-Guard (-not $RootFull.StartsWith([IO.Path]::GetFullPath($Base), [StringComparison]::OrdinalIgnoreCase)) 'silme hedefi proje klasoru icinde'
Assert-Guard (-not ((Get-Location).Path.StartsWith($RootFull, [StringComparison]::OrdinalIgnoreCase))) 'calisma dizini silinecek kokun icinde'
Assert-Guard (Test-Path -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt')) 'arsiv yok - silme yapilmaz'
Assert-Guard (@(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count -eq 0) 'test postmaster calisiyor - silme yapilmaz'
"SILINECEK: $RootFull"
$confirm = Wait-DeleteConfirmation   # [A10.4] runbook: $confirm = Read-Host 'Silmek icin RunId'yi aynen yazin ($RunId)'
Assert-Guard ($confirm -eq $RunId) 'onay verilmedi - silme yapilmadi'

Remove-Item -LiteralPath $env:PGPASSFILE -Force          # YIKICI: yalnizca test pgpass (cfg\pgpass.conf)
Remove-Item -LiteralPath $Root -Recurse -Force            # YIKICI: yalnizca bu RunId'nin test koku
Assert-Guard (-not (Test-Path -LiteralPath $Root)) 'test koku silinemedi'
foreach ($v in 'PGPASSFILE','PGSERVICEFILE','PGSYSCONFDIR','PSQLRC','PGCONNECT_TIMEOUT') { Remove-Item -LiteralPath "Env:$v" -ErrorAction SilentlyContinue }
Assert-LiveUnchanged
Add-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt') -Encoding ASCII -Value ('{0} S10.4-root-removed PASS' -f (Get-Date -Format 'o'))

$__delOk = $true
} catch {
    "10.4 SILME YAPILMADI: $($_.Exception.Message)"
    if (Test-Path -LiteralPath $Root) {


# ======== RUNBOOK BLOK 18 (S10.4-erteleme) - EXECUTION_RUNBOOK_V1.md L1387-L1387 - AYNEN ========
'===== S10.4-erteleme ====='

Add-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt') -Encoding ASCII -Value ('{0} S10.4-root-removed DEFERRED root={1}' -f (Get-Date -Format 'o'), $Root)

    } else {
        Add-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt') -Encoding ASCII -Value ('{0} S10.4-root-removed FAIL {1}' -f (Get-Date -Format 'o'), ($_.Exception.Message -replace '[^\x20-\x7E]', '?'))
    }
}


# [A-TS] ---- transcript + konsol gunlugu gizli taramasi (ek; yalnizca sayi yazar) ----
function Read-Shared([string]$p) { $fs = [IO.File]::Open($p, 'Open', 'Read', 'ReadWrite'); try { (New-Object IO.StreamReader($fs)).ReadToEnd() } finally { $fs.Dispose() } }
foreach ($tf in @($TranscriptFile, $ConsoleLog)) {
    if (Test-Path -LiteralPath $tf) {
        $__t = Read-Shared $tf
        foreach ($k in @($TestSecrets.Keys)) {
            $n = $__t.Split([string[]]@($TestSecrets[$k]), [StringSplitOptions]::None).Length - 1
            "konsol/transcript parola taramasi ${k}: $n eslesme ($([IO.Path]::GetFileName($tf)))"
            Assert-Guard ($n -eq 0) "test parolasi ($k) konsol/transcript icinde"
        }
        Assert-Guard (-not $__t.Contains('PRIVATE KEY')) 'konsol/transcript icinde ozel anahtar'
        $__t = $null
    } else { "konsol/transcript bulunamadi: $tf" }
}
Save-LiveCheckpoint 'before-S11'


# ======== RUNBOOK BLOK 19 (S11) - EXECUTION_RUNBOOK_V1.md L1415-L1472 - AYNEN ========
'===== S11 ====='

# --- 11.1 Canli servis bitis anlik goruntusu ---
$Live1      = Get-LiveSnapshot
$Live5432_1 = Get-Live5432
$Live1 | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Archive 'live-end.json') -Encoding ASCII
Set-Content -LiteralPath (Join-Path $Archive 'live-end-5432.txt') -Encoding ASCII -Value $Live5432_1
$LiveSame = ($Live1.State -eq $Live0.State) -and ($Live1.Pid -eq $Live0.Pid) -and ($Live1.Created -eq $Live0.Created) -and ($Live1.PathName -eq $Live0.PathName) -and ($Live5432_1 -eq $Live5432_0)

# --- 11.2 Butunluk (nihai SQL, plan, matris) ---
$IntegrityOk = $true
$intLines = foreach ($f in $IntegrityFiles) {
    $h1 = (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLower()
    if ($h1 -ne $Hash0[$f]) { $IntegrityOk = $false }
    '{0}  {1}  {2}' -f $h1, $(if ($h1 -eq $Hash0[$f]) { 'AYNI' } else { 'DEGISTI' }), $f
}
$intLines | Set-Content -LiteralPath (Join-Path $Archive 'integrity-end.sha256') -Encoding ASCII
$AuditShaEnd = (Get-FileHash -Algorithm SHA256 -LiteralPath $AuditSql).Hash.ToLower()

# --- 11.3 Nihai sonuc karari (test koku silinmediyse V1 TAMAMLANMADI) ---
$RootRemoved = -not (Test-Path -LiteralPath $Root)
$Reasons = @()
if (-not $LiveSame)               { $Reasons += 'canli servis degisti' }
if (-not $IntegrityOk)            { $Reasons += 'plan/matris/SQL butunlugu degisti' }
if ($AuditShaEnd -ne $AuditSha)   { $Reasons += 'nihai SQL SHA-256 degisti' }
if (-not $RootRemoved)            { $Reasons += "test koku silinmedi (temizlik ertelendi veya yapilamadi): $Root" }
$Result = if ($Reasons.Count -eq 0) { 'SONUC: V1 TAMAMLANDI' } else { 'SONUC: V1 TAMAMLANMADI - ' + ($Reasons -join '; ') }

# --- 11.4 Ozet ---
$Summary = @(
    "RunId: $RunId",
    "Final SQL SHA-256 bitis: $AuditShaEnd  beklenen: $AuditSha  sonuc: $(if ($AuditShaEnd -eq $AuditSha) { 'AYNI' } else { 'DEGISTI' })",
    "Plan/matris/SQL butunlugu degismedi: $IntegrityOk",
    "Canli servis baslangic: State=$($Live0.State) Pid=$($Live0.Pid) Created=$($Live0.Created)",
    "Canli servis bitis    : State=$($Live1.State) Pid=$($Live1.Pid) Created=$($Live1.Created)",
    "Canli PathName ayni: $($Live1.PathName -eq $Live0.PathName)",
    "5432 dinleyicileri baslangic: $Live5432_0",
    "5432 dinleyicileri bitis    : $Live5432_1",
    "Canli servis degismedi: $LiveSame",
    "Test koku mevcut degil: $RootRemoved",
    "Port $TestPort bos: $($null -eq (Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue))",
    '--- Asama sonuclari ---'
) + @(Get-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt')) + @('--- Nihai sonuc ---', $Result)
$Summary | Set-Content -LiteralPath (Join-Path $Archive 'SUMMARY.txt') -Encoding UTF8
$Summary

# --- 11.5 Arsiv manifesti (SHA256SUMS.txt kendini icermez; Asama 11 yeniden calistirilirsa yeniden yazilir) ---
$manifest = Get-ChildItem -LiteralPath $Archive -Recurse -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object FullName |
    ForEach-Object { '{0}  {1}' -f (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower(), $_.FullName.Substring($Archive.Length + 1) }
$manifest | Set-Content -LiteralPath (Join-Path $Archive 'SHA256SUMS.txt') -Encoding ASCII

# --- 11.6 Gizli bilgilerin bellekten temizlenmesi (silme ertelendiyse test pgpass dosyasi diskte kalir; bkz. 10.4) ---
$TestSecrets.Clear()
Remove-Variable -Name SuperPw -ErrorAction SilentlyContinue

Assert-Guard $LiveSame 'CANLI SERVIS DEGISTI - DUR, MUDAHALE ETME, RAPORLA'
Assert-Guard $IntegrityOk 'butunluk dosyalarindan biri degisti'
Assert-Guard ($AuditShaEnd -eq $AuditSha) 'nihai SQL SHA-256 degisti'
if (-not $RootRemoved) { Write-Warning "Test koku silinmedi: $Root - V1 TAMAMLANMADI" }
$Result

'RUNNER_END'
} catch {
    $__failed = $true
    $__msg = $_.Exception.Message
    "HATA/DUR: $__msg"
    try {
        if ((Get-Variable -Name Evidence -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $Evidence)) {
            Add-Content -LiteralPath (Join-Path $Evidence 'stage-results.txt') -Encoding ASCII -Value ('{0} RUNNER-STOP FAIL {1}' -f (Get-Date -Format 'o'), ($__msg -replace '[^\x20-\x7E]', '?'))
        }
    } catch { "kayit yazilamadi: $($_.Exception.Message)" }
    try {   # 12.1 / 12.2: yalnizca test veri dizini hedeflenir
        if ((Get-Variable -Name Data -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath (Join-Path $Data 'postmaster.pid'))) {
            Assert-UnderRoot $Data
            & "$PgBin\pg_ctl.exe" -D $Data -m fast -w stop
            "test kumesi durdurma cikis: $LASTEXITCODE"
        }
    } catch { "test kumesi durdurulamadi: $($_.Exception.Message)" }
    try { Get-LiveSnapshot | Format-List; "5432: $(Get-Live5432)" } catch { }
} finally {
    Stop-Transcript | Out-Null
}
if ($__failed) { exit 1 } else { exit 0 }
