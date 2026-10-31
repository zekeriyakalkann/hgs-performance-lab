# FINAL_EXECUTION_REPORT — HGS2 PostgreSQL Read-Only Audit V2, izole küme V1 yürütmesi

- Tarih: 2026-10-30 (+03:00)
- Dayanak: `role-design\EXECUTION_RUNBOOK_V1.md` (değiştirilmedi) + `role-design\EXECUTION_RUNBOOK_V1_ADDENDUM_R1.md` (yeni)
- **Nihai sonuç: `SONUC: V1 TAMAMLANDI`.** Geçerli RunId `iso18-20261030T231228`'dir.
- Bu sonuç izole sentetik kümeye aittir. **Gerçek kümeye geçiş onayı değildir** (runbook §14).

---

## 1. RunId ayrımı

| RunId | Rol | Sonuç | Arşiv |
|---|---|---|---|
| `iso18-20261030T223605` | Önceki çalıştırma. Aşama 2.4'ten sonra PowerShell oturumu kayboldu | **V1 TAMAMLANMADI**. Devam ettirilmedi, küme başlatılmadı, parolalar yeniden üretilmedi | `role-design\iso-runs-incomplete\iso18-20261030T223605\` |
| `iso18-20261030T230745` | Bu oturumun ilk yeni çalıştırması | **FAIL (Aşama 2.5) / V1 TAMAMLANMADI**. Runbook'taki komut satırı / yol ayırıcı kusuru (EK R1-8) | `role-design\iso-runs-incomplete\iso18-20261030T230745\` |
| `iso18-20261030T231228` | Düzeltilmiş çalıştırıcı (R2) ile yeni çalıştırma | **V1 TAMAMLANDI** | `role-design\iso-runs\iso18-20261030T231228\` |

- Eksik iki çalıştırmanın her biri için `INCOMPLETE_STATUS.md`, `review\closeout-results.txt` ve `SHA256SUMS.txt` vardır.
- Test kökleri §10.4 kapılarıyla silindi. `%LOCALAPPDATA%\hgs2-iso\` artık boştur.

## 2. Ortam ve sürümler

Kaynak yolları arşiv köküne göredir: `role-design\iso-runs\iso18-20261030T231228\`.

| Öğe | Değer | Destekleyen kanıt |
|---|---|---|
| PowerShell | 5.1.26100.9711, `ConsoleHost`, yönetici **değil** (G1) | `evidence\00-inputs\toolchain.txt`. Yönetici olmama durumu yazılı bir değer değildir; G1 kapısının geçtiği, `S0 kapilari: PASS` ve sonraki aşamaların varlığından anlaşılır (`runner\run3-console.log` L63) |
| Kullanıcı | `DESKTOP-N286CHO\Ceng Zeki` | `evidence\00-inputs\toolchain.txt` |
| İkili sürümler: postgres, psql, initdb, pg_ctl, pg_controldata | **18.6** | `evidence\00-inputs\toolchain.txt` |
| Sunucu sürümü (izole küme) | `PostgreSQL 18.6 on x86_64-windows, compiled by msvc-19.44.35229, 64-bit` | `evidence\S2-identity\stdout.txt`. Ayrıca `server_version = 18.6`: `evidence\S6-audit-hgs2_audit\stdout.txt` L16 |
| Python | 3.13.16 | `evidence\00-inputs\toolchain.txt` |
| OpenSSL | 3.5.8 | `evidence\00-inputs\toolchain.txt` |
| İndirme | **Yok.** Gerekli tüm araçlar mevcuttu | **Arşivlenmiş kanıt yok.** Yalnızca yürütme oturumunun beyanıdır |
| Test portu | **55438**. Dinleyiciler `127.0.0.1` ve `::1`; ikisi de test postmaster'a ait. Ayrılmış port aralığında değil | Port: `evidence\S2-identity\stdout.txt`. Dinleyiciler: `evidence\S2-port-pid.txt`. Ayrılmış aralık: `evidence\00-inputs\toolchain.txt` |
| system_identifier | `7702556342130788452` | `pg_controldata` çıktısı: `evidence\test-system-identifier.txt`. Denetime verilen beklenen değer: `evidence\S6-audit-hgs2_audit\args.txt`. Sunucunun bildirdiği değer: `evidence\S6-audit-hgs2_audit\stdout.txt` (`sunucu system_identifier= … beklenen= …`) |
| cluster_name | `hgs2iso18` | `evidence\S2-identity\stdout.txt` |
| TLS bağlantısı | `ssl = on`; denetim bağlantısı `TLSv1.3`, `TLS_AES_256_GCM_SHA384`, 256 bit; `hgs2_audit` bağlantısında `pg_stat_ssl.ssl = t` | `ssl = on`: `evidence\S2-identity\stdout.txt`. Şifreleme parametreleri: `evidence\S6-audit-hgs2_audit\stdout.txt` L20. `ssl = t`: `evidence\S5-pos-connect\stdout.txt` |
| TLS sertifikaları | Test CA + sunucu sertifikası, `-days 7` ile üretildi | Komut: `runner\runner_v1_single_session.ps1` (`-days 7`). Dosya adları ve boyutları: `runner\run3-console.log`. Sertifikaların kendisi arşivlenmedi; geçerlilik süresi sertifikadan **doğrulanamaz** |
| Kimlik doğrulama | Parolalar `SCRAM-SHA-256$…` biçiminde. `pg_hba` varyant A, `hgs2_audit` için ilk TCP kuralı: `hgs2_perftest_db` → `scram-sha-256`, diğer veritabanları → `reject` | Parola biçimi: `evidence\S4-password-check\stdout.txt`. pg_hba yöntemleri: `evidence\S4-role-create\stdout.txt` (`first_tcp_rule_method`). pg_hba satırları: `runner\runner_v1_single_session.ps1` (`$Hba['A']`) |

## 3. Yürütme biçimi

- Runbook §0.7 tüm aşamaların **aynı PowerShell oturumunda** çalıştırılmasını ister. Önceki çalıştırma bu oturumun kaybolması yüzünden yarım kaldı.
- Bu yüzden blokların **tamamı tek bir `powershell.exe` (5.1, ConsoleHost) sürecinde** çalıştırıldı: `runner_v1_single_session.ps1`.
  - Runbook blokları **aynen ve sırayla** yer aldı.
  - Blok başına runbook satır aralığı ve SHA-256 `evidence\00-inputs\runner_provenance.txt` içindedir.
  - Çalıştırıcının SHA-256'sı `92deca08dac31d9a3e9dc6724ff18894ffeb72e1718d4ea3b7ca14fd36a0f8a2`. Kanıta yazılan değerle eşleşti. Betik arşivin `runner\` klasöründedir.
- Oturuma bağlı kapılar korundu: `$Live0` / `Assert-LiveUnchanged`, `$TestSecrets` ile §10.2 taraması ve Aşama 11 karşılaştırması. **Hiçbiri atlanmadı.**
- Runbook'tan farklılıklar. Hepsi ekleme veya kusur düzeltmesidir; gevşetilen kapı yoktur:

| # | Fark | Gerekçe |
|---|---|---|
| D1 | `[A0]` Aşama 0 "Beklenen" tablosu kapıya dönüştürüldü (PS 5.1, ConsoleHost, 3 hash, 5 ikili 18.6, py 3.13, openssl, `excludedportrange`) | Elle okunan beklentilerin makinece denetimi |
| D2 | `[LC]` Her bloktan sonra canlı servis + 5432 kontrol noktası (`evidence\live-checks.txt`, 15 nokta) | Görev şartı: "her aşamada karşılaştır" |
| D3 | `[A10.4]` `Read-Host` yerine onay dosyası | Etkileşimsiz süreç. Operatör `SILINECEK:` satırını ve arşivi doğruladıktan sonra Aşama 1'deki RunId'yi yazdı. Dosya önceden varsa çalıştırıcı başlamaz |
| D4 | `[A-TS]` Transcript ve konsol günlüğünde parola ve özel anahtar taraması | Kanıt kalitesi. Sonuç: 3 rol × 2 dosya, **0 eşleşme** |
| D5 | **EK R1-8:** 4 yerde `CommandLine -like "*$Data*"` → `Test-CmdLineHasData` (`/` → `\` normalizasyonu) | Kusur kanıtı `iso18-20261030T230745`'te. Düzeltilmeden §10.1 ve §10.4 negatif kapıları anlamsız biçimde geçiyordu |
| D6 | **EK R1-9:** Çalıştırıcı betiği kanıta kopyalanmaz, yalnızca SHA-256'sı yazılır | Betik, §10.2'nin `PRIVATE KEY` desenini içerdiği için kendi taramasını bozuyordu |
| D7 | `[A2.5]`/`[A10.1]` `S2-port-pid.txt`, `S10.1-port-free.txt` | Port ve PID kanıtı |
| D8 | `[A-ERR]` Hata durumunda: DUR, kayıt ve **yalnızca** `pg_ctl -D <test data> -m fast` | §12.1/§12.2. `iso18-20261030T230745`'te bu yol işledi |

## 4. Aşama sonuçları — `iso18-20261030T231228`

Kaynak: `role-design\iso-runs\iso18-20261030T231228\SUMMARY.txt` ve `evidence\stage-results.txt`.

| Aşama | İş | Sonuç | Ana kanıt |
|---|---|---|---|
| 0 | Ön kontroller, sürümler, hash, port, yönetici değil | **PASS** (`S0 kapilari: PASS`) | `00-inputs\toolchain.txt`, `integrity-start.sha256`, `runner\run3-console.log` L63 |
| 1 | Canlı servis + 5432 başlangıç görüntüsü | **RECORDED** | `live-start.json`, `live-start-5432.txt` |
| 2.1 | Dizinler, ACL (`icacls /inheritance:r`, yalnızca kullanıcı), ortam yalıtımı | **PASS**. Kapılar geçti; runbook bu adım için ayrı stage satırı yazmaz | `live-checks.txt` after-S2.1 |
| 2.2 | initdb (SCRAM, ayrı data dizini; parola dosyası hemen silindi) | **PASS** | `test-system-identifier.txt` |
| 2.3 | TLS (CA + sunucu) | **PASS** | `stage-results.txt`, `runner\run3-console.log` (dosya listesi) |
| 2.4 | `postgresql.conf` | **PASS** | `stage-results.txt`. Ayarların etkisi: `S2-identity\stdout.txt` (port, cluster_name, ssl). `postgresql.conf` dosyasının kendisi arşivlenmedi |
| 2.5 | pg_hba A, başlatma, kimlik, port/PID | **PASS** | `S2-identity\`, `S2-port-pid.txt` |
| 3 | Sentetik fixture | **PASS** | `S3-*` |
| 4 | `hgs2_audit` oluşturma + parola | **PASS** (`approved_sha256=b1053606…bf07`) | `S4-*`, `00-inputs\role_draft_approved_iso.*` |
| 5 | Bağımsız least-privilege doğrulaması + 1 pozitif / 3 negatif | **PASS** (`HGS2_V1_ROLE_VERIFY_OK` ×1; 3× `42501`) | `S5-*` |
| 6 | Nihai SQL denetimi (`hgs2_audit`, TLS) | **PASS** (`EXIT=0`) | `S6-audit-hgs2_audit\` |
| 7 | Doğrulayıcı (7 kural) | **PASS** (`validator_exit=0`) | `verdict.txt`, `verdict-explicit.txt` |
| 8 | `hgs2_audit` → `hibrit_giris_db` engeli (pg_hba, 28000) | **PASS** | `S8-*`, `S8-log-28000.txt` |
| 9 | `hgs2_perftest` 42501 davranışı | **PASS** | `S9-*`, `S9-log-sqlstate.txt` |
| 10.1 | Küme durduruldu, port boş | **PASS** | `S10.1-port-free.txt` |
| 10.2 | Gizli bilgi taraması (`$TestSecrets` ×3 + `PRIVATE KEY`) | **PASS** (0 eşleşme) | Parola sayıları: `runner\run3-console.log` L316–318. `PRIVATE KEY` sayısı yazdırılmaz; yalnızca kapının geçtiği `stage-results.txt` içindeki `S10.2-secret-scan PASS` satırından anlaşılır |
| 10.3 | Kanıt arşivi (90 dosya, hash kümesi eşit) | **PASS** | arşiv |
| 10.4 | Test kökü silme (7 kapı + RunId onayı) | **PASS** | `stage-results.txt` |
| 11 | Bütünlük + canlı servis başlangıç/bitiş | **PASS** → `SONUC: V1 TAMAMLANDI` | `SUMMARY.txt`, `integrity-end.sha256`, `live-end.json` |

## 5. Önemli sonuçlar

### 5.1 Doğrulayıcı (Aşama 7)

| Kural | Sonuç |
|---|---|
| 1. psql çıkış kodu 0 | `exit.txt = 0` ✔ |
| 2. stderr boş | `stderr.txt` 0 bayt ✔ |
| 3. Son boş olmayan stdout satırı `HGS2_AUDIT_COMPLETE` | 277. satır ✔ |
| 4. COMPLETE tam bir kez | 1 ✔ |
| 5. PREFLIGHT tam bir kez ve COMPLETE'ten önce | 24. satır ✔ |
| 6. ABORT yok | 0 ✔ |
| 7. Kabul edilmemiş WARNING yok | 0. `--accept-warning` **kullanılmadı** ✔ |

- Doğrulayıcı çıktısı `PASS` ve çıkış kodu `0`. Karar yalnızca psql çıkış koduna dayanmadı.

### 5.2 Nihai SQL

- SHA-256: Başlangıç, çalıştırmadan hemen önce ve bitiş değerlerinin üçü de `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`. Dosya değiştirilmedi.
  - Kanıtlar: `evidence\integrity-start.sha256`, `evidence\S6-audit-hgs2_audit\audit_sql.sha256`, `integrity-end.sha256`.
- Denetim, `hgs2_audit` ile `sslmode=require` kullanılarak, `127.0.0.1:55438` üzerinde ve `expected_system_identifier = 7702556342130788452` ile yapıldı.

### 5.3 Gerçek DB erişim engeli

- `hgs2_audit` → `hibrit_giris_db` bağlantıları:
  - `sslmode=disable`: çıkış 2, `pg_hba.conf rejects connection … no encryption`
  - `sslmode=require`: çıkış 2, `… SSL encryption`
- Sunucu günlüğünde iki `28000` satırı var; oturum açılış satırı yok.
- `hgs2_perftest` → `hibrit_giris_db`: çıkış 2, `42501 permission denied for database` + `User does not have CONNECT privilege`. `28000`/`28P01` sayısı 0.
- `hgs2_perftest` kendi veritabanına bağlanabildi (`hgs2_perftest|hgs2_perftest_db`).
- **Gerçek `hibrit_giris_db` ve `hgs2_perftest_db` veritabanlarına hiçbir bağlantı denemesi yapılmadı.** Her iki ad da yalnızca izole kümedeki sentetik veritabanlarıdır.

## 6. Canlı sisteme dokunulmadığının kanıtı

Kaynak yolları arşiv köküne göredir: `role-design\iso-runs\iso18-20261030T231228\`. Eksik çalıştırma arşivleri ayrıca belirtilmiştir.

| Kontrol | Başlangıç | Bitiş | Destekleyen kanıt |
|---|---|---|---|
| `postgresql-x64-18` State | Running | Running | `evidence\live-start.json` / `live-end.json`; `SUMMARY.txt` |
| Servis PID | 4708 | 4708 | aynı |
| Süreç oluşturma zamanı | 2026-10-30T16:29:54.8155590+03:00 | aynı | aynı |
| PathName | `pg_ctl.exe runservice -N "postgresql-x64-18" -D "C:\Program Files\PostgreSQL\18\data" -w` | aynı | `evidence\live-start.json` / `live-end.json`; `SUMMARY.txt` (`Canli PathName ayni: True`) |
| 5432 dinleyicileri | `::1:5432 pid=6164; 127.0.0.1:5432 pid=6164` | aynı | `evidence\live-start-5432.txt` / `live-end-5432.txt`; `SUMMARY.txt` |
| Ara kontrol noktaları | 15/15 `unchanged` | — | `evidence\live-checks.txt` (after-S2.1 … before-S11). `after-S1` noktası kanıt klasörü henüz yokken alındı; yalnızca `runner\run3-console.log` içinde görünür |
| Eski çalıştırma kapanışları (bu oturumun arşivlenmiş ilk okumaları) | `live_now` PID 4708, aynı Created | `live_end` aynı | `role-design\iso-runs-incomplete\iso18-20261030T223605\review\closeout-results.txt` ve `…\iso18-20261030T230745\review\closeout-results.txt` |
| Kapanıştan önceki ilk elle okuma | PID 4708, 5432 pid 6164 | — | **Arşivlenmiş kanıt yok.** Yalnızca yürütme oturumunun çıktısıdır |
| Çalıştırma sonrası bağımsız son okuma (servis listesi, port 55438, test süreçleri) | — | Servis listesinde yalnızca `postgresql-x64-18`; 55438 boş; test `postgres.exe` yok | **Arşivlenmiş kanıt yok.** Port 55438'in boş olduğu ve test kökünün bulunmadığı ayrıca `SUMMARY.txt` ile desteklenir. "Yeni servis kaydı yok" iddiası için arşivlenmiş kanıt yoktur |

- `port=5432` kullanılmadı: Geçerli çalıştırmadaki her psql çağrısının `args.txt` dosyası `port=55438` ve `host=127.0.0.1` içerir. `Assert-TestConn` kapısının kodu `runner\runner_v1_single_session.ps1` içindedir.
- `C:\Program Files\PostgreSQL\18\data` altında hiçbir dosya okunmadı veya yazılmadı: Bu bir **beyandır**. Dosya erişim günlüğü yoktur. Dayanağı çalıştırıcı betiğin içeriğidir: canlı veri dizinine erişen komut yoktur; yol yalnızca servis `PathName` karşılaştırmasında geçer.
- Uygulama başlatılmadı, Maven çalıştırılmadı, uygulama kodu değiştirilmedi: **Arşivlenmiş kanıt yok.** Yürütme oturumunun beyanıdır.

## 7. Temizlik sonucu

| Öğe | Durum | Destekleyen kanıt |
|---|---|---|
| `%LOCALAPPDATA%\hgs2-iso\iso18-20261030T231228` | Silindi | `evidence\stage-results.txt` (`S10.4-root-removed PASS`); `SUMMARY.txt` (`Test koku mevcut degil: True`) |
| `%LOCALAPPDATA%\hgs2-iso\iso18-20261030T230745` | Silindi (closeout v2, 7 kapı + RunId) | `role-design\iso-runs-incomplete\iso18-20261030T230745\review\closeout-results.txt` (`old_root_removed = True`) |
| `%LOCALAPPDATA%\hgs2-iso\iso18-20261030T223605` | Silindi (closeout v1, 7 kapı + RunId; EK R1-8 notuna bakın) | `role-design\iso-runs-incomplete\iso18-20261030T223605\review\closeout-results.txt` (`old_root_removed = True`) |
| Test pgpass dosyaları | Kök silinmeden önce ayrıca silindi | Silme komutları: `runner\runner_v1_single_session.ps1` ve iki `review\closeout_script_v*.ps1`. Ayrı bir silme kaydı yoktur; kökün yokluğu yukarıdaki kanıtlarla doğrulanır |
| Port 55438 | Boş | `evidence\S10.1-port-free.txt`; `SUMMARY.txt` (`Port 55438 bos: True`) |
| Test `postgres.exe` süreci | 0 | `evidence\S10.1-port-free.txt` (`test_postmaster_count: 0`) |
| Kullanıcı ortam değişkeni `PGPASSFILE` | Tanımlı değil | **Arşivlenmiş kanıt yok.** Yürütme oturumunun son okumasıdır |

## 8. Üretilen ve değiştirilen dosyalar

**Yeni dosyalar:**
- `asama4-v1-execution\` altında 5 dosya: `FINAL_EXECUTION_REPORT.md`, `FINAL_SECURITY_AUDIT.md`, `FINAL_TEST_MATRIX.md`, `KNOWN_LIMITATIONS.md`, `FINAL_SHA256SUMS.txt`
- Dokümantasyon kapanışı: `asama4-v1-execution\DOCUMENTATION_CLOSURE_REPORT.md`. Yalnızca belge düzeltmelerini kaydeder; test sonucu değiştirmez
- `role-design\EXECUTION_RUNBOOK_V1_ADDENDUM_R1.md`
- `role-design\iso-runs\iso18-20261030T231228\`:
  - 95 dosyalık çalıştırma arşivi + `SHA256SUMS.txt`
  - Çalıştırma sonrasında eklenen `runner\` klasörü (6 dosya; çalıştırmanın manifestinde değil, `FINAL_SHA256SUMS.txt` içinde)
- `role-design\iso-runs-incomplete\` altında iki eksik çalıştırma arşivi

**SHA-256 ile doğrulanan değişmemiş dosyalar** (`FINAL_SHA256SUMS.txt` "Girdiler" bölümü):
- `asama3-final\postgresql_readonly_audit_v2.sql` (nihai SQL). Ayrıca çalıştırmanın `evidence\integrity-start.sha256` ve `integrity-end.sha256` dosyalarında `AYNI` olarak kayıtlı.
- `asama3-final\tools\validate_audit_result.py` (doğrulayıcı)
- `role-design\EXECUTION_RUNBOOK_V1.md`
- `role-design\ISOLATED_CLUSTER_TEST_PLAN.md` ve `role-design\AUDIT_ROLE_PRIVILEGE_MATRIX.md`. Ayrıca `integrity-start.sha256` ve `integrity-end.sha256` dosyalarında `AYNI`.

**Bu teslimatla doğrulanmayan dosyalar:**
- `asama3-final\` klasöründeki diğer dosyalar: `CHANGELOG_FINAL.md`, `FINAL_DELIVERY.md`, `FINAL_SECURITY_AUDIT.md`, `FINAL_SHA256SUMS.txt`, `FINAL_TEST_MATRIX.md`, `KNOWN_LIMITATIONS.md`, `MINIMUM_PRIVILEGE_ANALYSIS.md` ve `kanit\`.
- Kök klasördeki 2. aşama `postgresql_readonly_audit_v2.sql` dosyası.
- Bu yürütmede bu dosyalara yazma işlemi yapılmadı. Ancak `FINAL_SHA256SUMS.txt` bu dosyaları kapsamaz; değişmedikleri bu teslimatın manifestiyle **doğrulanmış sayılmaz**.

## 9. Açık kalan riskler

Ayrıntı `KNOWN_LIMITATIONS.md` dosyasındadır. Kısa liste:
1. Gerçek kümede `hgs2_perftest`'in bugün 42501 aldığı **UNVERIFIED** kalır (runbook §9 notu, plan P5).
2. `hgs2_audit` için IPv6 (`::1`) bağlantısı ve T2–T10 senaryoları V1 kapsamı dışındadır ve **NOT RUN** durumundadır.
3. Sahiplik doğrulaması:
   - Diğer veritabanlarında doğrudan doğrulanmadı.
   - `hgs2_perftest_db`'de doğrudan sahiplik yok.
   - Paylaşılan bağımlılık kataloğunda sahiplik kaydı yok.
4. Eski çalıştırmalar için özgün §10.2 parola taraması **NOT RUN** durumundadır. İkame tarama yapıldı.
5. `Remove-Item` güvenli silme garanti etmez.
6. Runbook V1'de EK R1-8 kusuru düzeltilmeden kullanılırsa §10.1 ve §10.4 negatif kapıları anlamsız biçimde geçer.
