"""Builds runner_v1_single_session.ps1 from EXECUTION_RUNBOOK_V1.md powershell blocks (verbatim) + additive adaptations.
Usage: py -3.13 -I build_runner.py <runbook.md> <out_dir>
"""
import hashlib, sys, os

runbook, outdir = sys.argv[1], sys.argv[2]
raw = open(runbook, 'rb').read()
lines = raw.decode('utf-8').split('\n')
blocks = []
i = 0
while i < len(lines):
    if lines[i] == '```powershell':
        s = i + 1; e = s
        while lines[e] != '```':
            e += 1
        blocks.append((s + 1, e, '\n'.join(lines[s:e])))
        i = e
    i += 1
assert len(blocks) == 22, len(blocks)
names = ['S0', 'S1', 'S2.1', 'S2.2', 'S2.3', 'S2.4', 'S2.5', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9',
         'S10.1', 'S10.2', 'S10.3', 'S10.4', 'S10.4-erteleme', 'S11', 'S12.2', 'S12.3']

SUB_PM = ('$_.CommandLine -like "*$Data*"', '(Test-CmdLineHasData $_.CommandLine)')
SUB_CL = ('$cl -like "*$Data*"', '(Test-CmdLineHasData $cl)')
def subst(n, b):
    c1 = b.count(SUB_PM[0]); c2 = b.count(SUB_CL[0])
    return b.replace(SUB_PM[0], SUB_PM[1]).replace(SUB_CL[0], SUB_CL[1]), c1 + c2
READ_HOST = "$confirm = Read-Host \"Silmek icin RunId'yi aynen yazin ($RunId)\""
assert blocks[17][2].count(READ_HOST) == 1

HEADER = r'''param([Parameter(Mandatory = $true)][string]$ConfirmFile,
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
'''

A0 = r'''
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
'''

LC_DEF = r'''
# [A-R1-8] ---- komut satiri / veri dizini karsilastirmasi: pg_ctl yolu '/' ile kanoniklestirir (postmaster.opts kaniti) ----
# Ayni anlam, iki ayirici bicimi de kabul edilir; bos komut satiri (baska kullanicinin sureci) asla eslesmez.
function Test-CmdLineHasData([string]$CommandLine) {
    if ([string]::IsNullOrEmpty($CommandLine)) { return $false }
    return ($CommandLine.Replace([char]47, [char]92).IndexOf([IO.Path]::GetFullPath($Data), [StringComparison]::OrdinalIgnoreCase) -ge 0)
}
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
'''

A21 = r'''
# [A2.1] ---- calistirici, blok kaynaklari ve arac surumleri kanita (ek) ----
# EK R1-9: betigin kendisi kanita KOPYALANMAZ (10.2 tarama sabitini icerir); yalnizca SHA-256'si yazilir, betik kosu sonrasi arsive eklenir
Write-TestFile (Join-Path $Inputs 'runner_v1_single_session.sha256') (((Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash.ToLower()) + '  runner_v1_single_session.ps1' + "`n")
Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $PSCommandPath) 'runner_provenance.txt') -Destination (Join-Path $Inputs 'runner_provenance.txt')
Write-TestFile (Join-Path $Inputs 'toolchain.txt') (($__tool -join "`n") + "`n")
'''

A25 = r'''
# [A2.5] ---- 55438 port/PID kaniti (ek) ----
$__pp = foreach ($l in $listen) {
    $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$($l.OwningProcess)").CommandLine
    '{0}:{1} pid={2} test_postmaster={3}' -f $l.LocalAddress, $l.LocalPort, $l.OwningProcess, (Test-CmdLineHasData $cl)
}
Write-TestFile (Join-Path $Evidence 'S2-port-pid.txt') ((@($__pp) + "live_5432: $(Get-Live5432)" + "live_service_pid: $($Live0.Pid)") -join "`n")
'''

A101 = r'''
# [A10.1] ---- port/surec serbest kaniti (ek) ----
$__pf1 = @(Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue).Count
$__pf2 = @(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { Test-CmdLineHasData $_.CommandLine }).Count
Write-TestFile (Join-Path $Evidence 'S10.1-port-free.txt') (@("port_${TestPort}_listen_count: $__pf1", "test_postmaster_count: $__pf2", "live_5432: $(Get-Live5432)") -join "`n")
'''

WAIT_FN = r'''
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
'''

DEL_TAIL = r'''
$__delOk = $true
} catch {
    "10.4 SILME YAPILMADI: $($_.Exception.Message)"
    if (Test-Path -LiteralPath $Root) {
'''

DEL_END = r'''
    } else {
        Add-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt') -Encoding ASCII -Value ('{0} S10.4-root-removed FAIL {1}' -f (Get-Date -Format 'o'), ($_.Exception.Message -replace '[^\x20-\x7E]', '?'))
    }
}
'''

ATS = r'''
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
'''

FOOTER = r'''
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
'''

def lc(label):
    return f"\nSave-LiveCheckpoint '{label}'   # [LC]\n"

def banner(n):
    s, e, _ = blocks[n]
    return f"\n# ======== RUNBOOK BLOK {n} ({names[n]}) - EXECUTION_RUNBOOK_V1.md L{s}-L{e} - AYNEN ========\n'===== {names[n]} ====='\n"

out = [HEADER]
prov = ['# runner_v1_single_session.ps1 kaynak kaydi',
        f'runbook_sha256={hashlib.sha256(raw).hexdigest()}', 'blok  asama  runbook_satirlari  sha256(blok)  kullanim']
def use(n, how):
    s, e, b = blocks[n]
    prov.append(f'{n}  {names[n]}  L{s}-L{e}  {hashlib.sha256(b.encode()).hexdigest()}  {how}')

out += [banner(0), blocks[0][2], A0]; use(0, 'AYNEN')
out += [banner(1), blocks[1][2], LC_DEF]; use(1, 'AYNEN')
out += [banner(2), blocks[2][2], A21, lc('after-S2.1')]; use(2, 'AYNEN')
for n in (3, 4, 5):
    out += [banner(n), blocks[n][2], lc('after-' + names[n])]; use(n, 'AYNEN')
b6, k6 = subst(6, blocks[6][2]); assert k6 == 2
out += [banner(6), b6, A25, lc('after-S2.5')]; use(6, 'AYNEN, EK R1-8 ikamesi x2: CommandLine/cl -like *$Data* -> Test-CmdLineHasData')
for n in range(7, 14):
    out += [banner(n), blocks[n][2], lc('after-' + names[n])]; use(n, 'AYNEN')
b14, k14 = subst(14, blocks[14][2]); assert k14 == 1
out += [banner(14), b14, A101]; use(14, 'AYNEN, EK R1-8 ikamesi x1')
out += [banner(15), blocks[15][2], lc('after-S10.2')]; use(15, 'AYNEN')
out += [banner(16), blocks[16][2], lc('after-S10.3')]; use(16, 'AYNEN')
b17, k17 = subst(17, blocks[17][2]); assert k17 == 1
b17 = b17.replace(READ_HOST, "$confirm = Wait-DeleteConfirmation   # [A10.4] runbook: " + READ_HOST.replace('"', "'"))
out += [WAIT_FN, banner(17), b17, DEL_TAIL, banner(18), blocks[18][2], DEL_END]
use(17, 'AYNEN, Read-Host -> Wait-DeleteConfirmation; EK R1-8 ikamesi x1; blok try/catch icinde')
use(18, 'AYNEN, yalnizca 10.4 kapi/silme hatasinda ve test koku hala varken calisir')
out += [ATS, banner(19), blocks[19][2]]; use(19, 'AYNEN')
use(20, 'KULLANILMADI (acil durum; [A-ERR] yalnizca -m fast stop uygular)')
use(21, 'KULLANILMADI (oturum kaybi proseduru)')
out.append(FOOTER)

runner = '\n'.join(out).replace('\r\n', '\n').replace('\n', '\r\n')
assert all(ord(c) < 128 for c in runner)
for n in [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 15, 16, 18, 19]:
    assert blocks[n][2].replace('\n', '\r\n') in runner, n
assert '*$Data*' not in runner
open(os.path.join(outdir, 'runner_v1_single_session.ps1'), 'w', encoding='ascii', newline='').write(runner)
open(os.path.join(outdir, 'runner_provenance.txt'), 'w', encoding='ascii', newline='\r\n').write('\n'.join(prov) + '\n')
print('ok', len(runner.splitlines()), 'lines')
