# MINIMUM_PRIVILEGE_ANALYSIS — HGS2 PostgreSQL Read-Only Audit V2

- Tarih: 2026-10-30 (+03:00)
- İncelenen dosya: `postgresql_readonly_audit_v2.sql`. SHA-256 `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`. Analizden önce ve sonra yeniden hesaplandı, değişmedi.
- Yardımcı belgeler: `FINAL_DELIVERY.md`, `FINAL_SECURITY_AUDIT.md`, `KNOWN_LIMITATIONS.md`
- Ek olarak salt okunur biçimde bakılan kanıtlar (değiştirilmedi):
  - `kanit/harness/fixture_global.sql`, `fixture_harden.sql`, `fixture_db.sql`, `fixture_v3_*.sql`, `evil_full_setup.sql`
  - `kanit/runs-final/N1-normal-pg{12,16,18}/stdout.txt`
  - `kanit/snapshots/before/pg18/schema.sql`
- Hedef sürüm: **PostgreSQL 18.6**

**Yöntem: yalnızca statik analiz.**
- PostgreSQL bağlantısı kurulmadı. SQL çalıştırılmadı.
- CREATE ROLE, GRANT, REVOKE ve ALTER ROLE yapılmadı. Git işlemi yapılmadı.
- Bu dosya dışında hiçbir dosya oluşturulmadı ya da değiştirilmedi.
- Bu belgedeki SQL örnekleri **ileride, ayrı onayla** çalıştırılmak üzere yazılmıştır. Hiçbiri çalıştırılmadı.

**Kanıt etiketleri:**

| Etiket | Anlamı |
|---|---|
| **[K]** | Proje kanıtıyla doğrulandı: test çıktısı, fixture veya anlık görüntü |
| **[D]** | Betiğin ya da teslim belgelerinin statik okuması |
| **[S]** | PostgreSQL semantiği veya belgeleri. **Bu projede test edilmedi**; gerçek hedefe geçmeden doğrulanmalı |

---

## 0. Yönetici özeti

1. **Betik yalnızca katalog okur. Kullanıcı tablosu verisine SELECT yetkisi gerekmez.** [D]
   - 21 katalog ilişkisi kullanılır: 19 katalog tablosu/görünümü, artı `pg_stat_ssl` ve `pg_user_mappings` görünümleri.
   - Yaklaşık 40 yerleşik fonksiyon kullanılır, tamamı `pg_catalog` içinde.
   - Kullanıcı nesnelerinin hiçbirinin satırı okunmaz.
2. **Testlerdeki denetim rolü `hgs2_auditor`, minimum yetkili rolün canlı örneğidir.** [K]
   - Hiçbir role üye değildi.
   - Nesne sahibi değildi.
   - Tablo yetkisi yoktu.
   - Yalnızca şunlara sahipti:
     - `LOGIN`,
     - PUBLIC varsayılanları,
     - `pg_control_system()` için açık EXECUTE (sertleştirilmiş fixture PUBLIC'ten geri aldığı için).
   - Dört sürümde PASS verdi (N1-normal).
3. **Betikle ilgili minimum yetkiler**, hepsi `hgs2_perftest_db` içinde:
   - `LOGIN`
   - `CONNECT`
   - `pg_catalog` şemasında `USAGE`
   - `public` şemasında `USAGE` (yalnızca 5.8'deki `to_regclass('public.users')` için) [S]
   - 21 katalog ilişkisinde `SELECT`
   - Kullanılan yerleşik fonksiyonlarda `EXECUTE`, `pg_control_system()` dahil

   Stok PG 18.6'da bunların **tamamı PUBLIC üzerinden** gelir. Doğru kurulmuş bir audit rolü için tipik durumda **hiçbir GRANT gerekmez**. Tek istisna: hedef sertleştirilmişse ve bu yetkilerden biri PUBLIC'ten geri alınmışsa, yalnızca o yetki koşullu olarak verilir.
4. **`hgs2_perftest` ile çalıştırmak minimum yetki ilkesini ihlal eder ve betik bunu yakalamaz.** [D]
   - P8 yalnızca şunlara bakar:
     - süper kullanıcı,
     - süper kullanıcı üyeliği,
     - CREATEROLE / BYPASSRLS / REPLICATION,
     - beş tehlikeli önceden tanımlı rol.
   - Şunlara **bakmaz**:
     - nesne sahipliği,
     - veritabanı sahipliği (dolayısıyla `pg_database_owner` üyeliği),
     - `hgs2_perftest` rolüne üyelik.

   Ayrı bir ön kontrol gerekir (Bölüm 12, Q3).
5. **CREATE çelişkisinin betik içinde somut ve kanıtlı bir açıklaması var, ama tek açıklama bu değil.** [K]
   - Betikte iki ayrı sütunun adı `perftest_create`:
     - 3.2: **veritabanı** düzeyi CREATE,
     - 5.1: **şema** düzeyi CREATE.
   - PG 12 test çıktısında aynı çalıştırmada 3.2 → `f`, 5.1 → `t` görünüyor.
   - Kullanıcı testlerinin hangi iki sorguyu çalıştırdığı bilinmeden kesin karar verilemez. Bölüm 11'de 8 hipotez ve bunları ayırt edecek salt okunur sorgu (K1, K2) var.

---

## 1. Betikte kullanılan kataloglar, görünümler ve fonksiyonlar

### 1.1 Katalog ilişkileri (21)

"Paylaşılan" sütunu şunu belirtir:
- **Evet:** Küme geneli katalog; `hgs2_perftest_db` üzerinden okunduğunda tüm kümeyi gösterir.
- **Hayır:** Yalnızca bağlı veritabanını gösterir.

| # | İlişki | Tür | Paylaşılan | Kullanıldığı bölümler (satır) |
|---|---|---|---|---|
| 1 | `pg_roles` | görünüm (`pg_authid` üzerinde; `rolpassword` maskeli) | Evet | P8 (723–737), 2.1–2.4 (793–863), 4 (993), 5.1, 5.4a, 5.4b, 5.5b, 5.11 (`me` CTE) |
| 2 | `pg_auth_members` | tablo | Evet | 2.3 (820–841) |
| 3 | `pg_database` | tablo | Evet | 3.1–3.4 (878–931), 4 (992) |
| 4 | `pg_db_role_setting` | tablo | Evet | 4 (991) |
| 5 | `pg_namespace` | tablo | Hayır | 5.1, 5.2, 5.5, 5.5b, 5.6, 5.7, 5.9, 5.10, 5.11, 5.12, 5.14, 5.15, 5.17 |
| 6 | `pg_class` | tablo | Hayır | 5.2–5.5b, 5.6, 5.7, 5.9, 5.12, 5.15, 5.17 |
| 7 | `pg_attribute` | tablo | Hayır | 5.4c, 5.5, 5.5b, 5.8, 5.9, 5.17 |
| 8 | `pg_depend` | tablo | Hayır | 5.5, 5.5b, 5.9, 5.11, 5.17 |
| 9 | `pg_constraint` | tablo | Hayır | 5.6, 5.7, 5.17 |
| 10 | `pg_type` | tablo | Hayır | 5.10 |
| 11 | `pg_proc` | tablo | Hayır | 5.11 |
| 12 | `pg_trigger` | tablo | Hayır | 5.12 |
| 13 | `pg_event_trigger` | tablo | Hayır | 5.13 |
| 14 | `pg_extension` | tablo | Hayır | 5.14 |
| 15 | `pg_foreign_server` | tablo | Hayır | 5.14b |
| 16 | `pg_foreign_data_wrapper` | tablo | Hayır | 5.14b (1502) |
| 17 | `pg_user_mappings` | görünüm (yalnızca `count(*)`; `umoptions` seçilmez) | Hayır | 5.14b (1499) |
| 18 | `pg_policy` | tablo | Hayır | 5.15 |
| 19 | `pg_default_acl` | tablo | Hayır | 5.4d |
| 20 | `pg_largeobject_metadata` | tablo (içerik tablosu `pg_largeobject` **kullanılmaz**) | Hayır | 5.16 |
| 21 | `pg_stat_ssl` | görünüm (`pg_stat_get_activity` üzerinde) | — (oturum bilgisi) | P6b (604) |

**Kullanılmayan, hassas ve PUBLIC'e kapalı kataloglar** [D]: `pg_authid`, `pg_shadow`, `pg_user_mapping` (taban tablo), `pg_largeobject`, `pg_statistic`, `pg_subscription`, `pg_hba_file_rules`.

Betik bunların hiçbirine dokunmaz. Bu yüzden ek yetki gerekmez.

**Belgeyle küçük tutarsızlıklar** [D]. Yalnızca not olarak; SQL dosyası değiştirilmedi:
- `FINAL_SECURITY_AUDIT.md` §2 "18 katalog" der. Betik 21 ilişki kullanır.
- Betiğin Bölüm 5 başlık yorumundaki PUBLIC okunabilir katalog listesinde (satır 1004–1008) `pg_foreign_data_wrapper` ve `pg_user_mappings` geçmez. `pg_stat_ssl` o listede yoktur ama P6b yorumunda (satır 577–578) ayrıca açıklanır.

  Yetki sonucu değişmez; bunlar da PUBLIC okunabilir.

### 1.2 Fonksiyonlar (tümü `pg_catalog`)

| Grup | Fonksiyonlar | Bölümler |
|---|---|---|
| Transaction / zaman | `now()`, `statement_timestamp()`, `pg_current_xact_id_if_assigned()` (sunucu ≥ 13; PG 18.6'da bu dal), `txid_current_if_assigned()` (yalnızca < 13) | P2, son kontrol |
| Ayar / oturum | `current_setting()`, `current_database()`; `current_user` ve `session_user` (SQL anahtar sözcükleri) | P4, 0, 1, P6, P8, 4 |
| Ağ / sunucu | `inet_server_addr()`, `inet_server_port()`, `host()`, `pg_is_in_recovery()`, `pg_backend_pid()` | P6, P6b, P7 |
| Sistem kimliği | `pg_control_system()` | P7 |
| Yetki sorgulama | `has_function_privilege`, `has_database_privilege`, `has_schema_privilege`, `has_table_privilege`, `has_any_column_privilege`, `has_sequence_privilege`, `pg_has_role` | P7, P8, 2.4, 3.2, 5.1, 5.4a, 5.4b, 5.5b, 5.11 |
| ACL | `aclexplode()`, `acldefault()` | 3.3, 3.4, 5.1, 5.4, 5.4a, 5.4c, 5.4d |
| Ad çözümleme | `to_regnamespace()`, `to_regclass()`, `pg_get_userbyid()`; `::regclass` ve `::regprocedure` dönüşümleri | 5.x |
| Tanım çıktısı | `pg_get_constraintdef()`, `pg_get_expr()`, `pg_get_function_identity_arguments()`, `format_type()` | 5.7, 5.8, 5.11, 5.15 |
| Metin / dizi / toplama | `regexp_replace`, `lower`, `split_part`, `substr`, `strpos`, `unnest … WITH ORDINALITY`, `string_agg`, `count`, `bool_or`, `bool_and` | çeşitli |
| Görünümlerin içinden | `pg_stat_get_activity()` (`pg_stat_ssl`); `pg_has_role` ve `has_server_privilege` (`pg_user_mappings` tanımı) | P6b, 5.14b |

Ayrıca operatörlerin ve tür dönüşümlerinin arkasındaki yerleşik fonksiyonlar kullanılır: `=`, `<>`, `>=`, `<<=` (inet), `~`, `||`, `::int4`, `::inet`, `::text`. [S] Görünüm içindeki fonksiyonların EXECUTE denetimi, görünümü sorgulayan rol için yapılır.

### 1.3 SELECT dışındaki ifadeler [D]

- `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` (406)
- `SET TRANSACTION ISOLATION LEVEL …` ×2 (407–408)
- `SET LOCAL search_path / statement_timeout / lock_timeout` (410–412)
- `SHOW transaction_read_only` (415)
- `ROLLBACK` (1614)
- `\encoding UTF8` (251), yani `set client_encoding`

**Yetki gereksinimi: yok.** [S]
- Bu ayarların tamamı `USERSET` sınıfındadır.
- Transaction kontrol komutları yetki gerektirmez.
- `\encoding` dışındaki her şey transaction yereldir.

---

## 2. Sorgu bazında yetki gereksinimi

Sütunlar:
- **Gerekli yetki:** İlgili nesnede aranan yetki.
- **PG 18.6 stok kaynağı:** Yetkinin varsayılan kurulumda nereden geldiği.
- **Yetki yoksa:** Betiğin davranışı.

| Bölüm | Okunan nesne | Gerekli yetki | PG 18.6 stok kaynağı | Yetki yoksa |
|---|---|---|---|---|
| Bağlantı | `hgs2_perftest_db` | `LOGIN` özniteliği + veritabanında `CONNECT` + `pg_hba.conf` kuralı | `CONNECT`: PUBLIC (`=Tc`) [S] | psql çıkış 2 |
| P1 | yok (psql değişkenleri) | `pg_catalog` USAGE (nitelenmiş operatör/tür) | PUBLIC `=U` | 3, işaretçisiz |
| P2 | `now`, `statement_timestamp`, `pg_current_xact_id_if_assigned` | EXECUTE | PUBLIC | 3, işaretçisiz |
| P3 | BEGIN / SET / SHOW | yok | — | — |
| P4 | `current_setting` (`transaction_*`, `search_path`, `*_timeout`) | EXECUTE; ayarlar süper kullanıcıya özel değil | PUBLIC | 3, işaretçisiz |
| 0 | `current_database`, `regexp_replace` | EXECUTE | PUBLIC | 3, işaretçisiz |
| 1 | `current_setting('server_version*')` | EXECUTE | PUBLIC | 3, işaretçisiz |
| P6 | `inet_server_addr/port`, `host`, `current_setting('port')`, `current_setting('cluster_name')`, `pg_is_in_recovery` | EXECUTE; `port` ve `cluster_name` `GUC_SUPERUSER_ONLY` değil (`pg_read_all_settings` **gerekmez**) [K: süper olmayan `hgs2_auditor` ile PASS] | PUBLIC | 3, işaretçisiz |
| P6b | `pg_stat_ssl` (yalnızca kendi `pg_backend_pid()` satırı) | görünüm SELECT + `pg_stat_get_activity` EXECUTE. Kendi oturum satırı her rol için tam görünür; `pg_read_all_stats` / `pg_monitor` **gerekmez** [K] | PUBLIC | 3, işaretçisiz |
| P7 | `has_function_privilege(...)`, `pg_control_system()` | `pg_control_system()` üzerinde **EXECUTE** (Bölüm 3) | Stokta PUBLIC [S]; test fixture'ı geri aldı [K] | `HGS2_AUDIT_ABORT: system_identifier_unverifiable` (fail-closed) [K: A13] |
| P8 | `pg_roles`, `pg_has_role` | SELECT, EXECUTE | PUBLIC | 3, işaretçisiz |
| 2.1–2.4 | `pg_roles`, `pg_auth_members`, `pg_has_role(oid, oid, …)` | SELECT, EXECUTE. Başka rol adına `pg_has_role` sorgulamak ek yetki istemez [S] | PUBLIC | 3, işaretçisiz |
| 3.1–3.4 | `pg_database`, `has_database_privilege`, `aclexplode`, `acldefault` | SELECT, EXECUTE. **`hibrit_giris_db`'ye CONNECT gerekmez**: satırlar paylaşılan katalogdan okunur | PUBLIC | 3, işaretçisiz |
| 4 | `pg_db_role_setting`, `pg_database`, `pg_roles` | SELECT [K: süper olmayan rolle] | PUBLIC | 3, işaretçisiz |
| 5.1 | `pg_namespace`, `has_schema_privilege` | SELECT, EXECUTE | PUBLIC | 3, işaretçisiz |
| 5.2, 5.3, 5.9, 5.17 | `pg_class`, `pg_namespace`, `pg_depend`, `pg_attribute`, `pg_constraint`, `to_regnamespace` | SELECT, EXECUTE. `to_regnamespace` şema USAGE denetimi yapmaz [S] | PUBLIC | 3, işaretçisiz |
| 5.4, 5.4a–d | `pg_class.relacl`, `pg_attribute.attacl`, `pg_default_acl`, `has_table_privilege`, `has_any_column_privilege` (MAINTAIN dalı PG 18.6'da çalışır) | SELECT, EXECUTE. **Tablo üzerinde SELECT gerekmez**; yalnızca ACL metaverisi okunur | PUBLIC | 3, işaretçisiz |
| 5.5, 5.5b | `pg_depend`, `pg_attribute`, `has_sequence_privilege`; `'pg_catalog.pg_class'::regclass` | SELECT, EXECUTE. Sequence USAGE/SELECT **gerekmez**; `nextval`/`currval` yok | PUBLIC | 3, işaretçisiz |
| 5.6, 5.7 | `pg_constraint`, `pg_get_constraintdef`, `confrelid::regclass` | SELECT, EXECUTE. `regclass` çıktısı yetki denetimi yapmaz [S] | PUBLIC | 3, işaretçisiz |
| **5.8** | `pg_attribute`, `format_type`, **`to_regclass('public.users')`** | SELECT, EXECUTE **ve `public` şemasında USAGE** [S] | PUBLIC `=U` (PG 15+ yeni DB) | **3, işaretçisiz: `permission denied for schema public`** [S] |
| 5.10 | `pg_type` | SELECT | PUBLIC | 3, işaretçisiz |
| 5.11 | `pg_proc`, `pg_depend`, `pg_get_function_identity_arguments`, `has_function_privilege(oid, oid, …)` | SELECT, EXECUTE. Kullanıcı fonksiyonları **çağrılmaz**, yalnızca listelenir | PUBLIC | 3, işaretçisiz |
| 5.12–5.14 | `pg_trigger`, `::regprocedure`, `pg_event_trigger`, `pg_extension` | SELECT | PUBLIC | 3, işaretçisiz |
| 5.14b | `pg_foreign_server`, `pg_foreign_data_wrapper`, `pg_user_mappings` | SELECT. Foreign server üzerinde USAGE **gerekmez**; `umoptions` seçilmez | PUBLIC | 3, işaretçisiz |
| 5.15 | `pg_policy`, `pg_get_expr` | SELECT, EXECUTE. RLS'li tablonun verisi okunmaz | PUBLIC | 3, işaretçisiz |
| 5.16 | `pg_largeobject_metadata` | SELECT. Büyük nesne içeriği ve `lo_*` fonksiyonları kullanılmaz | PUBLIC | 3, işaretçisiz |
| Son | `now()`, `statement_timestamp()` | EXECUTE | PUBLIC | 3, işaretçisiz |

**Sonuç** [D]: Yetki eksikliğinin her biçimi betiği **durdurur**. Yanlış ama hatasız sonuç üreten bir yetki eksikliği yolu tespit edilmedi:
- P7'de durdurma işaretçilidir.
- Diğer bölümlerde "çıkış 3 + işaretçi yok" olur; doğrulayıcı bunu FAIL sayar.

### 2.1 Bölüm 5.8: `public` şeması USAGE bağımlılığı [S]

`to_regclass('public.users')` nitelenmiş adı çözer. Bu sırada `LookupExplicitNamespace` çalışır ve çağıran rol için şema üzerinde `USAGE` denetimi yapar.
- `to_regclass` yalnızca "bulunamadı" durumunda NULL döner.
- Yetki eksikliğinde **hata** verir.
- `to_regnamespace('public')` ise yalnızca OID arar ve USAGE denetlemez.

Etkisi:
- `public` şemasında PUBLIC'ten `USAGE` geri alınmış bir `hgs2_perftest_db`'de betik 5.8'de işaretçisiz durur.
- Testlerde bu durum oluşmadı: tüm kümelerde PUBLIC `=U` vardı [K: N1 çıktıları, 5.1].
- **Doğrulanmadı.** Gerçek hedeften önce bir test kümesinde denenmelidir (Bölüm 13, karar 3).

---

## 3. `pg_control_system()` ve sistem kimliği okuma gereksinimi

### 3.1 Betik ne yapıyor [D]

1. **P7, satır 669:**
   ```sql
   has_function_privilege('pg_catalog.pg_control_system()', 'EXECUTE')
   ```
   - Bu çağrı **current_user** için denetler.
   - Fonksiyon da current_user yetkisiyle çağrılır. İkisi tutarlıdır.
2. Yetki yoksa `system_identifier_unverifiable` ile durur. Kapı kapalı kalır (fail-closed).
3. Yetki varsa `system_identifier` değerini `expected_system_identifier` ile karşılaştırır. Farklıysa durur.
4. Parametre zorunludur (P1b). **Betiği bu adımı atlayacak biçimde çalıştırmanın yolu yoktur.** Dolayısıyla bu yetki, nihai SQL dosyası değişmedikçe **zorunludur**.

### 3.2 Yetkinin kaynağı

- **[S]** Stok PostgreSQL'de `pg_control_system()` için `proacl` NULL'dır; EXECUTE PUBLIC'e açıktır. PG 18'de de `system_functions.sql` bu fonksiyonu PUBLIC'ten geri almaz.
- **[K]** Belgeler (betik satır 54, `FINAL_DELIVERY.md` §5.5) test kümelerinde `proacl = NULL` görüldüğünü söyler.
  - Ancak incelenen anlık görüntü (`kanit/snapshots/before/pg18/schema.sql` satır 360–363) **sertleştirilmiş** durumu gösterir: `REVOKE ALL … FROM PUBLIC` ve yalnızca test rollerine GRANT. Bu, `fixture_harden.sql` kaynaklıdır.
  - NULL gözleminin kaydı incelenen kanıtlarda bulunamadı.
  - Sonuç: stok varsayılan için kaynak [S]'dir. **Gerçek hedefte doğrulanmalıdır** (Q2).
- **[S] Fonksiyon ACL'leri veritabanı başınadır.**
  - `pg_proc` paylaşılan bir katalog değildir.
  - Önemli olan, fonksiyonun **`hgs2_perftest_db` içindeki** ACL'sidir.
  - Başka bir veritabanında verilen ya da geri alınan yetki bu betiği etkilemez.
  - `fixture_harden.sql` da geri alma işlemini yalnızca `hgs2_perftest_db`'de yaptı.

### 3.3 Değerlendirme

| Soru | Cevap |
|---|---|
| EXECUTE gerekli mi? | **Evet.** Betik tasarımı gereği zorunlu ve fail-closed. |
| Ek rol üyeliği gerekir mi (ör. `pg_monitor`)? | **Hayır.** Fonksiyon, `pg_read_all_settings` ya da `pg_monitor` üyeliği aramaz. |
| PUBLIC'te zaten varsa GRANT gerekir mi? | **Hayır.** Gereksiz bir GRANT olur. Testlerdeki açık GRANT, PUBLIC'ten geri alma yapılmış fixture yüzündendi [K]. |
| PUBLIC'te yoksa ne yapılmalı? | Yalnızca `hgs2_perftest_db`'de ve **yalnızca audit rolüne** tek bir `EXECUTE` (betik satır 57'deki biçim). PUBLIC'e geri verilmemeli: sertleştirme kararını bozar. Bu bir `hgs2_perftest_db` değişikliğidir ve ayrı onay ister. |
| Gizlilik riski | Düşük. Döndürülen değerler: control sürümü, katalog sürümü, `system_identifier`, son değişiklik zamanı. Kimlik doğrulama sırrı değildir. |

### 3.4 Beklenen değerin (`expected_system_identifier`) alınması

Bu bir veritabanı yetkisi değildir. Sunucunun veri dizinindeki `global/pg_control` dosyasını okuyabilen **işletim sistemi** kimliğiyle `pg_controldata` çalıştırmayı gerektirir. Bu kimlik genellikle `postgres` OS kullanıcısı veya Windows servis hesabıdır.

[D] **Aynı SQL kanalından** alınan değer bağımsız doğrulama sağlamaz. Örnek: süper kullanıcıyla `SELECT system_identifier FROM pg_control_system()`. Bu durumda betik kendi kanalını kendisiyle karşılaştırmış olur. Belgelerin "ayrı ve yetkili adım" şartı (FINAL_DELIVERY §5.2) bu nedenle korunmalıdır.

Hatırlatma (KNOWN_LIMITATIONS 2): replika ve klon aynı değeri taşır.

---

## 4. Tablo verisi için SELECT gerekiyor mu?

**Hayır. Yalnızca katalog erişimi yeterlidir.** [D] [K]

- Betikte hiçbir kullanıcı şeması nesnesinin satırı okunmaz:
  - `FROM` yan tümcelerinin tamamı `pg_catalog.*` ilişkileridir.
  - `users`, `admins`, `logs`, `devices` yalnızca `relname` sabiti ve `to_regclass` OID'i olarak geçer.
- Etkin yetkiler `has_*_privilege` fonksiyonlarıyla hesaplanır. Bu fonksiyonlar sorgulanan nesne üzerinde yetki istemez; başka bir rol adına da sorgulanabilir [S].
- Testteki `hgs2_auditor` rolü kullanıcı tablolarında hiçbir yetkiye sahip değildi ve tam denetim PASS verdi [K: fixture_db.sql'de `hgs2_auditor` için tablo GRANT'i yok; N1-normal 4 sürüm].
- Şu yetkiler **gerekmez** ve verilmemelidir:
  - `pg_read_all_data`. Verilirse P8 `audit_role_excess_privilege` uyarısı üretir.
  - Sequence USAGE/SELECT.
  - Büyük nesne SELECT.
  - Foreign server USAGE.

**Dikkat: audit rolü PUBLIC üzerinden yine de veri erişimi kazanabilir.** Betik buna ihtiyaç duymaz, ama minimum yetki hedefi açısından ayrıca bakılmalıdır:
- **Kullanıcı tabloları:** PUBLIC'e verilmiş tablo yetkileri. 5.4 çıktısında `grantee = PUBLIC` satırları olarak görünür.
- **Varsayılan yetkiler:** PUBLIC'e varsayılan yetki veren `ALTER DEFAULT PRIVILEGES` kayıtları (5.4d).
- **`users.parmak_izi_sablonu oid` sütunu** büyük nesne kullanımına işaret eder. İki ayrı yol vardır:
  - `lo_compat_privileges = on` ise her rol tüm büyük nesneleri okuyabilir [S].
  - `lomacl` içinde PUBLIC'e verilmiş SELECT, aynı sonucu belirli nesneler için doğurur.

  5.16 bunlardan yalnızca açık ACL sayısını verir; PUBLIC ayrımını ve `lo_compat_privileges` değerini göstermez. Q4 bu boşluğu kapatır.

---

## 5. CONNECT, USAGE, CREATE ve EXECUTE (ayrı ayrı)

### 5.1 CONNECT (veritabanı)

| Veritabanı | Gerekli mi | Not |
|---|---|---|
| `hgs2_perftest_db` | **Evet** | Stokta PUBLIC `c`. `datacl` PUBLIC'ten geri alınmışsa audit rolüne tek bir CONNECT gerekir (koşullu). Ayrıca `pg_hba.conf`'ta bu rol ve veritabanı için kural gerekir; ACL tek başına yetmez. |
| `hibrit_giris_db` | **Hayır** | Betik bu veritabanının satırını paylaşılan `pg_database` kataloğundan okur. Bağlanırsa betik `production_database` ile durur. |
| `postgres`, `template1`, diğerleri | **Hayır** | — |

**Risk** [S]: Yeni bir rol, `hibrit_giris_db` dahil, `datacl`'i varsayılan olan her veritabanına **PUBLIC üzerinden ACL düzeyinde bağlanabilir**. Bu, yeni rolün o veritabanında şunları yapabilmesi demektir:
- katalog metaverisini okumak,
- PUBLIC'e açık fonksiyonları çağırmak, PUBLIC EXECUTE'lu `SECURITY DEFINER` fonksiyonlar dahil.

Durum şöyledir:
- **Test kümesi:** `hibrit_giris_db`'de PUBLIC kaldırılmıştı [K: fixture_global.sql].
- **Gerçek küme:** Bilinmiyor. Betiğin 3.3/3.4 çıktısı bunu gösterecektir.

Önerilen kontrol GRANT/REVOKE değildir:
- `pg_hba.conf`'ta audit rolü yalnızca `hgs2_perftest_db` için tanımlanmalıdır.
- Bu, yönetici tarafından ayrı bir adımda doğrulanmalıdır.
- `hibrit_giris_db` ACL'sine dokunmak bu çalışmanın kapsamı dışındadır.

Test fixture'ında `hgs2_auditor` rolüne verilen `GRANT CONNECT ON DATABASE hibrit_giris_db` yalnızca A02 negatif senaryosu içindi [K: suite3.sh satır 11]. **Gerçek ortamda tekrarlanmamalıdır.**

### 5.2 TEMPORARY (veritabanı)

**Gerekmez.**
- `search_path`'teki `pg_temp` yalnızca ad çözümleme sırasıdır. Geçici şema oluşturulmaz [K: FINAL_SECURITY_AUDIT §12.4].
- Ayrıca READ ONLY transaction geçici tablo oluşturmayı engeller.

Stokta PUBLIC `T` vardır. Bu, audit rolüne denetim dışındaki oturumlarda geçici nesne oluşturma imkânı verir. PUBLIC'ten geri almak tüm rolleri etkiler ve gereksiz bir REVOKE olur; **önerilmez**. Bilinen ve kabul edilen bir PUBLIC artığı olarak kaydedilir.

### 5.3 USAGE (şema)

| Şema | Gerekli mi | Gerekçe |
|---|---|---|
| `pg_catalog` | **Evet** | Bütün nitelenmiş ad ve operatör çözümlemesi. Stokta PUBLIC `=U`. |
| `public` (`hgs2_perftest_db`) | **Evet, yalnızca 5.8 için** [S] | `to_regclass('public.users')` (Bölüm 2.1). PG 15+ yeni veritabanında PUBLIC `=U`. |
| Diğer kullanıcı şemaları | **Hayır** | Yalnızca `pg_namespace` satırları ve OID karşılaştırmaları kullanılır. |
| `information_schema` | **Hayır** | Kullanılmaz. |

### 5.4 CREATE

| Kapsam | Gerekli mi | Olması gereken |
|---|---|---|
| Veritabanında CREATE (şema oluşturma) | **Hayır** | `false`. Stokta PUBLIC'te yoktur; yalnızca sahip ve yetkilendirilenlerde vardır. |
| `public` şemasında CREATE | **Hayır** | `false`. PG 15+ yeni veritabanında yalnızca `pg_database_owner`. **Uyarı:** PG ≤ 14'ten `pg_upgrade` edilmiş kümede veya eski `template1`'den oluşturulmuş veritabanında PUBLIC `=UC` korunur [S, PG 15 sürüm notları]. Bu durumda yeni rol PUBLIC yoluyla CREATE kazanır (Bölüm 11, H5). |
| Diğer şemalarda CREATE | **Hayır** | `false` |
| `CREATEDB` / `CREATEROLE` öznitelikleri | **Hayır** | `false`. P8 yalnızca CREATEROLE için uyarır; CREATEDB'yi raporlar ama uyarmaz [D, satır 754–757]. |

CREATE yetkisi, rolü bir nesnenin **sahibi** yapabilecek tek yoldur. Bu yüzden yeni rolde her kapsamda `false` olması hedeflenmelidir (Bölüm 9).

Denetim transaction'ı READ ONLY olduğu için **betik çalışırken** CREATE kullanılamaz. Bu hedef denetim dışındaki oturumlar içindir.

### 5.5 EXECUTE

| Nesne | Gerekli mi | Kaynak |
|---|---|---|
| Bölüm 1.2'deki yerleşik fonksiyonlar | **Evet** | Stokta PUBLIC. `pg_control_system` dışında hiçbiri `system_functions.sql` ile PUBLIC'ten geri alınan listede değildir [S]. Geri alınanlar örneğin `pg_read_file`, `pg_ls_dir`, `pg_stat_reset*`, `lo_import/export`. |
| `pg_control_system()` | **Evet** | Bölüm 3 |
| Kullanıcı şemasındaki fonksiyonlar | **Hayır** | `search_path` `pg_catalog, pg_temp` olarak sabitlenmiştir. Kullanıcı fonksiyonları çağrılmaz, 5.11'de yalnızca listelenir. |
| Dil USAGE (`plpgsql`) | **Hayır** | — |

---

## 6. PostgreSQL 18.6 için minimum yetki matrisi

PG 18.6'da çalışan kod dalları [K: FINAL_SECURITY_AUDIT §7]:
- P2: `pg_current_xact_id_if_assigned`
- 2.3: PG 16+ (`inherit_option`, `set_option`)
- 5.4b: MAINTAIN

Bu dalların hiçbiri ek yetki istemez.

| # | Yetki / öznitelik | Nesne (veritabanı) | Gerekli | Stok PG 18.6 kaynağı | Ek GRANT gerekir mi |
|---|---|---|---|---|---|
| 1 | `LOGIN` | rol | **Evet** | — | Rol oluşturulurken verilir |
| 2 | `CONNECT` | `hgs2_perftest_db` | **Evet** | PUBLIC | Yalnızca `datacl` PUBLIC'ten geri alınmışsa |
| 3 | `pg_hba.conf` kuralı | `hgs2_perftest_db` + rol | **Evet** | — | ACL değil; yönetici yapılandırması |
| 4 | `USAGE` | şema `pg_catalog` (`hgs2_perftest_db`) | **Evet** | PUBLIC | Hayır (stokta geri alınamaz kabul edilir) |
| 5 | `USAGE` | şema `public` (`hgs2_perftest_db`) | **Evet** (5.8) [S] | PUBLIC | Yalnızca PUBLIC'ten geri alınmışsa |
| 6 | `SELECT` | Bölüm 1.1'deki 21 ilişki | **Evet** | PUBLIC | Yalnızca sertleştirme ile geri alınmışsa (test edilmedi) |
| 7 | `EXECUTE` | Bölüm 1.2'deki yerleşik fonksiyonlar | **Evet** | PUBLIC | Yalnızca geri alınmışsa |
| 8 | `EXECUTE` | `pg_catalog.pg_control_system()` (`hgs2_perftest_db`) | **Evet** | PUBLIC [S] | Yalnızca geri alınmışsa; yalnızca audit rolüne |
| 9 | `TEMPORARY` | `hgs2_perftest_db` | Hayır | PUBLIC (fazlalık) | — (REVOKE önerilmez) |
| 10 | `CONNECT` | `hibrit_giris_db` | **Hayır; olmamalı** | PUBLIC olabilir | — (`pg_hba.conf` ile kısıtlanmalı) |
| 11 | `CREATE` | herhangi bir veritabanı / şema | **Hayır; olmamalı** | PG ≤ 14 kökenli `public` şemasında PUBLIC olabilir | — |
| 12 | Tablo / sütun / sequence / LO yetkisi | kullanıcı nesneleri | **Hayır; olmamalı** | PUBLIC grant'leri varsa gelir | — |
| 13 | `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS` | rol | **Hayır; olmamalı** | — | — |
| 14 | Rol üyeliği (`hgs2_perftest`, `pg_database_owner`, `pg_read_all_data`, `pg_read_all_settings`, `pg_read_all_stats`, `pg_monitor`, `pg_maintain`, …) | — | **Hayır; hiçbiri** | — | — |
| 15 | Nesne / veritabanı / şema sahipliği | tüm veritabanları | **Hayır; hiçbiri** | — | — |
| 16 | Rol düzeyi kalıcı ayar (`ALTER ROLE … SET`) | `pg_db_role_setting` | **Hayır; olmamalı** | — | — (Bölüm 4 raporlar) |

**Özet:** Stok PG 18.6'da satır 1–8 için ek GRANT **gerekmez**. Rolün `LOGIN` ile oluşturulması ve `pg_hba.conf` kuralı yeterlidir.

---

## 7. PUBLIC üzerinden gelen varsayılan yetkiler (PG 18.6 stok)

Kaynak: PostgreSQL belgeleri, "Privileges" bölümündeki varsayılan PUBLIC yetkileri tablosu ve initdb davranışı [S]. Gerçek hedefte Q2 ile doğrulanmalıdır.

| Nesne | PUBLIC varsayılanı | Betik için | Audit rolü için değerlendirme |
|---|---|---|---|
| Veritabanı | `CONNECT`, `TEMPORARY` (`=Tc`) | CONNECT **gerekli** (yalnızca `hgs2_perftest_db`) | `hibrit_giris_db` ve diğer veritabanlarındaki CONNECT ile her yerdeki TEMPORARY **fazlalıktır** |
| Şema `pg_catalog` | `USAGE` | **Gerekli** | — |
| Şema `public` (PG 15+ yeni DB) | `USAGE` (`=U/pg_database_owner`) | **Gerekli** (5.8) | — |
| Şema `public` (PG ≤ 14 kökenli) | `USAGE`, `CREATE` (`=UC`) | Yalnızca USAGE gerekli | CREATE **fazlalık ve sahiplik riski** (Bölüm 11) |
| Sistem katalogları ve görünümleri | `SELECT`. İstisnalar: `pg_authid`, `pg_user_mapping`, `pg_largeobject`, `pg_statistic`, `pg_subscription`'ın bir kısmı | **Gerekli** (21 ilişki) | Betik istisnaların hiçbirini kullanmaz |
| Fonksiyonlar / prosedürler | `EXECUTE`. Yerleşiklerin bir kısmı initdb'de geri alınır | **Gerekli** (yerleşikler) | Kullanıcı şemalarındaki PUBLIC EXECUTE'lu fonksiyonlar fazlalıktır. Özellikle `SECURITY DEFINER` olanlar 5.11'de raporlanır. |
| Diller | `USAGE` (`plpgsql`) | Gerekmez | Fazlalık (zararsız) |
| Türler / domain'ler | `USAGE` | Dolaylı (yerleşik türler) | — |
| Tablolar, sequence'lar, büyük nesneler, foreign server'lar | **Yok**. Açık GRANT veya `ALTER DEFAULT PRIVILEGES … TO PUBLIC` ile gelebilir | Gerekmez | 5.4, 5.4d, 5.5b, 5.16 ile görünür hale gelir |

**Testte gözlenen PUBLIC durumu** [K: N1-normal 5.1 ve 3.2]:

| Gözlem | PG 12 | PG 16 / 17 / 18 |
|---|---|---|
| `public` şeması ACL'si | `{pgadmin=UC/pgadmin,=UC/pgadmin}` → PUBLIC CREATE var | `{pg_database_owner=UC/pg_database_owner,=U/pg_database_owner}` → PUBLIC CREATE yok |
| `hgs2_perftest_db` CONNECT / TEMPORARY | PUBLIC yoluyla `t` | PUBLIC yoluyla `t` |
| `hibrit_giris_db` | PUBLIC geri alınmış (fixture) | PUBLIC geri alınmış (fixture) |

---

## 8. `hgs2_perftest` sahipliğinden gelen yetkiler audit rolüne aktarılmamalı

`hgs2_perftest` gerçek ortamda tabloların veya veritabanının sahibiyse şu yetkilere örtük olarak sahiptir. Bu yetkiler ACL'de görünmeyebilir [S]:
- `ALTER`, `DROP`, `TRUNCATE`
- `GRANT/REVOKE` yönetimi
- RLS'yi kapatma ve politika değiştirme
- Sahip kendi yetkisini REVOKE etmiş olsa bile yetkiyi geri alabilme (5.4a yorumu, satır 1101–1103)

Veritabanı sahibiyse ayrıca `pg_database_owner` yoluyla PG 15+ `public` şeması CREATE yetkisine de sahiptir.

**Bu yetkilerin hiçbiri betik için gerekmez.** Aşağıdakilerin **hiçbiri yapılmamalıdır**:

| Yapılmaması gereken | Neden |
|---|---|
| Audit rolünü `hgs2_perftest`'e üye yapmak (`GRANT hgs2_perftest TO …`), hangi seçenekle olursa olsun | PG 16+'da `INHERIT FALSE` olsa bile `SET TRUE` ile `SET ROLE hgs2_perftest` mümkündür ve tüm sahip yetkileri gelir. P8 bunu **algılamaz**. |
| Audit rolünü `hgs2_perftest_db` veya başka bir veritabanının sahibi yapmak | Örtük `pg_database_owner` üyeliği, dolayısıyla `public` CREATE. P8 **algılamaz**. |
| `REASSIGN OWNED`, `ALTER … OWNER TO <audit>` | Sahiplik aktarımı |
| `hgs2_perftest` adına `ALTER DEFAULT PRIVILEGES … TO <audit>` | İleride oluşturulacak nesnelerde yetki birikir |
| `hgs2_perftest`'in tablo / sequence yetkilerini `WITH GRANT OPTION` dahil kopyalamak | Betik veri okumaz |
| Denetimi `hgs2_perftest` kimliğiyle çalıştırmak | Hem denetlenen hem denetleyen olur. Sahip yetkileri READ ONLY transaction dışında kullanılabilir. P8 uyarı **vermez**. Uygulama kimlik bilgisinin denetim otomasyonuna taşınması gerekir. |

**Betik boşluğu** [D]: P8'deki `audit_role_excess_privilege` (satır 753–755) yalnızca şunlara bakar:
- `rolcreaterole`, `rolbypassrls`, `rolreplication`
- beş önceden tanımlı rol

Sahiplik, `hgs2_perftest` üyeliği ve `pg_database_owner` kapsam dışıdır. SQL dosyası değiştirilmeyeceği için bu boşluk **betik dışı ön kontrolle** kapatılmalıdır (Bölüm 12, Q3).

---

## 9. Yeni audit rolü hiçbir veritabanında nesne sahibi olmamalı

**Kural:** Audit rolü kümedeki **hiçbir** veritabanında, `hibrit_giris_db` dahil, şunların sahibi olmamalıdır:
- veritabanı, şema, tablo, sequence, fonksiyon, tür
- büyük nesne, extension, foreign server, event trigger
- tablespace

**Gerekçe:**
- Sahiplik, ACL'den bağımsız ve geri alınamayan yetki verir.
- Sahip, kendi nesnesinin yetkilerini istediği zaman kendine geri verebilir.
- P8 bunu algılamaz.

**Doğrulama yöntemi** [S]:
- `pg_shdepend` paylaşılan bir katalogdur.
- Bir rolün **tüm veritabanlarındaki** sahiplik kayıtlarını (`deptype = 'o'`) ve ACL kayıtlarını (`deptype = 'a'`) tek bağlantıdan gösterir.
- Bu sayede `hibrit_giris_db`'ye **bağlanmadan** o veritabanındaki sahiplik de görülebilir (Q3).
- Veritabanı sahipliği ayrıca `pg_database.datdba` ile denetlenir.

**Kuralı korumak için:**
- Audit rolünde hiçbir şemada CREATE, hiçbir veritabanında CREATE ve CREATEDB olmamalıdır (Bölüm 5.4).
- Rol, `hgs2_perftest` tarafından değil, yetkili yönetici tarafından oluşturulmalıdır.
  - [S] PG 16+'da CREATEROLE'lü süper olmayan bir rol yeni rolü oluşturduğunda, oluşturan rol yeni role ADMIN seçeneğiyle üye yapılır.
  - Bu, audit rolünün yetkisini artırmaz.
  - Ama oluşturan rolün `SET ROLE <audit>` yapmasına ve audit kimliğiyle işlem yapmasına izin verir.

---

## 10. Önerilmeyen GRANT / REVOKE / üyelikler ve tek koşullu istisnalar

**Önerilmez** (gereksiz veya kapsam dışı):
- `pg_read_all_data`, `pg_read_all_settings`, `pg_read_all_stats`, `pg_monitor`, `pg_maintain`, `pg_signal_backend` üyelikleri. Betik bunların hiçbirini kullanmaz.
- Kullanıcı tablosu, sütun, sequence, büyük nesne ve foreign server yetkileri.
- `hibrit_giris_db` üzerinde herhangi bir GRANT veya REVOKE.
- PUBLIC'ten REVOKE işlemleri (TEMPORARY, `public` USAGE/CREATE, fonksiyonlar). Bunlar tüm rolleri ve uygulamayı etkiler. Gerekip gerekmediği bu çalışmanın değil, ayrı bir sertleştirme kararının konusudur.
- `pg_control_system()` EXECUTE'unu PUBLIC'e geri vermek.
- PUBLIC'te zaten olan bir yetkiyi audit rolüne ayrıca vermek. Etkisizdir ve ileride PUBLIC sertleştirildiğinde gözden kaçan bir istisnaya dönüşür.

**Yalnızca Q2 eksik gösterirse, yalnızca `hgs2_perftest_db`'de ve yalnızca audit rolüne** (ayrı onaylı adımda):
1. `EXECUTE ON FUNCTION pg_catalog.pg_control_system()`
2. `CONNECT ON DATABASE hgs2_perftest_db`
3. `USAGE ON SCHEMA public` [S: 5.8 bağımlılığı önce testte doğrulanmalı]
4. Sertleştirmede geri alınmış bir katalog `SELECT`'i veya yerleşik fonksiyon `EXECUTE`'u. Bu durum test edilmedi (KNOWN_LIMITATIONS 21). Önce test kümesinde denenmelidir.

---

## 11. CREATE çelişkisi: `hgs2_perftest` için `public` şemasında bir sorguda FALSE, diğerinde TRUE

**Eldeki bilgi:** Kullanıcı testlerinin hangi iki sorguyu, hangi veritabanında, hangi rolle ve hangi sürümde çalıştırdığı bu dosyalarda yoktur. Bu yüzden aşağıdaki hipotezlerden **hiçbiri seçilmemiştir**. Her biri için ayırt edici gözlem ve kesinleştirecek sorgu sütunu verilmiştir.

**Kayıt kuralı:** "TRUE" ile "FALSE" arasındaki fark çoğunlukla **etkin yetki** (`has_schema_privilege`) ile **ACL içeriği** (`nspacl` / `aclexplode`) arasındaki farktan doğar. PostgreSQL'de bu ikisi farklı şeyleri ölçer [S]:
- Etkin yetki şunları hesaba katar:
  - sahiplik,
  - süper kullanıcı,
  - PUBLIC,
  - kalıtımla gelen üyelikler,
  - `pg_database_owner`.
- ACL listesi yalnızca kayıtlı girdileri gösterir.

### 11.1 Hipotezler

| # | Hipotez | Mekanizma | Kanıt / not | Ayırt eden K1/K2 sütunu |
|---|---|---|---|---|
| **H1** | **Aynı adlı iki farklı sütun karıştırıldı** | Betikte 3.2 `perftest_create` = `has_database_privilege(..., 'CREATE')`, yani **veritabanında** şema oluşturma (satır 898). 5.1 `perftest_create` = `has_schema_privilege(..., 'CREATE')`, yani **`public` şemasında** nesne oluşturma (satır 1033). | **[K]** PG 12 N1-normal aynı çıktıda: 3.2 `hgs2_perftest_db perftest_create = f` (satır 54), 5.1 `public perftest_create = t` (satır 89). PG 16/18'de ikisi de `f`. | `veritabani_create_etkin` ile `sema_create_etkin` farklı |
| **H2** | Etkin yetki ile ACL listesi karşılaştırıldı | 5.1 `effective_acl` sütununda `hgs2_perftest` girdisi olmayabilir. Yetki PUBLIC (`=UC`), sahiplik veya `pg_database_owner` yoluyla gelir; `perftest_create = t` olur. | **[K]** PG 12: `effective_acl = {pgadmin=UC/pgadmin,=UC/pgadmin}`, `hgs2_perftest` girdisi yok, `perftest_create = t` | K2'de `hgs2_perftest` satırı yok ama `PUBLIC` veya üye olunan bir grantee'de `CREATE` var |
| **H3** | `hgs2_perftest` veritabanı sahibi (`pg_database_owner`) | PG 15+'da `public` şemasının sahibi `pg_database_owner`'dır. Veritabanı sahibi buna örtük üyedir. Bu üyelik `pg_auth_members`'ta **görünmez**. Üyelik tablosuna bakan bir sorgu FALSE, `has_schema_privilege` TRUE verir. | Gerçek ortamda `hgs2_perftest`'in veritabanı sahibi olup olmadığı bilinmiyor | `perftest_db_sahibi = t`, `sema_sahibi = pg_database_owner`, `sema_sahibine_uye = t` |
| **H4** | Şema sahipliği ile ACL farkı | `hgs2_perftest` `public` şemasının sahibi olabilir ve kendi `C` yetkisini REVOKE etmiş olabilir. Bu durumda `has_schema_privilege = f`, ama "sahip mi?" sorgusu TRUE verir; sahip yetkiyi her an geri verebilir. Ters durumda sahiplik ACL'de görünmeden TRUE verir. | — | `perftest_sema_sahibi`, `sema_acl` |
| **H5** | PG ≤ 14 kökenli `public` ACL'si (`=UC`) | `pg_upgrade` veya eski `template1` kopyası PG 18.6'da PUBLIC CREATE'i korur. Biri "PG 15+ varsayılanı" beklentisiyle FALSE, diğeri gerçek durumu ölçüp TRUE görür. Aynı küme içindeki farklı veritabanları farklı ACL'ye sahip olabilir. | **[K]** PG 12 testinde `=UC`; PG 16+'da `=U` | `sema_acl` içinde `=UC` |
| **H6** | Sorgular farklı veritabanlarında çalıştırıldı | Her veritabanının **kendi** `public` şeması vardır (`pg_namespace` paylaşılan değildir). `postgres` ile `hgs2_perftest_db` farklı sonuç verebilir. | Sorguların bağlandığı veritabanı bilinmiyor. `hibrit_giris_db` ise bu ayrıca bir kural ihlalidir ve bildirilmelidir. | `db` sütunu; aynı sorgu iki tarafta da yalnızca izin verilen veritabanında |
| **H7** | Farklı rol için ölçüldü | `has_schema_privilege('public', 'CREATE')` iki argümanlı biçimdir ve **current_user** için ölçer, `hgs2_perftest` için değil. Süper kullanıcıyla çalıştırılırsa her zaman TRUE döner. Ayrıca `hgs2_perftest` süper kullanıcıysa `has_*` her zaman TRUE döner, ACL listesi ise FALSE görünür. | — | `oturum_rolu`, `etkin_rol`, `perftest_super` |
| **H8** | Kalıtım ile üyelik farkı | Yetki, `hgs2_perftest`'in üye olduğu bir rolden geliyor ve üyelik kalıtımsız olabilir (`NOINHERIT` veya PG 16+ `inherit_option = false`). `has_schema_privilege` FALSE verir. Üyelik tabanlı bir sorgu (`pg_has_role … 'MEMBER'`) veya `SET ROLE` sonrası ölçüm TRUE verir. | **[K]** Fixture'da `hgs2_perftest → grp_nested → grp_reader` dolaylı üyelik zinciri var | K2: `perftest_uye_veya_kendisi = t` ama `perftest_kalitimla_kullanir = f` |
| **H9** | Anlık görüntü farkı (düşük olasılık) | `has_*_privilege` katalog önbelleğini ve en güncel kaydedilmiş durumu okur. `SELECT nspacl` ise REPEATABLE READ anlık görüntüsünü okur [S]. Denetim sırasında eşzamanlı bir GRANT veya REVOKE kaydedilirse aynı transaction içinde 5.1'in iki sütunu çelişebilir. Ayrı zamanlarda yapılan iki test arasında ACL gerçekten değişmiş de olabilir. | — | K1'i iki kez ve tek ifadede çalıştırmak; `sema_acl` ile `sema_create_etkin`'in aynı ifadede tutarlı olması |

### 11.2 Kesinleştirecek salt okunur sorgular (ÇALIŞTIRILMADI)

**Koşullar:**
- Yalnızca ayrı onayla, yalnızca `hgs2_perftest_db`'ye bağlanılarak çalıştırılmalıdır.
- Herhangi bir süper kullanıcı olmayan rolle çalıştırılabilir. Sonuçlar çağıran rolden bağımsızdır; yalnızca `oturum_rolu` ve `etkin_rol` sütunları değişir.
- Yazma yapmaz. Transaction READ ONLY'dir ve ROLLBACK ile kapanır.

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL search_path = pg_catalog, pg_temp;

-- K1: tek ifade, tek anlık görüntü; H1, H3-H7, H9'u ayırır
WITH me AS (
    SELECT oid, rolsuper, rolinherit FROM pg_roles WHERE rolname = 'hgs2_perftest'
), sch AS (
    SELECT oid, nspowner, nspacl FROM pg_namespace WHERE nspname = 'public'
), db AS (
    SELECT oid, datdba FROM pg_database WHERE datname = current_database()
)
SELECT current_database()                                      AS db,
       session_user                                            AS oturum_rolu,
       current_user                                            AS etkin_rol,
       current_setting('server_version_num')                   AS surum,
       me.rolsuper                                             AS perftest_super,
       me.rolinherit                                           AS perftest_rolinherit,
       pg_get_userbyid(db.datdba)                              AS db_sahibi,
       (db.datdba = me.oid)                                    AS perftest_db_sahibi,
       pg_get_userbyid(sch.nspowner)                           AS sema_sahibi,
       (sch.nspowner = me.oid)                                 AS perftest_sema_sahibi,
       (sch.nspacl IS NULL)                                    AS sema_acl_varsayilan,
       COALESCE(sch.nspacl, acldefault('n', sch.nspowner))::text AS sema_acl,
       has_schema_privilege(me.oid, sch.oid, 'CREATE')         AS sema_create_etkin,
       has_schema_privilege(me.oid, sch.oid, 'USAGE')          AS sema_usage_etkin,
       has_database_privilege(me.oid, db.oid, 'CREATE')        AS veritabani_create_etkin,
       pg_has_role(me.oid, sch.nspowner, 'MEMBER')             AS sema_sahibine_uye,
       pg_has_role(me.oid, sch.nspowner, 'USAGE')              AS sema_sahibi_yetkisi_kalitimla
FROM me CROSS JOIN sch CROSS JOIN db;

-- K2: CREATE'in hangi ACL girdisinden geldiği; H2 ve H8'i ayırır
WITH me AS (SELECT oid FROM pg_roles WHERE rolname = 'hgs2_perftest')
SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
       pg_get_userbyid(a.grantor)                               AS grantor,
       a.privilege_type,
       a.is_grantable,
       CASE WHEN a.grantee = 0 THEN true
            ELSE pg_has_role(me.oid, a.grantee, 'MEMBER') END   AS perftest_uye_veya_kendisi,
       CASE WHEN a.grantee = 0 THEN true
            ELSE pg_has_role(me.oid, a.grantee, 'USAGE') END    AS perftest_kalitimla_kullanir
FROM pg_namespace n
CROSS JOIN me
CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl, acldefault('n', n.nspowner))) AS a
WHERE n.nspname = 'public'
ORDER BY 1, 3;

ROLLBACK;
```

**K1/K2 ile birlikte kullanıcıdan alınması gereken bilgiler** (varsayım yapmamak için):
1. Çelişen **iki sorgunun tam metni**. Hangisi `has_schema_privilege`, hangisi ACL veya üyelik okuyor?
2. Her birinin bağlandığı **veritabanı**, **rol** (`session_user` / `current_user`), sunucu sürümü ve zamanı.
3. Sorgulardan biri betiğin 3.2 / 5.1 çıktısı ise **hangi bölümün** `perftest_create` sütunu olduğu.

**Karar tablosu:**

| K1 / K2 sonucu | Açıklama |
|---|---|
| `veritabani_create_etkin ≠ sema_create_etkin` ve çelişen değerler 3.2 ile 5.1'den geliyor | **H1** |
| `sema_create_etkin = t`, K2'de `hgs2_perftest` satırı yok, `PUBLIC … CREATE` var | **H2 + H5**. `public` şeması PUBLIC'e CREATE açık. Yeni audit rolü de CREATE kazanır (Bölüm 5.4). |
| `perftest_db_sahibi = t` ve `sema_sahibi = pg_database_owner` | **H3** |
| `perftest_sema_sahibi = t` | **H4** |
| `perftest_super = t` | **H7**. Ayrıca bu ciddi bir bulgudur. |
| `etkin_rol ≠ hgs2_perftest` ve test iki argümanlı biçim kullanmış | **H7** |
| K2'de `perftest_uye_veya_kendisi = t`, `perftest_kalitimla_kullanir = f` olan bir CREATE satırı | **H8** |
| Aynı ifadede tutarlı, iki zaman arasında farklı | **H9**. ACL değişikliği, sunucu günlüğünden araştırılmalı. |
| `db ≠ hgs2_perftest_db` | **H6** |

---

## 12. Gerçek veritabanına geçmeden önce salt okunur doğrulama sorguları (ÇALIŞTIRILMADI)

**Koşullar:**
- Ayrı onayla, yalnızca `hgs2_perftest_db`'ye bağlanılarak çalıştırılmalıdır.
- `<denetim_rolu>` yer tutucudur.
- Q2–Q4 rol **oluşturulduktan sonra** ve denetimden **önce** çalıştırılır.
- Hepsi aşağıdaki çerçeve içinde çalıştırılır:
  ```sql
  BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
  SET LOCAL search_path = pg_catalog, pg_temp;
  -- (sorgu)
  ROLLBACK;
  ```

**Q1: Hedef sürüm.** Beklenen: 18.6 ve test kapsamındaki platform.
```sql
SELECT current_setting('server_version'), current_setting('server_version_num');
```

**Q2: Betiğin ihtiyaç duyduğu yetkiler audit rolünde etkin mi?** Beklenen: üç sorgu da **0 satır**.
```sql
-- Q2a: 21 katalog ilişkisi
SELECT v.rel
FROM (VALUES ('pg_roles'), ('pg_auth_members'), ('pg_database'), ('pg_db_role_setting'),
             ('pg_namespace'), ('pg_class'), ('pg_attribute'), ('pg_depend'),
             ('pg_constraint'), ('pg_type'), ('pg_proc'), ('pg_trigger'),
             ('pg_event_trigger'), ('pg_extension'), ('pg_foreign_server'),
             ('pg_foreign_data_wrapper'), ('pg_user_mappings'), ('pg_policy'),
             ('pg_default_acl'), ('pg_largeobject_metadata'), ('pg_stat_ssl')) AS v(rel)
WHERE NOT has_table_privilege('<denetim_rolu>', 'pg_catalog.' || v.rel, 'SELECT');

-- Q2b: kullanılan yerleşik fonksiyonlar (pg_control_system dahil)
SELECT p.oid::regprocedure AS fonksiyon, p.proacl::text
FROM pg_proc p
WHERE p.pronamespace = 'pg_catalog'::regnamespace
  AND p.proname IN ('now', 'statement_timestamp', 'pg_current_xact_id_if_assigned',
                    'current_setting', 'current_database', 'regexp_replace', 'host',
                    'inet_server_addr', 'inet_server_port', 'pg_is_in_recovery',
                    'pg_backend_pid', 'lower', 'has_function_privilege', 'pg_control_system',
                    'pg_has_role', 'pg_get_userbyid', 'has_database_privilege', 'aclexplode',
                    'acldefault', 'has_schema_privilege', 'to_regnamespace',
                    'has_table_privilege', 'has_any_column_privilege', 'has_sequence_privilege',
                    'unnest', 'split_part', 'substr', 'strpos', 'string_agg',
                    'pg_get_constraintdef', 'format_type', 'to_regclass',
                    'pg_get_function_identity_arguments', 'pg_get_expr', 'bool_or', 'bool_and',
                    'count', 'pg_stat_get_activity', 'has_server_privilege')
  AND NOT has_function_privilege('<denetim_rolu>', p.oid, 'EXECUTE');

-- Q2c: veritabanı ve şema
SELECT x.kontrol
FROM (VALUES
  ('CONNECT hgs2_perftest_db', has_database_privilege('<denetim_rolu>', 'hgs2_perftest_db', 'CONNECT')),
  ('USAGE pg_catalog',         has_schema_privilege('<denetim_rolu>', 'pg_catalog', 'USAGE')),
  ('USAGE public',             has_schema_privilege('<denetim_rolu>', 'public', 'USAGE'))
) AS x(kontrol, ok)
WHERE NOT x.ok;
```
Ek olarak `pg_control_system` için PUBLIC'in ve audit rolünün durumu `proacl` ile görülür: `SELECT proacl FROM pg_proc WHERE oid = 'pg_catalog.pg_control_system()'::regprocedure;`. NULL, stok PUBLIC EXECUTE demektir.

**Q3: Audit rolünde fazlalık var mı?** Sahiplik, üyelik, öznitelik ve ayar. Bu sorgu P8'in görmediklerini kapsar.
```sql
WITH a AS (SELECT oid, * FROM pg_roles WHERE rolname = '<denetim_rolu>')
SELECT a.rolsuper, a.rolcreatedb, a.rolcreaterole, a.rolreplication, a.rolbypassrls,
       a.rolcanlogin, a.rolconnlimit, a.rolvaliduntil,
       (SELECT count(*) FROM pg_database d WHERE d.datdba = a.oid)                AS sahip_olunan_db,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype = 'o')                            AS sahip_olunan_nesne_tum_dbler,
       (SELECT count(*) FROM pg_auth_members m WHERE m.member = a.oid)            AS dogrudan_uyelik,
       (SELECT count(*) FROM pg_roles r
         WHERE r.oid <> a.oid AND pg_has_role(a.oid, r.oid, 'MEMBER'))            AS toplam_uyelik,
       pg_has_role(a.oid, 'hgs2_perftest', 'MEMBER')                              AS perftest_uyesi,
       (SELECT count(*) FROM pg_db_role_setting s WHERE s.setrole = a.oid)        AS kalici_ayar,
       has_database_privilege(a.oid, 'hgs2_perftest_db', 'CREATE')                AS db_create,
       has_database_privilege(a.oid, 'hgs2_perftest_db', 'TEMPORARY')             AS db_temporary,
       has_database_privilege(a.oid, 'hibrit_giris_db', 'CONNECT')                AS hibrit_connect_acl,
       has_schema_privilege(a.oid, 'public', 'CREATE')                            AS public_create
FROM a;
```

Q3 için beklenen değerler:

| Sütun | Beklenen |
|---|---|
| `rolsuper`, `rolcreatedb`, `rolcreaterole`, `rolreplication`, `rolbypassrls` | `f` |
| `rolcanlogin` | `t` |
| `sahip_olunan_db`, `sahip_olunan_nesne_tum_dbler` | **0** |
| `dogrudan_uyelik`, `toplam_uyelik` | **0** |
| `perftest_uyesi` | `f` |
| `kalici_ayar` | 0 |
| `db_create`, `public_create` | `f` |
| `db_temporary` | `t` olabilir (PUBLIC, kabul edilen fazlalık) |
| `hibrit_connect_acl` | `t` ise `pg_hba.conf` kısıtlaması **zorunlu** hale gelir |

Not: `toplam_uyelik` yalnızca açık üyelikleri sayar; `pg_database_owner` örtük üyeliği `sahip_olunan_db` ile yakalanır.

**Q4: Audit rolü PUBLIC yoluyla veri erişimi kazanıyor mu?** Beklenen: tablo satırı **0**, `lo_compat_privileges = off`, PUBLIC'e açık LO **0**.
```sql
SELECT n.nspname, c.relname, c.relkind
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND has_table_privilege('<denetim_rolu>', c.oid, 'SELECT');

SELECT current_setting('lo_compat_privileges') AS lo_compat_privileges;

SELECT count(*) AS public_veya_audit_okuyabilir_lo
FROM pg_largeobject_metadata m
CROSS JOIN LATERAL aclexplode(m.lomacl) AS x
WHERE x.privilege_type = 'SELECT'
  AND (x.grantee = 0 OR x.grantee = (SELECT oid FROM pg_roles WHERE rolname = '<denetim_rolu>'));
```

**Q5:** Bölüm 11'deki **K1 ve K2**.

---

## 13. Kararlar

### Karar 1: Audit rolü oluşturmak gerekli mi?

**Evet. Ayrı, süper kullanıcı olmayan, hiçbir role üye olmayan ve hiçbir nesnenin sahibi olmayan bir `LOGIN` rolü gereklidir.**

Gerekçeler:
- `hgs2_perftest` hem denetlenen roldür hem de muhtemelen nesne sahibidir. Bu Bölüm 11'de doğrulanacaktır.
  - Sahiplikten gelen ALTER / DROP / TRUNCATE / GRANT ve `pg_database_owner` yetkileri denetimin hiçbir adımında gerekmez.
  - P8 bunları algılamadığı için `hgs2_perftest` ile yapılan bir çalıştırma **uyarısız PASS** verir. Bu, minimum yetki ilkesinin sessizce ihlali olur.
- Testlerdeki `hgs2_auditor` rolü bu profilin yeterli olduğunu dört sürümde gösterdi [K].

Rol oluşturmanın kendisi için notlar:
- Rol oluşturma **küme geneli** bir değişikliktir (`pg_authid`).
- `hibrit_giris_db` aynı kümedeyse yeni rol o veritabanında da PUBLIC yetkilerine sahip olur.
- Bu yüzden rol oluşturma, `pg_hba.conf` kısıtlamasıyla birlikte ve ayrı onayla yapılmalıdır.
- Bu aşamada yapılmamıştır.

### Karar 2: Hangi minimum yetkiler gerekiyor?

Tümü `hgs2_perftest_db` içinde:

| # | Yetki | Stok PG 18.6'da kaynağı |
|---|---|---|
| 1 | Rol özniteliği: `LOGIN` | Rol oluşturulurken. Diğer bütün öznitelikler kapalı: `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`. |
| 2 | `CONNECT` on `hgs2_perftest_db` + `pg_hba.conf` kuralı (yalnızca bu veritabanı) | PUBLIC; `pg_hba.conf` yöneticiden |
| 3 | `USAGE` on schema `pg_catalog` | PUBLIC |
| 4 | `USAGE` on schema `public` (5.8 için) [S] | PUBLIC |
| 5 | `SELECT` on 21 katalog ilişkisi (Bölüm 1.1) | PUBLIC |
| 6 | `EXECUTE` on kullanılan yerleşik fonksiyonlar (Bölüm 1.2) | PUBLIC |
| 7 | `EXECUTE` on `pg_catalog.pg_control_system()` | PUBLIC [S] |

- **Stok kurulumda bunların tamamı PUBLIC'ten gelir. Hiçbir GRANT gerekmez.**
- Q2 bir eksik gösterirse yalnızca o yetki, yalnızca audit rolüne ve yalnızca `hgs2_perftest_db`'de verilir (Bölüm 10).
- **Gerekmeyenler** (verilmemeli):
  - tablo verisi SELECT,
  - sequence / büyük nesne / foreign server yetkileri,
  - CREATE ve TEMPORARY,
  - `hibrit_giris_db` CONNECT,
  - herhangi bir rol üyeliği,
  - herhangi bir sahiplik.

### Karar 3: Gerçek veritabanına geçmeden önce hangi kontroller eksik?

1. **CREATE çelişkisinin çözülmesi.** Çelişen iki sorgunun metni, veritabanı, rol ve sürüm bilgisi toplanmalı ve K1/K2 çalıştırılmalı (Bölüm 11). H5 doğrulanırsa (`public` şemasında PUBLIC CREATE), yeni audit rolü de CREATE kazanır. Bu durum rol oluşturulmadan önce bilinmelidir.
2. **Hedefin gerçek sürümü ve platformu** (Q1). 18.6 dışı bir sürüm, Linux, unix soketi, pooler veya SCRAM kullanımı **NEEDS REVIEW** kapsamındadır (FINAL_DELIVERY §8).
3. **PUBLIC varsayılanlarının hedefte doğrulanması** (Q2). Özellikle:
   - `hgs2_perftest_db` içindeki `pg_control_system` `proacl` değeri,
   - `hgs2_perftest_db` `datacl`,
   - `public` şeması ACL'si.

   Testlerdeki "proacl = NULL" gözlemi incelenen kanıtlarda izlenebilir değil; anlık görüntüler sertleştirilmiş durumu gösteriyor.
4. **Bölüm 5.8 `public` USAGE bağımlılığının test kümesinde doğrulanması** [S]. `public` USAGE PUBLIC'ten geri alınmış bir kopyada betiğin işaretçisiz çıkış 3 ile durduğu gösterilmeli. Hedefte de USAGE'ın etkin olduğu Q2c ile teyit edilmeli.
5. **Audit rolünün fazlalık kontrolü** (Q3). Bu, P8'in kapsamadığı alanları kapatır:
   - sahiplik (tüm veritabanları, `pg_shdepend`),
   - veritabanı sahipliği,
   - `hgs2_perftest` üyeliği,
   - CREATEDB,
   - kalıcı ayarlar.

   Ayrıca rolü kimin oluşturduğu kaydedilmeli; PG 16+'da oluşturan role ADMIN üyelik verilir.
6. **`hibrit_giris_db` erişiminin kapatıldığının doğrulanması.** Yeni rol için `has_database_privilege(..., 'hibrit_giris_db', 'CONNECT')` sonucu ve `pg_hba.conf` kuralı yönetici tarafından ayrı bir adımda doğrulanmalı. Betik `pg_hba.conf`'u sorgulamaz.
7. **PUBLIC yoluyla veri erişiminin kontrolü** (Q4): kullanıcı tablolarında PUBLIC SELECT, `lo_compat_privileges` ve büyük nesnelerde PUBLIC SELECT.
8. **Sertleştirilmiş katalog senaryosunun testi.** Katalog SELECT veya fonksiyon EXECUTE'unun PUBLIC'ten geri alındığı kurulum test edilmedi (KNOWN_LIMITATIONS 21). Hedef sertleştirilmişse önce test kümesinde denenmeli.
9. **Önceki teslim belgelerinde açık kalan operasyonel kararlar:**
   - `expected_system_identifier`'ın `pg_controldata` ile bağımsız kanaldan alınması (Bölüm 3.4),
   - parola yöntemi (FINAL_DELIVERY §5.8: belgelenmemiş),
   - `verify-full` bağlantı dizesi,
   - çıktı saklama yeri ve erişimi (§5.9: belgelenmemiş).

**Hash doğrulaması:** Analizden önce ve sonra hesaplanan `postgresql_readonly_audit_v2.sql` SHA-256 değeri `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`. Nihai SQL dosyası değişmedi.
