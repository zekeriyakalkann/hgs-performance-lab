# FINAL_TEST_MATRIX — V1 izole küme yürütmesi

- Geçerli çalıştırma: `iso18-20261030T231228`
- Arşiv kökü: `role-design\iso-runs\iso18-20261030T231228\`
  - Kanıt sütunundaki kısa yollar, aksi belirtilmedikçe `evidence\` altındadır.
  - Arşiv kökündeki dosyalar ön eksiz yazılır: `SUMMARY.txt`, `integrity-end.sha256`, `live-end.json`, `live-end-5432.txt`, `log\postgres.log`, `runner\…`.
- Durumlar: **PASS**, **FAIL**, **NOT RUN** (V1 kapsamı dışında veya çalıştırılamadı) ve **RECORDED** (yalnızca kayıt).

## A. Geçerli çalıştırma — `iso18-20261030T231228`

| ID | Test | Beklenen | Gerçek sonuç | Durum | Kanıt |
|---|---|---|---|---|---|
| S0-1 | PS 5.1 / ConsoleHost / yönetici değil | 5.1, ConsoleHost, admin=False | 5.1.26100.9711, ConsoleHost, G1 geçti | PASS | `00-inputs\toolchain.txt` |
| S0-2 | İkili sürümler | 18.6 ×5 | postgres, psql, initdb, pg_ctl, pg_controldata 18.6 | PASS | aynı |
| S0-3 | Python / OpenSSL | 3.13.x / 1.1.1 veya 3.x | 3.13.16 / 3.5.8 | PASS | aynı |
| S0-4 | SHA-256: SQL, plan, matris | 5916d1… / 398889… / 5733d4… | Üçü de eşit | PASS | `integrity-start.sha256` |
| S0-5 | 55438 ayrılmış aralıkta değil (IPv4/IPv6) | Kapsanmıyor | Kapsanmıyor | PASS | `00-inputs\toolchain.txt`; `runner\run3-console.log` L60 |
| S1 | Canlı servis + 5432 görüntüsü | Running, dinleyici var | Running PID 4708, 5432 ×2 (pid 6164) | RECORDED | `live-start.json`, `live-start-5432.txt`, `stage-results.txt` |
| S2.1 | Test kökü, ACL, ortam yalıtımı | Dizinler var, icacls 0 | Geçti | PASS | `live-checks.txt` |
| S2.2 | initdb + system identifier | Çıkış 0, sayı | 7702556342130788452 | PASS | `test-system-identifier.txt` (pg_controldata); aynı değer `S6-audit-hgs2_audit\args.txt` ve `stdout.txt` içinde |
| S2.3 | TLS sertifikaları | openssl ×3 çıkış 0 | 7 dosya oluştu | PASS | `stage-results.txt`; dosya listesi `runner\run3-console.log`. Sertifikalar arşivlenmedi |
| S2.4 | postgresql.conf eki | Yazıldı | Yazıldı | PASS | `stage-results.txt`; ayarların etkisi `S2-identity\stdout.txt`. Dosyanın kendisi arşivlenmedi |
| S2.5-a | Küme kimliği | 18.6, 55438, hgs2iso18, ssl on, data hgs2-iso | Tamamı eşleşti (`PostgreSQL 18.6 on x86_64-windows…`) | PASS | `S2-identity\stdout.txt` |
| S2.5-b | Test postmaster süreci var | ≥1 | Var (EK R1-8 karşılaştırmasıyla) | PASS | `S2-port-pid.txt` |
| S2.5-c | 55438 dinleyicileri yalnızca test postmaster'a ait | Hepsi test | `127.0.0.1` ve `::1`, pid 1296, test_postmaster=True | PASS | `S2-port-pid.txt` |
| S2.5-d | args tırnaklaması (R-N7) | Bağlantı dizesi tek argüman | Doğru | PASS | `S2-identity\args.txt` |
| S3-a | Global fixture | 3 DB, rol, REVOKE | Doğru; `hibrit_giris_db` datacl `{=T/postgres,…}` (PUBLIC'te `c` yok) | PASS | `S3-fixture-global\` |
| S3-b | Şema fixture | 4 tablo, sahip hgs2_perftest | Doğru, relacl boş | PASS | `S3-fixture-db\` |
| S3-c | hgs2_perftest parolası | Çıkış 0 | 0 | PASS | `S3-perftest-password\` |
| S4-a | Rol oluşturma (onaylı kopya) | `HGS2_ROLE_DESIGN_OK`, 3 BILGI, stderr boş | Tamamı sağlandı; GRANT üretilmedi | PASS | `S4-role-create\` |
| S4-b | Parola SCRAM biçiminde | `SCRAM-SHA-256$` ×2 | ×2 | PASS | `S4-password-check\` |
| S4-c | Günlükte `ALTER ROLE … PASSWORD` yok | 0 | 0 | PASS | `log\postgres.log` |
| S5-a | Bağımsız rol doğrulaması (A–G, `v1_role_ok` içinde 31 ölçüt) | `HGS2_V1_ROLE_VERIFY_OK` ×1 | ×1, tüm satırlar t/0 | PASS | `S5-role-verify\` |
| S5-b | Pozitif bağlantı (TLS) | `hgs2_audit\|hgs2_audit\|hgs2_perftest_db\|t` | Aynısı | PASS | `S5-pos-connect\` |
| S5-c | `SET ROLE hgs2_perftest` | 42501, çıkış ≠0 | `42501 permission denied to set role`, çıkış 1 | PASS | `S5-neg-set-role\` |
| S5-d | `SELECT public.users` | 42501 | `42501 permission denied for table users`, çıkış 1 | PASS | `S5-neg-select-users\` |
| S5-e | `CREATE TABLE public.v1_probe` | 42501 | `42501 permission denied for schema public`, çıkış 1 | PASS | `S5-neg-create-table\` |
| S6 | Nihai SQL denetimi | Çıkış 0, PREFLIGHT, COMPLETE | Çıkış 0; PREFLIGHT satır 24, COMPLETE satır 277; TLSv1.3, `TLS_AES_256_GCM_SHA384`, 256 bit (L20); sunucu system_identifier = beklenen | PASS | `S6-audit-hgs2_audit\` (`exit.txt`, `stdout.txt`, `stderr.txt`) |
| S6-h | SQL SHA-256 (çalıştırmadan hemen önce) | 5916d1… | Eşit | PASS | `audit_sql.sha256` |
| S7 | Doğrulayıcı (7 kural) | PASS, çıkış 0 | `PASS`, `validator_exit=0`; uyarı kabul edilmedi | PASS | `verdict.txt`, `verdict-explicit.txt` |
| S8-a | `hgs2_audit` → hibrit (disable) | Çıkış 2, pg_hba reddi | Çıkış 2, `… no encryption` | PASS | `S8-audit-hibrit-disable\` |
| S8-b | `hgs2_audit` → hibrit (require) | Çıkış 2, pg_hba reddi | Çıkış 2, `… SSL encryption` | PASS | `S8-audit-hibrit-require\` |
| S8-c | Günlükte 28000 ≥2, oturum 0 | ≥2 / 0 | 2 / 0 | PASS | `S8-log-28000.txt` |
| S9-a | `hgs2_perftest` kendi DB'si | Bağlanır | `hgs2_perftest\|hgs2_perftest_db` | PASS | `S9-perftest-own-db\` |
| S9-b | `hgs2_perftest` → hibrit = 42501 | Çıkış 2, 42501; 28000/28P01 yok | Çıkış 2, `permission denied for database` | PASS | `S9-perftest-hibrit\` |
| S9-c | Günlükte 42501 ≥1, 28xxx 0 | ≥1 / 0 | 1 / 0 | PASS | `S9-log-sqlstate.txt` |
| S10.1 | Küme durdu, port boş, süreç 0 | — | Port listen 0, süreç 0 | PASS | `S10.1-port-free.txt` |
| S10.2 | Parola (×3) ve özel anahtar taraması | 0 | 0 | PASS | Parola sayıları `runner\run3-console.log` L316–318. Anahtar sayısı yazdırılmaz; kapı sonucu `stage-results.txt` (`S10.2-secret-scan PASS`) |
| S10.2+ | Transcript + konsol günlüğü taraması (D4) | 0 | 3 rol × 2 dosya = 0 | PASS | `runner\run3-console.log` L326–331 |
| S10.3 | Arşiv kopyası | Hash kümesi eşit | 90 dosya, eşit | PASS | `stage-results.txt` |
| S10.4 | Test kökü silme | 7 kapı + RunId | Silindi | PASS | `stage-results.txt` |
| S11-a | SQL / plan / matris bütünlüğü | AYNI ×3 | AYNI ×3 | PASS | `integrity-end.sha256` |
| S11-b | Canlı servis başlangıç = bitiş | True | True | PASS | `SUMMARY.txt`; `live-start.json` / `live-end.json`; `live-start-5432.txt` / `live-end-5432.txt` |
| S11-c | Nihai sonuç | `SONUC: V1 TAMAMLANDI` | `SONUC: V1 TAMAMLANDI` | PASS | `SUMMARY.txt` |
| LC | Canlı servis + 5432 kontrol noktaları | Hepsi unchanged | 15/15 unchanged | PASS | `live-checks.txt`. `after-S1` noktası yalnızca `runner\run3-console.log` L78'dedir |
| POST | Bağımsız son doğrulama (arşiv manifesti, gizli bilgi sezgisel taraması, kök yok, port boş, canlı servis, servis listesi) | — | Manifest 95/95; PEM, `private key`, pgpass biçimi ve 32 karakterlik token: 0; kök yok | PASS (yürütme oturumu çıktısı) | **Arşivlenmiş kanıt yok.** Manifest ve gizli bilgi kontrolleri arşiv üzerinde yeniden yapılabilir. Kökün yokluğu ve 55438'in boş olduğu `SUMMARY.txt` ile ayrıca desteklenir; servis listesi ve son canlı servis okuması için kanıt dosyası yoktur |

## B. Eksik çalıştırmalar (sonuç değiştirilemez)

| RunId | Aşama | Durum | Not |
|---|---|---|---|
| `iso18-20261030T223605` | S1, S2.2–S2.4 | RECORDED / PASS (kayıtlı) | Oturum kaybı |
| | S2.5–S11 | **NOT RUN** | Runbook §12.3 gereği devam ettirilmedi |
| | Özgün §10.2 taraması | **NOT RUN** | `$TestSecrets` kayboldu. pgpass kaynaklı ikame tarama 0 eşleşme verdi |
| | Kapanış (arşiv + silme) | PASS | `INCOMPLETE_STATUS.md` |
| `iso18-20261030T230745` | S0–S2.4 | PASS | — |
| | S2.5 | **FAIL** | `GUARD: test postmaster bulunamadi`. Kök neden EK R1-8 |
| | S3–S11 | **NOT RUN** | DUR |
| | Özgün §10.2 taraması | **NOT RUN** | Süreç sonlandı. İkame tarama 0 eşleşme verdi |
| | Kapanış (arşiv + silme) | PASS | İlk denemede `PRIVATE KEY` yanlış pozitifi (EK R1-9) nedeniyle arşivleme durdu; dar istisnayla tekrarlandı |

## C. V1 kapsamı dışında kalanlar (runbook §0.3) — NOT RUN

| Test | Durum |
|---|---|
| T2–T5 (üyelik, tablo SELECT, sahiplik, CREATE ihlali negatif senaryoları), T6, T7 | NOT RUN (V1 dışı) |
| T8-b / T8-c / T8-e (OPEN/MISORDER pg_hba, PUBLIC CONNECT) | NOT RUN (V1 dışı) |
| T9 (IPv6 bağlantı testleri). `::1` dinleyicisi var, ancak bağlantı sınanmadı | NOT RUN (V1 dışı) |
| T10 (hostssl, verify-full, sahte CA, channel_binding, ssl=off) | NOT RUN (V1 dışı) |
| RC-02, RC-04, RC-05 | NOT RUN (V1 dışı) |
| Gerçek kümede `hgs2_perftest` 42501 | NOT RUN, **yasak**. UNVERIFIED |
