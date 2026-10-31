# FINAL_SECURITY_AUDIT — V1 izole küme yürütmesi

- Kapsam: `iso18-20261030T231228` (geçerli çalıştırma) ve iki eksik çalıştırmanın kapanışı.
- Kanıtlar sentetik kümeye aittir. Gerçek veri içermez.
- Kanıtlarda küme geneli rol, ACL ve ayar adları bulunur. FINAL_DELIVERY §5.9 gereği bu bilgiler **hassas yapılandırma bilgisi** olarak ele alınmalıdır.

## 1. `hgs2_audit` rolünün yetkileri (doğrulanmış)

Rol oluşturma ifadesi (onaylı kopya, SHA-256 `b1053606b9e0cc4a48d0e122ff4a26a28b1dc0a06070a6a75f4c23f48697bf07`; kaynak: matris §11):

```sql
CREATE ROLE hgs2_audit LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
```

- Stok PG 18.6'da **hiç GRANT üretilmedi** (3× `BILGI: … GRANT uretilmedi.`). Tüm gerekli erişimler PUBLIC'ten gelir: `acl_ref_count = 0`.
- Bağımsız doğrulama (`S5-role-verify`, `BEGIN READ ONLY … ROLLBACK`) sonuçları:

| Gereksinim | Ölçüt | Sonuç |
|---|---|---|
| Superuser değil; yönetim öznitelikleri yok | `not_superuser`, `attrs_ok` (NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS, NOINHERIT, LOGIN, connlimit 2) | t / t |
| Başka rollerin üyesi değil | `no_member_of`, `no_members_in_audit`, `no_effective_membership`, `not_member_perftest`, `not_member_postgres` | t ×5 |
| Nesne sahibi değil | `no_owned_db` (küme geneli), `no_owned_schema_this_db` (yalnızca hgs2_perftest_db), `no_owner_shdep_records`, `no_other_shdeps`, `no_owned_tablespace` | t ×5 |
| Uygulama tablolarında SELECT yok | `user_rel_access_count = 0`, `no_select_users = t`, `lo_public_or_audit_count = 0`, `defacl_risk_count = 0` | ✔ |
| Gereksiz CREATE yok | `no_db_create_any`, `no_schema_create` | t / t |
| Yalnızca gerekli bağlantı ve katalog okuma | `connect_target`, `usage_pg_catalog`, `usage_public`, `ctrl_exec`, `catalogs_ok` (21 katalog), `functions_ok` (42 fonksiyon) = t; `role_setting_count = parameter_acl_count = 0` | ✔ |
| `hibrit_giris_db` kapalı | `hibrit_acl_closed = t` (ACL) ve `hba_hibrit_rejected = t` (ilk TCP kuralı `reject`) | ✔ |
| Kayda geçen (R10) | `has_db_temporary = t` (PUBLIC TEMPORARY artığı), `secdef_callable_count = 0` | kayıt |

- Oturum düzeyi kanıtları:
  - TLS ile hedef veritabanına bağlantı kuruldu (`evidence\S5-pos-connect\stdout.txt`: `…|t`). Denetim bağlantısının TLS parametreleri (`TLSv1.3`, `TLS_AES_256_GCM_SHA384`, 256 bit) `evidence\S6-audit-hgs2_audit\stdout.txt` L20'dedir.
  - `SET ROLE hgs2_perftest`, `SELECT public.users` ve `CREATE TABLE public.…` işlemlerinin üçü de `42501` ile reddedildi.
- Denetim betiğinin kendi rol kontrolü: `super= f`, `super_role_uyeligi= f`, `createrole/createdb/replication/bypassrls= false`. `audit_role_excess_privilege` uyarısı yok.
- **Kapsam notu (runbook §5):** Doğru ifade şudur: "`hgs2_perftest_db`'de doğrudan sahiplik yok; paylaşılan bağımlılık kataloğunda sahiplik kaydı yok." Diğer veritabanlarının `pg_namespace` ve `pg_class` katalogları doğrudan okunmadı.

## 2. Erişim engeli (pg_hba varyant A, yalnızca izole küme)

```text
host    hgs2_perftest_db  hgs2_audit  127.0.0.1/32  scram-sha-256
host    hgs2_perftest_db  hgs2_audit  ::1/128       scram-sha-256
host    all               hgs2_audit  all           reject
host    replication       hgs2_audit  all           reject
local   all               hgs2_audit                reject
local   replication       hgs2_audit                reject
host    all               all         127.0.0.1/32  scram-sha-256
host    all               all         ::1/128       scram-sha-256
```

- `hgs2_audit` → `hibrit_giris_db` bağlantısı hem TLS'siz hem TLS'li olarak **pg_hba katmanında (28000)** reddedildi. Kimlik doğrulama ve oturum aşamasına geçilmedi.
- `hgs2_perftest` bu bloktan **etkilenmez**. `hibrit_giris_db` için yalnızca ACL (42501) devreye girer ve `PerfTestSafetyGuard` uyumluluğu korunur. Kendi veritabanına bağlanabilir.
- Gerçek kümenin `pg_hba.conf` dosyası **okunmadı ve değiştirilmedi.** Bu blok yalnızca izole kümede sınandı.

## 3. Gizli bilgi yönetimi

Kaynak yolları arşiv köküne göredir: `role-design\iso-runs\iso18-20261030T231228\`.

| Konu | Uygulama | Destekleyen kanıt |
|---|---|---|
| Parola üretimi | `RandomNumberGenerator`, 24 bayt → base64; `[+/=]` → `x` | Kod: `runner\runner_v1_single_session.ps1` (`New-TestSecret`) |
| Parola aktarımı | Süper kullanıcı parolası: initdb `--pwfile`; dosya hemen silindi. Rol parolaları: süreç ortamı `HGS2_ISO_PW` → psql `\getenv`. Atama `SET log_statement='none'` ile yapıldı ve ortam değişkeni hemen silindi | Kod: `runner\runner_v1_single_session.ps1`, `evidence\00-inputs\set_password_v1.sql`. Sonuç: `log\postgres.log` içinde `ALTER ROLE … PASSWORD` satırı yok |
| Saklama | Yalnızca test kökündeki port kapsamlı `pgpass.conf` (`*:55438:*:…`). `PGPASSWORD` kullanılmadı. Komut satırında parola yok | 17 `evidence\*\args.txt` dosyasında parola yok. pgpass dosyası arşivlenmedi |
| Kanıt taraması (§10.2) | 3 parola × (kanıt + sunucu günlüğü) = 0; `PRIVATE KEY` = 0 | Parola sayıları: `runner\run3-console.log` L316–318. `PRIVATE KEY` sayısı yazdırılmaz; kapının geçtiği `evidence\stage-results.txt` içindeki `S10.2-secret-scan PASS` satırından anlaşılır |
| Konsol taraması | 3 parola × (transcript + konsol günlüğü) = 0 | `runner\run3-console.log` L326–331 |
| Son bağımsız tarama (arşiv) | PEM başlığı 0, `private key` (büyük/küçük harf duyarsız) 0, pgpass biçimi 0, 32 karakterlik karışık token 0, SCRAM doğrulayıcı gövdesi 0 | **Arşivlenmiş kanıt yok.** Yürütme oturumunun çıktısıdır; arşiv üzerinde yeniden yapılabilir |
| Arşive alınmayanlar | `cfg\` (pgpass), `certs\` (ca.key, server.key) | Arşivin dosya listesi (`SHA256SUMS.txt`): bu dosyalar yok |
| Temizlik | pgpass ayrıca silindi; test kökü `Remove-Item -Recurse` ile silindi; bellekteki `$TestSecrets` temizlendi | Kökün yokluğu: `SUMMARY.txt`, `evidence\stage-results.txt`. Bellek temizliği yalnızca koddadır (`runner\runner_v1_single_session.ps1`, §11.6) |
| Test kökü ACL | `icacls /inheritance:r`, yalnızca geçerli kullanıcıya FullControl | Kod: `runner\runner_v1_single_session.ps1`. Uygulanan ACL'nin çıktısı arşivlenmedi; `icacls` çıkış kodu kapısı geçti |

## 4. Canlı ortamın korunması

- Servis `postgresql-x64-18`: State, PID (4708), süreç oluşturma zamanı ve PathName başlangıçta ve bitişte aynı.
  - Kanıt: `evidence\live-start.json`, `live-end.json`, `SUMMARY.txt`.
  - Çalıştırma sırasında 15 ara kontrol noktası alındı: `evidence\live-checks.txt`.
  - Eksik iki çalıştırmanın kapanışında da başlangıç ve bitiş karşılaştırıldı: `role-design\iso-runs-incomplete\<RunId>\review\closeout-results.txt` (`live_now`, `live_end`).
- 5432 dinleyicileri: `::1:5432 pid=6164; 127.0.0.1:5432 pid=6164`, değişmedi.
  - Kanıt: `evidence\live-start-5432.txt`, `live-end-5432.txt`, `SUMMARY.txt`.
- Bağlantılar:
  - Tüm psql çağrıları `Assert-TestConn` kapısından geçti: `port=55438` zorunlu, `port=5432` yasak, yalnızca loopback.
    - Kanıt: 17 `evidence\*\args.txt` dosyasının tamamında `port=55438` ve `host=127.0.0.1` var; hiçbirinde `port=5432` yok.
  - Dört SQL dosyasının içindeki kapılar `port = 55438` ve `cluster_name = hgs2iso18` koşullarını ayrıca denetledi: `fixture_global_v1.sql`, `fixture_db_v1.sql`, `set_password_v1.sql` ve `role_verify_v1.sql` (`evidence\00-inputs\`).
    - `role_draft_approved_iso.sql` (matris §11 kopyası) bu port kapısını içermez. Onun kapıları hedef veritabanı, süper kullanıcı, rolün yokluğu, `search_path` ve PG 18 kontrolleridir. Bağlantısı `Assert-TestConn` ile korundu.
- Yeni Windows servisi kaydedilmedi (`pg_ctl register` kullanılmadı). Servis listesinde yalnızca `postgresql-x64-18` var.
  - Kod dayanağı: Çalıştırıcıda `register` komutu yok (`runner\runner_v1_single_session.ps1`).
  - Servis listesi okuması için **arşivlenmiş kanıt yok.**
- Hiçbir canlı süreç sonlandırılmadı. Hata yolu yalnızca `pg_ctl -D <test data>` komutunu hedefledi.
  - Bu yol `iso18-20261030T230745` çalıştırmasında bir kez kullanıldı: test kümesi `-m fast` ile durduruldu, çıkış 0.
  - Kanıt: `role-design\iso-runs-incomplete\iso18-20261030T230745\review\runner-console.log` (`test kumesi durdurma cikis: 0`) ve aynı arşivdeki `log\postgres.log` (`received fast shutdown request`).

## 5. Güvenlik bulguları (bu yürütmede ortaya çıkanlar)

| ID | Bulgu | Etki | Durum |
|---|---|---|---|
| SF-1 | **Runbook V1 süreç kimliği karşılaştırması etkisiz** (`CommandLine -like "*$Data*"`; `pg_ctl` yolu `/` ile kanonikleştirir) | §10.1 "test postmaster hala calisiyor" ve §10.4 "test postmaster calisiyor - silme yapilmaz" kapıları **her zaman geçer**. Çalışan bir kümenin veri dizini silinmeye çalışılabilir. §2.5 pozitif kapıları ise her zaman başarısız olur | EK R1-8 ile düzeltildi; birim testi yapıldı. Runbook V1 dosyasının kendisi değiştirilmedi |
| SF-2 | §10.2 `PRIVATE KEY` taraması, runbook kodunu içeren bir dosyada kendi deseniyle eşleşir | Arşivleme yanlış pozitifle durur (fail-closed; güvenli yönde) | EK R1-9: Çalıştırıcı kanıta kopyalanmaz |
| SF-3 | Oturum kaybından sonra §10.2 özgün taraması yapılamaz | Eksik çalıştırmalarda tarama sınırlı kalır | EK R1-2: pgpass kaynaklı ikame tarama; NOT RUN olarak raporlandı |
| SF-4 | `Remove-Item` güvenli silme değildir | Silinen test parolaları ve özel anahtarlar diskte kurtarılabilir olabilir | Kabul edildi: değerler yalnızca yok edilmiş test kümesine ve 7 günlük test CA'sına aittir |
