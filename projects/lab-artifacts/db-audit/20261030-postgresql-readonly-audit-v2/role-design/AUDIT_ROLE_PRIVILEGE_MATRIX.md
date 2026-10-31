# AUDIT_ROLE_PRIVILEGE_MATRIX — `hgs2_audit` yetkilendirme mimarisi

- Proje: HGS2 PostgreSQL Read-Only Audit V2
- Tarih: 2026-10-30 (+03:00)
- Hedef rol: `hgs2_audit` (henüz **yok**; bu belge yalnızca tasarımdır)
- Hedef ortam: PostgreSQL 18.6, Windows, yerel servis. Test veritabanı `hgs2_perftest_db`, korunan veritabanı `hibrit_giris_db`, mevcut uygulama/test rolü `hgs2_perftest`.
- Analiz edilen betik: `asama3-final/postgresql_readonly_audit_v2.sql` (SHA-256 `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`, 1630 satır)

**Yöntem: yalnızca statik analiz ve dokümantasyon.**
- PostgreSQL'e bağlanılmadı. psql çalıştırılmadı. Hiçbir SQL çalıştırılmadı.
- CREATE ROLE / ALTER ROLE / GRANT / REVOKE yapılmadı. Servisler, `pg_hba.conf` ve `application.properties` okunmadı, değiştirilmedi.
- Gerçek kümenin `pg_hba.conf` dosyası **okunmadı**. Bu belgedeki pg_hba önerileri kullanıcının aktardığı bulgulara dayanır.
- `asama3-final/` ve önceki aşamaların kanıt dosyaları değiştirilmedi. Git işlemi yapılmadı.
- Oluşturulan tek dosya bu belgedir. Bölüm 11'deki SQL bir **taslaktır, çalıştırılmadı**.

**Kanıt etiketleri:**

| Etiket | Anlamı |
|---|---|
| **[SQL Lnnn]** | Nihai SQL dosyasının ilgili satırının statik okuması |
| **[K]** | Proje kanıtı: test çıktısı, fixture, anlık görüntü. Yol verilir. Yalnızca **test kümeleri** için geçerlidir (PG 12.22 / 16.15 / 17.11 / 18.6, `trust` kimlik doğrulama) |
| **[K-dolaylı]** | Proje kanıtından mantıksal çıkarım |
| **[PG]** | PostgreSQL semantiği / belgeleri. **Bu projede test edilmedi** |
| **[BEYAN]** | Kullanıcının aktardığı gerçek ortam bulgusu. Bu klasörde kanıt dosyası yok → **UNVERIFIED** |

**Durum etiketleri:** VERIFIED · NEEDS TEST · NEEDS DECISION · NOT APPLICABLE · UNVERIFIED

---

## 1. Executive Summary

1. **Betiğin yetki ihtiyacı küçüktür ve stok PG 18.6'da tamamı PUBLIC üzerinden gelir.** [SQL] [K]
   - Gerekenler: `LOGIN`; `hgs2_perftest_db` üzerinde `CONNECT`; `hgs2_perftest_db` içinde `pg_catalog` ve `public` şemalarında `USAGE`; 21 katalog ilişkisinde `SELECT` (18 tablo + 3 görünüm); 40 yerleşik fonksiyon imzasında `EXECUTE` (sunucu başına 39 çalışır) ve 3 görünüm içi fonksiyon.
   - Testlerdeki `hgs2_auditor` rolü yalnızca PUBLIC varsayılanları + `pg_control_system()` için açık GRANT ile 4 sürümde `HGS2_AUDIT_COMPLETE` verdi (`kanit/runs-final/N1-normal-pg{12,16,17,18}`).
   - **Sonuç:** Stok bir hedefte `hgs2_audit` için **sıfır GRANT** beklenir. Her GRANT yalnızca hedefte ilgili PUBLIC yetkisinin eksik olduğu ölçülürse, yalnızca `hgs2_audit`'e ve yalnızca `hgs2_perftest_db` içinde verilir.

2. **Görevde örnek olarak listelenen bazı nesneleri betik KULLANMAZ.** [SQL, grep]
   - `pg_index`, `pg_shdepend`, `pg_settings`, `pg_database_size()`, `pg_size_pretty()`, `pg_get_functiondef()`, `pg_authid`, `pg_largeobject`, `pg_stat_activity`, `pg_hba_file_rules`, `lo_*` fonksiyonları: kod satırlarında **0** geçiş.
   - Bunlar için yetki tasarlanmaz. (`pg_shdepend` yalnızca Bölüm 11'deki **yönetici** doğrulamasında, süper kullanıcı oturumunda kullanılır.)

3. **`pg_control_system()` zorunludur ve stokta PUBLIC'e açıktır.** [SQL L669–698] [K-dolaylı]
   - Betik fail-closed: yetki yoksa `system_identifier_unverifiable` ile durur. Atlanamaz.
   - Yeni kanıt: 4 sürümün `pg_dump` anlık görüntülerinde `REVOKE ALL ON FUNCTION pg_catalog.pg_control_system(...) FROM PUBLIC` satırı var (`kanit/snapshots/before/pg{12,16,17,18}/schema.sql`, satır 358–360). `pg_dump`, sistem nesnelerinde yalnızca initdb başlangıç ACL'sinden **farkı** yazar. Bu satır, initdb başlangıcında PUBLIC EXECUTE bulunduğunu gösterir.
   - Gerçek `hgs2_perftest_db` içindeki `proacl` değeri bilinmiyor → **NEEDS TEST**.

4. **`hibrit_giris_db` izolasyonu için tek hedefli kontrol `pg_hba.conf`'tur.** [PG]
   - PostgreSQL ACL'lerinde "deny" girdisi yoktur. PUBLIC'e verilmiş bir CONNECT, tek bir rol için geri alınamaz.
   - Önerilen: `hgs2_audit` için `pg_hba.conf` dosyasının **en üstüne** "yalnızca `hgs2_perftest_db`, yalnızca loopback, `scram-sha-256`; geri kalan her şey `reject`" kuralları. Bu satırlar yalnızca `hgs2_audit` kullanıcı adıyla eşleşir. Diğer rollerin bağlantı davranışı değişmez.
   - Sıralama: **önce pg_hba, sonra rol.** Rol, var olduğu ilk andan itibaren yalnızca hedef veritabanına bağlanabilir.
   - `hibrit_giris_db` ACL'sine ve PUBLIC CONNECT'e **dokunulmaz**.
   - [BEYAN] `hgs2_perftest`'in `hibrit_giris_db` üzerinde CONNECT yetkisi yok. Bu bulgu `has_database_privilege` (etkin yetki) ile ölçüldüyse PUBLIC CONNECT o veritabanında zaten kaldırılmıştır, çünkü PUBLIC yetkisi her role uygulanır. Ölçüm yöntemi bilinmiyor → **NEEDS TEST**.

5. **PUBLIC'ten gelen ve betiğin ihtiyaç duymadığı artıklar vardır.** Bunlar tek bir rol için kaldırılamaz:
   - `hgs2_perftest_db` üzerinde `TEMPORARY` → **NEEDS DECISION** (Bölüm 12, R10).
   - `public` şeması PG ≤ 14 kökenliyse PUBLIC `CREATE`. Bu, audit rolüne nesne **sahibi** olma yolunu açar → **NEEDS TEST**, sonra **NEEDS DECISION** (R11).
   - `postgres`, `template1` ve diğer veritabanlarında ACL düzeyinde CONNECT → pg_hba ile kapatılır.

6. **Betiğin kendi P8 kontrolü rolün gerçek yetkilerini tam görmez.** [SQL L722–783]
   - Şunları **algılamaz**:
     - sahiplik,
     - `hgs2_perftest` üyeliği,
     - `pg_database_owner`,
     - `pg_monitor` / `pg_read_all_settings` / `pg_read_all_stats` / `pg_maintain` vb.,
     - `CREATEDB` (yalnızca raporlar),
     - `NOINHERIT`, bağlantı limiti,
     - diğer veritabanlarına CONNECT,
     - audit rolüne **başkalarının** üye olması.
   - Bölüm 11'deki betik dışı doğrulama bu boşluğu kapatır.

7. **Bu çalışmada bulunan yeni riskler:**
   - **R09b:** Denetlenen taraf `hgs2_perftest`, kendi nesneleri üzerinde `hgs2_audit`'e GRANT verebilir. Bu, yönetici eylemi olmadan audit rolüne veri erişimi ekler. Kümenin tamamında `pg_shdepend` (`deptype = 'a'`) kontrolüyle tek bağlantıdan yakalanır.
   - **R13:** Rolü oluşturan süper kullanıcı oturumu `hgs2_perftest_db` içinde çalışır. Veritabanı sahibi `ALTER DATABASE … SET search_path` ile bu oturumu etkileyebilir. Taslak `search_path`'i ilk ifadede sabitler.
   - **R18:** `MINIMUM_PRIVILEGE_ANALYSIS.md` Q3 sorgusundaki `SELECT oid, * FROM pg_roles`, `pg_roles` zaten bir `oid` sütunu içerdiği için `a.oid` başvurusunda belirsizlik hatası verebilir [PG]. Belge değiştirilmedi. Taslak bu kalıbı kullanmaz.

8. **Önerilen rol:** `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2`.
   - Üyelik yok, sahiplik yok, rol düzeyi ayar yok.
   - Parola dosyada değil, `\password` ile verilir (SCRAM).
   - Oluşturan: süper kullanıcı.
   - Süre (`VALID UNTIL`) ve denetim dışında `NOLOGIN` → **NEEDS DECISION**.

---

## 2. Analyzed Files and Hashes

### 2.1 Başlangıç hash'leri (analizden önce hesaplandı)

| Dosya | SHA-256 (başlangıç) | Not |
|---|---|---|
| `asama3-final/postgresql_readonly_audit_v2.sql` | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` | Nihai SQL; tamamı okundu (1–1630) |
| `asama3-final/MINIMUM_PRIVILEGE_ANALYSIS.md` | `272b7091885d1d9ef25435d3a97f5bc629429c81bd712f2a3da2183ad86cbce6` | Tamamı okundu. `FINAL_SHA256SUMS.txt` kapsamında **değil** |
| `asama3-final/FINAL_DELIVERY.md` | `b395295d16ad4e8b5d8d40018a272d18986abe93736afbc9f2a0d70557821a9b` | §1–5, §8–9 okundu. `FINAL_SHA256SUMS.txt` kapsamında **değil** |
| `asama3-final/FINAL_SECURITY_AUDIT.md` | `1ce8c81485d0f9ba2d301a363f47d966b36a7762161695990af9b69637c27f8e` | §1–7 okundu |
| `asama3-final/FINAL_TEST_MATRIX.md` | `a64714d9582f311da0b0a3b6f4d9eea9cd59281c5febbfa36891acf76be9ee69` | Başlıklar; ilgili satırlar |
| `asama3-final/KNOWN_LIMITATIONS.md` | `13fac2fc4be69259d27d24e2626c916c0775e2507be922280ce3b4222af298a5` | Tamamı okundu |
| `asama3-final/CHANGELOG_FINAL.md` | `a284b4d8561f80f09006c3d3f543ebf649e5a8eca958e8f8414e1c78bae9dd87` | Başlıklar |
| `asama3-final/FINAL_SHA256SUMS.txt` | `f0afda59544d32d9708d8cf50d8dbb571a8145302ce42fd78859649523beb589` | 3119 satır, 3114 hash girdisi |
| `postgresql_readonly_audit_v2.sql` (proje kökü) | `b8eb2ac69b04ddc9ab6407798bf490a9bf80dccb32abf5fb96118b52fd1db841` | 2. aşama sonu sürümü; nihai dosya **değil**; analiz edilmedi |

Ek olarak salt okunur incelenen kanıtlar (değiştirilmedi):
- `kanit/harness/fixture_global.sql`, `fixture_harden.sql`, `fixture_db.sql`, `snap3.sql`, `suite3.sh`, `evil_full_setup.sql`, `fixture_v3_global.sql`
- `kanit/runs-final/N1-normal-pg{12,16,17,18}/{args.txt,stdout.txt,exit.txt}`
- `kanit/snapshots/before/pg{12,16,17,18}/schema.sql`
- `kanit/snapshots/{after,after_special}/pg*/state.txt`
- `kanit/server-logs/pg18-standby.log`

Başlangıç bütünlük kontrolleri:
- `asama3-final/` altında 3117 dosya. Her birinin hash'i kaydedildi (oturum scratchpad'i, proje dışında).
- `sha256sum -c FINAL_SHA256SUMS.txt`: **3114 OK, 0 FAILED**.
- Manifest dışındaki 3 dosya: `FINAL_SHA256SUMS.txt` (kendisi), `FINAL_DELIVERY.md`, `MINIMUM_PRIVILEGE_ANALYSIS.md`. Bunlar ayrıca yukarıdaki tabloyla izlendi.

### 2.2 Bitiş doğrulaması

Bölüm 2.3'e bakınız (bu belge yazıldıktan sonra hesaplandı).

### 2.3 Bitiş sonuçları

Bu belge yazıldıktan sonra, aynı yöntemle hesaplandı.

| Kontrol | Başlangıç | Bitiş | Sonuç |
|---|---|---|---|
| Nihai SQL SHA-256 | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` | **Aynı** |
| `asama3-final/` 3117 dosyanın hash listesi | kaydedildi | kaydedildi | **Birebir aynı** (`diff` boş) |
| `sha256sum -c FINAL_SHA256SUMS.txt` | 3114 OK / 0 FAILED | 3114 OK / 0 FAILED | **Değişmedi** |
| `FINAL_SHA256SUMS.txt` | `f0afda59…beb589` | `f0afda59…beb589` | Aynı |
| `FINAL_DELIVERY.md` (manifest dışı) | `b395295d…821a9b` | `b395295d…821a9b` | Aynı |
| `MINIMUM_PRIVILEGE_ANALYSIS.md` (manifest dışı) | `272b7091…ccbce6` | `272b7091…ccbce6` | Aynı |
| Proje kökündeki tüm dosyalar (3863) | kaydedildi | 3863 + 1 | Tek fark: yeni `role-design/AUDIT_ROLE_PRIVILEGE_MATRIX.md` |

- PostgreSQL bağlantısı: **yok**. SQL / psql çalıştırılmadı.
- Git işlemi: **yok** (proje klasörü bir git deposu değil).

---

## 3. SQL Dependency Inventory

Kaynak: dosyanın 1–1630 satırlarının tamamının okunması ve tam satır yorumları hariç tutularak yapılan sözcüksel tarama (`grep`). Satır numaraları nihai dosyaya aittir.

### 3.1 İfade türleri [SQL]

| Tür | Adet / satır | Yetki gereksinimi |
|---|---|---|
| `SELECT` / `WITH … SELECT` | Tüm denetim sorguları | Bölüm 5–6 |
| `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` | L406 | Yok [PG] |
| `SET TRANSACTION ISOLATION LEVEL …` | L407, L408 | Yok [PG] |
| `SET LOCAL search_path / statement_timeout / lock_timeout` | L410–412 | Yok; üçü de USERSET [PG] |
| `SHOW transaction_read_only` | L415 | Yok |
| `ROLLBACK` | L1614 | Yok |
| `CREATE` / `ALTER` / `DROP` / `GRANT` / `REVOKE` / `INSERT` / `UPDATE` / `DELETE` / `COPY` / `DO` / `CALL` / `LOCK` | **0** | — |

### 3.2 psql meta-komutları ve istemci değişkenleri [SQL]

| Meta-komut | Adet | Sunucu yetkisi |
|---|---|---|
| `\set` | 14 | Yok (istemci) |
| `\pset` | 6 | Yok (istemci) |
| `\encoding UTF8` | 1 (L251) | Sunucuya `client_encoding` ayarı gider; USERSET, yetki gerekmez [PG] |
| `\if` / `\else` / `\endif` | 39 / 32 / 39 | Yok (istemci) |
| `\gset` | 13 | Yok (istemci) |
| `\echo` | 45 | Yok (istemci) |
| `\quit` | 26 | Yok (istemci) |

Okunan psql değişkenleri: `VERSION_NUM`, `SERVER_VERSION_NUM`, `DBNAME`, `HOST`, `PORT`, beş `expected_*`, `allow_*`, `audit_*_timeout`. Hepsi istemci tarafıdır, sunucu yetkisi gerektirmez. SQL'e yalnızca `:'var'` biçiminde (tırnaklı sabit) aktarılır [SQL; FINAL_DELIVERY §4.2].

### 3.3 `current_setting()` ile okunan ayarlar [SQL]

| Ayar | Satır | `GUC_SUPERUSER_ONLY`? | Not |
|---|---|---|---|
| `transaction_read_only`, `transaction_isolation`, `search_path`, `statement_timeout`, `lock_timeout` | L420–426 | Hayır | Oturum/transaction ayarları |
| `server_version_num`, `server_version` | L503–509 | Hayır | |
| `port` | L533, 536, 538, 540 | Hayır | |
| `cluster_name` | L542 | Hayır | |
| `is_superuser` | L725 | Hayır | |

Sonuç: `pg_read_all_settings` **gerekmez**. **VERIFIED** [K]: süper kullanıcı olmayan `hgs2_auditor` ile N1-normal 4 sürümde COMPLETE.

### 3.4 Ad çözümleme ve tür dönüşümleri [SQL]

| Yapı | Satır | Yetki etkisi |
|---|---|---|
| `'pg_catalog.pg_class'::regclass` (sabit) | L1224, 1226, 1258, 1260, 1338, 1340, 1346, 1348, 1354, 1374, 1376, 1566, 1568, 1584, 1586 | Ayrıştırma sırasında `regclassin`: `pg_catalog` şemasında **USAGE** denetlenir. `pg_class` üzerinde SELECT **gerekmez** [PG] |
| `'pg_catalog.pg_proc'::regclass` | L1440 | Aynı |
| `'pg_catalog.pg_control_system()'` metni → `has_function_privilege(text,text)` | L669 | `regprocedurein`: `pg_catalog` USAGE [PG] |
| `pg_catalog.to_regclass('public.users')` | L1318 | Nitelenmiş ad → `public` şemasında **USAGE** denetimi; yetki yoksa NULL değil **hata** beklenir [PG] → **NEEDS TEST** (R02) |
| `pg_catalog.to_regnamespace('public')` | 12 yerde (L1068 … L1609) | Yalnızca OID arar, USAGE denetlemez [PG]. Testte çalıştı [K] |
| `con.confrelid::regclass` (çıktı) | L1302 | `regclassout`: yetki denetimi yok [PG] |
| `tg.tgfoid::regprocedure` (çıktı) | L1457 | `regprocedureout`: yetki denetimi yok [PG] |
| `::pg_catalog.int4` (ABORT ve P1) | 29 yer | Tür girdi fonksiyonu; ACL denetimi yok [PG] |
| `::inet`, `::int`, `::text`, `::pg_catalog.text` | L608–610, 503–509, 632, 756–757, 537, 680–681 | G/Ç dönüşümü veya `pg_catalog` cast fonksiyonu; PUBLIC EXECUTE |
| `current_user`, `session_user` | çeşitli | SQL anahtar sözcüğü (SQLValueFunction); EXECUTE denetimi yok [PG] |
| Operatörler: `=`, `<>`, `>=`, `>`, `+`, `\|\|`, `~`, `!~`, `<<=` (inet), `IN`, `OPERATOR(pg_catalog.=)`, `OPERATOR(pg_catalog.>=)` | çeşitli | Arkalarındaki fonksiyonlar için EXECUTE denetlenir; hepsi `pg_catalog`'da ve PUBLIC [PG]; testte çalıştı [K] |

### 3.5 search_path penceresi [SQL]

- L266–375 (P1, P2) ve L1621 (ROLLBACK sonrası), sabitlenmiş `search_path` **dışında** çalışır. Bu ifadelerde fonksiyon, operatör ve türlerin tamamı `pg_catalog.` ile nitelenmiştir.
- L410'dan L1614'e kadar `search_path = pg_catalog, pg_temp` sabittir ve L422/L445'te doğrulanır (`search_path_not_pinned` ile durur).
- `pg_temp` fonksiyon ve operatör çözümlemesinde hiç aranmaz [PG]. İlişkiler zaten hep `pg_catalog.` ile nitelenmiştir.
- **VERIFIED** [K]: FINAL_DELIVERY §4.2, S1–S5 saldırı senaryoları, 4 sürüm.

**Yetki sonucu:** Betik kullanıcı şemalarındaki hiçbir fonksiyonu, operatörü veya türü çağırmaz. Bu yüzden kullanıcı şemalarında USAGE/EXECUTE gerekmez. Tek istisna 5.8'deki `public` USAGE ad çözümlemesidir.

---

## 4. Database and Schema Privilege Matrix

| Nesne / Yetki | Kullanım noktası | Gerekli mi? | Varsayılan PUBLIC yetkisi | Özel GRANT gerekli mi? | Güvenlik notu | Kanıt / Durum |
|---|---|---|---|---|---|---|
| Rol özniteliği `LOGIN` | Bağlantı | **Evet** | — | Rol oluşturulurken verilir | Denetim dışında `NOLOGIN` tutmak bir seçenektir (R15) | [SQL KULLANIM L35–47] VERIFIED |
| `CONNECT` on `hgs2_perftest_db` | Bağlantı; L461 `on_target_db` | **Evet** | Var (`=Tc`, `datacl` NULL ise) | **Hayır**, yalnızca hedefte PUBLIC'ten geri alınmışsa `hgs2_audit`'e | ACL tek başına yetmez; pg_hba kuralı da gerekir (Bölüm 10). Veritabanı sahibi `hgs2_perftest` bu yetkiyi istediği zaman kaldırabilir (R14: fail-closed) | [K] N1 3.3/3.4: PUBLIC CONNECT `t`. Hedef: **NEEDS TEST** |
| `TEMPORARY` on `hgs2_perftest_db` | Kullanılmaz. L410'daki `pg_temp` yalnızca ad çözümleme sırasıdır | **Hayır** | Var (`T`) | — | READ ONLY transaction'da `CREATE TEMP TABLE` reddedilir [PG]. Denetim **dışındaki** oturumlarda geçici nesne oluşturma imkânı verir. Tek role özel kaldırılamaz | **NEEDS DECISION** (R10) |
| `CREATE` on `hgs2_perftest_db` (şema oluşturma) | Kullanılmaz | **Hayır; olmamalı** | Yok | — | Verilirse rol şema **sahibi** olabilir | Taslak §6 doğrular |
| `CONNECT` on `hibrit_giris_db` | Kullanılmaz. 3.1–3.4 paylaşılan `pg_database`'ten okur, bağlantı gerekmez | **Hayır; olmamalı** | Stokta var; gerçek kümede [BEYAN] muhtemelen kaldırılmış | — | Bağlanılırsa betik `production_database` ile durur (L476–481). Ama bağlantının kendisi ihlaldir. Kontrol: pg_hba `reject` | **NEEDS TEST** (R05, R17) |
| `CONNECT` on `postgres`, `template1`, diğerleri | Kullanılmaz | **Hayır; olmamalı** | Stokta var | — | ACL'de açık kalır, pg_hba ile kapatılır. PUBLIC'ten REVOKE **önerilmez** (küme geneli etki) | **NEEDS TEST** (R05) |
| `USAGE` on schema `pg_catalog` | Bütün nitelenmiş adlar ve `::regclass` sabitleri | **Evet** | Var (initdb) | Hayır | Kaldırılmış olması kümenin genel olarak bozuk olduğunu gösterir; GRANT değil inceleme gerekir | [K] VERIFIED (test) |
| `USAGE` on schema `public` (`hgs2_perftest_db`) | **Yalnızca L1318** `to_regclass('public.users')` (5.8) | **Evet** | PG 15+ yeni DB: `=U/pg_database_owner`; PG ≤ 14 kökenli: `=UC` | **Hayır**, yalnızca hedefte PUBLIC'ten geri alınmışsa `hgs2_audit`'e | `public` şemasının sahibi (PG15+: `pg_database_owner` = `hgs2_perftest`) bu yetkiyi kaldırabilir → 5.8'de işaretçisiz çıkış 3 (fail-closed) | [K] N1 5.1: `=U` var. Kaldırılmış durumdaki davranış: **NEEDS TEST** (R02) |
| `CREATE` on schema `public` | Kullanılmaz | **Hayır; olmamalı** | PG 15+ yeni DB: yok. PG ≤ 14 kökenli (`pg_upgrade`, eski template): **var** | — | Varsa audit rolü nesne oluşturup **sahip** olabilir. Tek role özel kaldırılamaz | [K] PG12 N1: `=UC`; PG16+: `=U`. Hedef: **NEEDS TEST → NEEDS DECISION** (R11) |
| `USAGE` / `CREATE` on diğer kullanıcı şemaları | Yalnızca `pg_namespace` satırları ve OID karşılaştırmaları | **Hayır** | Yok | — | — | [SQL] VERIFIED |
| `USAGE` on `information_schema` | Yalnızca `nspname <> 'information_schema'` metin filtresi (L1036 vb.) | **Hayır** | Var | — | Zararsız PUBLIC artığı | [SQL] VERIFIED |
| Tablespace `CREATE` | Kullanılmaz | **Hayır** | Yok | — | — | Taslak §8 |
| `SET` / `ALTER SYSTEM` on parameter (PG 15+ `pg_parameter_acl`) | Kullanılmaz | **Hayır** | Yok | — | — | Taslak §6 |

### 4.1 `public` USAGE bağımlılığının ayrıntısı

- **Neden tek bağımlılık L1318?** `public` adı geçen diğer yerler (5.3–5.17) ya `to_regnamespace('public')` (USAGE denetlemez) ya da `n.nspname = 'public'` metin karşılaştırması kullanır. Bu ikisi şema USAGE istemez [PG].
- **`to_regclass` davranışı [PG]:**
  - Nitelenmiş ad için şema adı `LookupExplicitNamespace` ile çözülür ve çağıran rol için `USAGE` denetlenir.
  - "Bulunamadı" durumu NULL döner. Ancak yetki eksikliğinin hata (`permission denied for schema public`) vermesi beklenir.
  - PG 16'da `to_reg*` fonksiyonları "soft error" altyapısına taşındı. Şema ACL denetiminin bu altyapıya dahil olup olmadığı bu projede doğrulanmadı.
  - → **NEEDS TEST** (test kümesinde `REVOKE USAGE ON SCHEMA public FROM PUBLIC` + çalıştırma; Bölüm 13, T1-05).
- **`search_path` etkisi:** Yoktur. Ad nitelenmiş (`public.users`) olduğundan `search_path` kullanılmaz. L410'daki sabitleme bu sorguyu etkilemez.
- **Tasarım kararı:** Betik değişmeyeceği için `public` USAGE **gereklidir**. Stokta PUBLIC'ten geldiği için GRANT üretilmez. Hedefte eksikse yalnızca `hgs2_audit`'e verilir (Taslak §3).

---

## 5. Catalog Access Matrix

Ortak bilgiler:
- Hiçbir satır kullanıcı tablosu verisi okumaz [SQL].
- Kataloglar her zaman `pg_catalog.` ile nitelenir.
- **PUBLIC varsayılanı [PG]:** initdb, `pg_catalog` ilişkilerinde PUBLIC'e SELECT verir. İstisnalar: `pg_authid`, `pg_shadow`, `pg_user_mapping`, `pg_largeobject`, `pg_statistic`, `pg_statistic_ext_data`, `pg_subscription` (sütun düzeyi), `pg_hba_file_rules` ve benzeri bazı görünümler. Betik istisnaların **hiçbirini** kullanmaz.
- **[K]:** Aşağıdaki 21 ilişkinin tamamı, katalog GRANT'i olmayan `hgs2_auditor` ile 4 sürümde okundu (N1-normal → COMPLETE).

Sonuç: 21 ilişkinin hiçbiri için **özel GRANT gerekmez**. Hedefte doğrulama Taslak §4'te (Q2a eşdeğeri) → **NEEDS TEST**.

| # | Tam ad | Tür | Paylaşılan | Kullanım noktası (satır) | Amaç | Gerekli erişim | PUBLIC varsayılan | Özel GRANT | Sürüm farkı |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `pg_catalog.pg_roles` | **Görünüm** (`pg_authid` üzerinde; `rolpassword` `********`) | Evet (taban) | P8 L723–736; 2.1 L793; 2.2 L811; 2.3 L827–828, 838–839; 2.4 L855, 861; 3.2 L894; 4 L993; 5.1 L1026; 5.4a L1113; 5.4b L1152; 5.5b L1247; 5.11 L1412 | Rol öznitelikleri, ad↔OID | SELECT (görünüm). Taban tabloya erişim görünüm sahibinin yetkisiyle yapılır [PG] | Var | Hayır | Kullanılan sütunlar 12–18'de aynı |
| 2 | `pg_catalog.pg_auth_members` | Tablo | Evet | 2.3 L826, 837 | Doğrudan üyelikler | SELECT | Var | Hayır | `inherit_option`, `set_option` yalnızca **PG 16+** (L819 dalı) |
| 3 | `pg_catalog.pg_database` | Tablo | Evet | 3.1 L884; 3.2 L900; 3.3 L915; 3.4 L926; 4 L992 | Sahip, `datacl`, bağlantı ayarları | SELECT | Var | Hayır | `datconnlimit = -2` (geçersiz DB) yeni alt sürümlerde; yetkiyle ilgisiz |
| 4 | `pg_catalog.pg_db_role_setting` | Tablo | Evet | 4 L991 | Kalıcı rol/DB ayarları (`setconfig`) | SELECT | Var | Hayır | — |
| 5 | `pg_catalog.pg_namespace` | Tablo | Hayır | 5.1 L1034; 5.2 L1051; 5.4d L1200; 5.5 L1222, 1230; 5.5b L1272; 5.6 L1287; 5.7 L1305; 5.9 L1361; 5.10 L1392; 5.11 L1445; 5.12 L1460; 5.14 L1478; 5.15 L1529; 5.17 L1582 | Şemalar, `nspacl` | SELECT | Var | Hayır | PG15+: `public` sahibi `pg_database_owner` |
| 6 | `pg_catalog.pg_class` | Tablo | Hayır | 5.2–5.5b, 5.6, 5.7, 5.9, 5.12, 5.15, 5.17 (L1050 … L1608, 24 erişim) + 15 `::regclass` sabiti | İlişkiler, `relacl`, `relowner`, RLS bayrakları | SELECT | Var | Hayır | — |
| 7 | `pg_catalog.pg_attribute` | Tablo | Hayır | 5.4c L1177; 5.5 L1231; 5.5b L1257; 5.8 L1317; 5.9 L1372; 5.17 L1572, 1590 | Sütun ACL, identity, tür | SELECT | Var | Hayır | `attidentity` PG10+ |
| 8 | `pg_catalog.pg_depend` | Tablo | Hayır | 5.5 L1223; 5.5b L1255; 5.9 L1337, 1345, 1353, 1370; 5.11 L1439; 5.17 L1565, 1583 | Identity/serial/extension bağımlılığı | SELECT | Var | Hayır | — |
| 9 | `pg_catalog.pg_constraint` | Tablo | Hayır | 5.6 L1285; 5.7 L1303; 5.17 L1597, 1602, 1607 | PK/UNIQUE/FK sayısı ve tanımı | SELECT | Var | Hayır | **PG 18:** NOT NULL `contype = 'n'`; betik p/u/f filtreler |
| 10 | `pg_catalog.pg_type` | Tablo | Hayır | 5.10 L1391, 1396 | Bağımsız kullanıcı türleri | SELECT | Var | Hayır | — |
| 11 | `pg_catalog.pg_proc` | Tablo | Hayır | 5.11 L1444 (+ L1440 `::regclass` sabiti) | Kullanıcı fonksiyonları, `prosecdef`, `proconfig` (maskeli) | SELECT | Var | Hayır | `prokind` PG11+ |
| 12 | `pg_catalog.pg_trigger` | Tablo | Hayır | 5.12 L1458 | Kullanıcı trigger'ları | SELECT | Var | Hayır | — |
| 13 | `pg_catalog.pg_event_trigger` | Tablo | Hayır | 5.13 L1469 | Event trigger'lar | SELECT | Var | Hayır | **PG 17+** `login` olayı (R16) |
| 14 | `pg_catalog.pg_extension` | Tablo | Hayır | 5.14 L1477 | Extension'lar | SELECT | Var | Hayır | — |
| 15 | `pg_catalog.pg_foreign_server` | Tablo | Hayır | 5.14b L1501 | FDW sunucuları (yalnızca seçenek adları) | SELECT | Var | Hayır | — |
| 16 | `pg_catalog.pg_foreign_data_wrapper` | Tablo | Hayır | 5.14b L1502 | FDW adı | SELECT | Var | Hayır | — |
| 17 | `pg_catalog.pg_user_mappings` | **Görünüm** (`pg_user_mapping` + `pg_foreign_server` + `pg_authid`) | Hayır | 5.14b L1499 (yalnızca `count(*)`) | User mapping sayısı | SELECT. Görünüm içi `pg_has_role(oid,text)` ve `has_server_privilege(oid,text)` için EXECUTE [PG] | Var | Hayır | Taban `pg_user_mapping` PUBLIC'e kapalıdır; betik onu kullanmaz |
| 18 | `pg_catalog.pg_policy` | Tablo | Hayır | 5.15 L1530 | RLS politikaları (sabitler maskeli) | SELECT | Var | Hayır | — |
| 19 | `pg_catalog.pg_default_acl` | Tablo | Hayır | 5.4d L1199 | Varsayılan yetkiler | SELECT | Var | Hayır | **PG 18:** `defaclobjtype = 'L'` (büyük nesne) |
| 20 | `pg_catalog.pg_largeobject_metadata` | Tablo | Hayır | 5.16 L1543 | LO sayısı, sahip, açık ACL sayısı | SELECT | Var | Hayır | İçerik tablosu `pg_largeobject` **kullanılmaz** (PUBLIC'e kapalı) |
| 21 | `pg_catalog.pg_stat_ssl` | **Görünüm** (`pg_stat_get_activity(NULL)` üzerinde) | — (oturum durumu) | P6b L604 (yalnızca `pg_backend_pid()` satırı) | Bu oturumun TLS durumu | SELECT + `pg_stat_get_activity(integer)` EXECUTE. Kendi oturum satırı tam görünür; `pg_read_all_stats` **gerekmez** [PG] [K] | Var | Hayır | PG14'te `compression` sütunu kaldırıldı; betik kullanmaz |

**Kullanılmayan ve yetki tasarımına girmeyen nesneler** [SQL, grep = 0]:
- `pg_index`, `pg_shdepend`, `pg_settings`, `pg_authid`, `pg_shadow`, `pg_user_mapping` (taban), `pg_largeobject`, `pg_statistic`, `pg_subscription`, `pg_stat_activity`, `pg_hba_file_rules`, `pg_tablespace`, `pg_init_privs`, `pg_sequence`, `information_schema.*`
- `pg_index` ve `pg_sequence` bilinçli olarak kullanılmaz (FINAL_SECURITY_AUDIT §2).

**Belge tutarsızlığı (yalnızca not):** `FINAL_SECURITY_AUDIT.md` §2 "18 katalog" der. Betik 18 katalog **tablosu** ve 3 **görünüm**, toplam 21 ilişki kullanır. Yetki sonucunu değiştirmez.

---

## 6. Function EXECUTE Matrix

Ortak bilgiler:
- **PUBLIC varsayılanı [PG]:** Fonksiyonlarda varsayılan ACL PUBLIC'e EXECUTE verir.
- initdb, `system_functions.sql` ile bazı yerleşiklerden bu yetkiyi geri alır. Örnekler: `pg_read_file`, `pg_ls_dir`, `pg_stat_reset*`, `lo_import` / `lo_export` (sunucu tarafı), `pg_reload_conf`, `pg_rotate_logfile`, yedekleme ve WAL fonksiyonları.
- Aşağıdaki fonksiyonların **hiçbiri** bu listede değildir.
- `pg_control_system()` için: [K-dolaylı] stokta PUBLIC EXECUTE vardı; testte fixture ile geri alındı.
- **[K]:** `pg_control_system` dışındaki her fonksiyon, EXECUTE GRANT'i olmayan `hgs2_auditor` ile çalıştı. Sürüme bağlı dallar ilgili sürümlerde çalıştı.

Sütun "Özel GRANT": stok hedefte gerekip gerekmediği.

| # | İmza (overload) | Kullanım (satır) | EXECUTE gerekli | PUBLIC varsayılan | Özel GRANT | Güvenlik etkisi | Sürüm |
|---|---|---|---|---|---|---|---|
| 1 | `pg_catalog.now()` | P2 L355, 359; son L1621 | Evet | Var | Hayır | Yok | Tümü |
| 2 | `pg_catalog.statement_timestamp()` | L355, 359, 1621 | Evet | Var | Hayır | Yok | Tümü |
| 3 | `pg_catalog.pg_current_xact_id_if_assigned()` | P2 L356 (sunucu ≥ 13) | Evet | Var | Hayır | Yok | **PG 13+**; PG 18.6'da çalışan dal |
| 4 | `pg_catalog.txid_current_if_assigned()` | P2 L360 (sunucu < 13) | Yalnızca PG 12 | Var | Hayır | Yok | PG 10+; PG 18'de var ama çağrılmaz |
| 5 | `pg_catalog.current_setting(text)` | L420–426, 503–509, 533–542, 725 | Evet | Var | Hayır | Yalnızca süper kullanıcıya özel olmayan ayarlar (§3.3) | `current_setting(text,bool)` kullanılmaz |
| 6 | `pg_catalog.current_database()` | L461, 468, 470 | Evet | Var | Hayır | Yok | Tümü |
| 7 | `pg_catalog.regexp_replace(text,text,text,text)` | L470, 471, 746, 747, 1524, 1526 | Evet | Var | Hayır | Maskeleme ve kontrol karakteri temizliği | PG 15+ ek overload'lar var; `'g'` bilinmeyen sabiti text overload'a çözülür [PG]; 16–18 testte doğru [K] |
| 8 | `pg_catalog.host(inet)` | L532, 534 | Evet | Var | Hayır | Sunucu IP'si (düşük) | Tümü |
| 9 | `pg_catalog.inet_server_addr()` | L532, 534, 601 | Evet | Var | Hayır | Sunucu IP'si (düşük) | Tümü |
| 10 | `pg_catalog.inet_server_port()` | L537 | Evet | Var | Hayır | Yok | Tümü |
| 11 | `pg_catalog.pg_is_in_recovery()` | L541, 683 | Evet | Var | Hayır | Replika bilgisi (düşük) | Tümü |
| 12 | `pg_catalog.pg_backend_pid()` | L604 | Evet | Var | Hayır | Yok | Tümü |
| 13 | `pg_catalog.lower(text)` | L614, 616, 971, 973, 985, 989, 1420, 1436, 1496 | Evet | Var | Hayır | Yok | `lower(anyrange/anymultirange)` overload'ları seçilmez |
| 14 | `pg_catalog.has_function_privilege(text,text)` | P7 L669 | Evet | Var | Hayır | **current_user** için ölçer | Tümü |
| 15 | `pg_catalog.has_function_privilege(oid,oid,text)` | 5.11 L1443 | Evet | Var | Hayır | Başka rol adına yetki sorgulamak ek yetki istemez [PG] | Tümü |
| 16 | **`pg_catalog.pg_control_system()`** | P7 L685 (kapı L669–678) | **Evet, zorunlu, fail-closed** | Var [K-dolaylı] | **Koşullu**: yalnızca hedef `hgs2_perftest_db`'de PUBLIC'ten geri alınmışsa, yalnızca `hgs2_audit`'e | Döndürülen değerler: control sürümü, katalog sürümü, `system_identifier`, son değişiklik zamanı. Sır değildir. Düşük | PG 9.6+; 12–18 aynı imza |
| 17 | `pg_catalog.pg_has_role(name,oid,text)` | P8 L739, 740 | Evet | Var | Hayır | Üyelik sorgusu | Tümü |
| 18 | `pg_catalog.pg_has_role(oid,oid,text)` | 2.4 L859, 862 | Evet | Var | Hayır | — | Tümü |
| 19 | `pg_catalog.pg_get_userbyid(oid)` | 25 yer (L825 … L1540) | Evet | Var | Hayır | Rol adı çözümleme. Bilinmeyen OID için `unknown (OID=n)` döner [PG] | Tümü |
| 20 | `pg_catalog.has_database_privilege(oid,oid,text)` | 3.2 L897–899 | Evet | Var | Hayır | Bağlantı gerektirmez; paylaşılan katalog | Tümü |
| 21 | `pg_catalog.aclexplode(aclitem[])` | L916, 927, 1087, 1141, 1178, 1201 | Evet | Var | Hayır | ACL metaverisi | Tümü |
| 22 | `pg_catalog.acldefault("char",oid)` | L917 (`'d'`), 928, 1031 (`'n'`), 1088, 1141 (`'r'`) | Evet | Var | Hayır | — | Tümü |
| 23 | `pg_catalog.has_schema_privilege(oid,oid,text)` | 5.1 L1032, 1033 | Evet | Var | Hayır | — | Tümü |
| 24 | `pg_catalog.to_regnamespace(text)` | 12 yer | Evet | Var | Hayır | USAGE denetimi yok [PG] | PG 9.5+ |
| 25 | `pg_catalog.has_table_privilege(oid,oid,text)` | 5.4a L1121, 1128; 5.4b L1156 (`MAINTAIN`) | Evet | Var | Hayır | Tablo üzerinde SELECT gerektirmez | `'MAINTAIN'` yalnızca **PG 17+** (L1150 kapısı) |
| 26 | `pg_catalog.has_any_column_privilege(oid,oid,text)` | 5.4a L1123 | Evet | Var | Hayır | — | Tümü |
| 27 | `pg_catalog.has_sequence_privilege(oid,oid,text)` | 5.5b L1267–1269 | Evet | Var | Hayır | Sequence USAGE gerektirmez; `nextval` yok | Tümü |
| 28 | `pg_catalog.unnest(anyarray)` (`WITH ORDINALITY`) | L994, 1432, 1435, 1494, 1497, 1522 | Evet | Var | Hayır | — | Tümü |
| 29 | `pg_catalog.split_part(text,text,integer)` | L971, 973, 985, 989, 1420, 1430, 1436, 1493 | Evet | Var | Hayır | — | Tümü |
| 30 | `pg_catalog.substr(text,integer)` | L982 | Evet | Var | Hayır | İzin listesindeki ayar değeri | Tümü |
| 31 | `pg_catalog.strpos(text,text)` | L982, 1496 | Evet | Var | Hayır | — | Tümü |
| 32 | `pg_catalog.string_agg(text,text)` (agregat) | L1419, 1493, 1519 | Evet (agregatlarda da denetlenir [PG]) | Var | Hayır | — | Tümü |
| 33 | `pg_catalog.count()` (`count(*)`, `FILTER`) | L1284, 1499, 1541, 1542, 1557, 1563, 1580, 1597, 1602, 1607 | Evet | Var | Hayır | — | Tümü |
| 34 | `pg_catalog.bool_or(boolean)` | L732, 733, 923, 924, 1139, 1140, 1496 | Evet | Var | Hayır | — | Tümü |
| 35 | `pg_catalog.bool_and(boolean)` | L925 | Evet | Var | Hayır | — | Tümü |
| 36 | `pg_catalog.pg_get_constraintdef(oid)` | 5.7 L1301 | Evet | Var | Hayır | Kısıt tanımı (şema bilgisi) | Tümü |
| 37 | `pg_catalog.format_type(oid,integer)` | 5.8 L1315 | Evet | Var | Hayır | — | Tümü |
| 38 | `pg_catalog.to_regclass(text)` | 5.8 L1318 | Evet | Var | Hayır | **`public` USAGE bağımlılığı** (§4.1) | Metin argümanlı biçim 9.6+; PG16'da soft-error altyapısı (R02) |
| 39 | `pg_catalog.pg_get_function_identity_arguments(oid)` | 5.11 L1416 | Evet | Var | Hayır | Fonksiyon imzası. Fonksiyon **çağrılmaz** | Tümü |
| 40 | `pg_catalog.pg_get_expr(pg_node_tree,oid)` | 5.15 L1524, 1526 | Evet | Var | Hayır | Politika ifadesi. Tırnaklı sabitler maskelenir (U9). Sayısal sabitler görünür (KNOWN_LIMITATIONS 17) | Tümü |
| G1 | `pg_catalog.pg_stat_get_activity(integer)` | `pg_stat_ssl` görünümü içinden (L604) | Evet [PG]: görünüm içindeki fonksiyonlar sorgulayan rolün yetkisiyle denetlenir | Var | Hayır | Doğrudan çağrılmaz | Tümü |
| G2 | `pg_catalog.pg_has_role(oid,text)` | `pg_user_mappings` içinden (L1499) | Evet [PG]. Yalnızca `count(*)` seçildiği için planlayıcı bu sütunu hiç değerlendirmeyebilir | Var | Hayır | — | Tümü |
| G3 | `pg_catalog.has_server_privilege(oid,text)` | `pg_user_mappings` içinden | Aynı | Var | Hayır | — | Tümü |

**Kullanılmayan fonksiyonlar** (görevde örnek olarak geçen) [SQL, grep = 0]:
- `pg_database_size()`, `pg_size_pretty()`: Ayrıca **önerilmez**. `pg_database_size()` hedef veritabanında CONNECT ya da `pg_read_all_stats` ister ve betiğin amacı dışındadır.
- `pg_get_functiondef()`: Kullanılmaz. Fonksiyon gövdesini döker ve gizli değer sızdırabilir. Betik bunun yerine maskeli `proconfig` ve imza kullanır (U9).
- Ayrıca: `lo_*`, `pg_read_file`, `pg_ls_dir`, `set_config`.

Toplam:
- **40** doğrudan imza. Sunucu başına 39 çalışır, çünkü #3 ve #4 birbirini dışlar.
- **3** görünüm içi fonksiyon.
- Operatör ve cast fonksiyonları (§3.4).

Hepsi `pg_catalog` içindedir. `pg_control_system()` dışında hiçbiri için GRANT tasarlanmaz.

### 6.1 `pg_control_system()` ayrı değerlendirmesi

| Soru | Cevap | Kanıt / Durum |
|---|---|---|
| Betik bu yetki olmadan çalışabilir mi? | **Hayır.** L669 kapısı fail-closed, L314–319 parametre zorunlu | [SQL] VERIFIED; [K] A13 |
| EXECUTE hangi rol için denetlenir? | `has_function_privilege(text,text)` → **current_user**. Fonksiyon da current_user ile çağrılır. `hgs2_audit` NOINHERIT ve üyeliksiz olduğundan yetki yalnızca doğrudan GRANT veya PUBLIC'ten gelir | [SQL] [PG] |
| Stok varsayılan nedir? | PUBLIC EXECUTE. `pg_dump` anlık görüntüleri 4 sürümde `REVOKE ALL … FROM PUBLIC` yazıyor. Sistem nesnelerinde `pg_dump` yalnızca initdb başlangıç ACL'sinden farkı yazdığı için başlangıçta PUBLIC'in yetkisi vardı | [K-dolaylı] `kanit/snapshots/before/pg{12,16,17,18}/schema.sql` ~L358–360 |
| Testte neden açık GRANT vardı? | `fixture_harden.sql` PUBLIC'ten geri aldı ve `hgs2_auditor`'a verdi. Sertleştirme sonrası `proacl` `{pgadmin=X/pgadmin,hgs2_auditor=X/pgadmin,…}` | [K] `snapshots/after/pg*/state.txt` `ctrl_acl` |
| ACL kapsamı nedir? | **Veritabanı başına.** `pg_proc` paylaşılan bir katalog değildir. Önemli olan, **`hgs2_perftest_db` içindeki** `proacl` değeridir | [PG] [K] fixture_harden yalnızca hgs2_perftest_db'de uygulandı |
| `pg_monitor` / `pg_read_all_settings` gerekli mi? | **Hayır** | [K] N1 |
| Hedefte ne yapılmalı? | Önce ölç (Taslak §5.1). `true` → **GRANT yok**. `false` → `GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO hgs2_audit;` yalnızca `hgs2_perftest_db`'de. PUBLIC'e **geri verilmez** (sertleştirme kararını bozar) | **NEEDS TEST** (R01) |
| Beklenen değerin kaynağı | `pg_controldata` (işletim sistemi düzeyinde, ayrı yetkili adım). Aynı SQL kanalından alınan değer bağımsız doğrulama sağlamaz | MINIMUM_PRIVILEGE_ANALYSIS §3.4; FINAL_DELIVERY §5.2 |

---

## 7. PUBLIC Privilege Analysis

### 7.1 PUBLIC üzerinden gelen yetki ile doğrudan GRANT arasındaki fark

| Özellik | PUBLIC üzerinden | Doğrudan `GRANT … TO hgs2_audit` |
|---|---|---|
| ACL kaydı | `=X/owner` (grantee OID 0) | `hgs2_audit=X/owner` |
| Kimi etkiler | Kümedeki **tüm** roller, ileride oluşturulacaklar dahil | Yalnızca `hgs2_audit` |
| Geri alma etkisi | `REVOKE … FROM PUBLIC` bütün rolleri ve uygulamaları etkiler | Yalnızca audit rolünü etkiler |
| Tek bir rol için kaldırılabilir mi? | **Hayır.** PostgreSQL'de negatif ("deny") ACL yoktur. `REVOKE … FROM hgs2_audit`, PUBLIC'ten gelen yetkiyi **kaldırmaz** [PG] | Evet |
| `NOINHERIT` etkisi | **Yok.** PUBLIC bir rol üyeliği değildir; NOINHERIT rolde de geçerlidir [PG] | Yok |
| `has_*_privilege` sonucunda ayırt edilir mi? | Hayır. Etkin yetki kaynağı göstermez. Ayırt etmek için `aclexplode` ile grantee 0 aranır (betik 5.4a `public_acl` sütunu) | Hayır, aynı şekilde |
| `pg_shdepend` kaydı | Yok (PUBLIC rol değildir) | `deptype = 'a'` satırı oluşur [PG]. `DROP ROLE` öncesinde REVOKE veya `DROP OWNED` gerekir. Küme genelinde izlenebilir |
| Sertleştirmeye dayanıklılık | PUBLIC'ten geri alınırsa audit rolü yetkiyi kaybeder; betik fail-closed durur | Kalır |
| Gereksiz olduğunda riski | — | PUBLIC zaten veriyorsa etkisizdir. İleride PUBLIC sertleştirildiğinde fark edilmeyen bir istisnaya dönüşür. Bu yüzden **üretilmez** |

**Tasarım kuralı:** Yetki stokta PUBLIC'ten geliyorsa GRANT üretilmez. Hedefte eksik olduğu **ölçülürse** yalnızca `hgs2_audit`'e ve yalnızca `hgs2_perftest_db` içinde verilir.

### 7.2 Stok PG 18.6 PUBLIC varsayılanları ve audit rolü için anlamı [PG]

| Nesne sınıfı | PUBLIC varsayılanı | Betik için | `hgs2_audit` için değerlendirme |
|---|---|---|---|
| Veritabanı | `CONNECT`, `TEMPORARY` | `hgs2_perftest_db` CONNECT **gerekli** | Diğer DB'lerde CONNECT → pg_hba ile kapatılır. TEMPORARY → artık (R10) |
| Şema `pg_catalog` | `USAGE` (initdb) | Gerekli | — |
| Şema `public` (PG 15+ yeni DB) | `USAGE` | Gerekli (5.8) | — |
| Şema `public` (PG ≤ 14 kökenli) | `USAGE`, `CREATE` | USAGE gerekli | CREATE → sahiplik riski (R11) |
| Sistem katalogları | `SELECT` (istisnalar §5) | 21 ilişki gerekli | Betik istisnaları kullanmaz |
| Fonksiyon / prosedür | `EXECUTE` | 40+3 yerleşik gerekli | Kullanıcı şemalarındaki fonksiyonlar → artık; özellikle `SECURITY DEFINER` (R12) |
| Dil (`plpgsql`) | `USAGE` | Gerekmez | Zararsız artık. CREATE yoksa kullanılamaz |
| Tür / domain | `USAGE` | Dolaylı | — |
| Tablo, view, sequence | **Yok**. Açık GRANT veya `ALTER DEFAULT PRIVILEGES … TO PUBLIC` ile gelebilir | Gerekmez | Bulunmamalı (R03, R06) |
| Büyük nesne | **Yok**. Açık GRANT, `lo_compat_privileges = on` veya PG 18 LO varsayılan yetkileri ile gelebilir | Gerekmez | Bulunmamalı (R04) |
| Foreign server / FDW, tablespace, parametre | **Yok** | Gerekmez | — |

### 7.3 Test kümelerinde gözlenen PUBLIC durumu [K]

| Gözlem | PG 12 | PG 16 / 17 / 18 | Kaynak |
|---|---|---|---|
| `hgs2_perftest_db` PUBLIC CONNECT / TEMPORARY | var | var | N1 stdout 3.3/3.4 |
| `public` şeması ACL | `=UC` (PUBLIC CREATE var) | `{pg_database_owner=UC/pg_database_owner,=U/pg_database_owner}` | N1 stdout 5.1 (PG18: satır 89) |
| `hibrit_giris_db` PUBLIC | kaldırılmış (fixture) | kaldırılmış (fixture) | `fixture_global.sql` L21 |
| `pg_control_system` | PUBLIC kaldırılmış (fixture) | aynı | `fixture_harden.sql` |
| Test `hgs2_auditor` ↔ hedef `hgs2_audit` farkı | `hgs2_auditor`'a A02 negatif senaryosu için `GRANT CONNECT ON DATABASE hibrit_giris_db` verilmişti | | `fixture_global.sql` L22. **Gerçek ortamda tekrarlanmaz** |

### 7.4 Audit rolünün PUBLIC yoluyla kazanabileceği, betiğin ihtiyaç duymadığı erişimler

1. **Kullanıcı tabloları:** tablo veya sütun düzeyinde PUBLIC'e verilmiş SELECT.
   - Betik 5.4 yalnızca beklenen 4 tablonun ACL'sini gösterir. 5.4c sütun ACL'lerini gösterir.
   - Diğer tablolar için betik dışı kontrol gerekir (Taslak §6 `user_rel_access_count`).
2. **Sequence'lar:** PUBLIC USAGE/SELECT. 5.5b yalnızca `hgs2_perftest` için ölçer.
3. **Büyük nesneler:** `lomacl` içinde PUBLIC SELECT veya `lo_compat_privileges = on`.
   - `users.parmak_izi_sablonu oid` türündedir. Bu sütun biyometrik veri taşıyan LO'lara işaret edebilir. **Yüksek önem.**
4. **SECURITY DEFINER fonksiyonlar:** Kullanıcı şemalarında PUBLIC EXECUTE'lu fonksiyonlar, sahibinin yetkisiyle çalışır.
   - Betik bunları çağırmaz, yalnızca listeler (5.11).
   - Denetim dışındaki bir oturumda audit kimlik bilgisiyle çağrılabilirler.
5. **Varsayılan yetkiler:** `ALTER DEFAULT PRIVILEGES … GRANT … TO PUBLIC` ileride oluşturulacak nesnelere otomatik erişim verir (5.4d gösterir).
6. **Diğer veritabanları:** Her DB'de yukarıdakilerin tamamı. pg_hba kapatmazsa geçerlidir.

---

## 8. Role Attribute Design

### 8.1 Öznitelikler

| Öznitelik | Önerilen | Gerekçe | Betik P8 algılar mı? [SQL L722–783] |
|---|---|---|---|
| `LOGIN` | Evet | Betik bir oturum ister | — |
| `SUPERUSER` | **NOSUPERUSER** | Süper kullanıcı her ACL'yi aşar; betik reddeder | **Evet** → ABORT `superuser_connection` |
| `CREATEDB` | **NOCREATEDB** | Veritabanı oluşturup sahibi olmak = örtük `pg_database_owner` | **Kısmen**: raporlar (L756), uyarmaz |
| `CREATEROLE` | **NOCREATEROLE** | Rol yönetimi yetkisi | **Evet** → WARNING |
| `REPLICATION` | **NOREPLICATION** | WAL akışı = tüm verinin kopyası | **Evet** → WARNING |
| `BYPASSRLS` | **NOBYPASSRLS** | RLS'yi aşar | **Evet** → WARNING |
| `INHERIT` | **NOINHERIT** | Bugün üyelik yok, etkisi yok. Yanlışlıkla eklenecek bir üyeliğin yetkilerinin otomatik kullanılmasını engeller. **Sınırı:** PG 16+'da NOINHERIT yalnızca yeni GRANT'lerin varsayılan `INHERIT` seçeneğini belirler. `SET` seçeneği varsayılan olarak TRUE kalır, yani `SET ROLE` yine mümkündür [PG]. Asıl koruma "üyelik yok" kuralıdır | **Hayır** |
| `CONNECTION LIMIT` | **2** | Bkz. §8.2 | **Hayır** |
| `PASSWORD` | Dosyada **yok**; `\password` ile SCRAM | Bkz. §8.3 | — |
| `VALID UNTIL` | Denetim penceresinin sonu | Yalnızca parola kimlik doğrulamasını etkiler [PG] | **NEEDS DECISION** |
| Rol düzeyi ayar (`ALTER ROLE … SET`) | **Hiç** | Kalıcı `search_path`/`role` denetimi manipüle eder | Bölüm 4 raporlar (U6); durdurmaz |
| `COMMENT ON ROLE` | İsteğe bağlı | Amaç kaydı | — |

### 8.2 CONNECTION LIMIT = 2 gerekçesi

- Betik `psql -f` ile **tek** bağlantı kullanır. `\gset` aynı bağlantıdadır [SQL].
- 1 ek bağlantı payı, kopan bir oturumun sunucu tarafında henüz temizlenmediği durumda (Windows TCP keepalive süreleri uzundur) yeniden denemeye izin verir.
- Paralel ya da kötüye kullanımı sınırlar.
- pg_hba tarafından reddedilen girişimler sayaca girmez. Reddetme kimlik doğrulama aşamasında, rol bağlantı limiti denetiminden önce olur [PG].
- Limit küme geneli sayılır ve yaklaşık uygulanır [PG]. Süper kullanıcılara uygulanmaz; ama bu rol süper kullanıcı değildir.
- Alternatif: `1` (daha katı; takılı oturumda yönetici müdahalesi gerekir). → Varsayılan öneri 2. Değiştirmek bir **karar** konusudur.

### 8.3 Parola ve kimlik doğrulama

- `CREATE ROLE` ifadesinde `PASSWORD` **verilmez**. Gerekçe: `log_statement = ddl/all` açıksa açık parola sunucu günlüğüne düşebilir [PG].
- Parola, rol oluşturulduktan sonra yönetici psql'inde `\password hgs2_audit` ile verilir. psql SCRAM özetini istemci tarafında hesaplar; açık metin sunucuya gitmez [PG].
- Öncesinde oturumda `SET password_encryption = 'scram-sha-256'` (PG 14+ varsayılanı zaten budur).
- Parola verilene kadar rol `rolpassword = NULL` durumundadır. Hiçbir `scram-sha-256` kuralıyla giriş yapamaz. Bu bir güvenlik payıdır.
- Operatör tarafı (FINAL_DELIVERY §5.8: "belgelenmemiş"):
  - psql parola istemi, ya da
  - erişimi yalnızca operatör hesabına açık NTFS ACL'li `%APPDATA%\postgresql\pgpass.conf`.
  - Windows'ta libpq pgpass dosya izinlerini denetlemez [PG]. Koruma NTFS ACL'sine kalır.
  - → **NEEDS DECISION** (R15).
- Parola komut satırında, URL'de veya `PGPASSWORD` içinde **verilmez** (betik L82).

### 8.4 Üyelik ve sahiplik kuralları

| Kural | Neden | Doğrulama |
|---|---|---|
| `hgs2_audit` hiçbir rolün üyesi değil (`pg_auth_members.member`) | `hgs2_perftest` üyeliği: PG 16+'da `INHERIT FALSE` olsa bile `SET TRUE` ile `SET ROLE hgs2_perftest` mümkündür ve sahip yetkileri gelir. P8 algılamaz | Taslak §7 |
| Hiçbir rol `hgs2_audit`'in üyesi değil (`pg_auth_members.roleid`) | Başkası `SET ROLE hgs2_audit` ile denetçi kimliğine bürünemesin. PG 16+'da süper kullanıcı olmayan bir CREATEROLE rolü yeni rolü oluşturursa ADMIN üyeliği otomatik eklenir [PG] → rol **süper kullanıcı** tarafından oluşturulur | Taslak §0, §7 |
| `postgres` ve diğer süper kullanıcı rollerine üyelik yok | P8 `superuser_membership` ile durdurur | P8 + Taslak §7 |
| Hiçbir önceden tanımlı role üyelik yok | §8.5 | Taslak §7 `no_effective_membership` |
| Hiçbir veritabanının sahibi değil | Örtük `pg_database_owner` → `public` CREATE ve şema sahipliği | Taslak §8 |
| Hiçbir nesnenin sahibi değil (tüm DB'ler) | Sahiplik ACL'den bağımsızdır ve geri alınamaz; sahip kendine yetki geri verebilir | `pg_shdepend` `deptype = 'o'` (Taslak §8) |
| Hiçbir yerde CREATE yok | Sahipliğin tek kaynağı | Taslak §6 |
| `ALTER DEFAULT PRIVILEGES … TO hgs2_audit` yok | İleride biriken yetki | Taslak §6 |

### 8.5 PostgreSQL 18.6 önceden tanımlı rolleri

Hiçbiri gerekmez ve hiçbiri verilmez. P8 kapsamı aşağıda gösterilmiştir.

| Rol | Sürüm | Etkisi | P8 |
|---|---|---|---|
| `pg_read_all_data` | 14+ | Tüm tablo verisini okur | WARNING |
| `pg_write_all_data` | 14+ | Tüm tablolara yazar | WARNING |
| `pg_read_server_files` / `pg_write_server_files` / `pg_execute_server_program` | 11+ | Sunucu dosyaları ve komut çalıştırma | WARNING |
| `pg_monitor` | 10+ | `pg_read_all_settings` + `pg_read_all_stats` + `pg_stat_scan_tables` | **Algılamaz** |
| `pg_read_all_settings` | 10+ | Süper kullanıcıya özel ayarlar | **Algılamaz** |
| `pg_read_all_stats` | 10+ | Diğer oturumların sorgu metinleri | **Algılamaz** |
| `pg_stat_scan_tables` | 10+ | Tablo tarayan izleme fonksiyonları | **Algılamaz** |
| `pg_signal_backend` | 9.6+ | Diğer oturumları iptal etme | **Algılamaz** |
| `pg_checkpoint` | 15+ | CHECKPOINT | **Algılamaz** |
| `pg_use_reserved_connections` | 16+ | Ayrılmış bağlantı slotları | **Algılamaz** |
| `pg_create_subscription` | 16+ | CREATE ile birlikte abonelik oluşturma | **Algılamaz** |
| `pg_maintain` | 17+ | VACUUM/ANALYZE/REINDEX/REFRESH/CLUSTER/LOCK | **Algılamaz** |
| `pg_signal_autovacuum_worker` | 18 [PG] | Autovacuum işçisine sinyal | **Algılamaz** |
| `pg_database_owner` | 14+ | Örtük; DB sahipliğinden gelir | **Algılamaz** |

PG 12'de 14+ rollerin adları bulunmaz. P8'in `IN (…)` listesi bu durumda hata vermez, yalnızca eşleşme olmaz [SQL L733–735] → **NOT APPLICABLE** (hedef 18.6).

### 8.6 Rolün cluster-wide olması

- `CREATE ROLE`, `pg_authid` paylaşılan kataloğuna yazar. Rol, `hibrit_giris_db` dahil **tüm** veritabanlarında anında var olur [PG].
- Her veritabanında PUBLIC'e verilmiş her yetkiyi (CONNECT dahil) otomatik kazanır.
- Bu nedenle:
  1. pg_hba kuralı rolden **önce** eklenir.
  2. Rol parolasız oluşturulur.
  3. Doğrulama paylaşılan kataloglarla tüm kümeyi kapsar (`pg_database`, `pg_auth_members`, `pg_shdepend`, `pg_db_role_setting`).

---

## 9. Cross-Database Isolation Design

### 9.1 Bilinen durum

| Bulgu | Kaynak | Durum |
|---|---|---|
| `hibrit_giris_db` sahibi `postgres` | [BEYAN] | UNVERIFIED (bu klasörde kanıt yok) |
| `hgs2_perftest`'in `hibrit_giris_db` üzerinde CONNECT yetkisi yok | [BEYAN] | UNVERIFIED. Ölçüm yöntemi (etkin yetki mi, ACL listesi mi, bağlantı denemesi mi) bilinmiyor |
| `hgs2_perftest_db` sahibi `hgs2_perftest` | [BEYAN] | UNVERIFIED |
| localhost bağlantılarında `scram-sha-256` | [BEYAN]; gerçek `pg_hba.conf` okunmadı | UNVERIFIED |
| PUBLIC CONNECT varsayılan olarak bulunur | [PG] | Stok için doğru |

**Çıkarım (koşullu, [K-dolaylı] mantık):**
- `has_database_privilege('hgs2_perftest','hibrit_giris_db','CONNECT') = false` ve `hgs2_perftest` süper kullanıcı değilse, `hibrit_giris_db` üzerinde PUBLIC CONNECT **yoktur**. Çünkü PUBLIC yetkisi her role uygulanır.
- Bu durumda üyeliksiz ve doğrudan GRANT'siz `hgs2_audit` de ACL düzeyinde bağlanamaz.
- Bulgu ACL listesine bakılarak ya da pg_hba reddiyle elde edildiyse bu çıkarım **geçersizdir**.
- → **NEEDS TEST** (Taslak §9, T0-03).

### 9.2 Seçeneklerin değerlendirilmesi

| # | Seçenek | Mekanizma | Etki alanı | Mevcut uygulama/rollere etkisi | `hgs2_audit`'i tek başına kısıtlar mı? | Değerlendirme |
|---|---|---|---|---|---|---|
| 1 | **Veritabanı ACL** (`GRANT/REVOKE … ON DATABASE hibrit_giris_db`) | `datacl` | Tek DB, tüm roller | `hgs2_audit`'e GRANT verilmezse etki yok | **Yalnızca PUBLIC CONNECT zaten yoksa.** Negatif ACL olmadığı için PUBLIC varsa `REVOKE … FROM hgs2_audit` işe yaramaz | **Değişiklik yapılmaz.** Yalnızca doğrulama: `has_database_privilege('hgs2_audit','hibrit_giris_db','CONNECT') = false` beklenir |
| 2 | **PUBLIC CONNECT kaldırma** (`REVOKE CONNECT ON DATABASE hibrit_giris_db FROM PUBLIC`) | `datacl` | Tek DB, **PUBLIC'e dayanan tüm roller** | `hibrit_giris_db`'ye PUBLIC yoluyla bağlanan uygulama rolleri **kesilir**. Önce bağlanan rollerin envanteri ve her birine açık CONNECT gerekir. Üretim veritabanı değişikliğidir | Evet, dolaylı | **Önerilmez.** [BEYAN] doğruysa zaten kaldırılmıştır. Kaldırılmamışsa ayrı bir üretim değişiklik kararıdır; bu çalışmanın kapsamı dışındadır |
| 3 | **`pg_hba.conf` kuralları** | İlk eşleşen kural | Yalnızca kuraldaki **kullanıcı adı** (`hgs2_audit`) | **Yok.** Kurallar yalnızca `hgs2_audit` adıyla eşleşir; diğer kullanıcılar mevcut satırlara düşer. Yeniden yükleme açık oturumları etkilemez [PG] | **Evet**, veritabanı ve adres bazında | **ÖNERİLEN birincil kontrol** (Bölüm 10) |
| 4 | **Rol bazlı kısıtlamalar** | `CONNECTION LIMIT`, `VALID UNTIL`, `NOLOGIN`, PG 17+ `login` event trigger | Tek rol (event trigger hariç) | Yok | **Hayır**: hiçbiri veritabanı bazında değildir. `login` event trigger hedef veritabanının **içinde** süper kullanıcıyla oluşturulmalıdır (= `hibrit_giris_db` değişikliği) ve bağlantı kurulduktan **sonra** çalışır | Tamamlayıcı: limit 2, süre ve denetim dışı `NOLOGIN` (karar). Event trigger **önerilmez** |
| 5 | **Bağlantı adresi ve kullanıcı doğrulaması** | `host` satırında adres (`127.0.0.1/32`, `::1/128`) + `scram-sha-256` | Tek rol | Yok | Kısmen. Adres ve kimlik doğrulama, DB sınırını tek başına koymaz; pg_hba satırının parçasıdır | Seçenek 3'ün içinde uygulanır |
| — | `datallowconn = false` | `pg_database` | Tüm roller | Üretim kesintisi | — | **Reddedildi** |
| — | `ALTER ROLE hgs2_audit IN DATABASE hibrit_giris_db SET …` | Oturum ayarı | — | — | **Hayır**: bağlantıyı engellemez | Reddedildi |

### 9.3 Önerilen katmanlı çözüm (en az müdahaleli)

1. **Katman 1 – pg_hba (zorunlu):** `hgs2_audit` yalnızca `hgs2_perftest_db`'ye, yalnızca loopback'ten, `scram-sha-256` ile bağlanır. Diğer her şey `reject`.
2. **Katman 2 – ACL (değişiklik yok, doğrulama):**
   - `hgs2_audit`'e hiçbir veritabanında açık CONNECT verilmez.
   - `hibrit_giris_db` için `has_database_privilege(..., 'CONNECT') = false` doğrulanır.
   - `true` çıkarsa (PUBLIC açık) Katman 1 tek engel olarak kaydedilir; PUBLIC kaldırma ayrı bir karardır (R05).
3. **Katman 3 – rol:**
   - Parolasız oluşturma, sonra `\password`.
   - `CONNECTION LIMIT 2`.
   - Süre/`NOLOGIN` kararı.
4. **Katman 4 – betik (son savunma):**
   - Yanlış veritabanında L476–495 durdurur.
   - Bu, bağlantıyı **önlemez**; yalnızca sorgu çalışmasını engeller (betik L456–457).
5. **Katman 5 – sürekli doğrulama:**
   - Her denetim çalıştırmasından önce Taslak §6–§9 sorguları (salt okunur) çalıştırılır.
   - Neden: denetlenen taraf (`hgs2_perftest`), kendi nesneleri ve veritabanı üzerinde `hgs2_audit`'e GRANT verebilir (R09b).

**Cevap — "Mevcut uygulamaların erişimini bozmadan izolasyon sağlanabilir mi?":**
- **Evet.** pg_hba kuralları yalnızca `hgs2_audit` kullanıcı adıyla eşleşir. Hiçbir ACL'ye, PUBLIC'e veya `hibrit_giris_db`'ye dokunulmaz [PG].
- Doğru konumlandırılmazsa risk vardır. Örneğin `all all` satırlarının **altına** eklenirse, önceki geniş bir kural `hgs2_audit`'i yakalar ve izolasyon sağlanmaz. Bu durum Taslak §9'daki `pg_hba_file_rules` kontrolüyle yakalanır.

---

## 10. pg_hba.conf Recommendations

> Bu bölüm **yalnızca dokümantasyondur**. `pg_hba.conf` okunmadı ve değiştirilmedi. Uygulama ayrı onay gerektirir.

### 10.1 Önerilen kurallar (dosyanın etkin kurallarının EN ÜSTÜNE)

```text
# --- HGS2 audit rolu (hgs2_audit) - BASLANGIC ----------------------------------
# Amac: hgs2_audit YALNIZCA hgs2_perftest_db'ye, YALNIZCA loopback'ten, SCRAM ile.
# Bu satirlar yalnizca "hgs2_audit" kullanici adiyla eslesir; diger roller
# asagidaki mevcut kurallara duser ve davranislari degismez.
# Ilk eslesen kural gecerlidir: bu blok, "all" iceren HER satirin USTUNDE olmali.
# TYPE   DATABASE           USER         ADDRESS         METHOD
host     hgs2_perftest_db   hgs2_audit   127.0.0.1/32    scram-sha-256
host     hgs2_perftest_db   hgs2_audit   ::1/128         scram-sha-256
host     all                hgs2_audit   all             reject
host     replication        hgs2_audit   all             reject
local    all                hgs2_audit                   reject
local    replication        hgs2_audit                   reject
# --- HGS2 audit rolu - BITIS ---------------------------------------------------
```

Satır gerekçeleri [PG]:

| Satır | Gerekçe |
|---|---|
| 1–2 | Yalnızca hedef DB, yalnızca IPv4/IPv6 loopback. `host` hem TLS'li hem TLS'siz TCP bağlantısıyla eşleşir. Betik uçtan uca loopback'i TLS'siz kabul eder (P6b) |
| 3 | `hibrit_giris_db`, `postgres`, `template0/1` ve diğer tüm DB'ler; tüm adresler. `reject`, parola sorulmadan bağlantıyı reddeder. Bu yüzden negatif testler parola gerektirmez |
| 4 | `all` anahtar sözcüğü replikasyon bağlantılarıyla **eşleşmez**; ayrı satır gerekir. Rol zaten `NOREPLICATION` (derinlemesine savunma) |
| 5–6 | Unix soketi. Windows'ta varsayılan olarak kapalıdır (`unix_socket_directories`); ileride açılırsa da kapsanır |

### 10.2 Varyant (karar): TLS zorunlu

Sunucuda `ssl = on` ise ve SCRAM `channel_binding=require` istenirse, 1–2. satırlarda `host` yerine `hostssl` yazılır ve `hostnossl` için `reject` eklenir.
- Proje bu kombinasyonu **test etmedi** (KNOWN_LIMITATIONS 20; FINAL_DELIVERY §8).
- → **NEEDS DECISION**.
- Loopback'te TLS, betik açısından zorunlu değildir.

### 10.3 Uygulama ve geri alma prosedürü (yönetici, ayrı onay)

1. `SHOW hba_file;` ile gerçek dosya yolunu belirle. Dosyanın yedeğini al (tarih damgalı kopya).
2. Mevcut kuralları kaydet: `SELECT line_number, type, database, user_name, address, auth_method, error FROM pg_catalog.pg_hba_file_rules ORDER BY line_number;`. Süper kullanıcı gerekir.
3. Bloğu ilk etkin kuralın **üstüne** ekle.
4. **Yeniden yüklemeden önce** doğrula: `pg_hba_file_rules` diskteki dosyayı okur [PG].
   - `error IS NULL` olmalı.
   - Diğer kullanıcıların satırları, yalnızca satır numarası kayması dışında, adım 2 ile aynı olmalı.
5. Yeniden yükle (yeniden başlatma **değil**): `SELECT pg_catalog.pg_reload_conf();`.
   - Dosyada hata varsa sunucu eski kuralları korur ve günlüğe yazar [PG].
   - Açık oturumlar etkilenmez.
6. Taslak §9 kontrolü: her veritabanı için `hgs2_audit`'e uyan ilk TCP kuralı → `hgs2_perftest_db`: `scram-sha-256`, diğerleri: `reject`.
7. **Geri alma:** yedeği geri koy, adım 5'i tekrarla.

### 10.4 Dikkat edilecek noktalar

- `listen_addresses` loopback dışını da dinliyorsa 3. satır uzak bağlantıları zaten reddeder.
- `+grup`, `samerole`, `@dosya` veya PG 16+ `/regex` biçimli mevcut satırlar `hgs2_audit`'i yakalayabilir. Blok en üstte olduğu için önceliği alır. Yine de Taslak §9 sorgusu bu biçimleri yorumlamaz; elle gözden geçirilmelidir.
- Mevcut uygulama bağlantıları (`application.properties`, okunmadı) farklı bir kullanıcı adı kullandığı sürece etkilenmez. `hgs2_audit` adı uygulamada **kullanılmamalıdır**.
- Kuralların yalnızca `hgs2_audit`'i etkilediği **[PG] semantiğine** dayanır. Gerçek dosyada doğrulama → **NEEDS TEST** (T2-02).

---

## 11. Proposed SQL Draft (NOT EXECUTED)

> **NOT EXECUTED.** Bu SQL hiçbir ortamda çalıştırılmadı.
> - İlk iki satırdaki `\quit`, dosya yanlışlıkla psql'e verilse bile sunucuya tek bir ifade gönderilmeden çıkmasını sağlar.
> - Uygulama aşamasında taslak, ayrı onayla ve bölüm bölüm gözden geçirilmiş bir kopyaya aktarılmalıdır.
> - Rol oluşturma ve koşullu GRANT'ler **tek transaction** içindedir. Doğrulamalar başarısızsa `ROLLBACK` olur ve rol hiç oluşmaz.

```sql
\echo 'HGS2_ROLE_DRAFT: NOT EXECUTED - bu taslak calistirilmaz'
\quit
-- =============================================================================
-- HGS2 - hgs2_audit rolu: olusturma, kosullu yetkilendirme ve dogrulama TASLAGI
-- Hedef: PostgreSQL 18.6 (Windows, yerel servis)
-- =============================================================================
-- On kosullar (uygulama asamasinda, ayri onaydan sonra):
--  (a) Bolum 10'daki pg_hba.conf blogu EKLENMIS ve yeniden yuklenmis olmali.
--  (b) Calistiran: super kullanici (or. postgres). PG 16+'da super kullanici
--      OLMAYAN bir CREATEROLE rolu yeni rolu olusturursa ADMIN uyeligi alir.
--  (c) psql -X -v ON_ERROR_STOP=1
--          -d "host=127.0.0.1 dbname=hgs2_perftest_db user=postgres"
--      -X: psqlrc yok. hibrit_giris_db'ye BAGLANILMAZ; oradaki durum paylasilan
--      kataloglardan (pg_database, pg_auth_members, pg_shdepend) okunur.
--  (d) Bu dosyada parola YOKTUR.
-- =============================================================================
\set ON_ERROR_STOP on
\set AUTOCOMMIT on

BEGIN;
-- R13: hgs2_perftest_db sahibi ALTER DATABASE ... SET search_path ile yonetici
-- oturumunu etkileyebilir. Nitelenmemis adlar yalnizca pg_catalog'dan cozulsun.
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

-- -----------------------------------------------------------------------------
-- 0. On kontroller (yalnizca okuma)
-- -----------------------------------------------------------------------------
SELECT current_database() = 'hgs2_perftest_db'                                AS on_target,
       COALESCE((SELECT r.rolsuper FROM pg_roles r
                  WHERE r.rolname = current_user), false)                      AS runner_is_superuser,
       NOT EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname = 'hgs2_audit')    AS role_absent,
       current_setting('search_path') = 'pg_catalog, pg_temp'                  AS search_path_pinned,
       current_setting('server_version_num')::int BETWEEN 180000 AND 189999    AS is_pg18
\gset
\if :on_target
\else
  \echo 'DUR: yalnizca hgs2_perftest_db icinde calistirilir'
  ROLLBACK;
  \quit
\endif
\if :runner_is_superuser
\else
  \echo 'DUR: rol super kullanici tarafindan olusturulmali (PG16+ ADMIN uyeligi olusmasin)'
  ROLLBACK;
  \quit
\endif
\if :role_absent
\else
  \echo 'DUR: hgs2_audit zaten var; mevcut rol yeniden kullanilmaz, once incelenir'
  ROLLBACK;
  \quit
\endif
\if :search_path_pinned
\else
  \echo 'DUR: search_path sabitlenemedi'
  ROLLBACK;
  \quit
\endif
\if :is_pg18
\else
  \echo 'DUR: sunucu 18.x degil; tasarim PG 18.6 icin (NEEDS REVIEW)'
  ROLLBACK;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 1. CREATE ROLE
--    IN ROLE / ROLE / ADMIN yan tumceleri KULLANILMAZ (uyelik olusturur).
--    PASSWORD yok: rolpassword NULL kalir, scram kurali giris izni vermez.
-- -----------------------------------------------------------------------------
CREATE ROLE hgs2_audit
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS
    CONNECTION LIMIT 2;
-- Istege bagli:
-- COMMENT ON ROLE hgs2_audit IS 'HGS2 read-only catalog audit; only hgs2_perftest_db; no memberships, no ownership';
-- NEEDS DECISION (R15): VALID UNTIL '<denetim penceresi sonu, +03>'

-- -----------------------------------------------------------------------------
-- 2. Veritabani CONNECT (yalnizca hgs2_perftest_db; PUBLIC yeterliyse GRANT YOK)
--    hgs2_audit uyeliksiz ve NOINHERIT: true sonucu yalnizca PUBLIC'ten gelir.
-- -----------------------------------------------------------------------------
SELECT has_database_privilege('hgs2_audit', 'hgs2_perftest_db', 'CONNECT') AS audit_connect_ok
\gset
\if :audit_connect_ok
  \echo 'BILGI: hgs2_perftest_db CONNECT PUBLIC uzerinden mevcut; GRANT uretilmedi.'
\else
  \echo 'BILGI: PUBLIC CONNECT yok; yalnizca hgs2_audit icin veriliyor.'
  GRANT CONNECT ON DATABASE hgs2_perftest_db TO hgs2_audit;
\endif

-- -----------------------------------------------------------------------------
-- 3. Sema USAGE (yalnizca hgs2_perftest_db icinde)
--    pg_catalog: tum nitelenmis adlar. public: YALNIZCA betik 5.8 / L1318
--    to_regclass('public.users').
-- -----------------------------------------------------------------------------
SELECT has_schema_privilege('hgs2_audit', 'pg_catalog', 'USAGE') AS usage_pg_catalog,
       has_schema_privilege('hgs2_audit', 'public', 'USAGE')     AS usage_public
\gset
\if :usage_pg_catalog
\else
  \echo 'DUR: pg_catalog USAGE PUBLIC icin yok; olagan disi kume, GRANT yerine inceleme gerekir'
  ROLLBACK;
  \quit
\endif
\if :usage_public
  \echo 'BILGI: public USAGE PUBLIC uzerinden mevcut; GRANT uretilmedi.'
\else
  \echo 'BILGI: public USAGE PUBLIC icin yok; yalnizca hgs2_audit icin veriliyor (5.8).'
  GRANT USAGE ON SCHEMA public TO hgs2_audit;
\endif

-- -----------------------------------------------------------------------------
-- 4. Katalog erisimleri (21 iliski). Eksik varsa GRANT URETILMEZ, DURULUR:
--    PUBLIC'ten geri alinmis katalog senaryosu test edilmedi
--    (KNOWN_LIMITATIONS 21) -> NEEDS DECISION.
-- -----------------------------------------------------------------------------
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
\echo 'eksik katalog SELECT:' :catalogs_missing
\if :catalogs_ok
\else
  \echo 'DUR: katalog SELECT eksik (sertlestirilmis kurulum, test edilmedi)'
  ROLLBACK;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 5. Fonksiyon EXECUTE
-- 5.1 pg_control_system(): zorunlu, fail-closed. PUBLIC yeterliyse GRANT YOK.
--     Yetki veritabani basinadir; burada yalnizca hgs2_perftest_db etkilenir.
--     PUBLIC'e GERI VERILMEZ.
-- -----------------------------------------------------------------------------
SELECT has_function_privilege('hgs2_audit', 'pg_catalog.pg_control_system()', 'EXECUTE') AS audit_ctrl_ok,
       COALESCE((SELECT p.proacl::text FROM pg_proc p
                  WHERE p.oid = 'pg_catalog.pg_control_system()'::regprocedure), 'NULL (stok: PUBLIC EXECUTE)') AS ctrl_proacl
\gset
\echo 'pg_control_system proacl:' :ctrl_proacl
\if :audit_ctrl_ok
  \echo 'BILGI: pg_control_system EXECUTE PUBLIC uzerinden mevcut; GRANT uretilmedi.'
\else
  \echo 'BILGI: PUBLIC EXECUTE geri alinmis; yalnizca hgs2_audit icin veriliyor.'
  GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO hgs2_audit;
\endif

-- 5.2 Betigin kullandigi diger yerlesik fonksiyonlar (40 imza + 3 gorunum ici).
--     Eksik varsa GRANT URETILMEZ, DURULUR (test edilmemis sertlestirme).
--     txid_current_if_assigned() yalnizca PG < 13'te cagrilir; PG 18'de listede yok.
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
  -- gorunum ici (pg_stat_ssl, pg_user_mappings):
  ('pg_catalog.pg_stat_get_activity(integer)'), ('pg_catalog.pg_has_role(oid,text)'),
  ('pg_catalog.has_server_privilege(oid,text)')
) AS v(sig)
WHERE to_regprocedure(v.sig) IS NULL
   OR NOT has_function_privilege('hgs2_audit', to_regprocedure(v.sig)::oid, 'EXECUTE')
\gset
\echo 'eksik/cozulemeyen fonksiyon EXECUTE:' :functions_missing
\if :functions_ok
\else
  \echo 'DUR: yerlesik fonksiyon EXECUTE eksik veya imza cozulemedi'
  ROLLBACK;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 6. Gereksiz yetkilerin BULUNMADIGININ dogrulanmasi (bu veritabani + rol)
-- -----------------------------------------------------------------------------
WITH a AS (SELECT r.* FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT (NOT a.rolsuper AND NOT a.rolcreatedb AND NOT a.rolcreaterole
        AND NOT a.rolreplication AND NOT a.rolbypassrls AND NOT a.rolinherit
        AND a.rolcanlogin AND a.rolconnlimit = 2)                           AS attrs_ok,
       NOT has_database_privilege(a.oid, 'hgs2_perftest_db', 'CREATE')      AS no_db_create,
       has_database_privilege(a.oid, 'hgs2_perftest_db', 'TEMPORARY')       AS has_db_temporary,
       NOT EXISTS (SELECT 1 FROM pg_namespace n
                    WHERE has_schema_privilege(a.oid, n.oid, 'CREATE'))     AS no_schema_create,
       (SELECT count(*) FROM pg_class c
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
       current_setting('lo_compat_privileges') = 'off'                      AS lo_compat_off,
       (SELECT count(*) FROM pg_largeobject_metadata m
          CROSS JOIN LATERAL aclexplode(m.lomacl) x
         WHERE x.privilege_type IN ('SELECT', 'UPDATE')
           AND x.grantee IN (0, a.oid))                                     AS lo_public_or_audit_count,
       (SELECT count(*) FROM pg_default_acl da
          CROSS JOIN LATERAL aclexplode(da.defaclacl) x
         WHERE x.grantee = a.oid
            OR (x.grantee = 0 AND da.defaclobjtype IN ('r', 'S', 'L')))      AS defacl_risk_count,
       (SELECT count(*) FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE p.prosecdef
           AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
           AND has_schema_privilege(a.oid, n.oid, 'USAGE')
           AND has_function_privilege(a.oid, p.oid, 'EXECUTE'))             AS secdef_callable_count,
       (SELECT count(*) FROM pg_db_role_setting s WHERE s.setrole = a.oid)  AS role_setting_count,
       (SELECT count(*) FROM pg_parameter_acl pa
          CROSS JOIN LATERAL aclexplode(pa.paracl) x
         WHERE x.grantee = a.oid)                                           AS parameter_acl_count
FROM a
\gset
\echo 'attrs_ok=' :attrs_ok ' no_db_create=' :no_db_create ' has_db_temporary=' :has_db_temporary ' no_schema_create=' :no_schema_create
\echo 'user_rel_access_count=' :user_rel_access_count ' lo_compat_off=' :lo_compat_off ' lo_public_or_audit_count=' :lo_public_or_audit_count
\echo 'defacl_risk_count=' :defacl_risk_count ' secdef_callable_count=' :secdef_callable_count ' role_setting_count=' :role_setting_count ' parameter_acl_count=' :parameter_acl_count
-- Karar kurallari:
--   attrs_ok, no_db_create, no_schema_create, lo_compat_off = t       (zorunlu)
--   user_rel_access_count, lo_public_or_audit_count, defacl_risk_count,
--   role_setting_count, parameter_acl_count = 0                        (zorunlu)
--   no_schema_create = f  -> R11: public sema PUBLIC CREATE (PG<=14 koken) -> NEEDS DECISION
--   has_db_temporary = t  -> R10: PUBLIC TEMPORARY artigi, kayda gecer   -> NEEDS DECISION
--   secdef_callable_count > 0 -> R12: tek tek incelenir                  -> NEEDS DECISION
-- R10 icin KARAR verilirse (yalnizca hgs2_perftest_db; kume geneli DEGIL;
-- veritabani sahibi sahiplik yoluyla TEMPORARY'yi korur; once bu DB'ye
-- baglanan rollerin envanteri cikarilir):
--   REVOKE TEMPORARY ON DATABASE hgs2_perftest_db FROM PUBLIC;
--   -- gereken roller icin: GRANT TEMPORARY ON DATABASE hgs2_perftest_db TO <rol>;

-- -----------------------------------------------------------------------------
-- 7. Rol uyeligi kontrolu (kume geneli)
-- -----------------------------------------------------------------------------
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
-- no_effective_membership: dolayli uyelikler, onceden tanimli roller ve bu
-- veritabanindaki ortuk pg_database_owner uyeligi dahil.

-- -----------------------------------------------------------------------------
-- 8. Nesne sahipligi kontrolu (TUM veritabanlari; pg_shdepend paylasilan katalog)
-- -----------------------------------------------------------------------------
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype = 'o') = 0                  AS no_owned_objects_any_db,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype NOT IN ('o', 'a')) = 0      AS no_other_shdeps,
       (SELECT count(*) FROM pg_database d WHERE d.datdba = a.oid) = 0     AS no_owned_db,
       (SELECT count(*) FROM pg_tablespace t WHERE t.spcowner = a.oid) = 0 AS no_owned_tablespace
FROM a
\gset

-- ACL referanslari (deptype 'a'), tum veritabanlari. Beklenen: yalnizca bu
-- taslagin 2, 3 ve 5.1 adimlarinda KOSULLU verilen yetkiler (hic yoksa 0 satir).
-- pg_describe_object yalnizca paylasilan ve bu veritabanindaki nesneleri cozer.
SELECT CASE WHEN s.dbid = 0 THEN '(paylasilan)'
            ELSE COALESCE((SELECT d.datname FROM pg_database d WHERE d.oid = s.dbid)::text, s.dbid::text)
       END                                                       AS db,
       s.classid::regclass                                       AS catalog,
       CASE WHEN s.dbid IN (0, (SELECT d.oid FROM pg_database d WHERE d.datname = current_database()))
            THEN pg_describe_object(s.classid, s.objid, s.objsubid) END AS object
FROM pg_shdepend s
WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
  AND s.refobjid = (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
  AND s.deptype = 'a'
ORDER BY 1, 2, 3;

-- -----------------------------------------------------------------------------
-- 9. Diger veritabanlarina CONNECT kontrolu (ACL + pg_hba)
--    Bu sorgular hibrit_giris_db'ye BAGLANMAZ.
-- -----------------------------------------------------------------------------
-- 9.1 ACL duzeyi (rapor). hgs2_perftest_db disinda 't' olan her satir YALNIZCA
--     pg_hba ile kapatilmistir; kayda gecer.
SELECT d.datname,
       d.datallowconn,
       has_database_privilege('hgs2_audit', d.oid, 'CONNECT') AS acl_connect,
       (d.datname = 'hgs2_perftest_db')                      AS expected_connect
FROM pg_database d
ORDER BY d.datname;

SELECT NOT has_database_privilege('hgs2_audit', 'hibrit_giris_db', 'CONNECT') AS hibrit_acl_closed
\gset
-- hibrit_acl_closed = f ise: PUBLIC CONNECT acik (R05). Tek engel pg_hba'dir.
-- PUBLIC kaldirma ayri karardir; burada YAPILMAZ.

-- 9.2 pg_hba: her veritabani icin hgs2_audit'e uyan ILK TCP kurali.
--     Beklenen: hgs2_perftest_db -> scram-sha-256, digerleri -> reject.
--     SINIR: adres, +grup, samerole, @dosya ve /regex yorumlanmaz; elle gozden gecirilir.
SELECT d.datname,
       (SELECT r.auth_method
          FROM pg_hba_file_rules r
         WHERE r.error IS NULL
           AND r.type IN ('host', 'hostssl', 'hostnossl', 'hostgssenc', 'hostnogssenc')
           AND ('hgs2_audit' = ANY (r.user_name) OR 'all' = ANY (r.user_name))
           AND (d.datname = ANY (r.database) OR 'all' = ANY (r.database))
         ORDER BY r.line_number
         LIMIT 1)                                              AS first_tcp_rule_method
FROM pg_database d
ORDER BY d.datname;

SELECT NOT EXISTS (SELECT 1 FROM pg_hba_file_rules r WHERE r.error IS NOT NULL) AS hba_no_errors,
       COALESCE((SELECT r.auth_method FROM pg_hba_file_rules r
                  WHERE r.error IS NULL
                    AND r.type IN ('host', 'hostssl', 'hostnossl', 'hostgssenc', 'hostnogssenc')
                    AND ('hgs2_audit' = ANY (r.user_name) OR 'all' = ANY (r.user_name))
                    AND ('hibrit_giris_db' = ANY (r.database) OR 'all' = ANY (r.database))
                  ORDER BY r.line_number LIMIT 1) = 'reject', false)            AS hba_hibrit_rejected
\gset

-- -----------------------------------------------------------------------------
-- 10. Nihai guvenlik dogrulamasi: hepsi gecerse COMMIT, aksi halde ROLLBACK
--     (rol hic olusmaz).
-- -----------------------------------------------------------------------------
SELECT (:'attrs_ok')::boolean AND (:'no_db_create')::boolean
   AND (:'no_schema_create')::boolean AND (:'lo_compat_off')::boolean
   AND :user_rel_access_count = 0 AND :lo_public_or_audit_count = 0
   AND :defacl_risk_count = 0 AND :role_setting_count = 0 AND :parameter_acl_count = 0
   AND (:'no_member_of')::boolean AND (:'no_members_in_audit')::boolean
   AND (:'no_effective_membership')::boolean AND (:'not_member_perftest')::boolean
   AND (:'not_member_postgres')::boolean
   AND (:'no_owned_objects_any_db')::boolean AND (:'no_other_shdeps')::boolean
   AND (:'no_owned_db')::boolean AND (:'no_owned_tablespace')::boolean
   AND (:'hba_no_errors')::boolean AND (:'hba_hibrit_rejected')::boolean   AS all_ok
\gset
\if :all_ok
  \echo 'HGS2_ROLE_DESIGN_OK: dogrulamalar gecti; COMMIT'
  \echo 'KAYIT: has_db_temporary=' :has_db_temporary ' secdef_callable_count=' :secdef_callable_count ' hibrit_acl_closed=' :hibrit_acl_closed
  COMMIT;
\else
  \echo 'HGS2_ROLE_DESIGN_FAIL: en az bir dogrulama basarisiz; ROLLBACK (rol olusmadi)'
  ROLLBACK;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 10b. Parola (ayri adim, transaction disinda, etkilesimli)
-- -----------------------------------------------------------------------------
-- SET password_encryption = 'scram-sha-256';
-- \password hgs2_audit
--   psql parolayi istemci tarafinda SCRAM ozetine cevirir; acik metin sunucuya,
--   sunucu gunlugune veya bu dosyaya girmez.

-- -----------------------------------------------------------------------------
-- 10c. Isletim sistemi kabugundan baglanti testleri (ayri onay; Bolum 13 T2)
-- -----------------------------------------------------------------------------
-- N1 psql -X -w -d "host=127.0.0.1 dbname=hibrit_giris_db user=hgs2_audit" -c "select 1"
--    beklenen: cikis 2, FATAL: pg_hba.conf rejects connection for host "127.0.0.1",
--              user "hgs2_audit", database "hibrit_giris_db" ...
-- N2 ayni test dbname=postgres, dbname=template1, host=::1      -> ayni FATAL
-- N3 psql -X -d "host=127.0.0.1 dbname=hgs2_perftest_db user=hgs2_audit" -c "select 1"
--    beklenen: parola istenir, basarili
-- N4 (N3 oturumunda) SET ROLE hgs2_perftest;  -> ERROR: permission denied to set role
-- N5 (N3 oturumunda) SELECT 1 FROM public.users LIMIT 1; -> ERROR: permission denied for table users
-- P1 Nihai denetim: FINAL_DELIVERY §6 komutu, user=hgs2_audit
--    beklenen: cikis 0, HGS2_AUDIT_PREFLIGHT_OK ve HGS2_AUDIT_COMPLETE birer kez,
--              HGS2_AUDIT_WARNING yok, stderr bos, validate_audit_result.py PASS
```

### 11.1 Her GRANT'in gerekçesi

| GRANT (yalnızca koşul sağlanırsa) | Koşul | Betikteki dayanak | Neden PUBLIC'e değil |
|---|---|---|---|
| `GRANT CONNECT ON DATABASE hgs2_perftest_db TO hgs2_audit` | Hedefte PUBLIC CONNECT kaldırılmışsa | Bağlantı; L461 | Sertleştirme kararını korumak için |
| `GRANT USAGE ON SCHEMA public TO hgs2_audit` (hgs2_perftest_db) | Hedefte PUBLIC USAGE kaldırılmışsa | L1318 `to_regclass('public.users')` | Aynı |
| `GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO hgs2_audit` (hgs2_perftest_db) | Hedefte PUBLIC EXECUTE kaldırılmışsa | L669–698 (P7, zorunlu) | Aynı; ayrıca FINAL_DELIVERY §5.5 |
| Katalog SELECT / diğer yerleşik EXECUTE | **GRANT üretilmez**; eksikse durulur | — | Test edilmemiş senaryo (KNOWN_LIMITATIONS 21) → NEEDS DECISION |

### 11.2 Taslakta bilinçli olarak OLMAYANLAR

- `REVOKE … FROM PUBLIC` (hiçbir nesnede; R10 için yalnızca yorum satırı ve karar şartı)
- `hibrit_giris_db` üzerinde herhangi bir GRANT/REVOKE
- `pg_read_all_data`, `pg_monitor` ve diğer önceden tanımlı rollere üyelik
- Tablo, sütun, sequence, LO veya foreign server yetkisi
- `ALTER DEFAULT PRIVILEGES`, `ALTER ROLE … SET`
- Parola

---

## 12. Security Risks and Open Questions

| # | Risk / soru | Bulgu ve kanıt | Durum | Kapanış yolu |
|---|---|---|---|---|
| R01 | `pg_control_system()` için hedef `hgs2_perftest_db`'deki EXECUTE | Stok PUBLIC [K-dolaylı: pg_dump REVOKE FROM PUBLIC, 4 sürüm]. Testte sertleştirilmişti [K]. Hedef değer bilinmiyor | **NEEDS TEST** | T0-04; Taslak §5.1 koşullu GRANT |
| R02 | `public` USAGE bağımlılığı (L1318) | Tek bağımlılık [SQL]. Kaldırılmış durumda `to_regclass`'ın hata verdiği [PG], test edilmedi. PG16 soft-error değişikliği | **NEEDS TEST** | T1-05 (test kümesi); Taslak §3 koşullu GRANT |
| R03 | PUBLIC üzerinden kullanıcı tablosu/sütun/sequence erişimi | Betik ihtiyaç duymaz [SQL]. Stokta yok [PG]. Hedefte bilinmiyor. 5.4 yalnızca 4 tabloyu gösterir | **NEEDS TEST** | T0-06; Taslak §6 `user_rel_access_count = 0` |
| R04 | Büyük nesne erişimi | `parmak_izi_sablonu oid` → LO kullanımı olası. `lo_compat_privileges` ve `lomacl` PUBLIC; PG 18'de LO varsayılan yetkileri (`defaclobjtype 'L'`). 5.16 yalnızca açık ACL sayısını verir | **NEEDS TEST** | T0-07; Taslak §6 `lo_*` |
| R05 | Audit rolünün diğer DB'lere erişimi | Rol cluster-wide [PG]. `postgres`/`template1` stokta PUBLIC CONNECT. `hibrit_giris_db` [BEYAN] muhtemelen kapalı | **NEEDS TEST** (ACL) + **NEEDS DECISION** (pg_hba onayı) | Bölüm 10; T2-03..05 |
| R06 | Default privileges | Gelecekteki nesneler PUBLIC'e veya rol adına otomatik açılabilir. Testte `ALTER DEFAULT PRIVILEGES … TO hgs2_perftest` vardı [K] | **NEEDS TEST** | Taslak §6 `defacl_risk_count`; her denetim öncesi tekrar |
| R07 | PG 18.6 önceden tanımlı rolleri | Tasarım hiçbirini vermez. P8 yalnızca 5'ini ve süper kullanıcıyı görür (§8.5) [SQL] | **VERIFIED** (statik boşluk) | Taslak §7 `no_effective_membership` |
| R08 | Betik kontrolleri ile rolün gerçek yetkilerinin uyuşmazlığı | §12.1 tablosu [SQL] | **VERIFIED** (statik) | Betik dışı ön kontrol (Taslak §6–§9); betik değiştirilmez |
| R09 | Sahiplik veya üyelik yoluyla dolaylı yetki | Tasarımda yok. PG16+ CREATEROLE yaratıcı ADMIN kuralı [PG] → süper kullanıcı oluşturur | **NEEDS TEST** | Taslak §0, §7, §8 |
| R09b | Denetlenen tarafın audit rolüne GRANT vermesi | `hgs2_perftest`, sahibi olduğu tablo/sequence/fonksiyon/DB üzerinde `hgs2_audit`'e yetki verebilir [PG]. Betik bunu yalnızca 4 tablo için raporlar (5.4), durdurmaz | **NEEDS TEST** (sürekli) | Taslak §8 `pg_shdepend 'a'` listesi; her denetim öncesi |
| R10 | `hgs2_perftest_db` PUBLIC TEMPORARY artığı | Betik kullanmaz. READ ONLY'de CREATE TEMP reddedilir [PG]. Tek role özel kaldırılamaz | **NEEDS DECISION** | Kabul (kayıt) **veya** yalnızca bu DB'de `REVOKE TEMPORARY … FROM PUBLIC` (envanter sonrası) |
| R11 | `public` şemasında PUBLIC CREATE (PG ≤ 14 kökenli DB) | PG12 testinde `=UC` [K]. Hedefin kökeni bilinmiyor. Varsa audit rolü nesne sahibi olabilir | **NEEDS TEST → NEEDS DECISION** | T0-05; Taslak §6 `no_schema_create` (false → durur). Şema sahibi `postgres` ise REVOKE `hgs2_perftest` migrasyonlarını bozabilir; önce sahip kontrolü |
| R12 | SECURITY DEFINER fonksiyonlarına PUBLIC EXECUTE | Betik çağırmaz [SQL]. Denetim dışı oturumda audit kimliğiyle çağrılabilir | **NEEDS TEST → NEEDS DECISION** | Taslak §6 `secdef_callable_count`; tek tek inceleme |
| R13 | Yönetici oturumunun `hgs2_perftest_db` içinde etkilenmesi | DB sahibi `ALTER DATABASE … SET search_path` yapabilir [PG]. Betik 4 kapsam 3'te raporlar. Süper kullanıcı oturumu tehlikeye girer | **VERIFIED** (taslak tasarımı: ilk ifadede `SET LOCAL search_path`, `psql -X`) | Uygulamada ayrıca betik Bölüm 4 kapsam 3 çıktısı incelenir |
| R14 | Denetlenen tarafın denetimi engellemesi (fail-closed DoS) | `hgs2_perftest` (DB ve `public` sahibi) PUBLIC CONNECT/USAGE'ı kaldırabilir → betik durur (çıkış 2/3). Yanlış PASS yolu yok | **NEEDS DECISION** (kabul) | Doğrulayıcı FAIL sayar; operasyonel izleme |
| R15 | Parola yöntemi, `VALID UNTIL`, denetim dışı `NOLOGIN` | FINAL_DELIVERY §5.8 "belgelenmemiş". SCRAM yolu hiç test edilmedi (`trust`) | **NEEDS DECISION** + **NEEDS TEST** | §8.3; T1-02 |
| R16 | PG 17+ `login` event trigger | Süper kullanıcı oluşturur, audit oturumunda kod çalıştırabilir. Rol tasarımıyla kontrol edilemez. 5.13 raporlar | **NEEDS TEST** | T0-08: `pg_event_trigger` `evtevent = 'login'` sayısı |
| R17 | "`hgs2_perftest`'in `hibrit_giris_db` CONNECT yetkisi yok" bulgusunun kaynağı | Ölçüm yöntemi bilinmiyor | **UNVERIFIED → NEEDS TEST** | T0-03 |
| R18 | `MINIMUM_PRIVILEGE_ANALYSIS.md` Q3 `SELECT oid, * FROM pg_roles` | `pg_roles` zaten `oid` sütunu içerir → `a.oid` belirsiz [PG] | **NEEDS TEST** (belge düzeltmesi; SQL dosyası değil) | Taslak bu kalıbı kullanmaz (`SELECT r.*`) |
| R19 | Süper kullanıcı düzeyinde ele geçirilmiş sunucu | KNOWN_LIMITATIONS 3 | **NOT APPLICABLE** (kapsam dışı) | — |
| R20 | Replikasyon bağlantısı | `NOREPLICATION` + pg_hba `replication … reject` | **NOT APPLICABLE** (tasarımla kapalı) | T2-06 |
| R21 | PG 12'de 14+ önceden tanımlı rollerin yokluğu | Hedef 18.6 | **NOT APPLICABLE** | — |
| R22 | Unix soketi | Windows'ta varsayılan kapalı; `local … reject` satırları kapsar | **NOT APPLICABLE** (hedef) | — |

### 12.1 Betiğin kendi güvenlik kontrolleri ile rolün gerçek yetkileri

| Özellik | Hedef değer | Betik davranışı | Uyuşma |
|---|---|---|---|
| SUPERUSER (session/current/`is_superuser`) | f | ABORT (L764–769) | ✓ |
| Süper kullanıcı role üyelik | yok | ABORT (L770–775) | ✓ |
| CREATEROLE / BYPASSRLS / REPLICATION | f | WARNING (L780–783) | ✓ |
| CREATEDB | f | Yalnızca rapor (L756–762) | ⚠ betik dışı kontrol (Taslak §6) |
| `pg_read_all_data`, `pg_write_all_data`, sunucu dosyası/programı rolleri | yok | WARNING | ✓ |
| `pg_monitor`, `pg_read_all_*`, `pg_maintain`, `pg_signal_backend`, `pg_checkpoint`, `pg_create_subscription`, `pg_use_reserved_connections`, `pg_signal_autovacuum_worker` | yok | **Görmez** | ✗ Taslak §7 |
| `hgs2_perftest` üyeliği | yok | **Görmez** (süper kullanıcı değilse) | ✗ Taslak §7 |
| Audit rolüne başkalarının üyeliği | yok | **Görmez** | ✗ Taslak §7 |
| Veritabanı / nesne sahipliği, `pg_database_owner` | yok | **Görmez** | ✗ Taslak §8 |
| NOINHERIT, CONNECTION LIMIT, VALID UNTIL | NOINHERIT, 2, karar | **Görmez** | ✗ Taslak §6 |
| Audit rolünün kalıcı ayarları | yok | Rapor (Bölüm 4, `session_user`) | ⚠ rapor, durdurmaz |
| Audit rolünün `hibrit_giris_db` CONNECT'i | f | 3.3 açık GRANT'i listeler; PUBLIC'i 3.4 gösterir; durdurmaz | ⚠ Taslak §9 |
| Audit rolünün tablo/sütun/sequence/LO yetkisi | yok | 5.4 yalnızca 4 tablonun tüm grantee'leri; diğerleri **görülmez** | ✗ Taslak §6 |
| `pg_control_system` EXECUTE | var | Yoksa ABORT (L673–678) | ✓ |
| Yanlış DB'ye bağlantı | olmamalı | ABORT (L476–495), ama bağlantı **olmuştur** | ⚠ pg_hba |
| pg_hba kuralı | Bölüm 10 | **Sorgulamaz** (KNOWN_LIMITATIONS 4) | ✗ Taslak §9.2 |

### 12.2 Açık sorular (karar sahibine)

1. **Q-A:** `hgs2_perftest`'in `hibrit_giris_db` CONNECT bulgusu hangi sorguyla elde edildi? (R17)
2. **Q-B:** `hgs2_perftest_db` PG ≤ 14'ten yükseltilmiş ya da eski bir şablondan oluşturulmuş olabilir mi? `public` şemasının sahibi kim? (R11)
3. **Q-C:** `hgs2_perftest_db`'ye `hgs2_perftest` dışında bağlanan rol var mı? (R10 kararı için)
4. **Q-D:** Parola saklama yöntemi, `VALID UNTIL` süresi, denetim dışında `NOLOGIN`. (R15)
5. **Q-E:** Loopback TLS (`hostssl`) ve `channel_binding=require` istenecek mi? (Bölüm 10.2)
6. **Q-F:** `CONNECTION LIMIT` 2 mi, 1 mi? (§8.2)

---

## 13. Test Plan

Hiçbiri bu çalışmada çalıştırılmadı. Her aşama ayrı onay gerektirir.

### T0 — Hedefte rol oluşturmadan önce salt okunur keşif

Koşullar:
- Yönetici, süper kullanıcı.
- `psql -X`, yalnızca `hgs2_perftest_db`.
- Çerçeve: `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY; SET LOCAL search_path = pg_catalog, pg_temp; … ROLLBACK;`

| ID | Kontrol | Beklenen | Risk |
|---|---|---|---|
| T0-01 | `current_setting('server_version')`, platform | 18.6, Windows | — |
| T0-02 | `pg_database` `datacl` (`hgs2_perftest_db`, `hibrit_giris_db`), sahipler | Kayıt | R05 |
| T0-03 | `has_database_privilege('hgs2_perftest','hibrit_giris_db','CONNECT')`, `rolsuper` | f / f → PUBLIC CONNECT yok çıkarımı geçerli | R17 |
| T0-04 | `pg_control_system()` `proacl` (hgs2_perftest_db) | NULL veya PUBLIC `=X` içeriyor | R01 |
| T0-05 | `public` `nspowner` ve `nspacl` | PG 15+ biçimi `=U` (PUBLIC CREATE yok) | R02, R11 |
| T0-06 | Kullanıcı tablolarında/sütunlarda/sequence'larda PUBLIC (grantee 0) ACL girdisi | 0 | R03 |
| T0-07 | `lo_compat_privileges`; `lomacl` PUBLIC SELECT/UPDATE sayısı; `pg_default_acl` PUBLIC girdileri | off / 0 / 0 (`r`, `S`, `L`) | R04, R06 |
| T0-08 | `pg_event_trigger` `evtevent = 'login'` | 0 | R16 |
| T0-09 | `pg_db_role_setting` kapsam 3–4 (`search_path`, `role`) | Kötü niyetli değer yok | R13 |
| T0-10 | `pg_roles` içinde `hgs2_audit` | Yok | — |
| T0-11 | `pg_hba_file_rules` mevcut kurallar (kayıt) | `error` yok | Bölüm 10 |

### T1 — Test kümesinde (scratchpad, proje harness yöntemiyle) ön doğrulama

| ID | Senaryo | Beklenen | Risk |
|---|---|---|---|
| T1-01 | Taslağın test kümesinde uygulanması (stok PUBLIC) | §2/§3/§5.1'de GRANT **üretilmez**; COMMIT | — |
| T1-02 | Bölüm 10 pg_hba bloğu + `scram-sha-256` + `\password` | Giriş başarılı. **İlk SCRAM testi** (proje `trust` kullanmıştı) | R15 |
| T1-03 | Nihai SQL, `user=hgs2_audit`, doğru parametreler | Çıkış 0, PREFLIGHT_OK + COMPLETE, WARNING yok, validator PASS | — |
| T1-04 | `REVOKE EXECUTE ON FUNCTION pg_control_system() FROM PUBLIC` (yalnızca test DB) → taslak | §5.1 koşullu GRANT üretilir; T1-03 tekrar PASS | R01 |
| T1-05 | `REVOKE USAGE ON SCHEMA public FROM PUBLIC` (test DB), GRANT yok → nihai SQL | Çıkış 3, işaretçisiz, stderr'de `permission denied for schema public` (5.8). Ardından taslak §3 GRANT → PASS | R02 |
| T1-06 | `public` `=UC` (PG12 tarzı) | Taslak §6 `no_schema_create = f` → ROLLBACK | R11 |
| T1-07 | `GRANT SELECT ON public.users TO PUBLIC` | Taslak `user_rel_access_count > 0` → ROLLBACK | R03 |
| T1-08 | `hgs2_perftest` (sahip) `GRANT SELECT ON public.users TO hgs2_audit` (rol oluştuktan sonra) | Taslak §8 `'a'` listesinde görünür; §6 sayaç > 0 | R09b |
| T1-09 | `CREATEROLE` sahibi süper kullanıcı olmayan rol ile `CREATE ROLE` | Taslak §0 durdurur. Elle yapılırsa §7 `no_members_in_audit = f` | R09 |
| T1-10 | `ALTER DATABASE test SET search_path = evil, pg_catalog` + yönetici taslağı | Taslak sonuçları değişmez | R13 |

### T2 — Hedefte uygulama (ayrı onay, sırayla)

| ID | Adım | Beklenen |
|---|---|---|
| T2-01 | pg_hba yedeği; blok en üste; `pg_hba_file_rules` hatasız; diğer kullanıcı satırları değişmemiş | Fark yalnızca 6 yeni satır |
| T2-02 | `pg_reload_conf()` | `true`; günlükte hata yok; mevcut uygulama oturumları kesilmedi |
| T2-03 | Taslak (§0–§10) | `HGS2_ROLE_DESIGN_OK`, COMMIT; `has_db_temporary`, `secdef_callable_count`, `hibrit_acl_closed` kayıtta |
| T2-04 | `\password hgs2_audit` | `rolpassword` SCRAM biçiminde (yalnızca süper kullanıcı `pg_authid`'de görür) |
| T2-05 | Negatif bağlantılar N1–N2 (`hibrit_giris_db`, `postgres`, `template1`, `::1`) | Hepsi `pg_hba.conf rejects connection`, çıkış 2 |
| T2-06 | `psql "… replication=database user=hgs2_audit"` | Ret |
| T2-07 | N3–N5 (pozitif bağlantı, `SET ROLE` reddi, tablo SELECT reddi) | Beklendiği gibi |
| T2-08 | Uygulama bağlantısı (mevcut uygulama rolüyle, normal kullanım) | Değişiklik yok |
| T2-09 | P1: nihai denetim + `validate_audit_result.py` | PASS, uyarısız |
| T2-10 | Denetim sonrası (karar Q-D): `ALTER ROLE hgs2_audit NOLOGIN` veya `VALID UNTIL` dolması | Giriş reddi |

### T3 — Her denetim çalıştırmasından önce (sürekli)

- Taslak §6–§9 sorguları, salt okunur çerçevede (§1–§5 hariç).
- Beklenen: önceki çalıştırmayla aynı sonuç.
- `pg_shdepend 'a'` listesinde **yeni** satır olmamalı (R09b).

---

## 14. Final Recommendation

1. **Yeni bir `hgs2_audit` rolü oluşturulmalı.** Denetim `hgs2_perftest` ile çalıştırılmamalıdır.
   - `hgs2_perftest` denetlenen ve büyük olasılıkla sahip olan roldür.
   - P8, sahiplik ve `pg_database_owner` yetkilerini görmediği için `hgs2_perftest` ile yapılan bir çalıştırma uyarısız PASS verir (MINIMUM_PRIVILEGE_ANALYSIS §8).

2. **Önerilen rol tanımı:** `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2`.
   - Üyelik yok, sahiplik yok, rol ayarı yok.
   - Süper kullanıcı tarafından, parolasız oluşturulur. Parola `\password` ile verilir.

3. **Yetkiler:** Stok PG 18.6'da **hiçbir GRANT gerekmez**. Hedefte ölçüm (T0) eksik gösterirse yalnızca şu üç koşullu GRANT, yalnızca `hgs2_audit`'e ve yalnızca `hgs2_perftest_db` içinde verilir:
   - `CONNECT` (hgs2_perftest_db)
   - `USAGE ON SCHEMA public`
   - `EXECUTE ON FUNCTION pg_catalog.pg_control_system()`

   Katalog veya diğer yerleşik fonksiyon eksikliğinde GRANT verilmez; durulur ve karar alınır.

4. **İzolasyon:** Uygulama sırası şöyle olmalıdır:
   1. Bölüm 10'daki pg_hba bloğu, dosyanın en üstüne ve **rolden önce**.
   2. Yeniden yükleme.
   3. Rol oluşturma.
   4. Parola.
   5. Negatif bağlantı testleri.

   `hibrit_giris_db` ACL'sine, PUBLIC CONNECT'e ve `datallowconn`'a dokunulmaz.

5. **Kaçınılacaklar:**
   - PUBLIC üzerinde küme geneli REVOKE.
   - Önceden tanımlı rol üyelikleri.
   - `hgs2_perftest` üyeliği.
   - Tablo/LO yetkileri.
   - Gereksiz (PUBLIC'i tekrarlayan) GRANT'ler.

6. **Uygulamadan önce kapatılması gerekenler:**
   - Kararlar: R10, R11, R12, R14, R15; sorular Q-A…Q-F.
   - Testler: T0'ın tamamı ve T1-02 / T1-05 (SCRAM ve `public` USAGE davranışı ilk kez burada test edilecek).

7. **Sürekli kontrol:** Denetlenen taraf audit rolüne yetki ekleyebilir (R09b). Taslak §6–§9 doğrulaması her denetim çalıştırmasından önce tekrarlanmalıdır. Betiğin P8 kontrolü bu amaç için **yeterli değildir** (§12.1).

**Genel durum:** Tasarım, nihai SQL'in gerçek bağımlılıklarına bağlanmıştır ve test kümelerindeki kanıtla tutarlıdır. Hedef ortam için **NEEDS TEST** ve **NEEDS DECISION** maddeleri kapanmadan uygulamaya geçilmemelidir.
