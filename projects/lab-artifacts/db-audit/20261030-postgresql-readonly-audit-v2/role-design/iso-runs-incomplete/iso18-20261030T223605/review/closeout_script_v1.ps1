# HGS2 - eski (oturumu kaybolmus) calistirmanin kapanisi: runbook 12.3 + 10.2 tarama mantigi + 10.3 benzeri arsiv + 10.4 kapilari
# Eski kume BASLATILMAZ, eski parolalar YENIDEN URETILMEZ, eski RunId uzerinde test YAPILMAZ.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$PgBin      = 'C:\Program Files\PostgreSQL\18\bin'
$LiveData   = 'C:\Program Files\PostgreSQL\18\data'
$LiveSvc    = 'postgresql-x64-18'
$LivePort   = 5432
$Base       = 'C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\db-audit\20261030-postgresql-readonly-audit-v2'
$OldRunId   = 'iso18-20261030T223605'   # gorev metninde kullanicinin verdigi RunId = RunId onayi kaynagi
$Root       = Join-Path $env:LOCALAPPDATA "hgs2-iso\$OldRunId"
$Data       = Join-Path $Root 'data'
$Evidence   = Join-Path $Root 'evidence'
$ArchParent = Join-Path $Base 'role-design\iso-runs-incomplete'
$Archive    = Join-Path $ArchParent $OldRunId

function Assert-Guard([bool]$Cond, [string]$Msg) { if (-not $Cond) { throw "GUARD: $Msg" } }
function Get-LiveSnapshot {
    $s = Get-CimInstance Win32_Service -Filter "Name='$LiveSvc'"
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($s.ProcessId)"
    [pscustomobject]@{ State = $s.State; Pid = $s.ProcessId; Created = $p.CreationDate.ToString('o'); PathName = $s.PathName }
}
function Get-Live5432 {
    @(Get-NetTCPConnection -LocalPort $LivePort -State Listen -ErrorAction SilentlyContinue |
      Sort-Object LocalAddress |
      ForEach-Object { '{0}:{1} pid={2}' -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess }) -join '; '
}
$R = [ordered]@{}
function Note([string]$k, $v) { $R[$k] = $v; '{0} = {1}' -f $k, $v }
function Get-TestPostmasterCount { @(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Data*" }).Count }

# --- 12.3 hedef kapisi ---
if ($Data -notmatch '\\hgs2-iso\\iso18-\d{8}T\d{6}\\data$') { throw 'GUARD: yanlis hedef' }
Assert-Guard (Test-Path -LiteralPath $Root) 'eski test koku bulunamadi'
Note 'old_root' $Root

# --- Canli servis: oturum baslangic goruntusu ve eski live-start.json ile elle karsilastirma (12.3) ---
$Live0 = Get-LiveSnapshot; $Live5432_0 = Get-Live5432
$oldLive = Get-Content -LiteralPath (Join-Path $Evidence 'live-start.json') -Raw | ConvertFrom-Json
$old5432 = (Get-Content -LiteralPath (Join-Path $Evidence 'live-start-5432.txt') -Raw).Trim()
$sameAsOld = ($Live0.State -eq $oldLive.State) -and ([int]$Live0.Pid -eq [int]$oldLive.Pid) -and ($Live0.Created -eq [string]$oldLive.Created) -and ($Live0.PathName -eq $oldLive.PathName) -and ($Live5432_0 -eq $old5432)
Note 'live_now' ("State={0} Pid={1} Created={2}" -f $Live0.State, $Live0.Pid, $Live0.Created)
Note 'live_old_start' ("State={0} Pid={1} Created={2}" -f $oldLive.State, $oldLive.Pid, $oldLive.Created)
Note 'live_pathname_same' ($Live0.PathName -eq $oldLive.PathName)
Note 'live5432_now' $Live5432_0
Note 'live5432_old_start' $old5432
Note 'live_same_as_old_run_start' $sameAsOld
Assert-Guard $sameAsOld 'CANLI SERVIS eski calistirma baslangicindan farkli - DUR, MUDAHALE ETME, RAPORLA'

# --- 12.3: eski test kumesinin durumu (BASLATILMAZ) ---
& "$PgBin\pg_ctl.exe" -D $Data status
$stRc = $LASTEXITCODE
Note 'pg_ctl_status_rc' $stRc
if ($stRc -eq 0) {
    # 12.3: calisiyorsa yalnizca test kumesi durdurulur
    & "$PgBin\pg_ctl.exe" -D $Data -m fast -w stop
    Assert-Guard ($LASTEXITCODE -eq 0) 'eski test kumesi durdurulamadi'
    Note 'old_cluster_stopped_now' $true
}
Note 'postmaster_pid_file_exists' (Test-Path -LiteralPath (Join-Path $Data 'postmaster.pid'))
Note 'test_postmaster_process_count' (Get-TestPostmasterCount)
Note 'port55438_listening' ($null -ne (Get-NetTCPConnection -LocalPort 55438 -State Listen -ErrorAction SilentlyContinue))

# --- Arsivlenecek dosyalar ve gizli bilgi taramasi (10.2 mantigi; bellekteki $TestSecrets kayip -> pgpass kaynakli ikame) ---
$logFiles = @(Get-ChildItem -LiteralPath (Join-Path $Root 'log') -Recurse -File -ErrorAction SilentlyContinue)
Note 'log_file_count' $logFiles.Count
$confLines = [IO.File]::ReadAllLines((Join-Path $Data 'postgresql.conf'))
$mk = -1; for ($i = 0; $i -lt $confLines.Length; $i++) { if ($confLines[$i] -like '# --- HGS2 isolated test cluster*') { $mk = $i; break } }
Assert-Guard ($mk -ge 0) 'S2.4 conf blogu bulunamadi'
$confBlock = $confLines[$mk..($confLines.Length - 1)]

$scanFiles = @(Get-ChildItem -LiteralPath $Evidence -Recurse -File) + $logFiles
$pgpassLines = @([IO.File]::ReadAllLines((Join-Path $Root 'cfg\pgpass.conf')) | Where-Object { $_ -ne '' })
Note 'pgpass_entry_roles' (($pgpassLines | ForEach-Object { ($_ -split ':')[3] }) -join ',')
$secretHits = 0
foreach ($pl in $pgpassLines) {
    $sec = (($pl -split ':')[4..(($pl -split ':').Length - 1)]) -join ':'
    Assert-Guard ($sec.Length -ge 16) 'pgpass satiri beklenen bicimde degil'
    $secretHits += @($scanFiles | Select-String -SimpleMatch -Pattern $sec).Count
    $secretHits += @($confBlock | Select-String -SimpleMatch -Pattern $sec).Count
    $sec = $null
}
$pgpassLines = $null
Note 'secret_scan_pgpass_derived_hits' $secretHits
$keyHits = @($scanFiles | Select-String -SimpleMatch -Pattern 'PRIVATE KEY').Count + @($confBlock | Select-String -SimpleMatch -Pattern 'PRIVATE KEY').Count
Note 'secret_scan_private_key_hits' $keyHits
$pgpassFmtHits = @($scanFiles | Select-String -Pattern '^\*:\d+:\*:').Count
Note 'secret_scan_pgpass_format_hits' $pgpassFmtHits
Assert-Guard (($secretHits -eq 0) -and ($keyHits -eq 0) -and ($pgpassFmtHits -eq 0)) 'kanitta gizli bilgi - ARSIVLEME YAPMA'

# --- Arsiv (ayri dizin: role-design\iso-runs-incomplete\<eski RunId>) ---
Assert-Guard (-not (Test-Path -LiteralPath $Archive)) 'arsiv klasoru zaten var'
Assert-Guard ([IO.Path]::GetFullPath($Archive).StartsWith([IO.Path]::GetFullPath($ArchParent) + '\', [StringComparison]::OrdinalIgnoreCase)) 'arsiv hedefi iso-runs-incomplete altinda degil'
New-Item -ItemType Directory -Force -Path $Archive, (Join-Path $Archive 'review') | Out-Null
Copy-Item -LiteralPath $Evidence -Destination (Join-Path $Archive 'evidence') -Recurse
$srcH = @(Get-ChildItem -LiteralPath $Evidence -Recurse -File | ForEach-Object { (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash } | Sort-Object)
$dstH = @(Get-ChildItem -LiteralPath (Join-Path $Archive 'evidence') -Recurse -File | ForEach-Object { (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash } | Sort-Object)
Assert-Guard (($srcH.Count -eq $dstH.Count) -and (@(Compare-Object $srcH $dstH).Count -eq 0)) 'arsiv kopyasi kaynakla ayni degil'
Note 'archive_evidence_files' $srcH.Count
Set-Content -LiteralPath (Join-Path $Archive 'review\postgresql.conf.hgs2-block.txt') -Encoding ASCII -Value $confBlock

# Envanter: yalnizca ad ve boyut (gizli dosya ICERIGI yazilmaz)
$inv = New-Object System.Collections.Generic.List[string]
$inv.Add("# Eski test koku envanteri (icerik degil, yalnizca ad/boyut). Kok: $Root")
foreach ($sub in 'certs', 'cfg', 'evidence', 'log') {
    $p = Join-Path $Root $sub
    foreach ($f in @(Get-ChildItem -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue)) {
        $inv.Add(('{0}\{1}  {2}' -f $sub, $f.FullName.Substring($p.Length + 1), $(if ($f.PSIsContainer) { '<DIR>' } else { $f.Length })))
    }
}
$df = @(Get-ChildItem -LiteralPath $Data -Recurse -File -Force)
$inv.Add(('data\  dosya={0}  bayt={1}' -f $df.Count, ($df | Measure-Object -Property Length -Sum).Sum))
Set-Content -LiteralPath (Join-Path $Archive 'review\root-inventory.txt') -Encoding ASCII -Value $inv
Note 'certs_cfg_archived' 'HAYIR (ozel anahtar ve pgpass arsive kopyalanmadi)'

# --- 10.4 kapilari (eski RunId icin) ---
$Deleted = $false
try {
    $RootFull  = [IO.Path]::GetFullPath($Root)
    $IsoParent = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hgs2-iso'))
    Assert-Guard ($RootFull -match '\\hgs2-iso\\iso18-\d{8}T\d{6}$') 'silme hedefi RunId bicimine uymuyor'
    Assert-Guard ([IO.Path]::GetDirectoryName($RootFull) -eq $IsoParent) 'silme hedefi hgs2-iso altinda degil'
    Assert-Guard (-not $RootFull.StartsWith('C:\Program Files', [StringComparison]::OrdinalIgnoreCase)) 'silme hedefi Program Files altinda'
    Assert-Guard (-not $RootFull.StartsWith([IO.Path]::GetFullPath($Base), [StringComparison]::OrdinalIgnoreCase)) 'silme hedefi proje klasoru icinde'
    Assert-Guard (-not ((Get-Location).Path.StartsWith($RootFull, [StringComparison]::OrdinalIgnoreCase))) 'calisma dizini silinecek kokun icinde'
    Assert-Guard (Test-Path -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt')) 'arsiv yok - silme yapilmaz'
    Assert-Guard ((Get-TestPostmasterCount) -eq 0) 'test postmaster calisiyor - silme yapilmaz'
    Assert-Guard (-not (Test-Path -LiteralPath (Join-Path $Data 'postmaster.pid'))) 'postmaster.pid var - silme yapilmaz'
    "SILINECEK: $RootFull"
    # RunId onayi: hedefin yaprak adi, gorev metninde verilen RunId ile birebir ayni olmali
    Assert-Guard ((Split-Path -Leaf $RootFull) -ceq $OldRunId) 'onay verilmedi - RunId eslesmiyor'
    Note 'gates_10_4' 'PASS (7 kapi + postmaster.pid + RunId onayi)'

    Remove-Item -LiteralPath (Join-Path $Root 'cfg\pgpass.conf') -Force   # YIKICI: yalnizca eski test pgpass
    Remove-Item -LiteralPath $Root -Recurse -Force                        # YIKICI: yalnizca eski RunId test koku
    Assert-Guard (-not (Test-Path -LiteralPath $Root)) 'test koku silinemedi'
    $Deleted = $true
} catch {
    Note 'gates_10_4_or_delete_error' $_.Exception.Message
}
Note 'old_root_removed' $Deleted
Note 'old_root_exists_after' (Test-Path -LiteralPath $Root)

# --- Bitis: canli servis karsilastirmasi ---
$Live1 = Get-LiveSnapshot; $Live5432_1 = Get-Live5432
$liveSame = ($Live1.State -eq $Live0.State) -and ($Live1.Pid -eq $Live0.Pid) -and ($Live1.Created -eq $Live0.Created) -and ($Live1.PathName -eq $Live0.PathName) -and ($Live5432_1 -eq $Live5432_0)
Note 'live_end' ("State={0} Pid={1} Created={2}" -f $Live1.State, $Live1.Pid, $Live1.Created)
Note 'live5432_end' $Live5432_1
Note 'live_unchanged_during_closeout' $liveSame
$R.GetEnumerator() | ForEach-Object { '{0} = {1}' -f $_.Key, $_.Value } | Set-Content -LiteralPath (Join-Path $Archive 'review\closeout-results.txt') -Encoding ASCII
Assert-Guard $liveSame 'CANLI SERVIS DEGISTI - DUR, MUDAHALE ETME, RAPORLA'
'CLOSEOUT_DONE'
