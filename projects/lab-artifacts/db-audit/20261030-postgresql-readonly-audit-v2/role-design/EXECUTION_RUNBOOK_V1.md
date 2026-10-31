# EXECUTION_RUNBOOK_V1 — `hgs2_audit` izole küme ilk çalışan sürüm uygulama kılavuzu

- Proje: HGS2 PostgreSQL Read-Only Audit V2
- Tarih: 2026-10-30 (+03:00)
- Durum: **KILAVUZ — hiçbir adım çalıştırılmadı.** Bu belge hazırlanırken PostgreSQL'e bağlanılmadı; psql, SQL veya PowerShell komutu çalıştırılmadı.
- Dayanak: `role-design\ISOLATED_CLUSTER_TEST_PLAN.md` (bundan sonra **plan**) ve `role-design\AUDIT_ROLE_PRIVILEGE_MATRIX.md` (bundan sonra **matris**). Bu iki dosyada değişiklik yapılmadı.
- Denetlenen nihai SQL: `asama3-final\postgresql_readonly_audit_v2.sql`, SHA-256 `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`.
  - **Uyarı:** Kök klasördeki aynı adlı `postgresql_readonly_audit_v2.sql` 2. aşama sürümüdür. **Kullanılmaz.**

---

## 0. Bu kılavuz nedir, ne değildir

### 0.1 Amaç

- Planın teknik tasarımını **değiştirmeden**, ilk teslim edilebilir sürüm (V1) için gereken asgari adımları sırayla vermek.
- Her aşama şu bölümleri içerir: amaç, çalışma dizini, tam PowerShell komutları, beklenen çıktı, durma noktası ve geçiş koşulu.

### 0.2 V1 zorunlu kapsamı

| Aşama | İş | Planda karşılığı |
|---|---|---|
| 0 | Hazırlık ve salt okunur ön kontroller | §5.1 G4, R-N8 |
| 1 | Canlı servisin başlangıç durumunu kaydetme | §5.1 (G1–G5) |
| 2 | PostgreSQL 18.6 ile port 55438'de ayrı veri dizinli geçici küme | §4.1, §5.2–§5.6 |
| 3 | Sentetik HGS2 veritabanı | §4.2 |
| 4 | Ayrı ve minimum yetkili `hgs2_audit` rolü | §3.1, §3.3 (test kümesi, yol b), matris §11 |
| 5 | Bağımsız rol yetki doğrulaması | §7 ortak kurallar ("Rol doğrulaması"), T1 (b)(c) |
| 6 | Nihai SQL ile denetim | T1 (a) |
| 7 | `validate_audit_result.py` ile sonuç doğrulama | T1 (a), §5.7 |
| 8 | `hgs2_audit` → `hibrit_giris_db` erişim engeli | T8-a (yalnızca IPv4) |
| 9 | `hgs2_perftest` 42501 davranışının korunması | T8-d, C10, C11 |
| 10 | Kümeyi güvenli kapatma ve kanıtları saklama | §9.2 |
| 11 | Son kontrol: SHA-256 ve canlı servis başlangıç/bitiş karşılaştırması | §9.1 (3), Ek B |

### 0.3 V1'de zorunlu olmayanlar (planda aynen kalır, silinmedi)

Aşağıdakiler planın parçası olmaya devam eder. Yalnızca V1 teslimatında zorunlu değildir:

- **T2–T5** (üyelik, tablo SELECT, sahiplik, CREATE ihlali negatif senaryoları), **T6**, **T7**.
- **T8-b / T8-c / T8-e** (OPEN ve MISORDER pg_hba varyantları, PUBLIC CONNECT açma).
- **T9** (IPv6 bağlantı testleri), **T10** (varyant B / `hostssl`, `verify-full`, sahte CA, `channel_binding`, `ssl = off`).
- **RC-02, RC-04, RC-05** rol oluşturma negatif testleri.
- `golden-base` / `golden-role` kopyaları ve `Restore-Golden`. V1'de veriyi değiştiren bir senaryo olmadığı için gerekmez.

### 0.4 Plan ile V1 arasındaki uygulama farkları (tasarım değişikliği değildir)

| Konu | V1 uygulaması | Gerekçe |
|---|---|---|
| pg_hba | Yalnızca **varyant A** tanımlanır (plan §5.6'daki satırlar, aynen) | Diğer varyantlar yalnızca T8-b/e, T9, T10 içindir |
| TLS | Sunucu sertifikası ve CA oluşturulur (plan §5.4). Sahte CA (`rogue`) **oluşturulmaz** | Sahte CA yalnızca T10-d içindir. `ssl = on` ve `sslmode=require` T1'in temel çizgisidir |
| `listen_addresses` | Plandaki gibi `'127.0.0.1,::1'` kalır | Tasarım değişmez. IPv6 bağlantısı V1'de **sınanmaz** |
| Test rol parolaları | Plan §3.3 "Test kümesi için" **yol (b)**: `\getenv` + `SET log_statement = 'none'` | Otomatik ve tekrarlanabilir. Parola komut satırına, dosyaya veya günlüğe girmez |
| Rol oluşturma SQL'i | Matris §11 taslağı, ilk iki satırı (`\echo` + `\quit`) çıkarılmış **onaylı kopya** olarak. Kopyanın SHA-256'sı kanıta yazılır | Plan §3.1 "Ayrı yönetici onayı" kuralı |
| Rol doğrulaması | Matris §11 §6–§9 ölçütleri ve T1 kontrol sorgusu ayrı, **salt okunur** bir dosyada (`BEGIN READ ONLY … ROLLBACK`) | Plan §7: "§1–§5 ve COMMIT olmadan" |
| Ek kapılar | Komut çıkış kodu denetimleri, BOM'suz dosya yazımı, silme hedefi için RunId biçim kapısı, kanıtta parola taraması | Yalnızca güvenliği artırır. Plandaki kapıların hiçbiri gevşetilmedi |

### 0.5 Değişmez güvenlik kuralları

1. Gerçek PostgreSQL servisi (`postgresql-x64-18`, port **5432**) **hiçbir aşamada** başlatılmaz, durdurulmaz, yeniden başlatılmaz veya yeniden yapılandırılmaz.
2. `C:\Program Files\PostgreSQL\18\data` altındaki hiçbir dosya okunmaz veya yazılmaz. Gerçek `pg_hba.conf` dahil.
3. Gerçek `hibrit_giris_db` ve `hgs2_perftest_db` veritabanlarına **bağlanılmaz**. Tüm bağlantılar `port=55438` ve loopback adresiyle yapılır. Bu kuralı `Assert-TestConn` kapısı uygular.
4. Test parolaları her çalıştırmada rastgele üretilir. Gerçek parolalarla hiçbir ilişkileri yoktur. Yalnızca port kapsamlı (`*:55438:*:…`) geçici `pgpass.conf` dosyasında tutulur.
5. Gerçek kümeye geçiş bu kılavuzun kapsamında **değildir**. Geçiş için plan §10'daki ön koşullar ve ayrı yönetici onayı gerekir.
6. Herhangi bir `GUARD:` hatası = **DUR**. Sonraki komuta geçilmez. §12 "Acil durum ve yarıda bırakma" uygulanır.

### 0.6 Komut işaretleri

| İşaret | Anlamı |
|---|---|
| 🟢 **SALT OKUNUR** | Hiçbir şey oluşturmaz veya değiştirmez |
| 🟡 **TEST KÖKÜNDE OLUŞTURUR** | Yalnızca `%LOCALAPPDATA%\hgs2-iso\<RunId>\` altında dosya veya süreç oluşturur. Kanıt arşivi için `role-design\iso-runs\<RunId>\` altına yazar |
| ⚠️ **YIKICI** | Dosya veya dizin siler ya da süreç durdurur. Hedef her zaman yalnızca geçici test köküdür ve komuttan önce kapıyla doğrulanır |

### 0.7 Çalışma ortamı kuralları

- **Windows PowerShell 5.1** (`powershell.exe`) **konsol** penceresi kullanılır. PowerShell ISE veya PowerShell 7 kullanılmaz.
  - ISE'de yerel komutların stderr çıktısı hata kaydına dönüşür ve `$ErrorActionPreference = 'Stop'` ile yanlış durmalara yol açar.
- Pencere **yönetici olarak açılmaz** (elevated değil). Plan G1 kapısı bunu denetler.
- Tüm aşamalar **aynı pencerede, sırayla** çalıştırılır. Fonksiyonlar ve değişkenler (`$Live0`, `$Root`, `$TestSecrets` …) yalnızca bu oturumda yaşar.
- Pencere kapanırsa veya oturum kaybolursa çalıştırma **devam ettirilmez**; §12.3 uygulanır.
- Kod blokları blok blok yapıştırılır. Her bloktan sonra çıktı okunur ve "Geçiş koşulu" kontrol edilir.

---

## Aşama 0 — Hazırlık ve salt okunur ön kontroller

**Amaç:** Araçların varlığını, sürümlerini ve korunacak üç dosyanın başlangıç SHA-256 değerlerini kaydetmek. Port 55438'in Windows tarafından ayrılmış bir aralıkta olmadığını görmek (plan R-N8).

**Çalışma dizini:** `C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\db-audit\20261030-postgresql-readonly-audit-v2` (bu blok `Set-Location` ile ayarlar; sonraki tüm aşamalar burada kalır).

**Komutlar** 🟢 SALT OKUNUR

```powershell
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
```

**Beklenen çıktı**

| Kontrol | Beklenen |
|---|---|
| `PSVersion` | `5.1.x` |
| `$Host.Name` | `ConsoleHost` |
| Final SQL SHA-256 | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` |
| Plan SHA-256 (bu kılavuz yazılırken ölçüldü) | `398889d315187e965bb555f2fa72ba92f7bfcb341d5cca50dfdaa96a822cf389` |
| Matris SHA-256 (bu kılavuz yazılırken ölçüldü) | `5733d45fa265309089a417c2e2653d2564f63783df854b78316447c11694bd7b` |
| `postgres.exe --version` | `postgres (PostgreSQL) 18.6` |
| `psql.exe --version` | `psql (PostgreSQL) 18.x` |
| `py -3.13 --version` | `Python 3.13.x` |
| `openssl version` | `OpenSSL 1.1.1` veya `3.x` (`-addext` desteği gerekir) |
| `excludedportrange` | Listelenen aralıkların hiçbiri **55438**'i kapsamıyor |
| `hgs2-iso` / `iso-runs` | Bilgi amaçlıdır; `True` olabilir. Bu RunId'ye ait klasör henüz yoktur |

**Durma noktası**

- Final SQL hash'i farklıysa **DUR**. Dosya değişmiştir; denetim yapılmaz.
- Plan veya matris hash'i yukarıdaki değerden farklıysa **DUR**. Kılavuz yazıldıktan sonra değişmişlerdir. Bu kılavuzun hâlâ geçerli olup olmadığı önce incelenir.
- Sürüm 18.6 değilse, `py -3.13` veya `openssl` yoksa **DUR**. Başka bir sürüm veya araç kullanmak ayrı bir karardır.
- 55438 ayrılmış aralıktaysa **DUR**. Port değişikliği planı değiştirir; ayrı karar gerekir. 5432 asla seçilmez.

**Geçiş koşulu:** Tüm satırlar beklenen değerde ve `$Hash0` oturumda tanımlı.

---

## Aşama 1 — Canlı PostgreSQL servisinin başlangıç durumunu kaydetme

**Amaç:**
- Plan §5.1'deki sabitleri, koruma kapılarını (G1–G5) ve canlı servis anlık görüntüsünü (`$Live0`) oluşturmak.
- Canlı servisin PID'sini, süreç oluşturma zamanını, yürütme yolunu ve 5432 dinleyicilerini **yalnızca Windows CIM üzerinden okuyarak** kaydetmek.
- Veritabanına bağlanılmaz.

**Çalışma dizini:** `$Base`

**Komutlar** 🟢 SALT OKUNUR — Plan §5.1, değiştirilmeden; ardından V1 eki.

```powershell
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
```

**Beklenen çıktı**

- Hiçbir `GUARD:` hatası yok.
- `$Live0` çıktısı:
  - `State : Running`
  - `Pid : <sayı>`. Plan yazılırken 4708 idi; bilgisayar yeniden başlatıldıysa farklı olabilir. Önemli olan, **başlangıç ile bitişin aynı** olmasıdır.
  - `Created : <ISO-8601 zaman>`
  - `PathName : "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" runservice -N "postgresql-x64-18" -D "C:\Program Files\PostgreSQL\18\data" -w`
- `5432 dinleyicileri:` en az bir satır, `pid=<postmaster>`. Plan yazılırken postmaster PID'si 6164 idi.
- `RunId` ve `Test koku` değerleri **not edilir**. §12.3'te gerekir.

**Durma noktası**

- `elevated olmayan PowerShell gerekli`: pencereyi kapat, normal kullanıcı olarak yeniden aç, Aşama 0'dan başla.
- `port 55438 dinleniyor`: **DUR**. Portu kimin kullandığı salt okunur incelenir. O süreç sonlandırılmaz.
- `canli servis Running degil`: **DUR**. Canlı servise müdahale edilmez. Başlangıç durumu bilinmeden devam edilmez.
- Diğer tüm `GUARD:` mesajları: **DUR**.

**Geçiş koşulu:** Kapılar geçti. `$Live0`, `$Live5432_0` ve `$RunId` ekranda görüldü ve not edildi.

---

## Aşama 2 — PostgreSQL 18.6 ile port 55438'de geçici test kümesi

**Amaç:** Canlı kümeden tamamen ayrı veri dizinine (`%LOCALAPPDATA%\hgs2-iso\<RunId>\data`) sahip, servis kaydı olmayan, yalnızca loopback dinleyen geçici bir küme oluşturup başlatmak.

**Çalışma dizini:** `$Base`. Komutlar mutlak yol kullanır; tüm yazma hedefleri `$Root` altındadır.

### 2.1 Ortam yalıtımı, dizinler, V1 yardımcıları ve başlangıç kaydının yazılması

🟡 TEST KÖKÜNDE OLUŞTURUR — Plan §5.2, değiştirilmeden; ardından V1 eki.

```powershell
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
```

**Beklenen:**
- Dizin listesinde `cfg`, `certs`, `evidence`, `log` görünür.
- `evidence\` altında `live-start.json`, `live-start-5432.txt`, `integrity-start.sha256` ve `stage-results.txt` bulunur.

### 2.2 initdb (ayrı veri dizini, SCRAM, süper kullanıcı parola dosyası anında silinir)

🟡 TEST KÖKÜNDE OLUŞTURUR + ⚠️ YIKICI (sınırlı: yalnızca `$Cfg\initdb.pw`) — Plan §5.3 ve V1 kapıları.

```powershell
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
```

**Beklenen:**
- initdb çıktısı `Success. You can now start the database server using:` ile biter.
- `$Cfg\initdb.pw` artık yoktur.
- `SysId:` uzun bir sayıdır.

### 2.3 Sentetik TLS sertifikaları (yalnızca CA ve sunucu)

🟡 TEST KÖKÜNDE OLUŞTURUR — Plan §5.4. Sahte CA satırı V1'de çalıştırılmaz. Çıkış kodu kapıları V1 ekidir.

```powershell
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
```

**Beklenen:** `ca.crt`, `ca.key`, `server.crt`, `server.key`, `server.csr`, `server_ext.cnf` ve `ca.srl` dosyaları oluşur. openssl'in stderr'e yazdığı ilerleme noktaları normaldir.

### 2.4 postgresql.conf ekleri

🟡 TEST KÖKÜNDE OLUŞTURUR — Plan §5.5, değiştirilmeden; yalnızca hedef kapısı eklendi.

```powershell
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
```

### 2.5 pg_hba varyant A, başlatma ve kimlik doğrulaması

🟡 TEST KÖKÜNDE OLUŞTURUR (test postmaster süreci başlar) — Plan §5.6 (yalnızca varyant A) ve §5.7, değiştirilmeden; ardından V1 kontrolleri.

```powershell
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
```

**Beklenen çıktı**

- `pg_ctl`: `waiting for server to start.... done` ve `server started`.
- `S2-identity` stdout (tek satır):
  `PostgreSQL 18.6, compiled by …|55438|hgs2iso18|on|C:/Users/…/hgs2-iso/<RunId>/data`
  - `data_directory` ayırıcısı `\` veya `/` olabilir.
- `args.txt` içinde bağlantı dizesi ve `-c` sorgusu **tek tırnaklı argüman** olarak görünür:
  `-X -v ON_ERROR_STOP=1 -d "host=127.0.0.1 port=55438 …" -w -At -c "select version(), …"`
  - Bu, plan R-N7'nin ilk kuru doğrulamasıdır.
- 55438 dinleyicileri:
  - Beklenen: `127.0.0.1` ve `::1`.
  - IPv6 devre dışıysa yalnızca `127.0.0.1` görünür ve günlükte `could not bind IPv6 address` uyarısı yer alır. V1'de IPv6 sınanmadığı için bu kabul edilir ve kayda geçer.
  - Her dinleyicinin sahibi test postmaster'dır.
- Günlüğün son satırlarında `database system is ready to accept connections` yer alır.

**Durma noktası**

- `pg_ctl start` başarısız olursa `$LogFile` okunur.
  - PG 18'de `log_connections = on` kabul edilmezse sunucu başlamaz (plan §5.5 notu, R-N11). **DUR.** Ayar değişikliği plan değişikliğidir ve ayrı karar gerektirir.
- `CANLI SERVIS DEGISTI` mesajı görülürse **DUR**; §12.1 uygulanır.
- `args.txt` tırnaklaması bozuksa **DUR**. Örneğin bağlantı dizesi parçalara bölünmüşse sonraki aşamalara geçilmez.
- `55438 dinleyicisi test postmaster degil` mesajı görülürse **DUR** ve test kümesi durdurulur (§12.2).

**Geçiş koşulu:** `stage-results.txt` içinde `S2-cluster PASS` satırı var ve tüm kapılar geçti.

---

## Aşama 3 — Sentetik HGS2 veritabanının hazırlanması

**Amaç:**
- Plan §4.2'deki mantıksal fixture'ı test kümesinde oluşturmak:
  - `hgs2_perftest` rolü (test parolasıyla);
  - `hgs2_perftest_db` (sahibi `hgs2_perftest`);
  - boş `hibrit_giris_db` (PUBLIC CONNECT kaldırılmış);
  - `other_db`;
  - `admins` / `devices` / `users` / `logs` tabloları ve sentetik satırlar.
- Önceki harness'teki ek ACL, RLS, LO, extension ve default privilege satırları **eklenmez** (plan §4.2).

**Çalışma dizini:** `$Base`

🟡 TEST KÖKÜNDE OLUŞTURUR (SQL dosyaları `evidence\00-inputs\` altına yazılır; nesneler yalnızca 55438 kümesinde oluşur).

```powershell
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
```

**Beklenen çıktı**

- `S3-fixture-global` stdout'unda komut etiketleri (`CREATE ROLE`, `CREATE DATABASE` ×3, `REVOKE`) ve şu veritabanı listesi bulunur:

  | datname | owner | datacl |
  |---|---|---|
  | `hgs2_perftest_db` | `hgs2_perftest` | boş (NULL) |
  | `hibrit_giris_db` | `postgres` | `{=T/postgres,postgres=CTc/postgres}`; PUBLIC'te `c` (CONNECT) **yok** |
  | `other_db` | `postgres` | boş |
  | `postgres`, `template0`, `template1` | `postgres` | initdb varsayılanı |

- `S3-fixture-db` stdout'unda 4 tablo (`admins`, `devices`, `logs`, `users`) yer alır. Sahip `hgs2_perftest`, `relacl` boştur.
- `S3-perftest-password` çıkış 0; stdout'ta `SET`, `SET`, `ALTER ROLE`, `RESET`, `RESET`.
- Hiçbir stdout'ta `DUR:` satırı yok.

**Durma noktası**

- Bir fixture `DUR:` yazarsa veya çıkış kodu 0 değilse **DUR**. Örneğin `division by zero` görülmesi bağlantının izole kümede olmadığını gösterir. `stderr.txt` incelenir.
- Parola atama çıkışı 0 değilse **DUR**. `HGS2_ISO_PW` tanımsız kaldıysa SQL sözdizimi hatası beklenir; bu, kapının bilinçli olarak fail-closed çalıştığını gösterir.

**Geçiş koşulu:** `S3-fixture PASS` kaydı var. `hibrit_giris_db` PUBLIC CONNECT'siz. Tablolar `hgs2_perftest` sahipliğinde.

---

## Aşama 4 — Ayrı ve minimum yetkili `hgs2_audit` rolünün oluşturulması

**Amaç:**
- Matris §11 taslağını **değiştirmeden**, yalnızca başındaki `\echo` + `\quit` iki satırı çıkarılmış onaylı kopya olarak test kümesinde süper kullanıcıyla çalıştırmak (plan §3.1, RC-01).
- Ardından `hgs2_audit`'e rastgele test parolası vermek (plan §3.3 yol b).
- Stok PG 18.6'da **hiç GRANT üretilmemesi** beklenir.

**Çalışma dizini:** `$Base`

**Ön koşul:** pg_hba varyant A yüklü (Aşama 2.5). Taslağın §9.2 `hba_hibrit_rejected` kontrolü buna dayanır.

🟢 Matris dosyası yalnızca **okunur**. 🟡 Onaylı kopya `evidence\00-inputs\` altına yazılır. Rol yalnızca 55438 kümesinde oluşur.

```powershell
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
```

**Beklenen çıktı** (`S4-role-create` stdout, sıra ile; komut etiketleri `BEGIN`, `SET`, `CREATE ROLE`, `COMMIT` araya karışır)

```text
BILGI: hgs2_perftest_db CONNECT PUBLIC uzerinden mevcut; GRANT uretilmedi.
BILGI: public USAGE PUBLIC uzerinden mevcut; GRANT uretilmedi.
eksik katalog SELECT: -
pg_control_system proacl: NULL (stok: PUBLIC EXECUTE)
BILGI: pg_control_system EXECUTE PUBLIC uzerinden mevcut; GRANT uretilmedi.
eksik/cozulemeyen fonksiyon EXECUTE: -
attrs_ok= t  no_db_create= t  has_db_temporary= t  no_schema_create= t
user_rel_access_count= 0  lo_compat_off= t  lo_public_or_audit_count= 0
defacl_risk_count= 0  secdef_callable_count= 0  role_setting_count= 0  parameter_acl_count= 0
(§8 'a' listesi: 0 satir)
(§9.1 tablosu: hgs2_perftest_db acl_connect=t, hibrit_giris_db acl_connect=f)
(§9.2 tablosu: hgs2_perftest_db -> scram-sha-256, diger tum DB'ler -> reject)
HGS2_ROLE_DESIGN_OK: dogrulamalar gecti; COMMIT
KAYIT: has_db_temporary= t  secdef_callable_count= 0  hibrit_acl_closed= t
```

Ek beklentiler:
- `S4-password-check`: `hgs2_audit|SCRAM-SHA-256$` ve `hgs2_perftest|SCRAM-SHA-256$`.
- Sunucu günlüğünde `ALTER ROLE … PASSWORD` satırı yok.
- `has_db_temporary = t`, PUBLIC TEMPORARY artığıdır. Matris R10 gereği yalnızca **kayda geçer**; V1'i durdurmaz.

**Durma noktası**

- `DUR:` veya `HGS2_ROLE_DESIGN_FAIL` görülürse **DUR**.
  - Taslak `ROLLBACK` yapar ve rol oluşmaz. Ancak psql çıkış kodu yine **0** olabilir. Bu yüzden karar çıkış koduna değil, işaretçi satırlarına göre verilir.
- `BILGI` satırlarından biri "veriliyor" diyorsa (yani GRANT üretildiyse) **DUR**. Stok kümede beklenmez; fixture veya küme stok değildir.
- `ALTER ROLE … PASSWORD` günlükte görülürse **DUR**. Günlük kanıt arşivine alınmaz; §12 uygulanır.

**Geçiş koşulu:** `S4-role-create PASS` kaydı var, onaylı kopyanın SHA-256'sı kanıtta ve iki rolün parolası SCRAM biçiminde.

---

## Aşama 5 — Rolün bağımsız yetki doğrulaması

**Amaç:**
- Rol oluşturma betiğinden **bağımsız**, salt okunur bir doğrulamayla `hgs2_audit`'in aşağıdaki koşulları sağladığını kanıtlamak:
  - SUPERUSER değil ve diğer yönetim öznitelikleri yok;
  - rol üyeliği yok;
  - veritabanı veya şema sahipliği yok;
  - kullanıcı tablolarında SELECT yok;
  - gereksiz CREATE yok;
  - yalnızca gerekli bağlantı ve katalog okuma yetkileri var.
- Ölçütler matris §11 §6–§9'dan ve plan T1 kontrol sorgusundan alınmıştır.
- Ek olarak oturum düzeyinde üç negatif kontrol ve bir pozitif bağlantı kontrolü yapılır (plan T1 (c)).

**Çalışma dizini:** `$Base`

🟡 Doğrulama SQL'i `evidence\00-inputs\` altına yazılır. 🟢 Veritabanında `BEGIN READ ONLY … ROLLBACK` içinde çalışır; hiçbir şey değiştirmez.

```powershell
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
```

**Beklenen çıktı**

`S5-role-verify` stdout'unda:

```text
A not_superuser= t  attrs_ok= t
B no_member_of= t  no_members_in_audit= t  no_effective_membership= t  not_member_perftest= t  not_member_postgres= t
C no_owned_db= t  no_owned_schema_this_db= t  no_owner_shdep_records= t  no_other_shdeps= t  no_owned_tablespace= t
D user_rel_access_count= 0  no_select_users= t  lo_public_or_audit_count= 0  defacl_risk_count= 0
E no_db_create_any= t  no_schema_create= t  has_db_temporary(kayit)= t
F connect_target= t  hibrit_acl_closed= t  usage_pg_catalog= t  usage_public= t  ctrl_exec= t
F acl_ref_count= 0  role_setting_count= 0  parameter_acl_count= 0  lo_compat_off= t  secdef_callable_count(kayit)= 0
F catalogs_ok= t  eksik: -
F functions_ok= t  eksik: -
G hba_no_errors= t  hba_hibrit_rejected= t
HGS2_V1_ROLE_VERIFY_OK
```

Gereksinimlerle eşleşme:

| Gereksinim | Ölçüt (hepsi zorunlu) |
|---|---|
| SUPERUSER olmamalı | `not_superuser = t`, `attrs_ok = t` |
| Rol üyeliği bulunmamalı | B satırının tamamı `t` |
| Veritabanı sahipliği bulunmamalı | `no_owned_db = t` (`pg_database`; küme geneli, doğrudan) |
| Şema sahipliği bulunmamalı | `no_owned_schema_this_db = t`: **yalnızca `hgs2_perftest_db`** içinde doğrudan (`pg_namespace`). Ek olarak `no_owner_shdep_records = t`, `no_other_shdeps = t` ve `no_owned_tablespace = t` (aşağıdaki kapsam notuna bakın) |
| Kullanıcı tablolarında SELECT bulunmamalı | `user_rel_access_count = 0`, `no_select_users = t` |
| Gereksiz CREATE bulunmamalı | `no_db_create_any = t`, `no_schema_create = t` |
| Yalnızca gerekli bağlantı ve katalog okuma | Gerekli olanlar mevcut: `connect_target`, `usage_*`, `ctrl_exec`, `catalogs_ok`, `functions_ok` = `t`. Fazlası yok: `acl_ref_count = 0` (hiç doğrudan GRANT yok; hepsi PUBLIC'ten), `role_setting_count = parameter_acl_count = 0`. `hibrit_giris_db` ACL kapalı ve pg_hba ilk TCP kuralı `reject` |

**Sahiplik ölçütlerinin kapsam notu (C satırı):**
- Doğrudan katalog kontrolleri:
  - `no_owned_db` ve `no_owned_tablespace` paylaşılan kataloglardan okunur; kapsamları küme genelidir.
  - `no_owned_schema_this_db` yalnızca bu oturumun bağlı olduğu `hgs2_perftest_db` için geçerlidir.
- `no_owner_shdep_records` yalnızca `pg_shdepend` paylaşılan kataloğunda `hgs2_audit`'e ait sahiplik kaydı (`deptype = 'o'`) bulunmadığını gösterir. Bu kayıt **dolaylı bir göstergedir**:
  - Bu oturum `hibrit_giris_db`, `other_db`, `postgres` gibi diğer veritabanlarının `pg_namespace` ve `pg_class` kataloglarını okumaz.
  - Bu nedenle diğer veritabanlarındaki şema ve nesne sahipliği bu aşamada **doğrudan doğrulanmış sayılmaz**.
  - Raporda "tüm veritabanlarında sahiplik yok" diye yazılmaz. Doğru ifade şudur: "`hgs2_perftest_db`'de doğrudan sahiplik yok; paylaşılan bağımlılık kataloğunda sahiplik kaydı yok."
- V1 kapsamında diğer veritabanlarına ek bağlantı veya kontrol **eklenmez**. Bu sınır sonuç raporunda olduğu gibi belirtilir.

Diğer beklentiler:
- Veritabanı tablosunda `hgs2_perftest_db acl_connect = t` ve `hibrit_giris_db acl_connect = f` görünür.
  - `postgres`, `template0`, `template1` ve `other_db` için `t` görülmesi PUBLIC varsayılanıdır. Bu satırlar matris §9.1 gereği **kayda geçer**; yalnızca pg_hba R3 kuralıyla kapalıdırlar.
- `S5-pos-connect`: `hgs2_audit|hgs2_audit|hgs2_perftest_db|t`.
- Üç negatif kontrolün her biri:
  - çıkış kodu **0 değil** (psql `-c` hatasında genellikle `1`);
  - stderr'de `ERROR:  42501: permission denied …`:
    - `to set role "hgs2_perftest"`
    - `for table users`
    - `for schema public`

**Durma noktası**

- `HGS2_V1_ROLE_VERIFY_FAIL` görülürse veya çıkış 3 ise **DUR**. Hangi satırın `f` veya `> 0` olduğu kanıta yazılmıştır. Denetime (Aşama 6) **geçilmez**.
  - Plan §8'deki "Önemli yorum" gereği, rol doğrulaması geçmeden betiğin PASS sonucu minimum yetkiyi göstermez.
- Negatif kontrollerden biri başarılı olursa (çıkış 0) **DUR**. Bu bir ihlaldir. `S5-neg-create-table` başarılıysa test kümesinde `public.v1_probe` oluşmuş demektir. Küme geçicidir; yine de sonuç kayda geçer ve V1 başarısız sayılır.

**Geçiş koşulu:** `S5-role-verify PASS` kaydı var, `HGS2_V1_ROLE_VERIFY_OK` tam bir kez görüldü ve negatif kontrollerin üçü de 42501 verdi.

---

## Aşama 6 — Nihai `postgresql_readonly_audit_v2.sql` dosyasının çalıştırılması

**Amaç:** Nihai SQL'i, bütünlüğü yeniden doğrulandıktan sonra `hgs2_audit` ile test kümesinde çalıştırmak (plan T1 (a)). Bağlantı: `host=127.0.0.1`, `sslmode=require`, pg_hba varyant A.

**Çalışma dizini:** `$Base`

🟢 Nihai SQL dosyası yalnızca **okunur**. 🟡 Çıktılar `evidence\S6-audit-hgs2_audit\` altına yazılır.

```powershell
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
```

**Beklenen çıktı**

- `Final SQL SHA-256: 5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`
- `psql cikis: 0`
- `args.txt` içeriği:
  - `-d "host=127.0.0.1 port=55438 dbname=hgs2_perftest_db user=hgs2_audit sslmode=require"`;
  - beş `expected_*` değişkeni;
  - `-f "C:\Users\Ceng Zeki\…\asama3-final\postgresql_readonly_audit_v2.sql" -w`.
- İşaretçi satırları, sırayla:

  ```text
  HGS2_AUDIT_PREFLIGHT_OK
  tasima= tcp-loopback  istemci_host_sinifi= loopback  tls= t  tls_surum= TLSv1.3 …
  HGS2_AUDIT_COMPLETE
  ```

  - `tls_surum` değeri `TLSv1.2` de olabilir.
  - `HGS2_AUDIT_WARNING:` ve `HGS2_AUDIT_ABORT:` satırı **yok**.

**Durma noktası**

- `denetim SQL hash uyusmuyor` mesajı görülürse **DUR**. Denetim çalıştırılmaz.
- Çıkış 0 değilse kararı yine Aşama 7 verir; ancak V1 başarısızdır. Yaygın nedenler:
  - `HGS2_AUDIT_ABORT: system_identifier_mismatch` → `$SysId` yanlış alınmıştır.
  - `server_addr_mismatch` → bağlantı adresi uyuşmuyordur.
  - `insecure_transport` → TLS kurulmamıştır.
  - Çıkış 2 → kimlik doğrulama sorunu vardır; pgpass satırı denetlenir.

**Geçiş koşulu:** `S6-audit-run EXIT=0` kaydı var ve işaretçi satırları beklendiği gibi.

---

## Aşama 7 — `validate_audit_result.py` ile sonucun doğrulanması

**Amaç:** Denetim sonucunu yalnızca doğrulayıcının yedi kuralıyla karara bağlamak (FINAL_DELIVERY §7). Doğrulayıcı `Invoke-Audit` içinde zaten bir kez çalışıp `verdict.txt` yazdı. Burada çıkış kodunu da almak için **ayrıca ve açıkça** yeniden çalıştırılır.

**Çalışma dizini:** `$Base`

🟢 SALT OKUNUR (yalnızca `verdict-explicit.txt` yazılır).

```powershell
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
```

**Beklenen çıktı**

```text
PASS
validator cikis: 0
PASS
```

- Doğrulayıcı FAIL nedeni listelemez; denetim `stderr.txt` dosyası boştur.

**Durma noktası**

- `FAIL` görülürse **DUR**. `  - …` satırları nedeni verir. V1 başarısızdır.
  - Hiçbir uyarı `--accept-warning` ile kabul **edilmez**. Bu ancak yazılı kararla yapılabilir (FINAL_DELIVERY §5.10).
- Doğrulayıcı çıkışı `2` ise (kullanım hatası) **DUR**. Argüman yolları kontrol edilir.

**Geçiş koşulu:** `S7-validator PASS` kaydı var.

---

## Aşama 8 — `hgs2_audit` kullanıcısının `hibrit_giris_db` veritabanına erişemediğinin doğrulanması

**Amaç:** `hgs2_audit`'in test kümesindeki `hibrit_giris_db`'ye bağlantısının pg_hba katmanında **28000** ile reddedildiğini, hem TLS'siz hem TLS'li olarak IPv4 loopback üzerinden kanıtlamak (plan T8-a; IPv6 kısmı V1 dışı).

**Çalışma dizini:** `$Base`

🟢 Bağlantı denemesidir; kabul edilmesi beklenmez. Kanıt dosyaları yazılır.

```powershell
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
```

**Beklenen çıktı**

- `S8-audit-hibrit-disable: cikis=2`, stderr:
  `… FATAL:  pg_hba.conf rejects connection for host "127.0.0.1", user "hgs2_audit", database "hibrit_giris_db", no encryption`
- `S8-audit-hibrit-require: cikis=2`, stderr: aynı mesaj, sonu `SSL encryption`.
- `28000 satirlari: 2` (veya daha fazla), `oturum acilis satirlari: 0`.
- `S8-log-28000.txt`, `%e` alanında `28000` taşıyan FATAL satırlarını içerir.

**Durma noktası**

- Bağlantı kurulursa (çıkış 0) **DUR**. İzolasyon yoktur; V1 başarısızdır. pg_hba sıralaması (varyant A, `hgs2_audit` bloğu en üstte) kanıttan kontrol edilir.
- Çıkış 2 ama mesaj `permission denied for database` (42501) ise **DUR**. pg_hba katmanı devrede değildir; ret yalnızca ACL'den gelmektedir. Plan beklentisi 28000'dir.
- Günlükte 28000 satırı yoksa: `logging_collector` etkinse günlük `$Data\log\` altında olabilir. Yalnızca okuma amaçlı orada aranır. Yine bulunamazsa **DUR**.

**Geçiş koşulu:** `S8-audit-hibrit-blocked PASS` kaydı var.

---

## Aşama 9 — `hgs2_perftest` kullanıcısının mevcut 42501 davranışının korunduğunun doğrulanması

**Amaç:**
- `PerfTestSafetyGuard` uyumluluk kısıtını test kümesinde kanıtlamak (plan §6.5, T8-d, C10, C11).
- `hgs2_audit` pg_hba bloğu eklendikten sonra `hgs2_perftest` için iki koşul doğrulanır:
  - (a) kendi veritabanına bağlanabiliyor;
  - (b) `hibrit_giris_db` denemesi pg_hba (28000) veya kimlik doğrulama (28P01) ile değil, **yalnızca ACL ile 42501** olarak reddediliyor.

**Çalışma dizini:** `$Base`

🟢 Bağlantı denemeleri; değişiklik yok.

```powershell
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
```

**Beklenen çıktı**

- `hgs2_perftest|hgs2_perftest_db`
- `S9-perftest-hibrit: cikis=2`, stderr:
  `… FATAL:  permission denied for database "hibrit_giris_db"` + `DETAIL:  User does not have CONNECT privilege.`
- `42501 satirlari: 1` (veya daha fazla), `28000/28P01 satirlari: 0`.

**Durma noktası**

- 28000 (`pg_hba.conf rejects`) görülürse **DUR**. Önerilen pg_hba bloğu `hgs2_perftest`'i etkiliyordur ve gerçek ortamda perftest uygulamasını başlatılamaz hale getirir (plan R-N3).
- 28P01 görülürse **DUR**. Test parolası veya pgpass satırı hatalıdır; bu bir uyumluluk kanıtı değildir.
- Bağlantı kurulursa (çıkış 0) **DUR**. Fixture'daki `REVOKE CONNECT … FROM PUBLIC` uygulanmamıştır.

**Geçiş koşulu:** `S9-perftest-42501 PASS` kaydı var.

> Not: Bu aşama yalnızca **test kümesinde** davranışı kanıtlar. Gerçek kümede `hgs2_perftest`'in bugün 42501 aldığı **UNVERIFIED** kalır (plan §6.5, P5). Gerçek kümeye bağlanılmaz.

---

## Aşama 10 — Test kümesini güvenli şekilde kapatma ve kanıtları saklama

**Amaç:**
- Test postmaster'ı durdurmak ve sürecin ve portun serbest kaldığını doğrulamak.
- Kanıtta test parolası veya özel anahtar bulunmadığını taramak.
- Kanıtları `role-design\iso-runs\<RunId>\` altına arşivlemek (plan §9.2 önerisi).
- Ancak arşiv doğrulandıktan sonra geçici test kökünü silmek.

**Çalışma dizini:** `$Base`. Bu dizin test kökünün dışındadır; silme sırasında çalışma dizini test kökünde olmamalıdır.

### 10.1 Kümenin durdurulması

⚠️ YIKICI (yalnızca test postmaster süreci; `pg_ctl -D <test data>`).

```powershell
Stop-TestCluster
Assert-Guard (@(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count -eq 0) 'test postmaster hala calisiyor'
Assert-Guard ($null -eq (Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue)) "port $TestPort hala dinleniyor"
Assert-LiveUnchanged
Write-Stage 'S10.1-cluster-stopped' 'PASS'
```

**Beklenen:**
- `waiting for server to shut down.... done` ve `server stopped`.
- Hiçbir kapı hatası yok.
- Canlı servis değişmemiş.

### 10.2 Gizli bilgi taraması (arşivlemeden önce)

🟢 SALT OKUNUR

```powershell
$scanFiles = @(Get-ChildItem -LiteralPath $Evidence -Recurse -File) + @(Get-Item -LiteralPath $LogFile)
foreach ($k in @($TestSecrets.Keys)) {
    $hits = @($scanFiles | Select-String -SimpleMatch -Pattern $TestSecrets[$k])
    "parola taramasi ${k}: $($hits.Count) eslesme"
    Assert-Guard ($hits.Count -eq 0) "test parolasi ($k) kanit veya gunluk icinde bulundu - ARSIVLEME YAPMA"
}
$keyHits = @($scanFiles | Select-String -SimpleMatch -Pattern 'PRIVATE KEY')
Assert-Guard ($keyHits.Count -eq 0) 'kanitta ozel anahtar icerigi var - ARSIVLEME YAPMA'
Write-Stage 'S10.2-secret-scan' 'PASS'
```

**Beklenen:** `postgres`, `hgs2_perftest` ve `hgs2_audit` için `0 eslesme`. Özel anahtar eşleşmesi yok.

### 10.3 Kanıt arşivi

🟡 OLUŞTURUR: `role-design\iso-runs\<RunId>\` (yeni klasör; mevcut dosyalara dokunmaz). Yalnızca `evidence\` ve `log\postgres.log` kopyalanır. `cfg\` (pgpass) ve `certs\` (özel anahtarlar) **kopyalanmaz**.

```powershell
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
```

**Beklenen:** `Arsiv: …\role-design\iso-runs\iso18-<zaman>  dosya: <N>`; kapı hatası yok.

> Kanıt içeriği küme geneli rol, ACL ve ayar adlarını içerir. FINAL_DELIVERY §5.9 gereği **hassas yapılandırma bilgisi** olarak ele alınır. Sentetik kümeye aittir; gerçek veri içermez.

### 10.4 Geçici test kökünün silinmesi

⚠️ **YIKICI** — Yalnızca `%LOCALAPPDATA%\hgs2-iso\iso18-<yyyyMMddTHHmmss>` biçimindeki bu çalıştırmanın kökü silinir.
- Komuttan önce yedi kapı ve elle RunId onayı vardır.
- Arşiv doğrulanmadan **çalıştırılmaz**.
- Silme ertelenebilir. Bu durumda test kökü kullanıcı profilinde kalır, servis kaydı yoktur ve küme durdurulmuştur. **Ancak ertelenen bir çalıştırma V1 TAMAMLANMADI olarak raporlanır.**
  - Erteleme kararı aşağıdaki "Erteleme kaydı" bloğuyla kanıta yazılır. Bu blok hiçbir şey silmez.
  - Aşama 11 kanıt ve karşılaştırma için yine çalıştırılır. Test kökü yerinde olduğu sürece sonucu `SONUC: V1 TAMAMLANMADI` olur.
  - Silme daha sonra **aynı oturumda** yapılırsa, ana blok çalıştırılır ve ardından Aşama 11 yeniden çalıştırılır. Aşama 11 özeti ve manifesti yeniden yazar.
  - Oturum kapandıysa sonuç TAMAMLANMADI olarak kalır (§12.3).

```powershell
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
$confirm = Read-Host "Silmek icin RunId'yi aynen yazin ($RunId)"
Assert-Guard ($confirm -eq $RunId) 'onay verilmedi - silme yapilmadi'

Remove-Item -LiteralPath $env:PGPASSFILE -Force          # YIKICI: yalnizca test pgpass (cfg\pgpass.conf)
Remove-Item -LiteralPath $Root -Recurse -Force            # YIKICI: yalnizca bu RunId'nin test koku
Assert-Guard (-not (Test-Path -LiteralPath $Root)) 'test koku silinemedi'
foreach ($v in 'PGPASSFILE','PGSERVICEFILE','PGSYSCONFDIR','PSQLRC','PGCONNECT_TIMEOUT') { Remove-Item -LiteralPath "Env:$v" -ErrorAction SilentlyContinue }
Assert-LiveUnchanged
Add-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt') -Encoding ASCII -Value ('{0} S10.4-root-removed PASS' -f (Get-Date -Format 'o'))
```

**Erteleme kaydı** 🟢 Silme yapmaz. Yalnızca yukarıdaki blok **çalıştırılmadıysa** ve silme bilinçli olarak ertelendiyse kullanılır:

```powershell
Add-Content -LiteralPath (Join-Path $Archive 'evidence\stage-results.txt') -Encoding ASCII -Value ('{0} S10.4-root-removed DEFERRED root={1}' -f (Get-Date -Format 'o'), $Root)
```

**Beklenen:** `SILINECEK:` satırı `C:\Users\…\AppData\Local\hgs2-iso\iso18-…` yolunu gösterir. RunId onayından sonra kapı hatası olmaz.

**Durma noktası**

- Herhangi bir kapı hatasında veya RunId onayı verilmediğinde **silme yapılmaz**. Bu durum, ertelemeyle aynı şekilde V1 **TAMAMLANMADI** sonucunu doğurur.
- `Remove-Item` kilitli dosya hatası verirse test postmaster hâlâ çalışıyor olabilir; §12.2 uygulanır. Başka bir dizin hedeflenmez.

**Geçiş koşulu:** Aşama 11'e her durumda geçilir.
- Test kökü silindiyse ve `S10.4-root-removed PASS` kaydı varsa Aşama 11 `SONUC: V1 TAMAMLANDI` verebilir.
- Test kökü silinmediyse (erteleme, kapı hatası veya onay verilmemesi) Aşama 11 `SONUC: V1 TAMAMLANMADI` verir.

---

## Aşama 11 — Son kontrol: SHA-256 bütünlüğü ve canlı servis başlangıç/bitiş karşılaştırması

**Amaç:**
- Nihai SQL'in, planın ve matrisin değişmediğini doğrulamak.
- Canlı servisin durumunu, PID'sini, süreç oluşturma zamanını, yürütme yolunu ve 5432 dinleyicilerini başlangıçla karşılaştırmak.
- Özeti ve SHA-256 manifestini arşive yazmak.

**Çalışma dizini:** `$Base`

🟢 SALT OKUNUR; yalnızca arşive özet ve manifest yazılır.

```powershell
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
```

**Beklenen çıktı**

```text
RunId: iso18-<yyyyMMddTHHmmss>
Final SQL SHA-256 bitis: 5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b  beklenen: 5916d12b…  sonuc: AYNI
Plan/matris/SQL butunlugu degismedi: True
Canli servis baslangic: State=Running Pid=<P> Created=<T>
Canli servis bitis    : State=Running Pid=<P> Created=<T>
Canli PathName ayni: True
5432 dinleyicileri baslangic: <...>
5432 dinleyicileri bitis    : <aynisi>
Canli servis degismedi: True
Test koku mevcut degil: True
Port 55438 bos: True
--- Asama sonuclari ---
... S1-live-snapshot RECORDED
... S2.2-initdb PASS
... S2.3-certs PASS
... S2.4-conf PASS
... S2-cluster PASS
... S3-fixture PASS
... S4-role-create PASS approved_sha256=<...>
... S5-role-verify PASS
... S6-audit-run EXIT=0
... S7-validator PASS
... S8-audit-hibrit-blocked PASS
... S9-perftest-42501 PASS
... S10.1-cluster-stopped PASS
... S10.2-secret-scan PASS
... S10.3-archive PASS files=<N>
... S10.4-root-removed PASS
--- Nihai sonuc ---
SONUC: V1 TAMAMLANDI
SONUC: V1 TAMAMLANDI
```

Silme ertelendiyse çıktının ilgili satırları şöyle olur. Bu bir **başarısızlık değil, tamamlanmamış** sonuçtur:

```text
Test koku mevcut degil: False
... S10.4-root-removed DEFERRED root=C:\Users\…\hgs2-iso\iso18-…
--- Nihai sonuc ---
SONUC: V1 TAMAMLANMADI - test koku silinmedi (temizlik ertelendi veya yapilamadi): C:\Users\…\hgs2-iso\iso18-…
UYARI: Test koku silinmedi: … - V1 TAMAMLANMADI
SONUC: V1 TAMAMLANMADI - …
```

**Durma noktası**

- `Canli servis degismedi: False` görülürse **DUR**.
  - Canlı servise **müdahale edilmez**: başlatma, durdurma ve yapılandırma yapılmaz.
  - Zaman damgasıyla raporlanır (plan §9.3). Test süreçleri canlı servisi etkileyemez, ancak değişikliğin nedeni ayrıca araştırılır.
- Bütünlük `False` ise **DUR**. Hangi dosyanın değiştiği `integrity-end.sha256` içinde yazılıdır.
- `Test koku mevcut degil: False` ise sonuç **V1 TAMAMLANMADI** olur. Teslim yapılmaz.
  - Tamamlamak için aynı oturumda 10.4 ana bloğu ve ardından Aşama 11 yeniden çalıştırılır.
  - Oturum kapandıysa sonuç TAMAMLANMADI olarak kalır. Test kökü ve içindeki test `pgpass.conf` dosyası diskte durmaya devam eder.

**V1 teslim kabul ölçütü:** `SUMMARY.txt` aşağıdaki koşulların **tamamını** sağlar:
- Yukarıdaki tüm aşamalar `PASS` (S6 için `EXIT=0`), `S10.4-root-removed PASS` dahil.
- `Canli servis degismedi: True`
- Final SQL `AYNI`
- `Test koku mevcut degil: True`
- Son satır `SONUC: V1 TAMAMLANDI`

`SONUC: V1 TAMAMLANMADI` içeren bir çalıştırma teslim edilmez.

---

## 12. Acil durum ve yarıda bırakma

### 12.1 Canlı servis değişti (`CANLI SERVIS DEGISTI`)

1. **DUR.** Canlı servise ve `C:\Program Files\PostgreSQL\18\data` dizinine **hiçbir** müdahale yapılmaz.
2. Test kümesi durdurulur: `Stop-TestCluster`. Bu yalnızca `-D $Data` hedefler.
3. `Get-LiveSnapshot | Format-List` ve `Get-Live5432` çıktıları zaman damgasıyla kanıta yazılır, sonra raporlanır.

### 12.2 Test postmaster kapanmıyor

⚠️ YIKICI — Yalnızca test veri dizinini hedefler.

```powershell
Assert-UnderRoot $Data
& "$PgBin\pg_ctl.exe" -D $Data -m immediate stop
@(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }) | Format-Table ProcessId, CommandLine -Wrap
```

- Yalnızca komut satırında **test veri dizini** geçen PID'ler sonlandırılabilir. Bu da yalnızca `pg_ctl` başarısız olduysa ve elle, tek tek yapılır.
- Canlı servis PID'leri ve onların alt süreçleri **asla** sonlandırılmaz.

### 12.3 Oturum kaybı (pencere kapandı)

Çalıştırma **devam ettirilmez**. Yeni, yönetici olmayan bir PowerShell 5.1 penceresinde aşağıdakiler yapılır:

```powershell
$PgBin = 'C:\Program Files\PostgreSQL\18\bin'
$RunId = '<Asama 1 ciktisinda not edilen RunId>'
$Root  = Join-Path $env:LOCALAPPDATA "hgs2-iso\$RunId"
$Data  = Join-Path $Root 'data'
if ($Data -notmatch '\\hgs2-iso\\iso18-\d{8}T\d{6}\\data$') { throw 'GUARD: yanlis hedef' }
& "$PgBin\pg_ctl.exe" -D $Data status
& "$PgBin\pg_ctl.exe" -D $Data -m fast -w stop      # YIKICI: yalnizca test kumesi
Get-Content -LiteralPath (Join-Path $Root 'evidence\live-start.json')
Get-CimInstance Win32_Service -Filter "Name='postgresql-x64-18'" | Format-List State, ProcessId, PathName
```

- Canlı servis değerleri `live-start.json` ile **elle** karşılaştırılır.
- Kanıt klasörü inceleme için korunur. Gerekirse §10.2 tarama mantığıyla kontrol edilip elle arşivlenir.
- Yeni bir çalıştırma **yeni RunId ile Aşama 0'dan** başlar.

### 12.4 Hiçbir koşulda kullanılmayacak komutlar

| Yasak | Neden |
|---|---|
| `Stop-Service`, `Restart-Service`, `Set-Service`, `Start-Service` (`postgresql-x64-18`), `net stop/start`, `sc.exe` | Canlı servis |
| `pg_ctl … -D "C:\Program Files\PostgreSQL\18\data"` veya `pg_ctl register/unregister` | Canlı veri dizini ve servis kaydı |
| `C:\Program Files\PostgreSQL\18\data\*` altında herhangi bir okuma/yazma (`pg_hba.conf`, `postgresql.conf` dahil) | Çalışma sınırı |
| `port=5432` içeren herhangi bir bağlantı dizesi | Gerçek küme |
| `Stop-Process` ile test kümesine ait olmayan bir PID | Canlı süreçler |
| `PGPASSWORD`, komut satırında veya URL'de parola | Betik L82 yasağı, plan §3.3 |
| `Remove-Item -Recurse` ile `$Root` dışında bir hedef | Silme yalnızca §10.4 kapılarıyla |
| `validate_audit_result.py --accept-warning` | Yazılı karar olmadan uyarı kabul edilmez |

---

## 13. Durum değiştiren komutların özeti

| Aşama | Komut | Hedef | Sınıf | Kapı |
|---|---|---|---|---|
| 2.1 | `New-Item`, `icacls /inheritance:r` | `$Root` ve alt dizinleri | 🟡 | G3 (`$Root` önceden yok), `Assert-UnderRoot` |
| 2.1 | `$env:PG*` atama/silme | Yalnızca bu PowerShell süreci | 🟡 | — |
| 2.2 | `initdb` | `$Data` | 🟡 | `$Data` yok, `Assert-UnderRoot` |
| 2.2 | `Remove-Item $PwFile` | `$Cfg\initdb.pw` | ⚠️ | `Assert-UnderRoot` |
| 2.3 | `openssl` | `$Certs` | 🟡 | Yol `$Root` altında |
| 2.4 / 2.5 | `Add-Content postgresql.conf`, `Set-TestHba` | `$Data\postgresql.conf`, `$Data\pg_hba.conf` | 🟡 | `Assert-UnderRoot` |
| 2.5 | `pg_ctl start` | Test postmaster (`-D $Data`) | 🟡 | `Assert-UnderRoot`, `Assert-LiveUnchanged` |
| 3–9 | `psql` (`Invoke-TestPsql`) | Yalnızca `127.0.0.1:55438` | 🟡 | `Assert-TestConn`, SQL içi port/cluster_name kapısı |
| 10.1 | `pg_ctl stop -m fast` | Test postmaster | ⚠️ | `Assert-UnderRoot` |
| 10.3 | `New-Item`, `Copy-Item` | `role-design\iso-runs\<RunId>\` (yeni) | 🟡 | Hedef önceden yok |
| 10.4 | `Remove-Item pgpass`, `Remove-Item -Recurse $Root` | Test pgpass, test kökü | ⚠️ | 7 kapı + RunId onayı |
| 11 | `Set-Content` (özet, manifest) | Arşiv klasörü | 🟡 | — |

---

## 14. V1 sonrası (bu kılavuzun kapsamı dışında)

- Plan §7'deki T2–T10 ve RC-02/04/05 senaryoları plan dosyasında aynen durmaktadır. V1 tesliminden sonra ayrı bir çalıştırmada uygulanabilir.
- Gerçek kümeye geçiş için plan §10'daki P1–P12 ön koşulları ve §11.2'deki açık kararlar (K-1…K-9) geçerlidir. Bu kılavuzun başarılı tamamlanması tek başına geçiş onayı **değildir**.
