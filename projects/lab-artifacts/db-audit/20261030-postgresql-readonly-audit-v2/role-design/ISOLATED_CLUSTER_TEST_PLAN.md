# ISOLATED_CLUSTER_TEST_PLAN — `hgs2_audit` bağımsız inceleme ve izole test planı

- Proje: HGS2 PostgreSQL Read-Only Audit V2
- Tarih: 2026-10-30 (+03:00)
- Durum: **PLAN — hiçbir adım çalıştırılmadı**
- İncelenen nihai SQL: `asama3-final/postgresql_readonly_audit_v2.sql`, SHA-256 `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`

**Etiketler** (görev tanımındaki sınıflandırma):

| Etiket | Anlamı |
|---|---|
| **[K]** | Mevcut test kanıtıyla doğrulanmış (yalnızca önceki aşamaların geçici test kümeleri: PG 12.22 / 16.15 / 17.11 / 18.6, `trust`, IPv4) |
| **[D]** | Dosyaların statik analiziyle doğrulanmış |
| **[S]** | PostgreSQL semantiğine dayalı; bu projede **test edilmedi** |
| **[P]** | Önerilen plan |

Gerçek ortama ait, bu klasörlerde kanıtı olmayan kullanıcı beyanları **UNVERIFIED** olarak ayrıca işaretlenmiştir.

---

## 0. Kapsam, dosya konumları ve sınırlar

### 0.1 Dosyaların gerçek konumları [D]

İstenen altı dosyanın **hiçbiri** HGS2 Git kökünde (`C:\Users\Ceng Zeki\Desktop\Projects\hgs2`) yoktur. Tamamı aşağıdaki klasördedir:

`C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\db-audit\20261030-postgresql-readonly-audit-v2\`

| İstenen | Bulunan yol (yukarıdaki köke göre) |
|---|---|
| `role-design/AUDIT_ROLE_PRIVILEGE_MATRIX.md` | `role-design\AUDIT_ROLE_PRIVILEGE_MATRIX.md` |
| `MINIMUM_PRIVILEGE_ANALYSIS.md` | `asama3-final\MINIMUM_PRIVILEGE_ANALYSIS.md` |
| `postgresql_readonly_audit_v2.sql` | `asama3-final\postgresql_readonly_audit_v2.sql` (**nihai**, `5916d12b…`). Kökteki aynı adlı dosya 2. aşama sürümüdür (`b8eb2ac6…`) ve analiz edilmedi |
| `FINAL_DELIVERY.md` | `asama3-final\FINAL_DELIVERY.md` |
| `FINAL_SECURITY_AUDIT.md` | `asama3-final\FINAL_SECURITY_AUDIT.md` |
| `KNOWN_LIMITATIONS.md` | `asama3-final\KNOWN_LIMITATIONS.md` |

- Bu belge, mevcut `role-design\` klasörüne, `AUDIT_ROLE_PRIVILEGE_MATRIX.md` dosyasının yanına yazıldı.
- HGS2 Git deposuna hiçbir dosya **eklenmedi**.

### 0.2 HGS2 Git deposundan salt okunur incelenenler [D]

Parola satırları okunmadı ve yazılmadı.

| Dosya | İlgili bulgu |
|---|---|
| `hgs2-main\HGS-main\HGS\src\main\resources\application.properties` L3–4 | Ana uygulama `hibrit_giris_db`'ye **`postgres`** (süper kullanıcı) ile `localhost:5432` üzerinden bağlanır |
| `…\application-perftest.properties` L1–22 | perftest profili `127.0.0.1:5432/hgs2_perftest_db`'ye ortam değişkeninden gelen kullanıcıyla bağlanır |
| `…\Config\PerfTestSafetyGuard.java` L46–47, 66–67, 74, 221–246 | Test kullanıcısının `hibrit_giris_db` bağlantı denemesi **yalnızca SQLState 42501** ile reddedilirse uygulama başlar. Başka her hata (pg_hba reddi = 28000 dahil) başlatmayı durdurur |

### 0.3 Bu çalışmanın sınırları

- PostgreSQL'e bağlanılmadı. psql çalıştırılmadı. SQL çalıştırılmadı.
- `pg_hba.conf` ve data directory okunmadı, değiştirilmedi.
- Git yalnızca okuma amaçlı sorgulandı (`status`, `rev-parse`). Commit/checkout/reset/push yapılmadı.
- `postgresql-x64-18` servisinin durumu yalnızca Windows WMI/CIM üzerinden **okundu** (durum, PID, oluşturma zamanı, yürütme yolu). Bu, veritabanı bağlantısı değildir.

---

## 1. Yönetici özeti

1. **Önceki tasarımın yetki sonucu bağımsız incelemede doğrulandı.** [D] [K]
   - Betiğin ihtiyaçları şunlardır:
     - `LOGIN`;
     - `hgs2_perftest_db` üzerinde `CONNECT`;
     - `pg_catalog` USAGE;
     - `public` USAGE (yalnızca L1318);
     - 21 katalog ilişkisinde SELECT;
     - 40 yerleşik fonksiyon imzası ile 3 görünüm içi fonksiyonda EXECUTE;
     - `pg_control_system()` EXECUTE.
   - Stok PG 18.6'da hepsi PUBLIC'ten gelir. **Hiç GRANT gerekmez.**
   - Yalnızca hedefte eksik olduğu ölçülen yetki, yalnızca `hgs2_audit`'e ve yalnızca `hgs2_perftest_db` içinde verilir.

2. **Önceki tasarımda olmayan, bu incelemede bulunan noktalar:**
   - **Uyumluluk kısıtı.** [D] `PerfTestSafetyGuard`, `hgs2_perftest`'in `hibrit_giris_db` denemesinde yalnızca 42501'i kabul eder.
     - `hgs2_perftest`'i etkileyen bir pg_hba `reject` kuralı, hatayı 28000'e çevirir ve perftest uygulamasını **başlatılamaz** hale getirir.
     - Önerilen pg_hba bloğu yalnızca `hgs2_audit` adıyla eşleşir. Bu kısıt T8-d ile test edilir.
   - **Ana uygulama `postgres` süper kullanıcısıyla bağlanıyor.** [D] Bu, audit rolü kapsamı dışında bir güvenlik bulgusudur (R-N2).
   - **IPv6 hiç test edilmedi.** [K] Önceki test kümeleri `listen_addresses = '127.0.0.1'` ile kuruldu (`kanit/harness/conf.sh`). Ana uygulama `localhost` kullandığı için Windows'ta `::1` yolu gerçekçidir [S]. T9 IPv6'yı kapsar.
   - **SCRAM ve `hostssl` kuralları hiç test edilmedi.** [K] Önceki kümeler `host all all 127.0.0.1/32 trust` kullandı. T1, T10 bunları kapsar.
   - **Betiğin P8 kontrolü T2, T3, T4, T5 ihlallerini durdurmaz.** [D] Bu ihlallerde betik **PASS** verir.
     - Testin başarı ölçütü, betiğin değil **betik dışı doğrulamanın** (`AUDIT_ROLE_PRIVILEGE_MATRIX.md` §11 §6–§9) FAIL vermesidir.
     - Bu, P8 boşluğunu kanıtlamak için tasarlanmış bir test grubudur.

3. **Disposable cluster tasarımı.** [P]
   - Ayrı dizin: `%LOCALAPPDATA%\hgs2-iso\<RUNID>`.
   - Ayrı port `55438`. Yalnızca `127.0.0.1` ve `::1` dinlenir. Unix soketi kapalı.
   - Servis kaydı yok. `pg_ctl` ile geçerli kullanıcı altında çalışır.
   - Ayrı log, sentetik veri, port kapsamlı geçici parola dosyası.
   - Her adımda canlı servis (PID 4708, oluşturma 16:29:54) ile değişmezlik karşılaştırması yapılır.
   - Senaryolar arası temizlik "golden" veri dizini kopyasından geri yükleme ile **deterministik** yapılır.

4. **pg_hba tasarımı.** [P] [S]
   - `hgs2_audit` blokları dosyanın en üstündedir.
   - Test kümesinde iki varyant denenir: A (TLS isteğe bağlı) ve B (TLS zorunlu, `hostssl`).
   - Varyant B, sunucuda SSL kapalıysa `hgs2_audit`'i tamamen kilitler. Yani fail-closed davranır [S].
   - Gerçek küme için varyant seçimi gerçek `ssl` ayarı bilinmeden yapılamaz → **açık karar**.

5. **Gerçek kümeye geçiş için önkoşullar:**
   - T1–T10'un tamamı beklenen sonuçla geçmeli.
   - `AUDIT_ROLE_PRIVILEGE_MATRIX.md` §13 T0 salt okunur keşfi yapılmalı.
   - Kararlar kapanmalı (§11).
   - Ayrı yönetici onayı alınmalı.

---

## 2. Audit rolü minimum yetki matrisi

### 2.1 Gerekli yetkiler (yalnızca nihai SQL'e dayanır)

| # | Yetki | Betikteki tek kaynak (satır) | Gerekli mi | Stok kaynağı | GRANT | Etiket |
|---|---|---|---|---|---|---|
| 1 | `LOGIN` | Bağlantı (kullanım L35–47) | Evet | — | `CREATE ROLE … LOGIN` | [D] |
| 2 | `CONNECT` on `hgs2_perftest_db` | Bağlantı; L461 | Evet | PUBLIC (`datacl` NULL ise) | Yalnızca hedefte PUBLIC yoksa, yalnızca `hgs2_audit`'e | [D] [K] |
| 3 | `USAGE` on schema `pg_catalog` | Tüm nitelenmiş adlar; `::regclass` sabitleri (L1224 …), L669 metin çözümlemesi | Evet | PUBLIC (initdb) | Hayır | [D] [K] |
| 4 | `USAGE` on schema `public` (`hgs2_perftest_db`) | **Yalnızca** L1318 `to_regclass('public.users')` | Evet | PUBLIC (`=U`, PG 15+) | Yalnızca hedefte PUBLIC yoksa | [D]; eksiklikte davranış [S] |
| 5 | `SELECT` on 21 katalog ilişkisi | §2.3 | Evet | PUBLIC | Hayır. Eksikse dur, karar ver | [D] [K] |
| 6 | `EXECUTE` on 40+3 yerleşik fonksiyon | §2.4 | Evet | PUBLIC | Hayır. Eksikse dur, karar ver | [D] [K] |
| 7 | `EXECUTE` on `pg_catalog.pg_control_system()` | L669 (kapı), L685 | **Evet, zorunlu** | PUBLIC (dolaylı kanıt) | Yalnızca hedefte PUBLIC yoksa | [D] [K]+[S] |

### 2.2 Gerekmeyen ve **bulunmaması gereken** yetkiler

| Yetki | Neden gerekmez | Etiket |
|---|---|---|
| `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS` | Betik yalnızca katalog okur | [D] |
| Herhangi bir rol üyeliği (`hgs2_perftest`, `postgres`, `pg_read_all_data`, `pg_monitor`, `pg_read_all_settings`, `pg_read_all_stats`, `pg_maintain`, …) | Kullanılan ayarlar süper kullanıcıya özel değil; `pg_stat_ssl` kendi satırını gösterir | [D] [K] |
| Veritabanı/şema/nesne sahipliği | Hiçbir DDL yok (`CREATE/ALTER/DROP/GRANT/REVOKE` = 0) | [D] |
| `TEMPORARY` | READ ONLY transaction; `pg_temp` yalnızca ad çözümleme sırasıdır | [D] [S] |
| `CREATE` (DB / şema) | DDL yok | [D] |
| Kullanıcı tablosu/sütun SELECT | Hiçbir `FROM` kullanıcı ilişkisi değildir. `users`/`admins`/`logs`/`devices` yalnızca `relname` sabiti ve `to_regclass` OID'i olarak geçer | [D] |
| Sequence USAGE/SELECT/UPDATE | `nextval`/`currval` yok; `has_sequence_privilege` başka rol için sorgular | [D] |
| Large object SELECT/UPDATE | Yalnızca `pg_largeobject_metadata`; `pg_largeobject` ve `lo_*` = 0 | [D] |
| Foreign server / FDW USAGE | Yalnızca `pg_foreign_server` satırı ve `pg_user_mappings` sayısı | [D] |
| `hibrit_giris_db` ve diğer DB'lerde CONNECT | 3.1–3.4 paylaşılan `pg_database`'ten okur | [D] |
| Kalıcı rol/DB ayarı (`ALTER ROLE/DATABASE … SET`) | Betik kendi `SET LOCAL`'larını yapar (L410–412) | [D] |

### 2.3 Konu bazında ayrı değerlendirme

**A. `pg_control_system()`**
- Gereklilik: **zorunlu** [D].
  - L669'da `has_function_privilege('pg_catalog.pg_control_system()', 'EXECUTE')` current_user için ölçülür. Yoksa `system_identifier_unverifiable` ile durur (L673–678).
  - `expected_system_identifier` zorunludur (L314–319). Atlama yolu yoktur.
- Kaynak:
  - 4 sürümün `pg_dump -s` çıktısında `REVOKE ALL ON FUNCTION pg_catalog.pg_control_system(...) FROM PUBLIC` var [K] (`kanit/snapshots/before/pg{12,16,17,18}/schema.sql` ~L358–360).
  - `pg_dump` sistem nesnelerinde yalnızca initdb başlangıç ACL'sinden farkı yazdığı için başlangıçta PUBLIC EXECUTE vardı [S].
- Testteki açık GRANT, `fixture_harden.sql` sertleştirmesi yüzündendi [K].
- ACL veritabanı başınadır; ilgili olan `hgs2_perftest_db` içindeki `proacl` [S].
- Yetki olmadan davranış: ABORT, çıkış 3 [K: A13 senaryosu, `hgs2_auditor_nosysid`, 4 sürüm].
- Test: **T6**.

**B. `pg_stat_ssl`**
- Gereklilik: **evet** [D]. P6b (L600–650) TLS durumunu ve `transport_ok` kararını buradan hesaplar. Görünüm okunamazsa ifade hata verir (çıkış 3) [S].
- Yalnızca `s.pid = pg_backend_pid()` satırı okunur (L604) [D].
- Görünüm içinden `pg_stat_get_activity(integer)` EXECUTE gerekir [S]. Kendi oturum satırı için `pg_read_all_stats` gerekmez [K: süper kullanıcı olmayan `hgs2_auditor`, N1-normal 4 sürüm, `tls=` satırı üretildi].
- Görünüm `client_port IS NOT NULL` filtreler. TCP bağlantıda satır vardır [S]. Satır yoksa LEFT JOIN `ssl = NULL` verir ve karar loopback sınıflamasına düşer [D].
- **Test edilmeyen:** IPv6 ve `hostssl` ile satır içeriği → T9, T10.

**C. `pg_user_mappings`**
- Gereklilik: **evet** [D]. 5.14b L1499'da yalnızca `count(*)` alınır; `umoptions` seçilmez.
- Taban tablo `pg_user_mapping` PUBLIC'e kapalıdır; görünüm açıktır [S]. Betik taban tabloyu kullanmaz [D]. Görünüm okunabildi [K: N1].
- Görünüm içinde `pg_has_role(oid,text)` ve `has_server_privilege(oid,text)` EXECUTE gerekir [S]. Yalnızca `count(*)` seçildiği için bu sütun değerlendirilmeyebilir [S].
- Foreign server yoksa alt sorgu hiç çalışmaz. Yine de ilişki yetki denetimi yürütme başlangıcında, plandaki tüm ilişkiler için yapılır [S]. Bu yüzden SELECT gereklidir.

**D. `public` şeması USAGE**
- Gereklilik: **evet, tek kaynak L1318** [D]. Diğer `public` geçişleri:
  - `to_regnamespace('public')`: USAGE denetlemez [S].
  - `n.nspname = 'public'`: metin karşılaştırması [D].
- Eksiklikte iki olasılık vardır; hangisinin olacağı **bilinmiyor** [S]:
  1. `permission denied for schema public` → çıkış 3, işaretçisiz.
  2. PG 16+ soft-error altyapısı yetki hatasını da yutuyorsa NULL → 5.8 boş sonuç ve **PASS**. Bu, "users.parmak_izi_sablonu" kontrolünün sessizce boş kalması demektir.
- Test: **T7**. Önceki belgeler yalnızca olasılık 1'i varsaymıştı. Bu plan iki sonucu da kaydeder ve önceden birini seçmez.

**E. Katalog SELECT** (21 ilişki: 18 tablo + 3 görünüm) [D]
- Tablolar: `pg_auth_members`, `pg_database`, `pg_db_role_setting`, `pg_namespace`, `pg_class`, `pg_attribute`, `pg_depend`, `pg_constraint`, `pg_type`, `pg_proc`, `pg_trigger`, `pg_event_trigger`, `pg_extension`, `pg_foreign_server`, `pg_foreign_data_wrapper`, `pg_policy`, `pg_default_acl`, `pg_largeobject_metadata`.
- Görünümler: `pg_roles`, `pg_user_mappings`, `pg_stat_ssl`.
- Hepsi PUBLIC ile okundu [K: N1, katalog GRANT'i olmayan `hgs2_auditor`].
- Satır ayrıntıları: `AUDIT_ROLE_PRIVILEGE_MATRIX.md` §5.
- Kullanılmayanlar: `pg_index`, `pg_shdepend`, `pg_settings`, `pg_authid`, `pg_largeobject`, `pg_stat_activity`, `pg_hba_file_rules` (grep = 0) [D].

**F. Yerleşik fonksiyon EXECUTE** [D] [K]
- 40 doğrudan imza. Sunucu başına 39 çalışır, çünkü `pg_current_xact_id_if_assigned()` (≥13) ile `txid_current_if_assigned()` (<13) birbirini dışlar.
- 3 görünüm içi fonksiyon.
- Operatör/cast fonksiyonları vardır. Hepsi `pg_catalog` içinde ve PUBLIC'tir.
- `pg_read_file`, `pg_ls_dir`, `lo_import` gibi initdb'nin PUBLIC'ten geri aldığı fonksiyonların hiçbiri kullanılmaz.
- İmza listesi: `AUDIT_ROLE_PRIVILEGE_MATRIX.md` §6 ve §11 §5.2.

### 2.4 `MINIMUM_PRIVILEGE_ANALYSIS.md` iddialarının yeniden kontrolü

| İddia | Sonuç | Etiket |
|---|---|---|
| 21 katalog ilişkisi | Doğru (18 tablo + 3 görünüm) | [D] |
| "Yaklaşık 40 fonksiyon" | Doğru: 40 imza + 3 görünüm içi | [D] |
| `pg_read_all_settings` / `pg_monitor` gerekmez | Doğru | [D] [K] |
| `hgs2_auditor` minimum profilin canlı örneğidir | **Kısmen.** Yetkiler açısından doğru. Ancak `hgs2_auditor`'a A02 için `hibrit_giris_db` CONNECT verilmişti (`fixture_global.sql` L22). Kimlik doğrulama `trust` idi. Bu yüzden pg_hba/SCRAM tarafını kanıtlamaz | [K] |
| `to_regclass` USAGE yoksa hata verir | **Doğrulanmadı**; iki olası sonuç (§2.3 D) | [S] |
| P8 sahiplik/üyelik/`pg_database_owner`'ı görmez | Doğru (L722–783) | [D] |
| Q3 sorgusu (`SELECT oid, * FROM pg_roles`) | `pg_roles` zaten `oid` içerdiği için `a.oid` belirsiz olabilir | [S] |

### 2.5 `AUDIT_ROLE_PRIVILEGE_MATRIX.md` bağımsız inceleme notları

| # | Konu | Değerlendirme | Etiket |
|---|---|---|---|
| M1 | Yetki matrisi ve "sıfır GRANT" sonucu | Doğrulandı | [D] [K] |
| M2 | §6.1 "[K-dolaylı]" etiketi | Bu plandaki sınıflamada **[K]+[S]** (kanıt + pg_dump semantiği) olarak okunmalı | — |
| M3 | §10 pg_hba yalnızca `host` (TLS isteğe bağlı) önerir | Betikle tutarlı (P6b loopback TLS'siz kabul). TLS zorunlu varyant test edilmedi → bu plan iki varyantı test eder | [D] [P] |
| M4 | §11 §9.2 `pg_hba_file_rules` kontrolü | Adresi, `hostssl`/`host` ayrımını ve TLS'siz bağlantının düşeceği kuralı yorumlamaz. Gerçek bağlantı testleri (T8–T10) gerekir | [D] |
| M5 | `PerfTestSafetyGuard` 42501 kısıtı | Matriste **yoktu**. Eklendi (§6.5, T8-d) | [D] |
| M6 | `pg_signal_autovacuum_worker` "PG 18" | Sürüm bilgisi bu projede doğrulanmadı | [S] |
| M7 | IPv6 | Matris `::1/128` kuralı önerdi ama önceki kanıtlar yalnızca IPv4 | [K] |
| M8 | Draft §10 `hba_hibrit_rejected` | Yalnızca ilk eşleşen TCP kuralının yöntemine bakar. Yanlış sıralamayı yakalar (T8-e). Adres bazlı istisnaları yakalamaz | [D] |

---

## 3. Rol oluşturma tasarımı

### 3.1 Kurallar

| Kural | Uygulama | Etiket |
|---|---|---|
| Ayrı yönetici onayı | Taslak, dosyanın başında koşulsuz `\quit` içerir. Onaylı kopyada `\quit` kaldırılır ve kopyanın SHA-256'sı onay kaydına yazılır. Ek kapı: `-v change_ref=<onay-no>` verilmezse dur | [P] |
| Oluşturan: **süper kullanıcı** | PG 16+'da süper kullanıcı **olmayan** bir `CREATEROLE` rolü yeni rolü oluşturursa kendisine `ADMIN OPTION` ile üyelik kaydı (`pg_auth_members`: `roleid = hgs2_audit`, `member = oluşturan`, `admin_option = t`) eklenir. `createrole_self_grant` ayarına göre `INHERIT`/`SET` de eklenebilir. Bu oluşturan rol parolayı değiştirebilir, rolü başkasına verebilir ve `SET` ile denetçi kimliğine bürünebilir. Süper kullanıcı oluşturduğunda otomatik üyelik kaydı yoktur | [S] → RC-02 testi |
| `IN ROLE` / `ROLE` / `ADMIN` yan tümceleri yok | Üyelik oluştururlar | [S] |
| Öznitelikler | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2` | [P] |
| `NOINHERIT` notu | Bugün üyelik olmadığı için etkisizdir. PG 16+'da `NOINHERIT` yalnızca yeni GRANT'lerin varsayılan `INHERIT` seçeneğini FALSE yapar; `SET` varsayılanı TRUE kalır. Asıl koruma "üyelik yok" kuralıdır. PUBLIC yetkileri `NOINHERIT`'ten etkilenmez | [S] |
| PUBLIC'i tekrarlayan GRANT yok | Her koşullu GRANT önce `has_*_privilege('hgs2_audit', …)` ile ölçülür. `true` → GRANT üretilmez | [P] |
| Dokunulmayanlar | `hibrit_giris_db` ACL'si, `hgs2_perftest` rolü, veritabanı sahiplikleri, PUBLIC üzerindeki her yetki | [P] |
| Tek transaction | `BEGIN` → `CREATE ROLE` → koşullu GRANT'ler → doğrulamalar → hepsi geçerse `COMMIT`, aksi halde `ROLLBACK` (rol oluşmaz) | [P] |
| Yönetici oturumu sertleştirmesi | `psql -X`; ilk ifadede `SET LOCAL search_path = pg_catalog, pg_temp`. Gerekçe: `hgs2_perftest_db` sahibi, `ALTER DATABASE … SET search_path` ile süper kullanıcı oturumunu etkileyebilir | [S] [P] |

Uygulanabilir SQL taslağı `AUDIT_ROLE_PRIVILEGE_MATRIX.md` §11'dedir ve bu planda değiştirilmeden kullanılır. Test kümesindeki tek fark bağlantı dizesidir (port 55438).

### 3.2 Koşullu GRANT karar tablosu

| Ölçüm (`hgs2_perftest_db`, yönetici oturumu) | Sonuç `true` | Sonuç `false` |
|---|---|---|
| `has_database_privilege('hgs2_audit','hgs2_perftest_db','CONNECT')` | GRANT yok | `GRANT CONNECT ON DATABASE hgs2_perftest_db TO hgs2_audit` |
| `has_schema_privilege('hgs2_audit','pg_catalog','USAGE')` | — | **Dur** (olağan dışı küme) |
| `has_schema_privilege('hgs2_audit','public','USAGE')` | GRANT yok | `GRANT USAGE ON SCHEMA public TO hgs2_audit` |
| 21 katalog `has_table_privilege(…,'SELECT')` | — | **Dur** (sertleştirilmiş katalog; test edilmedi) |
| `has_function_privilege('hgs2_audit','pg_catalog.pg_control_system()','EXECUTE')` | GRANT yok | `GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO hgs2_audit` |
| Diğer 42 imza `has_function_privilege` | — | **Dur** |

### 3.3 Parola yönetimi

**Gerçek küme için** [P]:
1. Rol **parolasız** oluşturulur. `rolpassword` NULL kalır ve hiçbir `scram-sha-256` kuralı girişe izin vermez [S].
2. Parola, yönetici tarafından etkileşimli psql'de verilir:
   ```text
   SET password_encryption = 'scram-sha-256';
   \password hgs2_audit
   ```
   psql SCRAM özetini istemci tarafında hesaplar; açık metin sunucuya gitmez [S].
   - Gönderilen `ALTER ROLE … PASSWORD 'SCRAM-SHA-256$…'` ifadesi `log_statement = ddl/all` ise günlüğe düşer. SCRAM özeti çevrim dışı tahmin saldırısına açıktır.
   - Bu yüzden yönetici aynı oturumda önce `SET log_statement = 'none'` yapmalıdır (süper kullanıcı) [S] [P].
3. Parola üretimi: en az 32 karakter rastgele; parola yöneticisinde saklanır.
4. Operatöre teslim ve kullanım:
   - Tercih edilen: psql parola istemi (etkileşimli).
   - Otomasyonda: Windows DPAPI ile korunan bir kimlik dosyasından (kullanıcı ve makineye bağlı) çalıştırma anında **geçici** bir `pgpass.conf` üretilir.
     - Dosya yalnızca operatör hesabına NTFS izinli bir dizine yazılır ve `PGPASSFILE` ile gösterilir.
     - pgpass satırı host ve port kapsamlıdır.
     - Çalıştırmadan sonra silinir.
   - Windows'ta libpq pgpass dosya izinlerini denetlemez; koruma NTFS ACL'ye kalır [S].
5. **Asla:** SQL dosyası, komut satırı, bağlantı URL'si, `PGPASSWORD` (betik L82 yasaklar), kalıcı ortam değişkeni, depo, günlük.
6. Süre ve rotasyon: `VALID UNTIL <denetim penceresi sonu>` ve/veya denetim dışında `ALTER ROLE hgs2_audit NOLOGIN`. Her pencereden sonra parola yenilenir → **karar** (§11).

**Test kümesi için** [P]:
- Parolalar rastgele ve kullanılıp atılır. Gerçek parolalarla **hiçbir ilişkileri yoktur**.
- Süper kullanıcı parolası `initdb --pwfile` ile verilir; dosya hemen silinir.
- Diğer roller için iki yol vardır:
  - (a) Üretim yöntemini sınamak için `hgs2_audit`'e etkileşimli `\password` (RC-03).
  - (b) Otomatik kurulumda: psql 15+ `\getenv` ile süreç ortamından okunan değer ve `SET log_statement = 'none'` altında `ALTER ROLE … PASSWORD :'pw'`.
- Parolalar yalnızca test portuna kapsamlı `pgpass.conf` dosyasında tutulur: `*:55438:*:<rol>:<parola>`. Bu yüzden 5432'ye karşı kullanılamaz.

### 3.4 Rol oluşturma testleri (test kümesinde)

| ID | Test | Beklenen | Etiket |
|---|---|---|---|
| RC-01 | Taslak, stok kümede süper kullanıcıyla | `HGS2_ROLE_DESIGN_OK`. §2/§3/§5.1'de **hiç GRANT üretilmez**. `pg_shdepend` `deptype = 'a'` listesi boş. `pg_auth_members WHERE roleid = hgs2_audit OR member = hgs2_audit` → 0 | [P] |
| RC-02 | Süper kullanıcı olmayan `iso_creator CREATEROLE` ile `CREATE ROLE iso_probe` | `pg_auth_members` satırı: `roleid = iso_probe`, `member = iso_creator`, `admin_option = t`. Bu, §3.1'deki "süper kullanıcı oluşturur" kuralının gerekçesini doğrular | [S] → test |
| RC-03 | `\password hgs2_audit` (etkileşimli) | `pg_authid.rolpassword LIKE 'SCRAM-SHA-256$%'`. Sunucu günlüğünde (`log_statement = 'none'` yapıldıysa) ALTER ROLE satırı yok | [P] |
| RC-04 | Taslak, `hgs2_audit` zaten varken | `DUR: hgs2_audit zaten var`. ROLLBACK | [P] |
| RC-05 | Taslak, süper kullanıcı olmayan bir rolle | `DUR: rol super kullanici tarafindan olusturulmali` | [P] |

---

## 4. Disposable PostgreSQL cluster mimarisi

### 4.1 Bileşenler

| Bileşen | Değer | Canlı kümeden ayrım | Etiket |
|---|---|---|---|
| İkili dosyalar | `C:\Program Files\PostgreSQL\18\bin` (yalnızca **okunur ve çalıştırılır**) | Önceki aşamalar aynı ikili dosyalarla ayrı `initdb` yaptı. Canlı servise dokunulmadı | [K] (ASAMA2_RAPORU L167, L300) |
| Canlı data directory | `C:\Program Files\PostgreSQL\18\data` | **Hiçbir komutta yazma hedefi değildir.** Koruma kapıları bu yolu ve `C:\Program Files` altını reddeder | [D] (servis `PathName`) [P] |
| Test kökü | `%LOCALAPPDATA%\hgs2-iso\<RUNID>\` | Kullanıcı profili altında; yönetici hakkı gerekmez | [P] |
| Data directory | `<kök>\data` | Ayrı `initdb` | [P] |
| Golden kopyalar | `<kök>\golden-base`, `<kök>\golden-role` | Senaryolar arası geri yükleme | [P] |
| Log | `<kök>\log\postgres.log` (`pg_ctl -l`) | Ayrı dosya | [P] |
| Sertifikalar | `<kök>\certs` (sentetik CA, 7 gün) | Gerçek sertifika yok | [P] |
| İstemci yapılandırması | `<kök>\cfg` (`PGPASSFILE`, `PSQLRC`, `PGSERVICEFILE`, `PGSYSCONFDIR`) | Kullanıcı/sistem psql ayarları devre dışı | [K] (`kanit/harness/env.sh` aynı yöntem) |
| Kanıt | `<kök>\evidence\<senaryo>\{args,stdout,stderr,exit,verdict}.txt` | Önceki harness düzeni | [K] (`run3.sh`) |
| Port | **55438** (canlı 5432; önceki test portları 55412/16/17/18) | Kapı: 5432 ise veya port dinleniyorsa dur | [P] |
| Dinleme | `listen_addresses = '127.0.0.1,::1'`, `unix_socket_directories = ''` | Ağa açık değil | [P] |
| Süreçler | `pg_ctl start` → geçerli kullanıcı altında yeni postmaster | Canlı servis `LocalSystem` altında PID 4708 / postmaster 6164. **Servis kaydı (`pg_ctl register`) yapılmaz** | [D] [P] |
| `cluster_name` | `hgs2iso18` | Betik P6'da raporlar (L542) | [P] |
| Bootstrap süper kullanıcı | `postgres` (gerçek ortamın adlarını yansıtmak için) | Ad çakışması riski şunlarla kapatılır: port kapsamlı pgpass, port/host kapısı, `-X`, ortam değişkeni temizliği | [P] |
| Veri | Sentetik (`kanit/harness/fixture_db.sql` tablo DDL'i). Ek ACL senaryosu satırları **kaldırılır** | Gerçek veri yok | [K] [P] |

### 4.2 Fixture (mantıksal)

**Global (`postgres` DB, süper kullanıcı)** [P]:
- `CREATE ROLE hgs2_perftest LOGIN` (+ test parolası).
- `CREATE DATABASE hgs2_perftest_db OWNER hgs2_perftest`.
- `CREATE DATABASE hibrit_giris_db OWNER postgres` (yalnızca ad; içi boş).
- `CREATE DATABASE other_db`.
- `REVOKE CONNECT ON DATABASE hibrit_giris_db FROM PUBLIC`: gerçek ortam beyanının aynası (UNVERIFIED). T8-c bu satırı geri alarak "PUBLIC açık" durumunu da sınar.
- Kapı: `current_setting('port') = '55438' AND current_setting('cluster_name') = 'hgs2iso18'` değilse dur. Önceki harness `data_directory LIKE '%scratchpad%'` kapısı kullanmıştı [K].

**`hgs2_perftest_db`** (tablolar `hgs2_perftest` sahipliğinde; `SET ROLE hgs2_perftest` ile oluşturulur) [P]:
- `admins`, `devices`, `users` (`parmak_izi_sablonu oid`), `logs`.
- 4 PK, 3 UNIQUE, 2 FK, 4 identity.
- DDL `kanit/harness/fixture_db.sql` L8–16'dan alınır [K].
- Önceki fixture'daki ek GRANT, RLS, LO, extension ve default privilege satırları **eklenmez**. T1 tertemiz bir "stok" durumu ölçer.

**Golden kopyalar** [P]:
- `golden-base`: fixture sonrası, `hgs2_audit` **yokken**.
- `golden-role`: RC-01 + RC-03 sonrası, `hgs2_audit` varken.
- T1–T10 `golden-role`'den başlar. RC testleri `golden-base`'den başlar.

---

## 5. Windows PowerShell komutları

> **NOT EXECUTED.** Aşağıdakiler uygulanabilir taslaktır.
> - Windows PowerShell 5.1, **yönetici olmayan** (elevated olmayan) bir oturum içindir.
> - İlk kullanımda adım adım ve ayrı onayla çalıştırılmalıdır.
> - Her adım kendi kapısını içerir.
> - Bu plan hazırlanırken hiçbiri çalıştırılmadı.

### 5.1 Sabitler, koruma kapıları ve canlı servis anlık görüntüsü

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
```

### 5.2 Ortam yalıtımı ve dizinler

```powershell
foreach ($v in 'PGHOST','PGHOSTADDR','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','PGPASSFILE','PGSERVICE',
               'PGSERVICEFILE','PGSYSCONFDIR','PGOPTIONS','PGSSLMODE','PGSSLROOTCERT','PGAPPNAME',
               'PGCLIENTENCODING','PGDATA','PSQLRC','PGCHANNELBINDING','PGTARGETSESSIONATTRS') {
    Remove-Item -LiteralPath "Env:$v" -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $Root, (Split-Path $LogFile), $Certs, $Cfg, $Evidence | Out-Null
# Test kokunu yalnizca gecerli kullaniciya ac
& icacls $Root /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(OI)(CI)F" | Out-Null
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
```

### 5.3 initdb (ayrı data directory, SCRAM, parola dosyası anında silinir)

```powershell
$SuperPw = New-TestSecret
$PwFile  = Join-Path $Cfg 'initdb.pw'
[IO.File]::WriteAllText($PwFile, $SuperPw)          # BOM ve satir sonu yok
& "$PgBin\initdb.exe" -D $Data -U postgres --pwfile=$PwFile --auth-host=scram-sha-256 --auth-local=scram-sha-256 -E UTF8 --locale=C
$rc = $LASTEXITCODE
Remove-Item -LiteralPath $PwFile -Force
Assert-Guard ($rc -eq 0) "initdb cikis $rc"
Add-TestPgpass 'postgres' $SuperPw
```

### 5.4 Sentetik TLS sertifikaları (IPv4 ve IPv6 SAN)

```powershell
$ext = Join-Path $Certs 'server_ext.cnf'
Set-Content -LiteralPath $ext -Encoding ASCII -Value @(
  'subjectAltName=DNS:hgs2-test.local,IP:127.0.0.1,IP:::1',
  'basicConstraints=CA:FALSE',
  'keyUsage=digitalSignature,keyEncipherment',
  'extendedKeyUsage=serverAuth')
& $OpenSsl req -x509 -newkey rsa:3072 -nodes -days 7 -subj '/CN=hgs2-iso-test-CA' -keyout "$Certs\ca.key" -out "$Certs\ca.crt" -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
& $OpenSsl req -newkey rsa:3072 -nodes -subj '/CN=hgs2-test.local' -keyout "$Certs\server.key" -out "$Certs\server.csr"
& $OpenSsl x509 -req -in "$Certs\server.csr" -CA "$Certs\ca.crt" -CAkey "$Certs\ca.key" -CAcreateserial -days 7 -extfile $ext -out "$Certs\server.crt"
# T10 negatif testi icin ayri (sahte) CA
& $OpenSsl req -x509 -newkey rsa:3072 -nodes -days 7 -subj '/CN=hgs2-iso-ROGUE-CA' -keyout "$Certs\rogue.key" -out "$Certs\rogue.crt"
```

Notlar:
- `IP:::1` SAN yazımı ve libpq'nun `host=::1` + `verify-full` ile IP SAN eşleştirmesi bu projede denenmedi [S].
- Önceki aşamanın SAN'ı yalnızca `DNS:hgs2-test.local,IP:127.0.0.1` idi [K] (`kanit/certs-public/ext.cnf`).

### 5.5 postgresql.conf ekleri

```powershell
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
```

- `%e`, sunucu günlüğüne SQLSTATE yazar. 28000 (pg_hba) ile 42501 (ACL) ayrımı günlükten de doğrulanır [S].
- PG 18'de `log_connections` liste biçimine genişletildi; `on` değerinin kabul edildiği varsayılmamalı, ilk çalıştırmada günlükten doğrulanmalı [S].

### 5.6 pg_hba varyant dosyaları ve başlatma

```powershell
$Hba = @{}
$Hba['A'] = @(   # TLS istege bagli (AUDIT_ROLE_PRIVILEGE_MATRIX §10.1)
 'host    hgs2_perftest_db  hgs2_audit  127.0.0.1/32  scram-sha-256',
 'host    hgs2_perftest_db  hgs2_audit  ::1/128       scram-sha-256',
 'host    all               hgs2_audit  all           reject',
 'host    replication       hgs2_audit  all           reject',
 'local   all               hgs2_audit                reject',
 'local   replication       hgs2_audit                reject',
 'host    all               all         127.0.0.1/32  scram-sha-256',
 'host    all               all         ::1/128       scram-sha-256')
# Parantezler zorunlu: PowerShell'de virgul operatoru -replace'den once baglanir
$Hba['B'] = @(($Hba['A'][0] -replace '^host ', 'hostssl'), ($Hba['A'][1] -replace '^host ', 'hostssl')) + $Hba['A'][2..7]   # TLS zorunlu
$Hba['V4'] = @($Hba['A'][0]) + $Hba['A'][2..7]                       # yalnizca IPv4 izinli
$Hba['V6'] = @($Hba['A'][1]) + $Hba['A'][2..7]                       # yalnizca IPv6 izinli
$Hba['OPEN'] = @('host all hgs2_audit 127.0.0.1/32 scram-sha-256') + $Hba['A'][6..7]   # T8-b: ACL katmanini ayri sinamak icin
$Hba['MISORDER'] = $Hba['A'][6..7] + $Hba['A'][0..5]                 # T8-e: bilincli yanlis siralama (negatif kontrol)

function Set-TestHba([string]$Variant) {
    $target = Join-Path $Data 'pg_hba.conf'; Assert-UnderRoot $target
    Set-Content -LiteralPath $target -Encoding ASCII -Value (@("# HGS2 iso test - variant $Variant") + $Hba[$Variant])
}
function Start-TestCluster { Assert-UnderRoot $Data; & "$PgBin\pg_ctl.exe" -D $Data -l $LogFile -w -t 60 start; Assert-Guard ($LASTEXITCODE -eq 0) 'pg_ctl start'; Assert-LiveUnchanged }
function Stop-TestCluster  { Assert-UnderRoot $Data; & "$PgBin\pg_ctl.exe" -D $Data -m fast -w stop;  Assert-Guard ($LASTEXITCODE -eq 0) 'pg_ctl stop';  Assert-LiveUnchanged }
function Sync-TestHba([string]$Variant) { Set-TestHba $Variant; Assert-UnderRoot $Data; & "$PgBin\pg_ctl.exe" -D $Data reload; Assert-Guard ($LASTEXITCODE -eq 0) 'pg_ctl reload' }

Set-TestHba 'A'
Start-TestCluster
# Ayri surec kaniti: komut satirinda test data directory gecen postgres.exe var, canli servis PID'i ayni
Assert-Guard (@(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count -ge 1) 'test postmaster bulunamadi'
```

### 5.7 Korumalı psql ve denetim çalıştırıcısı

```powershell
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
# Sistem kimligi: bagimsiz kanal (pg_controldata), gercek prosedurun aynasi
$SysId = ((& "$PgBin\pg_controldata.exe" -D $Data) | Select-String 'Database system identifier:\s+(\d+)').Matches[0].Groups[1].Value

function Invoke-Audit([string]$Id, [string]$HostArg, [string]$ServerAddr, [string]$SslPart, [string[]]$Extra) {
    $conn = "host=$HostArg port=$TestPort dbname=hgs2_perftest_db user=hgs2_audit $SslPart".Trim()
    $argv = @('-v', "expected_host=$HostArg", '-v', "expected_port=$TestPort", '-v', "expected_server_addr=$ServerAddr",
              '-v', "expected_server_port=$TestPort", '-v', "expected_system_identifier=$SysId", '-f', $AuditSql) + $Extra
    $rc = Invoke-TestPsql $Id $conn $argv
    $d = Join-Path $Evidence $Id
    & py -3.13 -I $Validator --exit-code $rc --stdout "$d\stdout.txt" --stderr "$d\stderr.txt" | Set-Content -LiteralPath "$d\verdict.txt" -Encoding UTF8
    return $rc
}
```

Notlar:
- Doğrulayıcı çağrısı önceki harness ile aynıdır [K] (`run3.sh`: `py -3.13 -I … --exit-code --stdout --stderr`).
- `Start-Process -ArgumentList` tırnaklamasının psql'e doğru argüman ilettiği ilk kuru çalıştırmada `args.txt` ile doğrulanmalıdır [P].
- Test kökü `C:\Users\Ceng Zeki\…` altında olduğu için yollar boşluk içerir [D]. Bağlantı dizesindeki dosya yolları libpq kuralına göre tek tırnakla verilmelidir [S]. Örnek (T10-c): `$SslPart = "hostaddr=127.0.0.1 sslmode=verify-full sslrootcert='$((Join-Path $Certs 'ca.crt') -replace '\\','/')'"`.

### 5.8 Golden kopya ve geri yükleme

```powershell
function Save-Golden([string]$Name) {
    $g = Join-Path $Root $Name; Assert-UnderRoot $g
    Stop-TestCluster
    & robocopy $Data $g /MIR /COPY:DAT /R:0 /W:0 /NFL /NDL /NJH /NJS | Out-Null
    Assert-Guard ($LASTEXITCODE -lt 8) "robocopy $LASTEXITCODE"
    Start-TestCluster
}
function Restore-Golden([string]$Name) {
    $g = Join-Path $Root $Name; Assert-UnderRoot $g; Assert-UnderRoot $Data   # /MIR yikicidir: hedef her zaman test data dizini
    Stop-TestCluster
    & robocopy $g $Data /MIR /COPY:DAT /R:0 /W:0 /NFL /NDL /NJH /NJS | Out-Null
    Assert-Guard ($LASTEXITCODE -lt 8) "robocopy $LASTEXITCODE"
    Start-TestCluster
}
```

Golden kopya aynı `system_identifier`'ı taşır. Bu yüzden `$SysId` tüm senaryolarda geçerli kalır [S].

---

## 6. pg_hba.conf tasarımı

### 6.1 Kural tablosu (test kümesi, varyant B: TLS zorunlu)

| Satır | TYPE | DATABASE | USER | ADDRESS | METHOD | Amaç |
|---|---|---|---|---|---|---|
| R1 | `hostssl` | `hgs2_perftest_db` | `hgs2_audit` | `127.0.0.1/32` | `scram-sha-256` | IPv4 loopback, yalnızca TLS |
| R2 | `hostssl` | `hgs2_perftest_db` | `hgs2_audit` | `::1/128` | `scram-sha-256` | IPv6 loopback, yalnızca TLS |
| R3 | `host` | `all` | `hgs2_audit` | `all` | `reject` | Diğer her DB/adres; TLS'siz bağlantılar |
| R4 | `host` | `replication` | `hgs2_audit` | `all` | `reject` | `all`, replikasyonla eşleşmez [S] |
| R5 | `local` | `all` | `hgs2_audit` | — | `reject` | Unix soketi (Windows'ta kapalı) |
| R6 | `local` | `replication` | `hgs2_audit` | — | `reject` | Aynı |
| R7 | `host` | `all` | `all` | `127.0.0.1/32` | `scram-sha-256` | Diğer kullanıcılar (gerçek ortam beyanının aynası) |
| R8 | `host` | `all` | `all` | `::1/128` | `scram-sha-256` | Aynı (IPv6) |

**Varyant A:** R1–R2'de `hostssl` yerine `host` yazılır (TLS isteğe bağlı). Diğer satırlar aynıdır.

**İlk eşleşme kuralı** [S]:
- PostgreSQL satırları yukarıdan aşağıya okur. TYPE + DATABASE + USER + ADDRESS eşleşen **ilk** satırın yöntemi uygulanır. Sonraki satırlara bakılmaz.
- `reject` parola sormadan reddeder. `scram-sha-256` başarısız olursa alttaki satırlara **geçilmez**.
- Sonuç: `hgs2_audit` bloğu, `all` kullanıcı içeren her satırın **üstünde** olmalıdır.
- R7/R8 `hgs2_audit` için hiçbir zaman değerlendirilmez, çünkü R3 adres `all` ile her TCP bağlantısını yakalar.

### 6.2 Beklenen bağlantı sonuçları

| # | Kullanıcı | DB | Adres | TLS | Varyant A: ilk eşleşme → sonuç | Varyant B: ilk eşleşme → sonuç | Etiket |
|---|---|---|---|---|---|---|---|
| C1 | `hgs2_audit` | `hgs2_perftest_db` | 127.0.0.1 | evet | R1 → SCRAM → **kabul** | R1 → **kabul** | [S] |
| C2 | `hgs2_audit` | `hgs2_perftest_db` | ::1 | evet | R2 → **kabul** | R2 → **kabul** | [S] |
| C3 | `hgs2_audit` | `hgs2_perftest_db` | 127.0.0.1 | hayır | R1 → **kabul** (betik loopback'i TLS'siz kabul eder, P6b) | R1/R2 eşleşmez (`hostssl`) → R3 → **red** ("no encryption") | [S] [D] |
| C4 | `hgs2_audit` | `hgs2_perftest_db` | ::1 | hayır | R2 → **kabul** | R3 → **red** | [S] |
| C5 | `hgs2_audit` | `hibrit_giris_db` | 127.0.0.1 / ::1 | evet/hayır | R3 → **red** (28000) | R3 → **red** | [S] |
| C6 | `hgs2_audit` | `postgres` / `template1` / `other_db` | herhangi | herhangi | R3 → **red** | R3 → **red** | [S] |
| C7 | `hgs2_audit` | replikasyon bağlantısı | herhangi | herhangi | R4 → **red** (ayrıca `NOREPLICATION`) | R4 → **red** | [S] |
| C8 | `hgs2_audit` | `hgs2_perftest_db` | 127.0.0.1 | evet | Yanlış parola: R1 → **28P01**, alt satıra geçilmez | Aynı | [S] |
| C9 | `hgs2_audit` | `hgs2_perftest_db` | 127.0.0.1 | evet | Parolasız rol (`rolpassword` NULL) → **28P01** | Aynı | [S] |
| C10 | `hgs2_perftest` | `hgs2_perftest_db` | 127.0.0.1 | herhangi | R7 → **kabul** | R7 → **kabul** | [S] |
| C11 | `hgs2_perftest` | `hibrit_giris_db` | 127.0.0.1 | herhangi | R7 → kimlik doğrulama başarılı → ACL → **42501** `permission denied for database` (PUBLIC CONNECT kaldırılmışsa). `PerfTestSafetyGuard` beklentisi | Aynı | [S] [D] |
| C12 | `postgres` | `hibrit_giris_db` | ::1 (`localhost`) | herhangi | R8 → **kabul** (ana uygulamanın aynası) | Aynı | [S] [D] |
| C13 | `hgs2_audit` | herhangi | loopback dışı | herhangi | R3 → **red**. Test kümesi loopback dışını dinlemediği için **test edilemez** | Aynı | [S] |

Ek bilgiler:
- **`sslmode=prefer`** (libpq varsayılanı): Önce TLS denenir.
  - B'de C3 senaryosunda istemci TLS ile R1'e eşleşir ve kabul edilir.
  - `sslmode=disable` ile R3'e düşer.
  - Reddedilen TLS denemesinden sonra libpq TLS'siz yeniden dener. İki hata mesajı görülebilir [S].
- **Sunucuda `ssl = off`:** Varyant B'de R1/R2 hiçbir zaman eşleşmez. PostgreSQL `hostssl` satırı için uyarı verebilir. `hgs2_audit` R3'e düşer ve tamamen kilitlenir. Bu, **fail-closed** davranıştır [S].
- **Varyant seçimi (gerçek küme):**
  - Gerçek sunucunun `ssl` ayarı bilinmiyor (okunmadı).
  - B, `channel_binding=require` imkânı verir. Ancak SCRAM + channel binding hiç test edilmedi [K: KNOWN_LIMITATIONS 20].
  - → **Karar K-3** (§11).

### 6.3 Yanlış sıralamanın etkisi (negatif kontrol, T8-e)

Varyant `MISORDER`'da R7/R8 üstte yer alır. Bu durumda:
- C5'te `hgs2_audit` → `hibrit_giris_db` R7 ile eşleşir ve SCRAM başarılı olur.
- PUBLIC CONNECT kaldırılmışsa 42501 ile reddedilir. PUBLIC açıksa **bağlantı kurulur**: izolasyon yoktur.

Bu test, "blok en üstte olmalı" kuralının neden zorunlu olduğunu kanıtlamak içindir [P].

### 6.4 Gerçek küme için öneri

- Gerçek dosyaya yalnızca R1–R6 eklenir; varyant A veya B karara göre seçilir. Yer: ilk etkin satırın üstü.
- Mevcut satırlar **değiştirilmez**.
- Yedekleme, `pg_hba_file_rules` ile ön doğrulama, `pg_reload_conf()` ve geri alma: `AUDIT_ROLE_PRIVILEGE_MATRIX.md` §10.3 [P].

### 6.5 `PerfTestSafetyGuard` uyumluluk kısıtı [D]

- `PerfTestSafetyGuard.requireNoProductionAccess` yalnızca SQLState **42501**'i kabul eder (L238).
- pg_hba reddi **28000** üretir. Kimlik doğrulama hatası 28P01, zaman aşımı da farklı bir hata üretir.
- Bu yüzden:
  - `hgs2_perftest` için `hibrit_giris_db`'ye **hiçbir** pg_hba `reject` kuralı eklenmemelidir.
  - Önerilen blok yalnızca `hgs2_audit` adıyla eşleştiği için bu kısıtı bozmaz [S].
  - T8-d bunu test kümesinde doğrular.
- Gerçek kümede `hgs2_perftest`'in bugün 42501 aldığı bir **beyandır**; çalıştırma kanıtı bulunamadı → **UNVERIFIED**.

---

## 7. Test senaryoları

Ortak kurallar [P]:
- Her senaryo `golden-role`'den başlar (`Restore-Golden 'golden-role'`). Varyant belirtilmemişse pg_hba **A**'dır.
- "Denetim" = `Invoke-Audit`. Varsayılan: `host=127.0.0.1`, `expected_server_addr=127.0.0.1`, `sslmode=require`.
- "Rol doğrulaması" = `AUDIT_ROLE_PRIVILEGE_MATRIX.md` §11'deki §6–§9 sorguları ve §10 `all_ok` hesabı. Salt okunur çerçevede çalıştırılır; §1–§5 ve COMMIT olmadan.
- Kontrol sorguları test süper kullanıcısıyla, `hgs2_perftest_db` içinde çalışır. Çerçeve: `BEGIN READ ONLY; SET LOCAL search_path = pg_catalog, pg_temp; … ROLLBACK;`.
- Her senaryodan sonra: `Assert-LiveUnchanged` ve sunucu günlüğünden ilgili SQLSTATE satırları kanıta kopyalanır.

### T1 — Minimum yetkili audit rolüyle başarılı denetim

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role`: RC-01 ve RC-03 geçti; hiç GRANT üretilmedi |
| Değişiklik | Yok |
| Adımlar | (a) Denetim, `sslmode=require`. (b) Rol doğrulaması. (c) Ek negatif oturum kontrolleri: `SET ROLE hgs2_perftest;` → hata; `SELECT 1 FROM public.users LIMIT 1;` → hata; `CREATE TABLE public.x(i int);` → hata |
| Beklenen | (a) çıkış 0, `HGS2_AUDIT_PREFLIGHT_OK` ve `HGS2_AUDIT_COMPLETE` birer kez, `HGS2_AUDIT_WARNING` yok, stderr boş, validator **PASS**. P6b satırı `tasima= tcp-loopback`, `tls= t`. (b) `all_ok = t`. (c) Üçü de `permission denied` (42501) |
| Kontrol sorgusu | `SELECT has_database_privilege('hgs2_audit','hgs2_perftest_db','CONNECT'), has_schema_privilege('hgs2_audit','public','USAGE'), has_function_privilege('hgs2_audit','pg_catalog.pg_control_system()','EXECUTE'), (SELECT count(*) FROM pg_shdepend WHERE refobjid = 'hgs2_audit'::regrole) AS shdeps, (SELECT count(*) FROM pg_auth_members WHERE member = 'hgs2_audit'::regrole OR roleid = 'hgs2_audit'::regrole) AS memberships;` → `t, t, t, 0, 0` |
| Başarısızlık | Denetim PASS değil; herhangi bir WARNING; `shdeps > 0` (gereksiz GRANT); `memberships > 0`; (c)'den biri başarılı |
| Temizlik | `Restore-Golden 'golden-role'` |
| Etiket | Betik davranışı [K] (N1 eşdeğeri); SCRAM/TLS-zorunlu yol [P] |

### T2 — Audit rolünün `hgs2_perftest` rolüne üye yapılması

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role` |
| Değişiklik | T2-a: `GRANT hgs2_perftest TO hgs2_audit;` (PG 16+ varsayılanı: `INHERIT` = üyenin `rolinherit` değeri = FALSE, `SET` = TRUE). T2-b: `GRANT hgs2_perftest TO hgs2_audit WITH INHERIT FALSE, SET FALSE;` |
| Beklenen — betik | **PASS, uyarısız.** P8 (L731–740) üyeliği görür ama `hgs2_perftest` süper kullanıcı değildir ve 5 tehlikeli rolden biri değildir. Bölüm 2.x yalnızca `hgs2_perftest`'in üyeliklerini listeler |
| Beklenen — rol doğrulaması | **FAIL**: `no_member_of = f`, `no_effective_membership = f`, `not_member_perftest = f` |
| Beklenen — oturum | T2-a: `SET ROLE hgs2_perftest;` **başarılı** (sahip yetkilerine erişim yolu). T2-b: `SET ROLE` reddedilir, ama üyelik yine de doğrulamada FAIL verir |
| Kontrol sorgusu | `SELECT m.admin_option, m.inherit_option, m.set_option FROM pg_auth_members m WHERE m.member = 'hgs2_audit'::regrole AND m.roleid = 'hgs2_perftest'::regrole;` ve `SELECT pg_has_role('hgs2_audit','hgs2_perftest','MEMBER'), pg_has_role('hgs2_audit','hgs2_perftest','USAGE');` |
| Başarısızlık | Rol doğrulamasının `all_ok = t` vermesi (ihlal kaçtı). Betiğin PASS vermesi beklenen davranıştır; farklı çıkarsa statik analiz yanlıştır ve incelenir |
| Temizlik | `REVOKE hgs2_perftest FROM hgs2_audit;` → kontrol sorgusu 0 satır; ardından `Restore-Golden` |
| Etiket | Betik sonucu [D]; seçenek varsayılanları [S] |

### T3 — Audit rolüne kullanıcı tablosunda SELECT verilmesi

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role` |
| Değişiklik | T3-a: `GRANT SELECT ON public.users TO hgs2_audit;` (`SET ROLE hgs2_perftest` ile, sahip olarak. **R09b**: denetlenen tarafın kendi başına yapabileceği ihlal). T3-b: `GRANT SELECT ON public.logs TO PUBLIC;` |
| Beklenen — betik | **PASS, uyarısız.** 5.4 (L1078–1092) `users | … | hgs2_audit | … | SELECT` ya da `PUBLIC` satırını **raporlar**, durdurmaz |
| Beklenen — rol doğrulaması | **FAIL**: `user_rel_access_count ≥ 1`. T3-a'da ayrıca §8 `pg_shdepend 'a'` listesinde `table users` |
| Beklenen — oturum | `SELECT count(*) FROM public.users;` **başarılı** (ihlalin gerçek olduğunun kanıtı; tek satır sentetik) |
| Kontrol sorgusu | `SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND has_table_privilege('hgs2_audit', c.oid, 'SELECT');` |
| Başarısızlık | `all_ok = t` |
| Temizlik | `REVOKE SELECT ON public.users FROM hgs2_audit;` / `REVOKE SELECT ON public.logs FROM PUBLIC;` → kontrol sorgusu boş; `Restore-Golden` |
| Etiket | [D] [P] |

### T4 — Audit rolüne veritabanı sahipliği verilmesi

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role` |
| Değişiklik | T4-a: `CREATE DATABASE iso_owned_db OWNER hgs2_audit;` (`postgres` DB'sinden). T4-b: `ALTER DATABASE hgs2_perftest_db OWNER TO hgs2_audit;` |
| Beklenen — betik | **PASS, uyarısız.** T4-a'yı hiç görmez (3.1 yalnızca iki DB'yi listeler). T4-b'de 3.1 `owner = hgs2_audit` **raporlanır**. `hgs2_audit` örtük olarak `pg_database_owner` üyesidir ve dolayısıyla `public` CREATE yetkisi alır; P8 bunu tehlikeli saymaz |
| Beklenen — rol doğrulaması | **FAIL**: `no_owned_db = f`. T4-b'de ek olarak `no_schema_create = f` ve `no_effective_membership = f` (`pg_database_owner`) |
| Kontrol sorgusu | `SELECT datname FROM pg_database WHERE datdba = 'hgs2_audit'::regrole;` ve (T4-b, `hgs2_perftest_db` içinde) `SELECT pg_has_role('hgs2_audit','pg_database_owner','MEMBER'), has_schema_privilege('hgs2_audit','public','CREATE');` |
| Başarısızlık | `all_ok = t` |
| Temizlik | T4-a: `DROP DATABASE iso_owned_db;`. T4-b: `ALTER DATABASE hgs2_perftest_db OWNER TO hgs2_perftest;`. Ardından `SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = 'hgs2_perftest_db'` → `hgs2_perftest`; `Restore-Golden` |
| Etiket | Betik sonucu [D]; `pg_database_owner` örtük üyeliği [S] |

### T5 — Audit rolüne CREATE yetkisi verilmesi

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role` |
| Değişiklik | T5-a: `GRANT CREATE ON DATABASE hgs2_perftest_db TO hgs2_audit;`. T5-b: `GRANT CREATE ON SCHEMA public TO hgs2_audit;`. T5-c (PG ≤ 14 kökenli DB benzetimi): `GRANT CREATE ON SCHEMA public TO PUBLIC;` |
| Beklenen — betik | **PASS, uyarısız.** T5-a: 3.3 `hgs2_audit CREATE` satırını raporlar. T5-b/c: 5.1 `effective_acl` içinde görünür |
| Beklenen — rol doğrulaması | **FAIL**: T5-a `no_db_create = f`; T5-b/c `no_schema_create = f` |
| Beklenen — oturum | T5-b/c: `CREATE TABLE public.iso_probe(i int);` başarılı ve tablo `hgs2_audit` **sahipliğinde**. Ardından `pg_shdepend 'o'` > 0 |
| Kontrol sorgusu | `SELECT has_database_privilege('hgs2_audit','hgs2_perftest_db','CREATE'), has_schema_privilege('hgs2_audit','public','CREATE'), (SELECT count(*) FROM pg_shdepend WHERE refobjid = 'hgs2_audit'::regrole AND deptype = 'o');` |
| Başarısızlık | `all_ok = t` |
| Temizlik | `DROP TABLE IF EXISTS public.iso_probe;` → ilgili REVOKE'lar (T5-c'de `REVOKE CREATE ON SCHEMA public FROM PUBLIC`) → `nspacl` golden değeriyle aynı (`{pg_database_owner=UC/pg_database_owner,=U/pg_database_owner}`); `Restore-Golden` |
| Etiket | [D] [S] [P] |

### T6 — `pg_control_system` EXECUTE yetkisinin PUBLIC'ten kaldırılması

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role` (stok: `proacl` NULL) |
| Değişiklik | (`hgs2_perftest_db` içinde, süper kullanıcı) `REVOKE EXECUTE ON FUNCTION pg_catalog.pg_control_system() FROM PUBLIC;` |
| Beklenen | (1) Denetim: çıkış 3, `HGS2_AUDIT_ABORT: system_identifier_unverifiable` (stdout ve stderr), validator FAIL. (2) Rol doğrulaması kendi başına PASS verir (fazlalık yok). (3) `golden-base`'den başlayan RC-01 tekrarı: taslak §5.1 bu kez `GRANT EXECUTE … TO hgs2_audit` üretir; ardından denetim PASS. (4) Yan kontrol: aynı REVOKE yalnızca `postgres` DB'sinde yapılırsa denetim etkilenmez (ACL veritabanı başınadır) |
| Kontrol sorgusu | `SELECT proacl FROM pg_proc WHERE oid = 'pg_catalog.pg_control_system()'::regprocedure;` ve `SELECT has_function_privilege('public','pg_catalog.pg_control_system()','EXECUTE'), has_function_privilege('hgs2_audit','pg_catalog.pg_control_system()','EXECUTE');` |
| Başarısızlık | (1)'de PASS veya farklı ABORT; (3)'te GRANT'in PUBLIC'e verilmesi ya da üretilmemesi; (4)'te denetimin etkilenmesi |
| Temizlik | `REVOKE EXECUTE … FROM hgs2_audit; GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO PUBLIC;`. Not: `proacl` NULL'a değil, eşdeğer açık ACL'ye döner [S]. Bu yüzden asıl temizlik `Restore-Golden`'dır |
| Etiket | (1) [K] (A13, 4 sürüm); (3)(4) [S] [P] |

### T7 — `public` şeması USAGE yetkisinin PUBLIC'ten kaldırılması

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role` |
| Değişiklik | (`hgs2_perftest_db` içinde; `public` şemasının sahibi `pg_database_owner` = `hgs2_perftest` de yapabilir) `REVOKE USAGE ON SCHEMA public FROM PUBLIC;` |
| Beklenen | **İki olası sonuç; hangisi olduğu kaydedilir, önceden varsayılmaz** [S]. **(a)** 5.8'de `ERROR: permission denied for schema public` → çıkış 3, ABORT işaretçisi yok → validator FAIL (fail-closed). **(b)** `to_regclass` NULL döner → 5.8 boş sonuç → denetim **PASS** (sessiz eksik kontrol). Ardından `golden-base`'den RC-01 tekrarı: taslak §3, `GRANT USAGE ON SCHEMA public TO hgs2_audit` üretir → denetim PASS ve 5.8 satırı **dolu** |
| Kontrol sorgusu | `SELECT nspacl FROM pg_namespace WHERE nspname = 'public';` ve `SELECT has_schema_privilege('hgs2_audit','public','USAGE');`. Denetim stdout'unda 5.8 bölümünde `parmak_izi_sablonu | oid` satırının varlığı |
| Başarısızlık | (a) veya (b) dışında bir sonuç; 5.8'den **önce** bir hata (statik analiz yanlış). **(b) çıkarsa:** bulgu olarak raporlanır, çünkü betik `public` USAGE eksikliğinde 5.8'i sessizce atlar. Gerçek kümede `public` USAGE'ın etkin olduğu ön koşulu **zorunlu** hale gelir |
| Temizlik | `GRANT USAGE ON SCHEMA public TO PUBLIC;` (+ varsa `REVOKE … FROM hgs2_audit`) → `nspacl` golden değeriyle aynı; `Restore-Golden` |
| Etiket | Bağımlılık [D]; sonuç [S] |

### T8 — Audit rolünün `hibrit_giris_db` bağlantısının engellenmesi

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role`; `hibrit_giris_db` PUBLIC CONNECT kaldırılmış (fixture) |
| Değişiklik ve beklenen | **T8-a** (varyant A): `psql -d "host=127.0.0.1 port=55438 dbname=hibrit_giris_db user=hgs2_audit sslmode=disable" -c "select 1"` → çıkış 2, `pg_hba.conf rejects connection for host "127.0.0.1", user "hgs2_audit", database "hibrit_giris_db", no encryption`; günlükte `28000`. Aynısı `sslmode=require` ve `host=::1` ile.<br>**T8-b** (varyant OPEN, yalnızca ACL katmanı): aynı komut → `permission denied for database "hibrit_giris_db"` / `42501` (ikinci katman çalışıyor).<br>**T8-c** (varyant A, `GRANT CONNECT ON DATABASE hibrit_giris_db TO PUBLIC`): T8-a ile aynı red (pg_hba tek başına yeterli).<br>**T8-d** (varyant A): `hgs2_perftest` ile aynı komut → **42501** (28000 değil) → `PerfTestSafetyGuard` kısıtı korunuyor.<br>**T8-e** (varyant MISORDER + T8-c durumu): `hgs2_audit` bağlantısı **kurulur** (negatif kontrol; sıralama zorunluluğunun kanıtı). Ardından denetim çalıştırılırsa `production_database` ile durmalı [K: A02] |
| Kontrol sorgusu | `SELECT datname, has_database_privilege('hgs2_audit', oid, 'CONNECT') AS acl_connect FROM pg_database ORDER BY 1;` + matris §11 §9.2 `first_tcp_rule_method` + sunucu günlüğünde `%e` alanı |
| Başarısızlık | T8-a/c'de bağlantı kurulması; T8-a'da 28000 dışında bir kod; T8-d'de 42501 dışında bir kod; T8-e'de bağlantının **kurulamaması** (test düzeneği hatalı) |
| Temizlik | `Sync-TestHba 'A'`; T8-c/e için `REVOKE CONNECT ON DATABASE hibrit_giris_db FROM PUBLIC`; `Restore-Golden` |
| Etiket | [S] [P]; T8-e'nin betik kısmı [K] |

### T9 — IPv4 ve IPv6 üzerinden bağlantı kısıtlamalarının doğrulanması

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role`; küme `127.0.0.1,::1` dinliyor (`Get-NetTCPConnection -LocalPort 55438 -State Listen` iki satır) |
| Değişiklik ve beklenen | **T9-a** (A): `host=127.0.0.1` ve `host=::1` → ikisi de kabul. Tam denetim `host=::1`, `expected_host=::1`, `expected_server_addr=::1` → **PASS**. P6 `sunucu adres= ::1`; P6b `tasima= tcp-loopback`, `istemci_host_sinifi= loopback` (L609, L614). **İlk IPv6 denetimi.**<br>**T9-b** (V4): `::1` → red (R3); `127.0.0.1` → kabul.<br>**T9-c** (V6): `127.0.0.1` → red; `::1` → kabul.<br>**T9-d**: `host=localhost` → hangi adres ailesinin seçildiği günlükteki `host=` alanından kaydedilir (ana uygulama `localhost` kullanır). `expected_host=localhost` ile denetim PASS |
| Kontrol sorgusu | Oturum içinde `SELECT inet_client_addr(), inet_server_addr();` (kabul edilen bağlantılarda) + günlük `host=` alanı |
| Başarısızlık | Varyantın izin vermediği adres ailesinden bağlantının kabul edilmesi; T9-a'da IPv6 denetiminin PASS vermemesi (betiğin IPv6 sınıflamasında hata) |
| Temizlik | `Sync-TestHba 'A'`; `Restore-Golden` |
| Etiket | Betik sınıflaması [D]; IPv6 davranışı [S] |

### T10 — SSL zorunluluğunun doğrulanması

| Alan | İçerik |
|---|---|
| Ön koşul | `golden-role`; `ssl = on`; varyant **B** (`Sync-TestHba 'B'`) |
| Değişiklik ve beklenen | **T10-a**: `sslmode=disable` (127.0.0.1 ve ::1) → red, `… no encryption`, 28000.<br>**T10-b**: `sslmode=require` → kabul; denetim PASS, P6b `tls= t`, `tls_surum=` TLSv1.2/1.3.<br>**T10-c**: `host=hgs2-test.local hostaddr=127.0.0.1 sslmode=verify-full sslrootcert=<certs>\ca.crt` → kabul; denetim (`expected_host=hgs2-test.local`) PASS.<br>**T10-d**: aynı, `sslrootcert=<certs>\rogue.crt` → istemci reddi, psql çıkış 2 (`certificate verify failed`) [K: T4 eşdeğeri].<br>**T10-e**: `host=::1 sslmode=verify-full` → IP SAN `::1` eşleşmesi [S].<br>**T10-f**: `channel_binding=require` + SCRAM → kabul (**ilk test**; KNOWN_LIMITATIONS 20).<br>**T10-g**: varyant B + `ssl = off` (postgresql.conf, yeniden başlatma) → `hgs2_audit` her yoldan reddedilir (fail-closed); `hgs2_perftest` etkilenmez |
| Kontrol sorgusu | Oturum içinde `SELECT ssl, version, cipher FROM pg_stat_ssl WHERE pid = pg_backend_pid();` + `pg_hba_file_rules` `error` sütunu (T10-g'de `hostssl` uyarısı/hatası kaydedilir) |
| Başarısızlık | T10-a'da kabul; T10-b/c/f'de red; T10-d'de bağlantı kurulması; T10-g'de `hgs2_audit`'in bağlanabilmesi |
| Temizlik | `ssl = on` geri; `Sync-TestHba 'A'`; `Restore-Golden` |
| Etiket | [K] (T3–T5 TLS testleri, `trust` ile); `hostssl` + SCRAM + IPv6 [S] [P] |

---

## 8. Beklenen sonuçlar (özet)

| Senaryo | Betik (çıkış / işaretçi / validator) | Rol doğrulaması (`all_ok`) | Bağlantı | Testin geçme ölçütü | Kaynak |
|---|---|---|---|---|---|
| T1 | 0 / COMPLETE / **PASS** | t | C1 kabul | Hepsi beklendiği gibi | [K] [P] |
| T2 | 0 / COMPLETE / **PASS** (P8 boşluğu) | **f** | — | Doğrulama FAIL | [D] |
| T3 | 0 / COMPLETE / **PASS** (5.4 raporlar) | **f** | — | Doğrulama FAIL | [D] |
| T4 | 0 / COMPLETE / **PASS** | **f** | — | Doğrulama FAIL | [D] |
| T5 | 0 / COMPLETE / **PASS** (3.3/5.1 raporlar) | **f** | — | Doğrulama FAIL | [D] |
| T6 | 3 / `system_identifier_unverifiable` / FAIL → koşullu GRANT sonrası PASS | t | — | ABORT + taslağın doğru GRANT'i | [K] [S] |
| T7 | (a) 3 / işaretçisiz / FAIL **veya** (b) 0 / PASS (5.8 boş) → koşullu GRANT sonrası PASS | t | — | Sonuç kaydedildi; (b) ise bulgu | [S] |
| T8 | — (T8-e: `production_database`) | — | a,c: 28000 · b,d: 42501 · e: kabul | Tablo §7 T8 | [S] [K] |
| T9 | IPv6 denetimi PASS | — | Varyanta göre | Tablo §7 T9 | [S] [D] |
| T10 | TLS ile PASS | — | disable: red · require/verify-full: kabul · rogue CA: istemci reddi | Tablo §7 T10 | [S] [K] |

**Önemli yorum:** T2–T5'te betiğin PASS vermesi bir **hata değil, kanıtlanmak istenen boşluktur** [D]. Gerçek kümede her denetimden önce rol doğrulaması (§6–§9) çalıştırılmadan betiğin PASS sonucu, audit rolünün minimum yetkili olduğunu **göstermez**.

---

## 9. Temizleme ve geri dönüş planı

### 9.1 Senaryo düzeyi [P]

1. Senaryonun kendi geri alma SQL'i çalıştırılır (§7, her satırda). Kontrol sorgusu golden değerini doğrular.
2. Ardından **her durumda** `Restore-Golden` uygulanır. Geri alma SQL'i eksik ya da hatalı olsa bile sonraki senaryo temiz başlar.
3. `Assert-LiveUnchanged` çalıştırılır.

### 9.2 Kümenin tamamen kaldırılması [P]

```powershell
Stop-TestCluster
Assert-Guard (@(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count -eq 0) 'test postmaster hala calisiyor'
Assert-Guard ($null -eq (Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue)) "port $TestPort hala dinleniyor"
# Kanit arsivi (ayri onayla; yalnizca evidence ve log; anahtar ve pgpass KOPYALANMAZ)
#   Hedef oneri: <Base>\role-design\iso-runs\<RunId>\   (yeni klasor; mevcut dosyalara dokunmaz)
Remove-Item -LiteralPath $env:PGPASSFILE -Force
Assert-UnderRoot (Join-Path $Root 'data')
Remove-Item -LiteralPath $Root -Recurse -Force
foreach ($v in 'PGPASSFILE','PGSERVICEFILE','PGSYSCONFDIR','PSQLRC','PGCONNECT_TIMEOUT') { Remove-Item -LiteralPath "Env:$v" -ErrorAction SilentlyContinue }
Assert-LiveUnchanged
```

### 9.3 Acil durum [P]

| Durum | Eylem |
|---|---|
| `Assert-LiveUnchanged` başarısız (canlı servisin durumu, PID'i veya başlatma zamanı değişti) | **Dur.** Canlı servise müdahale etme (başlatma/durdurma yok). Test kümesini durdur. Zaman damgası ve kanıtla raporla. Test süreçleri canlı servisi etkileyemez, ama değişikliğin nedeni ayrıca araştırılır |
| `pg_ctl start` port çakışması | Başka port seç; 5432 asla |
| Test postmaster kapanmıyor | `pg_ctl -m immediate stop -D <test data>`. **Yalnızca** komut satırında test data dizini olan PID'ler sonlandırılır; servis PID'leri (4708 / 6164 / alt süreçler) asla |
| `robocopy /MIR` hedef doğrulaması başarısız | `Assert-UnderRoot` bunu engeller; kapı devre dışı bırakılmaz |

### 9.4 Gerçek küme için geri dönüş (yalnızca bilgi; bu planda uygulanmaz)

- pg_hba: yedek dosyayı geri koy → `pg_reload_conf()` (`AUDIT_ROLE_PRIVILEGE_MATRIX.md` §10.3).
- Rol: koşullu GRANT'ler `pg_shdepend 'a'` listesinden bulunup REVOKE edilir → `DROP ROLE hgs2_audit`. Rol nesne sahibi olmadığı için `REASSIGN OWNED` gerekmez [S].

---

## 10. Gerçek kümeye geçiş ön koşulları

| # | Ön koşul | Kanıt biçimi | Etiket |
|---|---|---|---|
| P1 | T1–T10 ve RC-01…05'in bu plandaki beklentiyle eşleşmesi; T7 sonucunun (a/b) kayda geçmesi | `evidence\` + `SUMMARY` | [P] |
| P2 | T7 (b) çıkarsa: gerçek kümede `public` USAGE'ın `hgs2_audit` için etkin olduğu **zorunlu ön kontrol** olarak yazılı hale getirilmeli | Karar kaydı | [P] |
| P3 | `AUDIT_ROLE_PRIVILEGE_MATRIX.md` §13 T0 salt okunur keşfi: sürüm, `datacl`, `public` ACL'si, `pg_control_system` `proacl`, PUBLIC tablo/LO/default ACL, `login` event trigger, mevcut `pg_hba_file_rules` | Ayrı onaylı salt okunur oturum | [P] |
| P4 | Gerçek sunucunun `ssl` ayarı ve sertifika durumu → pg_hba varyant kararı (K-3) | T0 | [P] |
| P5 | `hgs2_perftest`'in `hibrit_giris_db` için bugün **42501** aldığının doğrulanması. Değişiklikten sonra da aynı kalmalı (`PerfTestSafetyGuard`) | Değişiklik öncesi/sonrası psql denemesi | [D] → test |
| P6 | Ana uygulama (`postgres`, `localhost`) bağlantısının değişiklikten sonra çalıştığının doğrulanması | Uygulama sağlık kontrolü | [P] |
| P7 | pg_hba dosyasının yedeği; `pg_hba_file_rules` ile yeniden yükleme öncesi hatasızlık; yalnızca 6 satır eklenmiş olması | Fark çıktısı | [P] |
| P8 | Rol oluşturmanın ayrı yönetici onayı: onaylı taslak kopyasının SHA-256'sı, `change_ref`, süper kullanıcı oturumu, `psql -X` | Onay kaydı | [P] |
| P9 | Parola süreci (§3.3) ve `VALID UNTIL` / `NOLOGIN` kararı | Karar kaydı | [P] |
| P10 | `expected_system_identifier`'ın `pg_controldata` ile yetkili işletim sistemi hesabından bağımsız alınması (FINAL_DELIVERY §5.2). Bu, gerçek data directory'nin okunmasıdır; ayrı onay gerekir | Onay kaydı | [P] |
| P11 | Uygulama sırası: pg_hba → reload → rol (parolasız) → doğrulama → `\password` → negatif bağlantılar (C5–C7) → denetim | Çalıştırma kaydı | [P] |
| P12 | Her denetim çalıştırmasından önce rol doğrulaması (§6–§9); `pg_shdepend 'a'` listesinde yeni satır yok | Önceki çalıştırmayla fark | [P] |

---

## 11. Bilinen riskler ve açık kararlar

### 11.1 Riskler

| # | Risk | Durum | Etiket |
|---|---|---|---|
| R-N1 | Betiğin P8 kontrolü üyelik, sahiplik, CREATE ve tablo yetkisi ihlallerinde PASS verir. Gerçek denetimde betik dışı rol doğrulaması atlanırsa fazla yetkili audit rolü fark edilmez | Tasarım boşluğu; T2–T5 ile kanıtlanacak | [D] |
| R-N2 | Ana uygulama `hibrit_giris_db`'ye süper kullanıcı `postgres` ile bağlanıyor. Audit rolü kapsamı dışında; ayrı güvenlik bulgusu | Raporlandı | [D] |
| R-N3 | `PerfTestSafetyGuard` yalnızca 42501'i kabul eder. `hgs2_perftest`'i etkileyen bir pg_hba değişikliği perftest uygulamasını başlatılamaz hale getirir | Kısıt; T8-d | [D] |
| R-N4 | `to_regclass` ile `public` USAGE eksikliği, betiği sessizce eksik çalıştırabilir (T7-b olasılığı) | Belirsiz | [S] |
| R-N5 | IPv6, SCRAM, `hostssl` ve channel binding hiç test edilmedi | T9, T10, T1 | [K] |
| R-N6 | Test kümesi bootstrap süper kullanıcısının adı `postgres`; yanlışlıkla 5432'ye bağlanma riski | Port kapsamlı pgpass, `Assert-TestConn`, ortam temizliği ile azaltıldı | [P] |
| R-N7 | `Start-Process` argüman tırnaklaması (PS 5.1) | İlk kuru çalıştırmada `args.txt` ile doğrulanmalı | [P] |
| R-N8 | Windows Defender / dışlanmış port aralıkları (`netsh int ipv4 show excludedportrange protocol=tcp`) 55438'i engelleyebilir | Başlatma öncesi kontrol | [P] |
| R-N9 | Loopback dışı adresler (C13) test kümesinde sınanamaz; test kümesi bilerek ağa açılmaz | Kabul; R3 `all` adresiyle kapsar | [S] |
| R-N10 | Gerçek ortam beyanları (sahiplik, CONNECT durumu, SCRAM, `ssl`) bu klasörlerde kanıtlanmadı | UNVERIFIED; P3–P5 | — |
| R-N11 | `pg_signal_autovacuum_worker` ve PG 18 `log_connections` biçimi gibi sürüm ayrıntıları doğrulanmadı | İlk çalıştırmada | [S] |
| R-N12 | Rol oluşturma sırasında `\password`'ün gönderdiği SCRAM özeti `log_statement` ile günlüğe düşebilir | `SET log_statement = 'none'`; RC-03 | [S] [P] |

### 11.2 Açık kararlar

| # | Karar | Seçenekler | Öneri |
|---|---|---|---|
| K-1 | Plan konumu | `hgs2-lab-artifacts\…\role-design\` (bu belge) / HGS2 Git deposu | Lab artifacts (uygulama deposu kirlenmez). Değiştirilecekse taşıma ayrı adımdır |
| K-2 | Test kümesi bootstrap süper kullanıcı adı | `postgres` (gerçek adları yansıtır; taslak `pg_has_role(…,'postgres',…)` içerir) / `pgadmin` (önceki harness) | `postgres` + §5 kapıları |
| K-3 | Gerçek pg_hba varyantı | A (TLS isteğe bağlı) / B (TLS zorunlu) | Gerçek `ssl` durumu ve T10 sonucuna göre; SSL hazırsa B |
| K-4 | `CONNECTION LIMIT` | 2 / 1 | 2 (`AUDIT_ROLE_PRIVILEGE_MATRIX.md` §8.2) |
| K-5 | Süre | `VALID UNTIL` / denetim dışında `NOLOGIN` / ikisi | İkisi |
| K-6 | Operatör parola teslimi | Etkileşimli istem / DPAPI + anlık pgpass | Etkileşimli; otomasyon gerekiyorsa DPAPI |
| K-7 | T7 (b) çıkarsa | Ön koşul ekle / betik değişikliği (yeni sürüm, ayrı aşama) | Önce ön koşul; betik değişikliği bu planın kapsamı dışında |
| K-8 | Ana uygulamanın `postgres` ile bağlanması (R-N2) | Kapsam dışı / ayrı iş | Ayrı iş olarak kayıt |
| K-9 | `hgs2_perftest_db` PUBLIC TEMPORARY ve `public` PUBLIC CREATE (PG ≤ 14 kökenli ise) | `AUDIT_ROLE_PRIVILEGE_MATRIX.md` R10/R11 | Değişmedi |

---

## Ek A. İncelenen dosyalar

| Dosya | Durum |
|---|---|
| `…\role-design\AUDIT_ROLE_PRIVILEGE_MATRIX.md` | Bu oturumda yazılmıştı; içerik bağlamda incelendi (bağımsız inceleme notları §2.5) |
| `…\asama3-final\MINIMUM_PRIVILEGE_ANALYSIS.md` | Tamamı okundu |
| `…\asama3-final\postgresql_readonly_audit_v2.sql` | Tamamı okundu (1–1630); satır referansları grep ile yeniden üretildi |
| `…\asama3-final\FINAL_DELIVERY.md` | §1–6, §8–9 |
| `…\asama3-final\FINAL_SECURITY_AUDIT.md` | §1–7 |
| `…\asama3-final\KNOWN_LIMITATIONS.md` | Tamamı |
| `…\asama3-final\kanit\harness\{env.sh, conf.sh, run3.sh, fixture_db.sql, fixture_global.sql, fixture_harden.sql, suite3.sh}` | İlgili satırlar |
| `…\asama3-final\kanit\certs-public\ext.cnf`, `kanit\env\edb-binary-zips.sha256` | Tamamı |
| `…\asama3-final\tools\validate_audit_result.py` | Argümanlar ve kurallar |
| `…\ASAMA2_RAPORU.md` | İlgili satırlar (L167, L300) |
| `hgs2\…\application.properties`, `application-perftest.properties` | Parola satırları hariç |
| `hgs2\…\Config\PerfTestSafetyGuard.java` | L40–79, L215–264 |
| `hgs2-lab-artifacts\README.md` | Anahtar sözcük taraması |

## Ek B. Bütünlük kontrolleri

Bu belge yazıldıktan sonra hesaplandı.

| Kontrol | Başlangıç | Bitiş | Sonuç |
|---|---|---|---|
| Nihai SQL SHA-256 | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` | Aynı |
| `hgs2-lab-artifacts` tüm dosyalar (5187) | kaydedildi | 5187 + 1 | Tek fark: bu belge |
| `sha256sum -c FINAL_SHA256SUMS.txt` | 3114 OK / 0 FAILED | 3114 OK / 0 FAILED | Değişmedi |
| HGS2 deposu, `.git` hariç (95 dosya) | kaydedildi | kaydedildi | Birebir aynı |
| HGS2 `HEAD` | `ad255a46…` | `ad255a46…` | Aynı |
| HGS2 `.git/index` SHA-256 | `b8508bd4…0e68ca` | aynı | Aynı |
| HGS2 `git status` (önceden var olan 1 değişik + 5 izlenmeyen giriş; bu çalışmaya ait değil) | kaydedildi | `GIT_OPTIONAL_LOCKS=0` ile | Aynı |
| `postgresql-x64-18` servisi (WMI, salt okunur) | Running, PID 4708, oluşturma 2026-10-30T16:29:54.8155590+03:00; postmaster PID 6164, 16:29:55.2627330 | aynı | Değişmedi (yeniden başlatılmadı) |
| Servis `PathName` / data directory | `-D "C:\Program Files\PostgreSQL\18\data"` | aynı | Data directory'ye erişilmedi |
| Test kökü `%LOCALAPPDATA%\hgs2-iso` / port 55438 | yok / dinlenmiyor | yok / dinlenmiyor | Test kümesi oluşturulmadı |
