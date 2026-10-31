# HGS2 PostgreSQL Read-Only Audit V2 — 2. Aşama Raporu

- Tarih: 2026-10-30 (+03:00)
- Hedef dosya: `postgresql_readonly_audit_v2.sql`
- Kanıt klasörü: `asama2-kanit/` (bu dosyanın yanında; içerik dizini en sonda)
- Bu rapor nihai onay DEĞİLDİR. 3. aşamadaki bağımsız denetime girdi olarak hazırlanmıştır.

---

## 1. Başlangıç dosyasının hash değeri

| Alan | Değer |
|---|---|
| SHA-256 | `726771681923c156925f571a81aca4b6bd0d02a456f1ef0d679c7822630e6f4b` |
| Boyut / satır | 56 048 bayt / 1 130 satır |
| Kayıt zamanı | Hiçbir değişiklik yapılmadan önce, çalışmanın ilk adımında |
| Yedek | `asama2-kanit/baseline/postgresql_readonly_audit_v2.ORIGINAL.sql` (aynı hash) |

## 2. Son dosyanın hash değeri

| Alan | Değer |
|---|---|
| SHA-256 | `b8eb2ac69b04ddc9ab6407798bf490a9bf80dccb32abf5fb96118b52fd1db841` |
| Boyut / satır | 72 646 bayt / 1 407 satır |
| Biçim | UTF-8, BOM yok, LF satır sonu (CRLF yok) |
| Test edilen dosya | Son test turu bu hash üzerinde çalıştı (`asama2-kanit/runs/FILE_UNDER_TEST.sha256`) |

Kullanmadan önce hash'i doğrulayın. Dosyada bundan sonra yapılacak her değişiklik bu raporu geçersiz kılar.

---

## 3. Yapılan geliştirmeler

Satır numaraları son dosyaya göredir.

| Kod | Konu | Yer |
|---|---|---|
| T1 | Sunucu tarafı transaction sondası (psql -1 / önceden açık transaction) | P3, satır 304–334 |
| T2 | P2 yeniden düzenlendi: önce xid kontrolü, sunucu sürüm kapısı BEGIN öncesine alındı, operatörler nitelendi | P1 183, P2 265 |
| T3 | `SET LOCAL search_path = pg_catalog, pg_temp` ve P4'te doğrulanması | 336, 344 |
| T4 | `expected_system_identifier` zorunlu; yetki yoksa durur; replika durumu raporlanır | P1b 212, P7 547 |
| T5 | Süper kullanıcı: yalnızca tam `1` kabul ediliyor; session_user + current_user + is_superuser kontrol ediliyor; kapı "kapalı kalma" (fail-closed) biçiminde | P8 588 |
| T6 | TLS raporlama (`pg_stat_ssl`); loopback dışı ve TLS'siz TCP'de durdurma; verify-full sınırı belgelendi | P6b 498, başlık "TLS" |
| T7 | Tüm parametre varlık kontrolleri BEGIN'den önce | P1b 212 |
| T8 | `FETCH_COUNT 0`, `\encoding UTF8`, pager kapalı | 172–180 |
| T9 | Kapsam genişletmesi (aşağıda) | Bölüm 5 |
| — | Otomasyon kuralı: başarı için stderr'in de boş olması şart | Başlık "ÇIKIŞ KODLARI" |
| — | Yanlış başlık bilgisi düzeltildi: pg_control_system() varsayılanda PUBLIC'e açıktır | Başlık, P7 |

**T9 kapsam değişiklikleri (Bölüm 3 "SQL kapsamı" incelemesi sonucunda):**

| Sorgu | Eksik / hata | Düzeltme |
|---|---|---|
| 5.4a | `has_table_privilege` sütun düzeyindeki yetkileri görmez. Sütun düzeyinde SELECT almış bir rol `f` görünüyordu. | `perftest_any_column` sütunu (`has_any_column_privilege`) eklendi |
| 5.4 | grantor ve grant seçeneği yoktu | `grantor`, `is_grantable` eklendi |
| 5.5b | Yalnızca beklenen 4 identity sequence vardı; serial ve bağımsız sequence yetkileri görünmüyordu | Kullanıcı şemalarındaki TÜM sequence'lar + `expected_identity` bayrağı |
| 5.11 | SECURITY DEFINER için `proconfig` (search_path) ve EXECUTE yetkisi yoktu | `proconfig`, `perftest_execute` eklendi |
| 5.12 | Şema adı yoktu | `table_schema` eklendi |
| 5.14b | Foreign server (ör. dblink/postgres_fdw ile prod'a erişim yolu) denetlenmiyordu | Yeni sorgu. umoptions (parola) OKUNMAZ; yalnızca user mapping sayısı alınır |
| 5.15 | Politika rolleri, ifadeleri ve FORCE RLS yoktu | `rls_forced`, `policy_roles`, `using_expr`, `with_check_expr` eklendi |
| 5.16 | LO ACL'si yoktu | `with_explicit_acl` eklendi |

Yorumlar her bölüm için hangi kataloğun okunduğunu, gereken yetkiyi ve sınırları belirtecek biçimde güncellendi. Gereksiz sorgu eklenmedi. Tek yeni sorgu 5.14b'dir.

## 4. Düzeltilen güvenlik sorunları

Her satırdaki "eski davranış", orijinal V2'nin (`726771…`) gerçek PostgreSQL üzerinde çalıştırılmasıyla ölçüldü. Yeni davranış son dosyayla (`b8eb2ac6…`) ölçüldü. Hücre biçimi: `çıkış kodu / işaretçi`.

### G1 — Açık transaction tespiti zaman damgasına bağımlıydı (T1, T2)
- **Sorun:** `now() = statement_timestamp()` bir ipucudur, güvenlik garantisi değildir (kaba saat çözünürlüğü veya saat geri ayarı). Orijinal sürümde tek engel buydu. Bu engel aşılırsa psql -1'in BEGIN'i betiğin BEGIN'ini etkisiz bırakıyor ve `default_transaction_isolation=repeatable read` + `default_transaction_read_only=on` ile P4 kontrolleri de geçiliyordu.
- **Eski davranış:** Zaman kapısı kaldırılmış orijinal + `psql -1` + bu varsayılanlar → **0 / COMPLETE** (O6, PG 12 ve 18). Yani yanlış başarı.
- **Yeni davranış:** BEGIN'den hemen sonra izolasyon önce READ COMMITTED'a, sonra REPEATABLE READ'e çevriliyor. Transaction önceden açıksa P1/P2 SELECT'leri anlık görüntü almış oluyor ve PostgreSQL bunu `SET TRANSACTION ISOLATION LEVEL must be called before any query` (25001) hatasıyla reddediyor. xid kontrolü zamandan bağımsız olduğu için önce yapılıyor. Hot standby'da da çalışıyor (SERIALIZABLE kullanılmıyor).
- **Kanıt:**
  - P2 kaldırıldığında bile sonda durduruyor: M3 (psql -1 + RR/RO varsayılanları), M5 (önceden açık RR+RO), A25 (SAVEPOINT içinde) → 4 sürümde **3**.
  - P2 ve sonda birlikte kaldırıldığında yanlış başarı geri geliyor: M4 → 4 sürümde **0 / COMPLETE**. Sondanın gerekliliği böylece kanıtlandı.
  - Normal akışta P2 aynı durumları işaretçiyle yakalıyor: A19–A23 `open_transaction`, A24 `open_transaction_with_xid`.
- **Güvenlik etkisi:** psql -1 veya önceden açık transaction ile yanlış başarı üretilmesi, zamanlamaya bağlı olmadan engelleniyor.

### G2 — search_path gölgeleme ile kapı kontrollerinin ve maskelemenin atlatılması (T3)
- **Sorun:** Orijinal sürümde kapı kontrollerindeki `text = text` karşılaştırmaları oturumun search_path'ine bağlıydı. Rol veya veritabanı düzeyindeki bir `search_path` ayarı (ör. veritabanı sahibinin `ALTER DATABASE … SET search_path`), kullanıcı şemasındaki sahte bir `=` operatörünü öne alabiliyordu.
- **Test:** PG 18 test kümesinde, `evil` şemasında `=(text,text)` operatörü tanımlandı. Operatör `'on'` dışındaki her karşılaştırmada true döndürüyordu. Oturum `search_path=evil,pg_catalog` ile açıldı. Parametreler bilerek yanlış verildi: `expected_host=attacker.example`, yanlış sistem kimliği, `expected_server_port=9999`.
- **Eski davranış:** O9 → **0 / COMPLETE**. Yanlış host, yanlış port ve yanlış sistem kimliği kabul edildi. Ayrıca Bölüm 4 maskelemesi atlatıldı ve sentetik gizli GUC değeri (`SENTETIK-GIZLI-DEGER`) çıktıya **açık metin** olarak yazıldı.
- **Yeni davranış:** X3 → **3 / client_host_mismatch**. Aynı saldırı altında doğru parametrelerle (X2) denetim tamamlanıyor ve değerler `<maskelendi>` kalıyor.
- **Statik kanıt:** QA B11: sabitleme penceresi (satır 336–1391) dışında nitelenmemiş fonksiyon veya operatör yok. P1, P2 ve son kontrol `OPERATOR(pg_catalog.=)` kullanıyor.
- **Güvenlik etkisi:** Hedef doğrulamasının ve gizli değer maskelemesinin, denetlenen tarafça manipüle edilmesi engelleniyor.

### G3 — Sistem kimliği isteğe bağlıydı (T4)
- **Eski:** O2 (sistem kimliği verilmeden) → **0 / COMPLETE**.
- **Yeni:**
  - A07 → 3 / `missing_parameter expected_system_identifier`
  - A12 → 3 / `system_identifier_mismatch`
  - A13 → 3 / `system_identifier_unverifiable` (EXECUTE yetkisi yok)
- **Not (yanlış varsayım düzeltildi):** Hem orijinal başlık hem benim ilk taslağım `pg_control_system()` fonksiyonunun varsayılanda PUBLIC'ten geri alındığını varsayıyordu. Gerçek test bunu çürüttü: 12/16/17/18'de `proacl = NULL`, yani fonksiyon PUBLIC'e açık. İlk turda A13 bu yüzden 0 ile tamamlanmıştı. Başlık metni düzeltildi. Yetkisiz yolu test etmek için test veritabanında sertleştirilmiş bir kurulum taklit edildi (PUBLIC'ten REVOKE, denetim rolüne GRANT; `harness/fixture_harden.sql`).
- **Replika:** `pg_is_in_recovery()` hem P6 satırında hem P7 satırında (`sunucu_rolu=…`) raporlanıyor. Fiziksel replikaların ve temel yedekten oluşturulmuş kopyaların aynı kimliği taşıdığı başlıkta ve P7'de belgelendi.

### G4 — `allow_superuser` yalnızca tanımlı olup olmadığına bakıyordu; süper kullanıcı rol arkasında gizlenebiliyordu (T5)
- **Eski:**
  - O3 (`allow_superuser=0`) → **0 / COMPLETE**
  - O4 (session_user süper kullanıcı, rolün `role` ayarıyla current_user sıradan) → **0 / COMPLETE**
- **Yeni:**
  - A14 (parametre yok), A15 (`=0`), A16 (`=true`), A18 (rol arkası) → 3 / `superuser_connection`
  - A17 (`=1`) → 0 / COMPLETE + UYARI satırı
- Kapı artık `\if :ok \else durdur` biçiminde. Değişken okunamazsa betik durur (fail-closed).

### G5 — TLS durumu görünmüyordu (T6)
- **Yeni:**
  - `tasima=`, `tls=`, `tls_surum=`, `sifre=`, `bit=` satırı eklendi.
  - Ayrıca şu satır yazılıyor: "tls=t yalnızca şifrelemeyi gösterir; verify-full SQL ile kanıtlanamaz".
  - Loopback dışı + TLS yok → `insecure_transport` ile durdurma. Yalnızca `allow_insecure_transport=1` ile geçilebilir.
- **Kanıt:**
  - T1 (`sslmode=require`) → `tls=t TLSv1.3`
  - T2 (`sslmode=disable`) → `tls=f`, loopback, denetim tamamlanıyor
  - Sınıflama ifadesinin birim testi 12 girdi ile yapıldı; `true` değeri reddediliyor (`runs/TLS_UNIT.txt`)

### G6 — Windows istemci kodlaması (T8)
- **Sorun:** psql, ifade içindeki yorumları ve sorgu sonuçlarını `client_encoding` üzerinden dönüştürür. Türkçe Windows konsolunda bu WIN1254 olabilir.
- **Eski:** O10 (WIN1254 + WIN1254'te karşılığı olmayan bir karakter içeren sentetik şema adı) → **3, işaretçisiz**. Hata PREFLIGHT_OK'tan sonra geldi, yani denetim yarım kaldı.
- **Yeni:** X4 → 0 / COMPLETE. QA B8: ifadelerin içinde ASCII dışı karakter yok.

### G7 — `FETCH_COUNT` ile yanlış pozitif (T8)
- **Eski:** O11, psql 12 + `-v FETCH_COUNT=10` → **3 / open_transaction**. psql P2 sorgusunu kendi BEGIN/imleci içine sarıyor. Güvenli yönde ama denetimi engelliyor. psql 18'de sorun oluşmadı.
- **Yeni:** X6 → psql 12 ve 18'de 0 / COMPLETE.

---

## 5. Parser test sonuçları (yalnızca SÖZDİZİMİ)

- **Araç:** pglast 8.7 / libpg_query (**PostgreSQL 18.6 parser'ı**). PyPI wheel SHA-256'sı PyPI kaydıyla doğrulandı.
- **Yöntem:**
  - psql meta-komutları ayıklandı ve `\gset` yerine `;` konuldu.
  - `:'değişken'` yerine sabit bir literal yazıldı.
  - **Tüm `\if` dalları** ayrıştırıldı (PG 12–15 dalı ve PG 12 xid dalı dahil).

| Ölçüm | Sonuç |
|---|---|
| SQL parçası | 80 |
| Sözdizimi hatası | **0** |
| İfade türleri | SelectStmt 72, TransactionStmt 2 (BEGIN, ROLLBACK), VariableSetStmt 5, VariableShowStmt 1 |
| SELECT … INTO / FOR UPDATE / veri değiştiren CTE | yok |
| Yan etkili / hassas fonksiyon (nextval, setval, set_config, lo_*, pg_advisory*, dblink*, pg_read_file, pg_sleep, txid_current …) | yok |
| Çağrılan farklı fonksiyon sayısı | 39 (liste `runs/QA_NEW.txt`) |

**Sınır:** Bu test SQL sözdizimini doğrular. Katalog sütunlarının varlığını, fonksiyon imzalarını, yetkileri ve sürüm uyumluluğunu doğrulamaz. Ayrıca yalnızca 18.6 parser'ıdır. Bunlar Bölüm 6'daki gerçek sunucu testleriyle ayrıca doğrulandı. Parser testi bir sunucu testi olarak sayılmamalıdır.

**Statik kontroller** (sunucu yok; `runs/QA_NEW.txt`):

| Kontrol | Sonuç |
|---|---|
| Meta-komutlar | `\set` 10, `\pset` 1, `\encoding` 1, `\gset` 13, `\if` 36, `\else` 31, `\echo` 39, `\quit` 25, `\endif` 36 |
| Tehlikeli meta-komut (`\!`, `\o`, `\w`, `\copy`, `\g dosya`, `\gexec`, `\setenv`, `\i`, `\c`, `\lo_*` …) | yok |
| `\if` / `\endif` dengesi | 36 / 36, kapanmamış yok, `\elif` yok |
| `\gset` değişkenleri | 46. Tanımsız kullanım yok, kullanılmayan yok (kullanılmayan `superuser_explicitly_allowed` QA sırasında bulunup kaldırıldı) |
| `ON_ERROR_STOP` | Tek atama: satır 173 `on`. Dosyada kapatılmıyor |
| ABORT blokları | 25'i de `\echo işaretçi` → `SELECT '…'::pg_catalog.int4` (aynı neden) → `\quit` biçiminde |
| Transaction | BEGIN 332 → SET TRANSACTION 333, 334 → SET LOCAL 336, 337, 338 → ROLLBACK 1391. COMMIT/END yok |
| COMPLETE işaretçisi | Tek kez (satır 1402), tüm başarı yolu ifadelerinden sonra, `\if :no_open_tx_after_rollback` dalında. Ardından yalnızca `\else` dalındaki ABORT SELECT'i var |
| Yazma/DDL/DCL anahtar sözcüğü (yorum ve literal dışı) | yok |
| Sürüm dalları | `server_v12` (204), `server_v13` (280), `pg12` (434), `pg16` (664), `pg17` (963) |

## 6. PostgreSQL sürüm test sonuçları (gerçek sunucu)

| Sürüm | Kaynak | Port | system_identifier |
|---|---|---|---|
| 12.22 | EDB taşınabilir zip (scratchpad) | 55412 | 7702464714983728304 |
| 16.15 | EDB taşınabilir zip (scratchpad) | 55416 | 7702464758499443628 |
| 17.11 | EDB taşınabilir zip (scratchpad) | 55417 | 7702464802515936996 |
| 18.6 | Kurulu PG 18 ikili dosyaları; ayrı `initdb` ile scratchpad'de **yeni** küme. Çalışan servise dokunulmadı | 55418 | 7702462757662851240 |

**Ortam:**
- Tüm kümeler yalnızca `127.0.0.1`'i dinledi; unix soketi kapalıydı.
- `pg_hba`: yalnızca `host all all 127.0.0.1/32 trust`.
- `ssl=on` (geçici, kendinden imzalı sertifika); `log_statement=all`.
- Kümeler testten sonra durduruldu.
- Zip SHA-256 değerleri: `env/edb-binary-zips.sha256`.
- Windows MAX_PATH nedeniyle 9 dosya açılmadı: `.mo` çevirileri, Perl test modülleri, PG 12'nin "unpackaged" betiği. Hiçbiri testte kullanılmıyor (`env/*-skipped-long-paths.txt`).

**Sentetik test veritabanı:**
- `admins`, `devices`, `logs`, `users` (identity PK, 3 unique, 2 FK, `parmak_izi_sablonu oid`).
- Her tabloda tek satır sentetik veri. Gerçek kullanıcı, parola veya parmak izi verisi yok.
- Roller ve ACL'ler sentetiktir (`harness/fixture_*.sql`).
- `hibrit_giris_db` adı yalnızca isim olarak sentetik test kümesinde oluşturuldu; içi boştur.

**Senaryo × sürüm matrisi** (her sürüm kendi psql'iyle; `runs/MATRIX.md`, `runs/EVALUATION.txt`):

| Senaryo | PG12 | PG16 | PG17 | PG18 |
|---|---|---|---|---|
| N1 normal (yetkili, süper kullanıcı değil, RO) | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE |
| N2 psql 18 → sunucu | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE | — |
| N3 psql 12 → sunucu 18 | — | — | — | 0 / COMPLETE |
| A01 yanlış veritabanı | 3 / wrong_database | ← | ← | ← |
| A02 `hibrit_giris_db` adı | 3 / production_database | ← | ← | ← |
| A03–A06 eksik host / port / server_addr / server_port | 3 / missing_parameter … | ← | ← | ← |
| A07 eksik sistem kimliği | 3 / missing_parameter expected_system_identifier | ← | ← | ← |
| A08 yanlış host | 3 / client_host_mismatch | ← | ← | ← |
| A09 yanlış port | 3 / client_port_mismatch | ← | ← | ← |
| A10 yanlış sunucu adresi | 3 / server_addr_mismatch | ← | ← | ← |
| A11 yanlış sunucu portu | 3 / server_port_mismatch | ← | ← | ← |
| A12 yanlış sistem kimliği | 3 / system_identifier_mismatch | ← | ← | ← |
| A13 yetkisiz system_identifier okuması | 3 / system_identifier_unverifiable | ← | ← | ← |
| A14 süper kullanıcı | 3 / superuser_connection | ← | ← | ← |
| A15 `allow_superuser=0` | 3 / superuser_connection | ← | ← | ← |
| A16 `allow_superuser=true` | 3 / superuser_connection | ← | ← | ← |
| A17 `allow_superuser=1` | 0 / COMPLETE | ← | ← | ← |
| A18 rol arkasında süper kullanıcı | 3 / superuser_connection | ← | ← | ← |
| A19 `psql -1` | 3 / open_transaction | ← | ← | ← |
| A20 `psql -1` + RR/RO varsayılanları | 3 / open_transaction | ← | ← | ← |
| A21 önceden açık transaction | 3 / open_transaction | ← | ← | ← |
| A22 önceden açık READ ONLY | 3 / open_transaction | ← | ← | ← |
| A23 önceden açık REPEATABLE READ | 3 / open_transaction | ← | ← | ← |
| A24 önceden açık + yazma (xid) | 3 / open_transaction_with_xid | ← | ← | ← |
| A25 SAVEPOINT içinde (P2 kaldırılmış) | 3 / işaretçisiz (sonda) | ← | ← | ← |
| M1 READ WRITE transaction (mutasyon) | 3 / tx_not_read_only | ← | ← | ← |
| M2 yanlış izolasyon (mutasyon) | 3 / tx_not_repeatable_read | ← | ← | ← |
| M3 P2 yok + `psql -1` + RR/RO | 3 / işaretçisiz (sonda) | ← | ← | ← |
| M4 P2 **ve** sonda yok + `psql -1` + RR/RO | **0 / COMPLETE** (beklenen yanlış başarı; sondanın gerekliliği) | ← | ← | ← |
| M5 P2 yok + önceden açık RR+RO | 3 / işaretçisiz (sonda) | ← | ← | ← |
| E1 komut satırında `ON_ERROR_STOP=0` | 3 / missing_parameter expected_host (dosya ayarı geçerli) | ← | ← | ← |
| E2 `ON_ERROR_STOP off` mutasyonu | 0 / ABORT işaretçisi var, COMPLETE yok (`\quit` ikincil emniyet) | ← | ← | ← |
| T1 `sslmode=require` | 0 / COMPLETE, tls=t | ← | ← | ← |
| T2 `sslmode=disable` (loopback) | 0 / COMPLETE, tls=f | ← | ← | ← |

"←" işareti soldaki hücreyle aynı sonucu gösterir. Toplam **144 çalıştırma, 144'ü beklentiye uygun.** Her çalıştırmanın `args.txt`, `exit.txt`, `stdout.txt` ve `stderr.txt` dosyaları `runs/<senaryo>/` altındadır.

**Her durdurma senaryosunda doğrulananlar:**
- Gerçek psql çıkış kodu kaydedildi.
- İşaretçi hem stdout'ta (`\echo`) hem stderr'de (hata mesajı) var.
- COMPLETE hiçbir satırda yok.
- `HGS2_AUDIT_PREFLIGHT_OK` yok.

**Başarılı senaryolarda:** Son satır tam olarak `HGS2_AUDIT_COMPLETE` ve stderr 0 bayt. Tek istisna M4 (bilinçli mutasyon).

**Hata yönetimi (2.5) bulguları:**
- `ON_ERROR_STOP`, psqlrc'ye ve komut satırına rağmen açık (E1).
- Kasıtlı int4 hatası her durdurmada çıkış kodu 3 üretiyor.
- Sunucu günlüğüne göre hatadan sonra betiğin hiçbir ifadesi çalışmadı. Hata sonrası görülen 31 ifadenin tamamı `psql -1` modunda psql'in kendi gönderdiği `COMMIT` (psql 12) veya `ROLLBACK` (psql 16+) (`runs/LOG_ANALYSIS.txt`).
- `\quit` doğru konumda, ancak yalnızca `ON_ERROR_STOP` kapalıysa devreye giriyor. O durumda çıkış **0** oluyor (E2). Bu nedenle otomasyon COMPLETE işaretçisini ve boş stderr'i birlikte şart koşmalıdır. Kural başlıkta yazılıdır.

## 7. Başarılı testler

- **Durdurma ve normal akış:** 144/144 (Bölüm 6).
- **Katalog ve ACL senaryoları (5.3):** 8 kombinasyonun her birinde (4 sürüm + psql 18→12/16/17 + psql 12→18) **28/28** doğrulama geçti (`runs/CATALOG_ASSERTIONS.txt`):
  - PUBLIC CONNECT / TEMPORARY
  - Doğrudan tablo yetkisi
  - Dolaylı rol üyeliği (perftest → grp_nested → grp_reader) ile tablo yetkisi
  - Sütun düzeyi SELECT (5.4a'da tablo `f` / sütun `t`, 5.4c'de iki sütun)
  - Identity sequence yetkisi
  - Serial sequence yetkisi
  - Default privileges
  - `ALTER ROLE ALL SET` (maskeli)
  - Rol / rol+veritabanı / veritabanı ayarları
  - Beklenmeyen identity sequence
  - Serial sequence ("serial / OWNED BY")
  - Extension nesnesi (`pg_stat_statements` view)
  - RLS politikası (rol ve ifadeyle)
  - Büyük nesne metadata'sı
  - 5.17 özet (4 / 5)
  - `parmak_izi_sablonu oid`
  - Gizli GUC değeri hiçbir çıktıda yok
- **Ek kapsam** (X5, PG 12 ve 18):
  - prod'a işaret eden sentetik foreign server ve 1 user mapping görünüyor; **user mapping parolası çıktıda yok**.
  - Trigger, event trigger, `SECURITY DEFINER` + boş `proconfig` ve LO ACL'si (`with_explicit_acl=1`) doğru raporlanıyor.
- **MAINTAIN dalı:** 17/18'de sorgu çalışıyor; 12/16'da bilgi satırı yazılıyor.
- **Salt okunur doğrulaması (5.4):**
  - Testten önce ve sonra alınan anlık görüntüler 4 sürümde birebir aynı: `pg_dump -s` şema + ACL'ler, `pg_dumpall -g` roller ve rol ayarları, tablo verisi md5'i, sequence son değerleri, LO metadata'sı, `pg_db_role_setting`, `pg_database` ACL'leri, `pg_auth_members`. Fark sayısı **0/12**. pg_dump'ın her çalıştırmada rastgele ürettiği `\restrict` anahtar satırları hariç tutuldu (`runs/READONLY_SNAPSHOT_DIFF.txt`).
  - Sunucu günlüğüne göre betiğin gönderdiği ifade türleri yalnızca SELECT, WITH, BEGIN, SET, SHOW, ROLLBACK. İzin dışı ifade **0**.
- **REPEATABLE READ ve ROLLBACK** (PG 12 ve 18, `runs/RR/`):
  - Betiğin transaction kipinde, eşzamanlı oturumun commit ettiği tablo görünmedi (0→0). READ COMMITTED ile görünür oldu (0→1).
  - Salt okunur transaction'da geçici tablo oluşturma bile reddedildi (`cannot execute CREATE TABLE in a read-only transaction`).
  - ROLLBACK sonrasında açık transaction kalmadı.
- **Saldırı ve kodlama:** X2, X3, X4, X6 (Bölüm 4).

## 8. Başarısız testler

- **Son dosya üzerinde başarısız test yok.**
- Süreç içinde ortaya çıkan ve giderilen durumlar:
  1. **A13 ilk turda 0 / COMPLETE verdi.** Neden test değil, belgedeki yanlış varsayımdı (pg_control_system() varsayılanda PUBLIC'e açık). Başlık metni düzeltildi; yetkisiz yol sertleştirilmiş kurulum taklidiyle test edildi (G3).
  2. **Katalog doğrulamasında 2 kalıp hatası** (16+ sürümlerde sütun genişliği, `read` komutunun sondaki `|` karakterini kırpması). Hata betikte değil test ifadesindeydi; kalıplar düzeltildi.
  3. **QA, kullanılmayan bir `\gset` değişkeni buldu** (`superuser_explicitly_allowed`); kaldırıldı. Ardından bütün testler son dosya üzerinde baştan çalıştırıldı.
- **M4'ün 0 / COMPLETE sonucu bir başarısızlık değil, beklenen sonuçtur.** Bilinçli bir mutasyondur: sonda kaldırıldığında açığın geri geldiğini gösterir.

## 9. Test edilemeyen senaryolar

| Senaryo | Neden | Yerine yapılan |
|---|---|---|
| Loopback dışı TCP + TLS yok (uçtan uca) | Geçici kümeyi ağa açmak gerekirdi; yapılmadı | SQL ifadesinin 12 girdili birim testi (PG 12 ve 18) |
| `sslmode=verify-full` + gerçek CA; SCRAM + `channel_binding=require` | Test kümeleri `trust` ve kendinden imzalı sertifika kullandı | Belgelendi. SQL tarafında zaten kanıtlanamaz |
| Unix soketi (`local-socket` yolu) | Windows test kümelerinde soket kapatıldı | Yok (statik inceleme) |
| Hot standby / fiziksel replika (`recovery=t`) | Replika kurulmadı | Kod yolu yalnızca raporlama yapıyor; statik inceleme |
| Pooler / proxy (`client_server_port_differ`) | Kurulmadı | Yok |
| psql 10/11 ve sunucu 13/14/15 | Bu aşamada istenen sürümler 12/16/17+ idi | psql 12/16/17/18 ve çapraz psql 18→12/16/17, 12→18 |
| psql < 10 (`psql_too_old`), sunucu < 12 (`server_too_old`) | İkili dosya yok | Statik inceleme |
| P2 zaman ipucunun kendiliğinden yanılması | Deterministik olarak üretilemez | Mutasyonlarla (M3/M5/A25) sondanın tek başına yeterli olduğu gösterildi |
| `statement_timeout` / `lock_timeout` tetiklenmesi | Kilit bekleten bir senaryo kurulmadı | Değerlerin uygulandığı çıktıda doğrulandı (`statement_timeout= 30s lock_timeout= 5s`) |
| Etkileşimli `\i` | Etkileşimli oturum yok | `-c BEGIN … -f` ile aynı sunucu durumu taklit edildi (A21–A24) |
| Linux / diğer derlemeler | Yalnızca Windows ikili dosyaları kullanıldı | — |
| Gerçek `hgs2_perftest_db` | Bu aşamanın kapsamı dışında | — |

## 10. Gerçek veritabanına bağlantı kurulmadığının doğrulaması

- Makinede `127.0.0.1:5432` üzerinde çalışan `postgresql-x64-18` servisi tespit edildi. Bu servise **bağlanılmadı**. Servis durdurulmadı, yapılandırılmadı; veri dizini ve günlükleri **okunmadı**. Yalnızca kurulu ikili dosyalar, scratchpad'de ayrı ve yeni bir küme (`initdb`) oluşturmak için kullanıldı.
- Tüm psql çağrıları `tpsql` koruma fonksiyonundan geçti (`harness/env.sh`). Fonksiyon yalnızca `-h 127.0.0.1` ve 55412/55416/55417/55418 portlarına izin verir, diğer portlarda durur. `pg_dump` ve `pg_dumpall` açık `-h 127.0.0.1 -p 554xx` ile çağrıldı.
- `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSERVICE`, `PGOPTIONS` ve `PGPASSWORD` silindi. `PGSERVICEFILE`, `PGPASSFILE`, `PGSYSCONFDIR` ve `PSQLRC` var olmayan scratchpad yollarına yönlendirildi. Ayrıca her çağrıda `-X` kullanıldı.
- Fixture betikleri, `data_directory` scratchpad içinde değilse kendini durduruyor.
- Çıktılarda sunucunun bildirdiği system_identifier değerlerinin tamamı (61 satır) 4 test kümesine ait. Sunucunun bildirdiği portların tamamı (84 satır) 55412/16/17/18. Hiçbir çalıştırma argümanında `-p 5432` yok. (`expected_port=5432` yalnızca A09/A11'de yanlış **beklenen değer** olarak verildi; bağlantı test portuna yapıldı.)
- `hgs2_perftest_db` ve `hibrit_giris_db` adları yalnızca geçici test kümelerinde sentetik olarak oluşturuldu.
- HGS2 uygulaması başlatılmadı. Maven çalıştırılmadı.
- **Sınır:** Bu doğrulama yapı ve kayıtlar üzerinden yapıldı. Gerçek sunucunun günlükleri bilerek okunmadığı için, o tarafta bağlantı olmadığı oradan kanıtlanmadı.

## 11. V1 dosyasının değişmediğinin doğrulaması

| Ölçüm | Çalışma başında | Çalışma sonunda |
|---|---|---|
| SHA-256 | `3423053a…c7ff` | `3423053a254ca6ff361631562e9e9a26e112fddd4e4ea5a5a9b539c0e984c7ff` |
| Boyut | 24 630 | 24 630 |
| mtime | 2026-10-30 01:12:41.581 | 2026-10-30 01:12:41.581 |

V1, yanındaki `SHA256SUMS.txt` içinde kayıtlı değildi. Başlangıç hash'i bu çalışmanın ilk adımında kaydedildi ve V2 başlığındaki değerle aynıdır.

## 12. Bilinen sınırlamalar

1. **P3 sondasının hatası işaretçisizdir** (çıkış 3, `HGS2_AUDIT_ABORT` yok). Normal koşullarda P2 aynı durumu işaretçiyle daha önce yakalar. Sonda yalnızca ikinci katmandır. Otomasyon "3 + işaretçi yok" durumunu başarısız saymalıdır; başlıkta yazılıdır.
2. **Sonda, PostgreSQL'in `check_transaction_isolation` davranışına dayanır.** 12–18'de doğrulandı. Her yeni ana sürümde yeniden test edilmelidir.
3. **Hataya dayalı durdurma,** etkileşimli `\i` kullanımında kullanıcının açık transaction'ını iptal eder; belgelendi.
4. **TLS:** `tls=t` yalnızca şifrelemeyi gösterir. Sunucu sertifikasının istemcide doğrulandığı (verify-full) SQL üzerinden **kanıtlanamaz**. Loopback (ör. SSH tüneli veya yerel proxy) TLS'siz kabul edilir.
5. **system_identifier** fiziksel replikalarda ve temel yedekten oluşturulan kopyalarda aynıdır. Primary ile klonu ayırt etmez; yalnızca recovery durumu raporlanır. Host ve port da kriptografik kimlik değildir.
6. **Süper kullanıcı yetkisine sahip bir saldırgan** katalogları ve `pg_catalog` fonksiyonlarını değiştirebilir. Betik, hedef sunucunun süper kullanıcı düzeyinde ele geçirilmediğini varsayar.
7. **`pg_hba.conf` sorgulanmaz.** ACL sonuçları gerçek bağlantı davranışının tamamını göstermez.
8. **Paylaşılan kataloglar** (Bölüm 2–4) küme genelini gösterir. Bölüm 5 yalnızca bağlı veritabanını gösterir; `hibrit_giris_db`'nin şeması hakkında sonuç vermez.
9. **Katalog okuma yetkileri** varsayılan kurulumda doğrulandı. Katalog SELECT yetkilerini PUBLIC'ten geri alan sertleştirilmiş kurulumlarda bazı sorgular yetki hatası (işaretçisiz 3) verebilir.
10. **Bölüm 4 maskelemesi bir izin listesine dayanır.** Listedeki ayarların değerleri açık gösterilir.
11. **`\encoding UTF8`,** WIN1254 konsolda Türkçe karakterleri bozuk gösterebilir (yalnızca görüntü sorunu).
12. **Testler yalnızca Windows ikili dosyalarıyla yapıldı.** EDB zip'leri HTTPS ile indirildi; satıcının yayımladığı bir checksum ile karşılaştırılmadı (hash'leri kayıtlıdır).
13. **Parser testi PG 18.6 dilbilgisiyle yapıldı.** Eski sürüm uyumluluğu yalnızca gerçek sunucu testleriyle doğrulandı.

## 13. Bir sonraki bağımsız denetim için öneriler

1. Çalıştırmadan önce dosya hash'ini doğrulayın: `b8eb2ac6…d1db841`.
2. Test düzeneğini (`asama2-kanit/harness/`) bağımsız bir makinede, tercihen Linux'ta ve PG 13/14/15 ile psql 10/11'i de ekleyerek yeniden çalıştırın. Değerlendirici: `evaluate.py`; statik ve parser kontrolü: `qa.py`.
3. İzole bir laboratuvarda şunları uçtan uca deneyin:
   - Loopback dışı TLS'siz TCP (`insecure_transport`)
   - `verify-full` + gerçek CA
   - SCRAM + `channel_binding=require`
   - Hot standby
   - Unix soketi
   - Pooler
4. Otomasyon sarmalayıcısı şu üç koşulu birlikte uygulamalıdır:
   - (a) çıkış kodu 0
   - (b) stdout'un son satırı tam olarak `HGS2_AUDIT_COMPLETE`
   - (c) stderr boş

   Başka her durum BAŞARISIZ sayılmalıdır. M4 senaryosu, (c) koşulunun psql -1 atlatmasında uyarı satırlarını yakaladığını gösteriyor.
5. Gerçek çalıştırmadan önce `expected_system_identifier` değerini hedef sunucuda `pg_controldata` ile, ayrı ve onaylı bir kanaldan alın. Denetim rolünün süper kullanıcı olmadığını ve `pg_control_system()` için EXECUTE yetkisine sahip olduğunu önceden doğrulayın.
6. `allow_insecure_transport` ve TLS zorunluluğu bir **politika kararıdır**. Bu aşamada güvenli varsayılan olarak eklendi. Bağımsız denetim bu varsayılanı onaylamalı ya da değiştirmelidir.
7. G2 (search_path gölgeleme) bulgusu göz önüne alınarak, gerçek hedefte rol ve veritabanı düzeyindeki `search_path` ayarlarının (Bölüm 4 çıktısı) ayrıca incelenmesi önerilir.
8. Her PostgreSQL ana sürüm yükseltmesinde P3 sondası ve 5.4b / 2.3 sürüm dalları yeniden test edilmelidir.

---

### Kanıt klasörü dizini (`asama2-kanit/`)

| Yol | İçerik |
|---|---|
| `baseline/` | 2. aşama öncesi V2 (`726771…`) ve kayıt zamanı |
| `harness/` | Ortam koruması, küme yapılandırması, sentetik fixture'lar, senaryo seti, mutasyon üretici, değerlendirici, parser/statik QA, günlük analizcisi, saldırı/kodlama betikleri |
| `mutants/` | Mutasyon kopyaları (yalnızca test; çalıştırılabilir denetim betiği DEĞİLDİR) |
| `runs/` | Her senaryonun argümanları, çıkış kodu, stdout ve stderr'i; `EVALUATION.txt`, `MATRIX.md`, `CATALOG_ASSERTIONS.txt`, `READONLY_SNAPSHOT_DIFF.txt`, `LOG_ANALYSIS.txt`, `QA_NEW.txt`, `QA_ORIGINAL.txt`, `COMPARISON_ORIGINAL_VS_NEW.txt`, `TLS_UNIT.txt`, `RR/` |
| `snapshots/` | Önce/sonra anlık görüntüleri (4 sürüm) |
| `server-logs/` | Test kümelerinin `log_statement=all` günlükleri |
| `env/` | EDB zip ve pglast wheel hash'leri, açılmayan dosyalar |
| `SHA256SUMS.txt` | Klasördeki tüm dosyaların hash'leri |
