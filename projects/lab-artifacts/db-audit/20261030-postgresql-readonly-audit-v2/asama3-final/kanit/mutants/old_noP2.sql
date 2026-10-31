-- =============================================================================
-- HGS2 — PostgreSQL veritabanı izolasyonu: salt okunur katalog denetimi (v2)
-- Hazırlanma: 2026-10-30 (+03:00)
-- =============================================================================
--
-- KAYNAK
--   * Bu dosya aşağıdaki orijinal betiğin düzeltilmiş YENİ sürümüdür. Orijinal
--     dosya değiştirilmedi; kanıt olarak olduğu gibi korunur:
--       hgs2-lab-artifacts\hgs2-evidence\
--         surefire-20261023T180529-HgsApplicationTests-default-profile\
--         postgresql_readonly_audit.sql
--       SHA-256: 3423053a254ca6ff361631562e9e9a26e112fddd4e4ea5a5a9b539c0e984c7ff
--
-- UYARI
--   * Bu dosya henüz ÇALIŞTIRILMADI. Hiçbir PostgreSQL sunucusunda ve hiçbir
--     SQL ayrıştırıcısında denenmedi; yalnızca statik (elle) incelendi.
--   * Bağlantı hedefi YALNIZCA hgs2_perftest_db olmalıdır.
--   * hibrit_giris_db veritabanına BAĞLANILMAMALIDIR.
--   * Dosya DDL/DML, rol değişikliği veya yetki değişikliği İÇERMEZ. Tek ayar
--     komutları, transaction sonunda kendiliğinden geri alınan iki
--     SET LOCAL zaman aşımı ayarıdır (P4).
--
-- KULLANIM (yalnızca ayrı ve yetkili bir onaydan sonra)
--   * YALNIZCA psql 10 veya üzeri ile ve YALNIZCA -f ile:
--       psql -X -v ON_ERROR_STOP=1
--            -h <host> -p <port> -d hgs2_perftest_db -U <denetim_rolu>
--            -v expected_host=<psql'e verilen host>
--            -v expected_port=<psql'e verilen port>
--            -v expected_server_addr=<sunucunun gördüğü adres veya local-socket>
--            -v expected_server_port=<sunucunun dinlediği port>
--            [-v expected_system_identifier=<küme sistem kimliği>]
--            [-v audit_statement_timeout=30s] [-v audit_lock_timeout=5s]
--            [-v allow_superuser=1]
--            -f postgresql_readonly_audit_v2.sql
--   * -1 / --single-transaction KULLANILMAMALIDIR (betik algılar ve durur).
--   * Etkileşimli bir oturumda \i ile ÇALIŞTIRILMAMALIDIR. Açık bir
--     transaction içinde \i ile çalıştırılırsa durdurma hatası o transaction'ı
--     "aborted" durumuna düşürür; kullanıcının kaydedilmemiş işi kaybolur.
--   * Parola komut satırında, URL'de veya PGPASSWORD içinde verilmemelidir.
--   * Ağ bağlantısında sslmode=verify-full ve sslrootcert kullanılmalıdır;
--     sunucuyu kriptografik olarak doğrulayan tek mekanizma budur.
--
-- ÇIKIŞ KODLARI VE İŞARETÇİLER (otomasyon ikisini birlikte değerlendirmeli)
--   psql 0 + stdout'ta HGS2_AUDIT_COMPLETE  -> denetim tamamlandı
--   psql 0 + HGS2_AUDIT_COMPLETE yok        -> BAŞARISIZ say (beklenmeyen durum)
--   psql 3 + stderr'de HGS2_AUDIT_ABORT:    -> güvenlik kontrolü nedeniyle durdu
--   psql 3 + işaretçi yok                   -> SQL/yetki hatası; denetim eksik
--   psql 2                                  -> bağlantı hatası
--   psql 1                                  -> psql'in kendi hatası
--   Durdurma yöntemi: önce \echo ile işaretçi yazılır, ardından yan etkisiz ve
--   kasıtlı bir tür dönüştürme hatası üretilir:
--     SELECT 'HGS2_AUDIT_ABORT: <neden>'::pg_catalog.int4;
--   ON_ERROR_STOP açıkken psql bu hatada çıkış kodu 3 ile çıkar; hata mesajı
--   işaretçiyi stderr'e taşır. Arkasındaki \quit, ON_ERROR_STOP bir şekilde
--   kapalıysa betiğin yine de durması için ikinci emniyettir.
--
-- DEĞİŞİKLİK LİSTESİ (v1 -> v2)
--   S1  READ ONLY durumu \gset + \if ile doğrulanır; değilse betik durur (P4).
--   S2  BEGIN öncesinde açık transaction algılanır (psql -1 / önceden açık
--       transaction); xid atanmışsa ayrı nedenle durur (P2). BEGIN'in gerçekten
--       yeni transaction başlattığı izolasyon düzeyiyle de doğrulanır (P4).
--   S3  Hedef doğrulama: sunucu tarafı veritabanı adı + istemci DBNAME +
--       hibrit_giris_db negatif kontrolü (Bölüm 0); istemci host/port, sunucu
--       adres/port (P6); isteğe bağlı system_identifier (P7).
--   S4  Tüm durdurmalar sıfır olmayan çıkış kodu (3) üretir;
--       başarı HGS2_AUDIT_COMPLETE ile işaretlenir.
--   S5  5.4 başlığı düzeltildi (tüm grantee'ler); etkin yetki matrisi (5.4a),
--       PG17+ MAINTAIN (5.4b), sütun ACL'leri (5.4c), varsayılan ACL'ler
--       (5.4d) ve identity sequence yetkileri (5.5b) eklendi.
--   S6  5.9: yalnızca beklenen 4 tabloya bağlı identity sequence'lar dışlanır;
--       kalan her satırın nedeni yazılır.
--   S7  5.5, 5.5b, 5.9 ve 5.17 aynı identity sequence tanımını kullanır.
--   S8  Bölüm 4: ALTER ROLE ALL (setrole = 0 ve setdatabase = 0) dahil
--       dört kapsamın tamamı denetlenir.
--   S9  Bölüm 4: ayar değerleri izin listesi dışında maskelenir; güvenlik
--       açısından önemli ayarlar işaretlenir.
--   S10 SET LOCAL statement_timeout / lock_timeout (P4).
--   S11 psql 10+ kontrolü (P1); ON_ERROR_STOP, AUTOCOMMIT ve
--       ON_ERROR_ROLLBACK psqlrc'den bağımsız olarak dosyanın başında ayarlanır.
--   Ek  Süper kullanıcıyla bağlantı allow_superuser olmadan durdurulur (P8).
--   Ek  REPEATABLE READ: bütün bölümler aynı anlık görüntüyü okur.
--   Ek  ROLLBACK sonrasında açık transaction kalmadığı doğrulanır.
--
-- KAPSAM VE SINIRLAR (v1'den korunur)
--   * Yalnızca sistem katalogları (pg_catalog) ve yetki/ACL metaverisi okunur.
--   * Hiçbir kullanıcı tablosu satırı, parmak izi verisi veya büyük nesne
--     (large object) içeriği okunmaz; büyük nesneler için yalnızca
--     pg_largeobject_metadata üzerinden sayı ve sahip bilgisi alınır.
--   * pg_authid (parola özetleri) kullanılmaz; pg_roles.rolpassword seçilmez.
--   * Bölüm 2–4'teki pg_roles, pg_auth_members, pg_database ve
--     pg_db_role_setting PAYLAŞILAN kataloglardır: hgs2_perftest_db üzerinden
--     okunduklarında küme genelindeki durumu gösterirler.
--   * Bölüm 5 yalnızca BAĞLI OLUNAN veritabanının (hgs2_perftest_db) şemasını
--     gösterir; hibrit_giris_db hakkında HİÇBİR sonuç çıkarılamaz.
--   * Katalog okuma yetkileri varsayılan kurulum için varsayıldı; DOĞRULANMADI.
--   * pg_hba.conf / pg_hba_file_rules SORGULANMAZ; gerçek bağlantı davranışı
--     yetkili bir yönetici tarafından ayrı ve onaylı bir adımda doğrulanmalıdır.
--
-- BEKLENEN REFERANS DEĞERLER (gerçek durum DEĞİL; sonuçlarla doğrulanacak)
--   * 4 tablo: admins, devices, logs, users (şema: public varsayıldı)
--   * 4 identity sequence
--   * 4 primary key, 3 unique, 2 foreign key
--   * users.parmak_izi_sablonu türü: oid (23 Ekim Surefire günlüğündeki DDL'e göre)
-- =============================================================================

-- psqlrc'den veya komut satırından gelebilecek farklı değerlere karşı (S11)
\set ON_ERROR_STOP on
\set AUTOCOMMIT on
\set ON_ERROR_ROLLBACK off

-- -----------------------------------------------------------------------------
-- P1. psql istemci sürümü (S11)
--     psql 10+ VERSION_NUM değişkenini tanımlar. Daha eski psql'de değişken
--     tanımsız kalır, satır sunucuya ham haliyle gider ve sözdizimi hatası
--     verir; ON_ERROR_STOP nedeniyle psql çıkış kodu 3 ile durur (işaretçisiz
--     "hata" sınıfı). Eski psql \if komutunu tanımadığı için bu kontrol,
--     herhangi bir \if'ten önce gelen ilk SQL ifadesidir.
-- -----------------------------------------------------------------------------
SELECT COALESCE(:'VERSION_NUM'::pg_catalog.int4 >= 100000, false)        AS psql_v10_or_newer,
       COALESCE(:'SERVER_VERSION_NUM'::pg_catalog.int4 >= 130000, false) AS server_v13_or_newer,
       COALESCE(:'SERVER_VERSION_NUM'::pg_catalog.int4 >= 100000, false) AS server_v10_or_newer
\gset

\if :psql_v10_or_newer
\else
  \echo 'HGS2_AUDIT_ABORT: psql_too_old (psql 10 veya uzeri gerekli)'
  SELECT 'HGS2_AUDIT_ABORT: psql_too_old'::pg_catalog.int4;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- P2. BEGIN'den ÖNCE: açık transaction var mı? (S2)
--     Transaction'ın ilk komutunda now() ile statement_timestamp() eşittir.
--     Autocommit modunda bu SELECT kendi örtük transaction'ının ilk komutudur:
--     değerler eşittir. psql -1 kullanıldıysa veya transaction önceden
--     açıldıysa now() o transaction'ın başlangıcıdır: değerler farklıdır.
--     Ayrım:
--       * xid atanmış  -> transaction daha önce yazma yapmış; psql -1'in
--                         kendi BEGIN'i bunu üretmez. Önceden açılmış ve
--                         kaydedilmemiş iş içeren bir transaction.
--       * xid yok      -> psql -1 VEYA önceden açılmış, yazma yapmamış
--                         transaction. Sunucu tarafında kesin ayrım yok;
--                         open_tx_age_ms yalnızca ipucudur (-1'de genelde
--                         birkaç ms).
--     Her iki durumda da betik durur.
-- -----------------------------------------------------------------------------
\if :server_v13_or_newer
SELECT pg_catalog.now() = pg_catalog.statement_timestamp()             AS no_open_tx,
       pg_catalog.pg_current_xact_id_if_assigned() IS NOT NULL          AS open_tx_has_xid,
       pg_catalog.round(EXTRACT(epoch FROM (pg_catalog.statement_timestamp()
                                            - pg_catalog.now())) * 1000)::pg_catalog.int8
                                                                         AS open_tx_age_ms
\gset
\elif :server_v10_or_newer
SELECT pg_catalog.now() = pg_catalog.statement_timestamp()             AS no_open_tx,
       pg_catalog.txid_current_if_assigned() IS NOT NULL                AS open_tx_has_xid,
       pg_catalog.round(EXTRACT(epoch FROM (pg_catalog.statement_timestamp()
                                            - pg_catalog.now())) * 1000)::pg_catalog.int8
                                                                         AS open_tx_age_ms
\gset
\else
-- PostgreSQL 10 öncesi: xid bilgisi alınmaz (sürüm kapısı zaten durduracak).
SELECT pg_catalog.now() = pg_catalog.statement_timestamp()             AS no_open_tx,
       false                                                            AS open_tx_has_xid,
       pg_catalog.round(EXTRACT(epoch FROM (pg_catalog.statement_timestamp()
                                            - pg_catalog.now())) * 1000)::pg_catalog.int8
                                                                         AS open_tx_age_ms
\gset
\endif


-- -----------------------------------------------------------------------------
-- P3. Salt okunur ve tutarlı anlık görüntülü transaction
--     REPEATABLE READ: bütün sorgular aynı anlık görüntüyü okur (sorguların
--     anlamını değiştirmez; yalnızca bölümler arası tutarlılık sağlar).
-- -----------------------------------------------------------------------------
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;

-- İşlemin gerçekten salt okunur olduğunu göster (beklenen: on) — v1'den korunur
SHOW transaction_read_only;

-- -----------------------------------------------------------------------------
-- P4. Zaman aşımları (S10) ve READ ONLY doğrulaması (S1)
--     SET LOCAL yalnızca bu transaction için geçerlidir; ROLLBACK ile geri
--     alınır. Veritabanına hiçbir şey yazmaz. Varsayılanlar -v ile değişir.
-- -----------------------------------------------------------------------------
\if :{?audit_statement_timeout}
\else
  \set audit_statement_timeout '30s'
\endif
\if :{?audit_lock_timeout}
\else
  \set audit_lock_timeout '5s'
\endif

SET LOCAL statement_timeout = :'audit_statement_timeout';
SET LOCAL lock_timeout = :'audit_lock_timeout';

SELECT COALESCE(pg_catalog.current_setting('transaction_read_only') = 'on', false)              AS tx_read_only,
       COALESCE(pg_catalog.current_setting('transaction_isolation') = 'repeatable read', false) AS tx_repeatable_read,
       pg_catalog.current_setting('transaction_read_only')                                     AS tx_read_only_value,
       pg_catalog.current_setting('transaction_isolation')                                     AS tx_isolation_value,
       pg_catalog.current_setting('statement_timeout')                                         AS tx_statement_timeout,
       pg_catalog.current_setting('lock_timeout')                                              AS tx_lock_timeout
\gset

\echo 'transaction_read_only=' :tx_read_only_value ' isolation=' :tx_isolation_value ' statement_timeout=' :tx_statement_timeout ' lock_timeout=' :tx_lock_timeout

\if :tx_read_only
\else
  \echo 'HGS2_AUDIT_ABORT: tx_not_read_only'
  SELECT 'HGS2_AUDIT_ABORT: tx_not_read_only'::pg_catalog.int4;
  \quit
\endif

-- BEGIN yok sayılmış olsaydı (önceden açık transaction) izolasyon düzeyi
-- REPEATABLE READ olmazdı (varsayılan değiştirilmemişse). P2'ye ek emniyet.
\if :tx_repeatable_read
\else
  \echo 'HGS2_AUDIT_ABORT: tx_not_started_by_script'
  SELECT 'HGS2_AUDIT_ABORT: tx_not_started_by_script'::pg_catalog.int4;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 0. Hedef veritabanı denetimi (S3)
--    Bağlı veritabanı hgs2_perftest_db değilse dosya burada durur
--    (çıkış kodu 3; açık işlem sunucu tarafından geri alınır).
--    Bu denetim bağlantı kurulduktan sonra çalışır; yanlış veritabanına
--    BAĞLANMAYI önleyemez, yalnızca orada sorgu çalışmasını engeller.
-- -----------------------------------------------------------------------------
-- v1 sorgusu (değiştirilmedi)
SELECT current_database() AS connected_database,
       current_user       AS connected_role,
       current_database() = 'hgs2_perftest_db' AS on_target_db
\gset

\echo 'Bagli veritabani:' :connected_database ' rol:' :connected_role

-- v2 ek kontroller: üretim veritabanı negatif kontrolü ve istemci tarafı ad
SELECT pg_catalog.current_database() <> 'hibrit_giris_db'  AS not_production_db,
       COALESCE(:'DBNAME' = 'hgs2_perftest_db', false)     AS client_dbname_ok
\gset

\if :not_production_db
\else
  \echo 'HGS2_AUDIT_ABORT: production_database (hibrit_giris_db)'
  SELECT 'HGS2_AUDIT_ABORT: production_database'::pg_catalog.int4;
  \quit
\endif

\if :on_target_db
\else
  \echo 'HGS2_AUDIT_ABORT: wrong_database (hgs2_perftest_db degil)'
  SELECT 'HGS2_AUDIT_ABORT: wrong_database'::pg_catalog.int4;
  \quit
\endif

\if :client_dbname_ok
\else
  \echo 'HGS2_AUDIT_ABORT: client_dbname_mismatch'
  SELECT 'HGS2_AUDIT_ABORT: client_dbname_mismatch'::pg_catalog.int4;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 1. PostgreSQL sürümü
--    Soru: Sunucu sürümü nedir? Sürüme bağlı katalog alanları hangi dalda okunur?
-- -----------------------------------------------------------------------------
SELECT current_setting('server_version_num')::int AS server_version_num,
       current_setting('server_version')          AS server_version;

-- v2: pg17_or_newer eklendi (MAINTAIN yetkisi için)
SELECT current_setting('server_version_num')::int >= 120000 AS pg12_or_newer,
       current_setting('server_version_num')::int >= 160000 AS pg16_or_newer,
       current_setting('server_version_num')::int >= 170000 AS pg17_or_newer
\gset

\if :pg12_or_newer
\else
  \echo 'HGS2_AUDIT_ABORT: server_too_old (PostgreSQL 12 ve uzeri gerekli)'
  SELECT 'HGS2_AUDIT_ABORT: server_too_old'::pg_catalog.int4;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- P6. Beklenen sunucu parametreleri ve istemci/sunucu karşılaştırması (S3)
--     Dört parametre ZORUNLUDUR; eksikse betik durur.
--       expected_host / expected_port               : psql'in bağlandığı hedef
--                                                     (istemci tarafı HOST/PORT)
--       expected_server_addr / expected_server_port : sunucunun gördüğü
--                                                     (inet_server_addr / port)
--     Unix soketinde inet_server_addr() NULL döner ve 'local-socket' olarak
--     karşılaştırılır. Host ve port sunucu kimliğini KANITLAMAZ (DNS, port
--     yönlendirme, SSH tüneli, pooler, failover, TLS doğrulaması olmayan
--     araya girme). Kriptografik doğrulama yalnızca sslmode=verify-full ile
--     sağlanır.
-- -----------------------------------------------------------------------------
\if :{?expected_host}
\else
  \echo 'HGS2_AUDIT_ABORT: missing_parameter expected_host'
  SELECT 'HGS2_AUDIT_ABORT: missing_parameter expected_host'::pg_catalog.int4;
  \quit
\endif
\if :{?expected_port}
\else
  \echo 'HGS2_AUDIT_ABORT: missing_parameter expected_port'
  SELECT 'HGS2_AUDIT_ABORT: missing_parameter expected_port'::pg_catalog.int4;
  \quit
\endif
\if :{?expected_server_addr}
\else
  \echo 'HGS2_AUDIT_ABORT: missing_parameter expected_server_addr'
  SELECT 'HGS2_AUDIT_ABORT: missing_parameter expected_server_addr'::pg_catalog.int4;
  \quit
\endif
\if :{?expected_server_port}
\else
  \echo 'HGS2_AUDIT_ABORT: missing_parameter expected_server_port'
  SELECT 'HGS2_AUDIT_ABORT: missing_parameter expected_server_port'::pg_catalog.int4;
  \quit
\endif

SELECT COALESCE(:'HOST' = :'expected_host', false)                                   AS client_host_ok,
       COALESCE(:'PORT' = :'expected_port', false)                                   AS client_port_ok,
       COALESCE(pg_catalog.host(pg_catalog.inet_server_addr()), 'local-socket')      AS server_addr_text,
       pg_catalog.current_setting('port')                                            AS server_port_text,
       COALESCE(COALESCE(pg_catalog.host(pg_catalog.inet_server_addr()), 'local-socket')
                = :'expected_server_addr', false)                                    AS server_addr_ok,
       COALESCE(pg_catalog.current_setting('port') = :'expected_server_port'
                AND COALESCE(pg_catalog.inet_server_port()::pg_catalog.text,
                             pg_catalog.current_setting('port')) = :'expected_server_port',
                false)                                                               AS server_port_ok,
       COALESCE(:'PORT' <> pg_catalog.current_setting('port'), true)                 AS client_server_port_differ,
       pg_catalog.pg_is_in_recovery()                                                AS server_in_recovery,
       pg_catalog.current_setting('cluster_name')                                    AS server_cluster_name
\gset

\echo 'istemci host=' :HOST ' port=' :PORT ' | sunucu adres=' :server_addr_text ' port=' :server_port_text ' cluster_name=' :server_cluster_name ' recovery=' :server_in_recovery
\if :client_server_port_differ
  \echo 'BILGI: istemci portu ile sunucu portu farkli (proxy, tunel veya pooler olabilir).'
\endif

\if :client_host_ok
\else
  \echo 'HGS2_AUDIT_ABORT: client_host_mismatch'
  SELECT 'HGS2_AUDIT_ABORT: client_host_mismatch'::pg_catalog.int4;
  \quit
\endif
\if :client_port_ok
\else
  \echo 'HGS2_AUDIT_ABORT: client_port_mismatch'
  SELECT 'HGS2_AUDIT_ABORT: client_port_mismatch'::pg_catalog.int4;
  \quit
\endif
\if :server_addr_ok
\else
  \echo 'HGS2_AUDIT_ABORT: server_addr_mismatch'
  SELECT 'HGS2_AUDIT_ABORT: server_addr_mismatch'::pg_catalog.int4;
  \quit
\endif
\if :server_port_ok
\else
  \echo 'HGS2_AUDIT_ABORT: server_port_mismatch'
  SELECT 'HGS2_AUDIT_ABORT: server_port_mismatch'::pg_catalog.int4;
  \quit
\endif

-- -----------------------------------------------------------------------------
-- P7. İsteğe bağlı küme kimliği: system_identifier (S3)
--     Yalnızca expected_system_identifier verilmişse çalışır.
--     pg_control_system() PostgreSQL 9.6+ (sürüm kapısı 12+ istediği için
--     her zaman mevcut). Çalıştırma yetkisi kuruluma göre değişebilir; önce
--     has_function_privilege ile kontrol edilir, yetki yoksa işaretçili
--     durdurma yapılır (işaretçisiz yetki hatası yerine).
--     Fiziksel replikalar primary ile AYNI system_identifier'ı paylaşır;
--     server_in_recovery (P6) birlikte okunmalıdır.
-- -----------------------------------------------------------------------------
\if :{?expected_system_identifier}
SELECT COALESCE(pg_catalog.has_function_privilege('pg_catalog.pg_control_system()', 'EXECUTE'), false)
           AS can_read_control_system
\gset
  \if :can_read_control_system
SELECT cs.system_identifier::pg_catalog.text                                           AS server_system_identifier,
       COALESCE(cs.system_identifier::pg_catalog.text = :'expected_system_identifier', false)
                                                                                       AS system_identifier_ok
FROM pg_catalog.pg_control_system() AS cs
\gset
    \echo 'sunucu system_identifier=' :server_system_identifier
    \if :system_identifier_ok
    \else
      \echo 'HGS2_AUDIT_ABORT: system_identifier_mismatch'
      SELECT 'HGS2_AUDIT_ABORT: system_identifier_mismatch'::pg_catalog.int4;
      \quit
    \endif
  \else
    \echo 'HGS2_AUDIT_ABORT: system_identifier_unverifiable (pg_control_system icin EXECUTE yetkisi yok)'
    SELECT 'HGS2_AUDIT_ABORT: system_identifier_unverifiable'::pg_catalog.int4;
    \quit
  \endif
\else
  \echo 'BILGI: expected_system_identifier verilmedi; kume kimligi dogrulanmadi (host/port kriptografik kimlik DEGILDIR).'
\endif

-- -----------------------------------------------------------------------------
-- P8. En az yetki: süper kullanıcı bağlantısı
--     allow_superuser tanımlı değilse süper kullanıcıyla çalıştırma durdurulur.
-- -----------------------------------------------------------------------------
SELECT COALESCE(pg_catalog.current_setting('is_superuser') = 'on', false) AS connected_as_superuser
\gset

\if :connected_as_superuser
  \if :{?allow_superuser}
    \echo 'UYARI: denetim super kullaniciyla calisiyor (allow_superuser verildi).'
  \else
    \echo 'HGS2_AUDIT_ABORT: superuser_connection (allow_superuser verilmedi)'
    SELECT 'HGS2_AUDIT_ABORT: superuser_connection'::pg_catalog.int4;
    \quit
  \endif
\endif

\echo 'HGS2_AUDIT_PREFLIGHT_OK'

-- -----------------------------------------------------------------------------
-- 2. Rol özellikleri — hgs2_perftest (v1'den değiştirilmeden korunur)
-- -----------------------------------------------------------------------------

-- 2.1 Rol var mı? (Yoksa aşağıdaki rol sorguları boş döner, hata vermez.)
SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'hgs2_perftest')
       AS perftest_role_exists;

-- 2.2 Rol öznitelikleri
--     Beklenen güvenli değerler: rolsuper, rolcreatedb, rolcreaterole,
--     rolreplication, rolbypassrls = false. rolcanlogin = true (uygulama girişi).
--     rolinherit = false ise rol NOINHERIT'tir.
--     rolconnlimit = -1 sınırsız demektir. rolvaliduntil NULL ise süresizdir.
SELECT rolname,
       rolsuper,
       rolcreatedb,
       rolcreaterole,
       rolreplication,
       rolbypassrls,
       rolinherit,
       rolcanlogin,
       rolconnlimit,
       rolvaliduntil
FROM pg_catalog.pg_roles
WHERE rolname = 'hgs2_perftest';

-- 2.3 Doğrudan rol üyelikleri (hgs2_perftest hangi rollerin üyesi?)
--     PostgreSQL 16+: inherit_option ve set_option üyelik başına tutulur.
--     PostgreSQL 12–15: bu sütunlar YOKTUR; kalıtım üyenin rolinherit değerine
--     bağlıdır. Sütunlar yalnızca desteklenen sürümde seçilir.
\if :pg16_or_newer
SELECT g.rolname                   AS granted_role,
       g.rolsuper                  AS granted_role_is_superuser,
       m.admin_option,
       m.inherit_option,
       m.set_option,
       pg_catalog.pg_get_userbyid(m.grantor) AS grantor
FROM pg_catalog.pg_auth_members m
JOIN pg_catalog.pg_roles r ON r.oid = m.member
JOIN pg_catalog.pg_roles g ON g.oid = m.roleid
WHERE r.rolname = 'hgs2_perftest'
ORDER BY g.rolname;
\else
SELECT g.rolname                   AS granted_role,
       g.rolsuper                  AS granted_role_is_superuser,
       m.admin_option,
       r.rolinherit                AS member_inherits,
       pg_catalog.pg_get_userbyid(m.grantor) AS grantor
FROM pg_catalog.pg_auth_members m
JOIN pg_catalog.pg_roles r ON r.oid = m.member
JOIN pg_catalog.pg_roles g ON g.oid = m.roleid
WHERE r.rolname = 'hgs2_perftest'
ORDER BY g.rolname;
\endif

-- 2.4 Doğrudan ve DOLAYLI üyelikler ile üyelik yoluyla kullanılabilen yetkiler
--     pg_has_role(..., 'MEMBER'): doğrudan veya dolaylı üyelik var mı?
--     pg_has_role(..., 'USAGE') : o rolün yetkileri SET ROLE yapmadan
--                                 kullanılabiliyor mu (kalıtım)?
--     Özellikle izlenmesi gerekenler: süper kullanıcı roller, postgres,
--     pg_read_all_data, pg_write_all_data, pg_read_server_files,
--     pg_write_server_files, pg_execute_server_program.
--     Sürümden bağımsızdır (sürüme bağlı sütun kullanmaz).
--     Not: hgs2_perftest süper kullanıcıysa pg_has_role tüm roller için true
--     döner; bu durumda 2.2 sonucu belirleyicidir.
WITH me AS (
    SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'hgs2_perftest'
)
SELECT r.rolname                                      AS role_name,
       r.rolsuper                                     AS role_is_superuser,
       pg_catalog.pg_has_role(me.oid, r.oid, 'USAGE') AS privileges_usable_without_set_role
FROM me
JOIN pg_catalog.pg_roles r ON r.oid <> me.oid
WHERE pg_catalog.pg_has_role(me.oid, r.oid, 'MEMBER')
ORDER BY r.rolname;

-- -----------------------------------------------------------------------------
-- 3. Veritabanı erişimleri — hibrit_giris_db ve hgs2_perftest_db
--    (v1'den değiştirilmeden korunur; yalnızca 3.1 yorumu genişletildi)
-- -----------------------------------------------------------------------------

-- 3.1 Sahiplik ve bağlantı ayarları (pg_database paylaşılan katalogdur)
--     datallowconn = false ise hiçbir rol bağlanamaz.
--     datconnlimit = -1 sınırsız demektir. Yeni sürümlerde -2, yarıda kalmış
--     DROP DATABASE sonrası GEÇERSİZ veritabanını gösterir (hangi alt
--     sürümden itibaren olduğu burada doğrulanmadı).
--     using_default_acl = true ise datacl NULL'dır; bu "yetki yok" DEĞİL,
--     varsayılan ACL demektir (varsayılan: PUBLIC'e CONNECT ve TEMPORARY).
SELECT d.datname,
       pg_catalog.pg_get_userbyid(d.datdba) AS owner,
       d.datallowconn,
       d.datconnlimit,
       d.datistemplate,
       (d.datacl IS NULL)                   AS using_default_acl
FROM pg_catalog.pg_database d
WHERE d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db')
ORDER BY d.datname;

-- 3.2 hgs2_perftest için ETKİN veritabanı yetkileri
--     has_database_privilege; doğrudan yetkiyi, PUBLIC yetkisini ve kalıtımla
--     gelen rol üyeliklerini birlikte hesaba katar.
--     Güvenli beklenti: hibrit_giris_db için perftest_connect = false.
--     Not: Bu yalnızca ACL sonucudur; pg_hba.conf kuralları burada görünmez.
WITH me AS (
    SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'hgs2_perftest'
)
SELECT d.datname,
       pg_catalog.has_database_privilege(me.oid, d.oid, 'CONNECT')   AS perftest_connect,
       pg_catalog.has_database_privilege(me.oid, d.oid, 'CREATE')    AS perftest_create,
       pg_catalog.has_database_privilege(me.oid, d.oid, 'TEMPORARY') AS perftest_temporary
FROM pg_catalog.pg_database d
CROSS JOIN me
WHERE d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db')
ORDER BY d.datname;

-- 3.3 Açık ACL girdileri (NULL ACL, acldefault ile varsayılana açılır)
--     grantee = PUBLIC olan CONNECT / TEMPORARY satırları, herkesin bu
--     veritabanına ACL düzeyinde erişebildiğini gösterir.
SELECT d.datname,
       CASE WHEN a.grantee = 0 THEN 'PUBLIC'
            ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
       pg_catalog.pg_get_userbyid(a.grantor)               AS grantor,
       a.privilege_type,
       a.is_grantable,
       (d.datacl IS NULL)                                  AS from_default_acl
FROM pg_catalog.pg_database d
CROSS JOIN LATERAL pg_catalog.aclexplode(
           COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))) AS a
WHERE d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db')
ORDER BY d.datname, grantee, a.privilege_type;

-- 3.4 Yalnızca PUBLIC'in CONNECT ve TEMPORARY durumu (özet)
SELECT d.datname,
       bool_or(a.grantee = 0 AND a.privilege_type = 'CONNECT')   AS public_connect,
       bool_or(a.grantee = 0 AND a.privilege_type = 'TEMPORARY') AS public_temporary,
       bool_and(d.datacl IS NULL)                                AS from_default_acl
FROM pg_catalog.pg_database d
CROSS JOIN LATERAL pg_catalog.aclexplode(
           COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))) AS a
WHERE d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db')
GROUP BY d.datname
ORDER BY d.datname;

-- -----------------------------------------------------------------------------
-- 4. Rol / veritabanı oturum ayarları (pg_db_role_setting, paylaşılan katalog)
--    Soru: hgs2_perftest rolüne, iki veritabanına veya TÜM rollere/veritabanlarına
--    bağlı kalıcı oturum ayarları (ör. search_path, role) var mı?
--    v2 (S8, S9): Dört kapsamın tamamı denetlenir; her ayar ayrı satırdır;
--    değerler izin listesi dışında maskelenir.
--      Kapsam 1: setrole = hgs2_perftest, setdatabase = hedef veritabanı
--                (ALTER ROLE hgs2_perftest IN DATABASE ... SET)
--      Kapsam 2: setrole = hgs2_perftest, setdatabase = 0
--                (ALTER ROLE hgs2_perftest SET)
--      Kapsam 3: setrole = 0, setdatabase = hedef veritabanı
--                (ALTER DATABASE ... SET ve ALTER ROLE ALL IN DATABASE ... SET;
--                 ikisi katalogda aynı biçimde saklanır)
--      Kapsam 4: setrole = 0, setdatabase = 0
--                (ALTER ROLE ALL SET — v1'de denetim DIŞINDA kalıyordu)
--    Maskeleme: ayar ADI her zaman gösterilir; DEĞER yalnızca aşağıdaki izin
--    listesindeki ayarlar için gösterilir, diğerleri '<maskelendi>' olur
--    (özel GUC'larda hassas değer bulunabilir).
--    security_relevant = true: girişte rol değiştiren (role), nesne çözümlemeyi
--    etkileyen (search_path), salt okunurluğu/RLS'yi değiştiren veya kütüphane
--    yükleyen ayarlar.
--    Yetki: varsayılan kurulumda okunabilir olduğu varsayıldı; DOĞRULANMADI.
-- -----------------------------------------------------------------------------
SELECT CASE
         WHEN s.setrole <> 0 AND s.setdatabase <> 0 THEN '1 rol+veritabani'
         WHEN s.setrole <> 0                        THEN '2 rol (tum veritabanlari)'
         WHEN s.setdatabase <> 0                    THEN '3 veritabani (tum roller)'
         ELSE '4 ALTER ROLE ALL (tum roller, tum veritabanlari)'
       END                                                                       AS setting_scope,
       CASE WHEN s.setdatabase = 0 THEN '(tum veritabanlari)' ELSE d.datname END AS database_name,
       CASE WHEN s.setrole     = 0 THEN '(tum roller)'        ELSE r.rolname END AS role_name,
       cfg.ord                                                                   AS setting_order,
       pg_catalog.lower(pg_catalog.split_part(cfg.item, '=', 1))                 AS setting_name,
       CASE
         WHEN pg_catalog.lower(pg_catalog.split_part(cfg.item, '=', 1)) IN (
                'search_path', 'role', 'row_security',
                'default_transaction_read_only', 'default_transaction_isolation',
                'default_transaction_deferrable',
                'statement_timeout', 'lock_timeout',
                'idle_in_transaction_session_timeout',
                'session_preload_libraries', 'local_preload_libraries',
                'default_tablespace', 'temp_tablespaces',
                'log_statement', 'log_min_duration_statement')
           THEN pg_catalog.substr(cfg.item, pg_catalog.strpos(cfg.item, '=') + 1)
         ELSE '<maskelendi>'
       END                                                                       AS setting_value,
       pg_catalog.lower(pg_catalog.split_part(cfg.item, '=', 1)) IN (
                'role', 'search_path', 'row_security',
                'default_transaction_read_only',
                'session_preload_libraries', 'local_preload_libraries')          AS security_relevant
FROM pg_catalog.pg_db_role_setting s
LEFT JOIN pg_catalog.pg_database d ON d.oid = s.setdatabase
LEFT JOIN pg_catalog.pg_roles    r ON r.oid = s.setrole
CROSS JOIN LATERAL pg_catalog.unnest(s.setconfig) WITH ORDINALITY AS cfg(item, ord)
WHERE (r.rolname = 'hgs2_perftest' AND (s.setdatabase = 0 OR d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db')))
   OR (s.setrole = 0 AND d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db'))
   OR (s.setrole = 0 AND s.setdatabase = 0)
ORDER BY setting_scope, database_name, role_name, setting_order;

-- -----------------------------------------------------------------------------
-- 5. Test şeması — YALNIZCA bağlı veritabanı (hgs2_perftest_db)
--    Bu bölümün sonuçları hibrit_giris_db hakkında bilgi VERMEZ.
--
--    ORTAK IDENTITY SEQUENCE TANIMI (S7) — 5.5, 5.5b, 5.9 ve 5.17'de aynıdır:
--      s.relkind = 'S'
--      ve pg_depend d: d.classid = pg_class, d.objid = s.oid,
--                      d.refclassid = pg_class, d.deptype = 'i',
--                      d.refobjsubid > 0
--      ve pg_attribute a (a.attrelid = d.refobjid, a.attnum = d.refobjsubid):
--                      a.attidentity IN ('a', 'd')
--    "Beklenen" identity sequence: bağlı tablo public şemasında, relkind 'r'
--    ve adı admins / devices / logs / users olanlar.
-- -----------------------------------------------------------------------------

-- 5.1 Kullanıcı şemaları, sahipleri ve şema ACL'leri (v1'den korunur)
--     NULL nspacl, acldefault ile varsayılana açılır.
--     perftest_create = true ise hgs2_perftest bu şemada nesne oluşturabilir.
WITH me AS (
    SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'hgs2_perftest'
)
SELECT n.nspname,
       pg_catalog.pg_get_userbyid(n.nspowner) AS owner,
       (n.nspacl IS NULL)                     AS using_default_acl,
       COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner)) AS effective_acl,
       pg_catalog.has_schema_privilege(me.oid, n.oid, 'USAGE')  AS perftest_usage,
       pg_catalog.has_schema_privilege(me.oid, n.oid, 'CREATE') AS perftest_create
FROM pg_catalog.pg_namespace n
LEFT JOIN me ON true
WHERE n.nspname <> 'information_schema'
  AND n.nspname !~ '^pg_'
ORDER BY n.nspname;

-- 5.2 Kullanıcı şemalarındaki tablolar, view'lar, sequence'lar ve sahipleri
--     (v1'den korunur)
--     relkind: r=tablo, p=bölümlenmiş tablo, v=view, m=materialized view,
--              f=foreign table, S=sequence, c=bileşik tür
--     İndeksler ve TOAST tabloları listelenmez.
SELECT n.nspname,
       c.relname,
       c.relkind,
       pg_catalog.pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity                       AS row_security_enabled
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname <> 'information_schema'
  AND n.nspname !~ '^pg_'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S', 'c')
ORDER BY c.relkind, n.nspname, c.relname;

-- 5.3 Beklenen 4 tablonun varlığı (public şeması varsayıldı) (v1'den korunur)
WITH expected(relname) AS (
    VALUES ('admins'), ('devices'), ('logs'), ('users')
)
SELECT e.relname,
       (c.oid IS NOT NULL)                    AS present,
       c.relkind,
       pg_catalog.pg_get_userbyid(c.relowner) AS owner
FROM expected e
LEFT JOIN pg_catalog.pg_class c
       ON c.relname = e.relname
      AND c.relnamespace = pg_catalog.to_regnamespace('public')
      AND c.relkind IN ('r', 'p')
ORDER BY e.relname;

-- 5.4 Beklenen tablolar üzerindeki açık ACL girdileri — TÜM grantee'ler
--     (v2: başlık düzeltildi; sorgu v1 ile aynı. v1 başlığı yalnızca
--     hgs2_perftest girdileri gösteriliyormuş gibi yazılmıştı; sorgu hiçbir
--     zaman grantee'ye göre filtrelemedi.)
--     (sahiplik yoluyla gelen yetkiler owner sütunundan okunmalıdır;
--      hgs2_perftest'in ETKİN yetkileri için 5.4a'ya bakınız)
SELECT c.relname,
       pg_catalog.pg_get_userbyid(c.relowner) AS owner,
       CASE WHEN a.grantee = 0 THEN 'PUBLIC'
            ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
       a.privilege_type,
       (c.relacl IS NULL)                     AS from_default_acl
FROM pg_catalog.pg_class c
CROSS JOIN LATERAL pg_catalog.aclexplode(
           COALESCE(c.relacl, pg_catalog.acldefault('r', c.relowner))) AS a
WHERE c.relnamespace = pg_catalog.to_regnamespace('public')
  AND c.relname IN ('admins', 'devices', 'logs', 'users')
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname, grantee, a.privilege_type;

-- 5.4a (v2, S5) hgs2_perftest'in beklenen tablolardaki ETKİN yetkileri
--      has_table_privilege; doğrudan, PUBLIC, rol üyeliği ve sahiplik yoluyla
--      gelen yetkileri birlikte hesaba katar. Rol yoksa sonuç boştur.
--      perftest_is_owner = true ise rol tablonun sahibidir (tüm yetkiler).
--      hgs2_perftest süper kullanıcıysa tüm değerler true döner (bkz. 2.2).
WITH me AS (
    SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'hgs2_perftest'
),
privs(privilege_type) AS (
    VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'),
           ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')
)
SELECT c.relname,
       p.privilege_type,
       pg_catalog.has_table_privilege(me.oid, c.oid, p.privilege_type) AS perftest_has_privilege,
       (c.relowner = me.oid)                                           AS perftest_is_owner
FROM pg_catalog.pg_class c
CROSS JOIN me
CROSS JOIN privs p
WHERE c.relnamespace = pg_catalog.to_regnamespace('public')
  AND c.relname IN ('admins', 'devices', 'logs', 'users')
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname, p.privilege_type;

-- 5.4b (v2, S5) MAINTAIN yetkisi — yalnızca PostgreSQL 17+
\if :pg17_or_newer
WITH me AS (
    SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'hgs2_perftest'
)
SELECT c.relname,
       'MAINTAIN'                                                  AS privilege_type,
       pg_catalog.has_table_privilege(me.oid, c.oid, 'MAINTAIN')  AS perftest_has_privilege,
       (c.relowner = me.oid)                                       AS perftest_is_owner
FROM pg_catalog.pg_class c
CROSS JOIN me
WHERE c.relnamespace = pg_catalog.to_regnamespace('public')
  AND c.relname IN ('admins', 'devices', 'logs', 'users')
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
\else
  \echo 'BILGI: MAINTAIN yetkisi PostgreSQL 17+ ozelligidir; bu sunucuda kontrol edilmedi.'
\endif

-- 5.4c (v2, S5) Beklenen tablolardaki SÜTUN düzeyi ACL girdileri
--      Yalnızca açık sütun ACL'si olan sütunlar listelenir (boş sonuç olağandır).
SELECT c.relname,
       a.attname,
       CASE WHEN x.grantee = 0 THEN 'PUBLIC'
            ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee_name,
       pg_catalog.pg_get_userbyid(x.grantor)               AS grantor_name,
       x.privilege_type
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
CROSS JOIN LATERAL pg_catalog.aclexplode(a.attacl) AS x
WHERE c.relnamespace = pg_catalog.to_regnamespace('public')
  AND c.relname IN ('admins', 'devices', 'logs', 'users')
  AND c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND a.attacl IS NOT NULL
ORDER BY c.relname, a.attname, grantee_name, x.privilege_type;

-- 5.4d (v2, S5) Varsayılan yetkiler (ALTER DEFAULT PRIVILEGES)
--      Gelecekte oluşturulacak nesnelere otomatik verilecek yetkiler.
--      defaclobjtype: r=tablo, S=sequence, f=fonksiyon, T=tür, n=şema.
--      Boş sonuç olağandır.
SELECT pg_catalog.pg_get_userbyid(da.defaclrole)          AS for_role,
       CASE WHEN da.defaclnamespace = 0 THEN '(tum semalar)'
            ELSE n.nspname END                            AS schema_name,
       da.defaclobjtype,
       CASE WHEN x.grantee = 0 THEN 'PUBLIC'
            ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee_name,
       x.privilege_type,
       x.is_grantable
FROM pg_catalog.pg_default_acl da
LEFT JOIN pg_catalog.pg_namespace n ON n.oid = da.defaclnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(da.defaclacl) AS x
ORDER BY for_role, schema_name, da.defaclobjtype, grantee_name, x.privilege_type;

-- 5.5 Identity sequence'lar: bağlı oldukları tablo ve sütun (4 satır beklenir)
--     pg_depend.deptype = 'i' identity sütunu ile sequence arasındaki iç
--     bağımlılıktır. attidentity: 'a' = ALWAYS, 'd' = BY DEFAULT.
--     v2 (S7): ortak tanım uygulandı (refobjsubid > 0 ve attidentity
--     IN ('a','d') eklendi; pratikte v1 ile aynı satırları döndürmesi
--     beklenir). table_schema ve on_expected_table sütunları eklendi.
--     Kapsam v1 ile aynı: sequence'ın şeması kullanıcı şemasıdır.
SELECT sn.nspname                             AS sequence_schema,
       s.relname                              AS sequence_name,
       pg_catalog.pg_get_userbyid(s.relowner) AS sequence_owner,
       tn.nspname                             AS table_schema,
       t.relname                              AS table_name,
       a.attname                              AS column_name,
       a.attidentity,
       (tn.nspname = 'public'
        AND t.relkind = 'r'
        AND t.relname IN ('admins', 'devices', 'logs', 'users')) AS on_expected_table
FROM pg_catalog.pg_class s
JOIN pg_catalog.pg_namespace sn ON sn.oid = s.relnamespace
JOIN pg_catalog.pg_depend d
  ON d.classid     = 'pg_catalog.pg_class'::regclass
 AND d.objid       = s.oid
 AND d.refclassid  = 'pg_catalog.pg_class'::regclass
 AND d.deptype     = 'i'
 AND d.refobjsubid > 0
JOIN pg_catalog.pg_class t      ON t.oid = d.refobjid
JOIN pg_catalog.pg_namespace tn ON tn.oid = t.relnamespace
JOIN pg_catalog.pg_attribute a  ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
WHERE s.relkind = 'S'
  AND a.attidentity IN ('a', 'd')
  AND sn.nspname <> 'information_schema'
  AND sn.nspname !~ '^pg_'
ORDER BY t.relname, a.attname;

-- 5.5b (v2, S5) hgs2_perftest'in beklenen identity sequence'lardaki etkin
--      yetkileri (ortak tanım + beklenen tablo koşulu)
WITH me AS (
    SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'hgs2_perftest'
)
SELECT s.relname                                                    AS sequence_name,
       t.relname                                                    AS table_name,
       pg_catalog.has_sequence_privilege(me.oid, s.oid, 'USAGE')   AS perftest_usage,
       pg_catalog.has_sequence_privilege(me.oid, s.oid, 'SELECT')  AS perftest_select,
       pg_catalog.has_sequence_privilege(me.oid, s.oid, 'UPDATE')  AS perftest_update,
       (s.relowner = me.oid)                                        AS perftest_is_owner
FROM pg_catalog.pg_class s
JOIN pg_catalog.pg_depend d
  ON d.classid     = 'pg_catalog.pg_class'::regclass
 AND d.objid       = s.oid
 AND d.refclassid  = 'pg_catalog.pg_class'::regclass
 AND d.deptype     = 'i'
 AND d.refobjsubid > 0
JOIN pg_catalog.pg_class t     ON t.oid = d.refobjid
JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
CROSS JOIN me
WHERE s.relkind = 'S'
  AND a.attidentity IN ('a', 'd')
  AND t.relnamespace = pg_catalog.to_regnamespace('public')
  AND t.relkind = 'r'
  AND t.relname IN ('admins', 'devices', 'logs', 'users')
ORDER BY t.relname, s.relname;

-- 5.6 Kısıt sayıları: primary key / unique / foreign key (v1'den korunur)
--     Referans: p = 4, u = 3, f = 2.
--     Not: PostgreSQL 18+ NOT NULL kısıtlarını contype = 'n' olarak kataloglar;
--     filtre yalnızca p/u/f aldığı için tüm sürümlerde aynı sonucu verir.
SELECT con.contype,
       count(*) AS constraint_count
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class t     ON t.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND con.contype IN ('p', 'u', 'f')
GROUP BY con.contype
ORDER BY con.contype;

-- 5.7 Kısıt tanımları (v1'den korunur)
--     Referans: unique -> admins(kullanici_adi), users(kart_no), users(ogrenci_no);
--               foreign key -> logs(device_id) -> devices, logs(user_id) -> users.
SELECT t.relname                              AS table_name,
       con.conname,
       con.contype,
       pg_catalog.pg_get_constraintdef(con.oid) AS definition,
       con.confrelid::regclass                AS referenced_table
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class t     ON t.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND con.contype IN ('p', 'u', 'f')
ORDER BY con.contype, t.relname, con.conname;

-- 5.8 users.parmak_izi_sablonu sütununun veri türü (referans: oid)
--     (v1'den korunur)
--     Yalnızca pg_attribute okunur; sütun verisi okunmaz.
--     Tablo yoksa to_regclass NULL döner ve sorgu boş sonuç verir.
SELECT a.attname,
       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
       a.attnotnull
FROM pg_catalog.pg_attribute a
WHERE a.attrelid = pg_catalog.to_regclass('public.users')
  AND a.attname = 'parmak_izi_sablonu'
  AND NOT a.attisdropped;

-- 5.9 Beklenmeyen tablo / view / sequence / bileşik tür (boş sonuç beklenir)
--     Beklenenler: public.admins, public.devices, public.logs, public.users
--     ve YALNIZCA bu tablolara ortak tanımla bağlı identity sequence'lar.
--     v2 (S6): v1 herhangi bir 'i' bağımlılığı olan her nesneyi dışlıyordu;
--     bu yüzden beklenmeyen bir tabloya ait identity sequence gizleniyordu.
--     v2 yalnızca beklenen identity sequence'ları dışlar ve kalan her satırın
--     nedenini (reason) yazar. Sonuç kümesi v1'inkini kapsar; ek olarak
--     beklenmeyen tablolara bağlı identity sequence'lar da görünür.
SELECT n.nspname,
       c.relname,
       c.relkind,
       pg_catalog.pg_get_userbyid(c.relowner) AS owner,
       CASE
         WHEN c.relkind = 'S' AND EXISTS (
                SELECT 1
                FROM pg_catalog.pg_depend d
                WHERE d.classid    = 'pg_catalog.pg_class'::regclass
                  AND d.objid      = c.oid
                  AND d.refclassid = 'pg_catalog.pg_class'::regclass
                  AND d.deptype    = 'i')
           THEN 'beklenmeyen tabloya bagli identity sequence'
         WHEN c.relkind = 'S' AND EXISTS (
                SELECT 1
                FROM pg_catalog.pg_depend d
                WHERE d.classid    = 'pg_catalog.pg_class'::regclass
                  AND d.objid      = c.oid
                  AND d.refclassid = 'pg_catalog.pg_class'::regclass
                  AND d.deptype    = 'a')
           THEN 'serial / OWNED BY sequence'
         WHEN EXISTS (
                SELECT 1
                FROM pg_catalog.pg_depend d
                WHERE d.classid = 'pg_catalog.pg_class'::regclass
                  AND d.objid   = c.oid
                  AND d.deptype = 'e')
           THEN 'extension nesnesi'
         ELSE 'beklenmeyen nesne'
       END AS reason
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname <> 'information_schema'
  AND n.nspname !~ '^pg_'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S', 'c')
  AND NOT (n.nspname = 'public'
           AND c.relkind = 'r'
           AND c.relname IN ('admins', 'devices', 'logs', 'users'))
  AND NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_depend d
        JOIN pg_catalog.pg_class t     ON t.oid = d.refobjid
        JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE c.relkind      = 'S'
          AND d.classid      = 'pg_catalog.pg_class'::regclass
          AND d.objid        = c.oid
          AND d.refclassid   = 'pg_catalog.pg_class'::regclass
          AND d.deptype      = 'i'
          AND d.refobjsubid  > 0
          AND a.attidentity IN ('a', 'd')
          AND t.relnamespace = pg_catalog.to_regnamespace('public')
          AND t.relkind      = 'r'
          AND t.relname IN ('admins', 'devices', 'logs', 'users'))
ORDER BY n.nspname, c.relkind, c.relname;

-- 5.10 Kullanıcı tanımlı bağımsız türler (tablo satır türleri ve diziler hariç)
--      (v1'den korunur)
SELECT n.nspname,
       t.typname,
       t.typtype,
       pg_catalog.pg_get_userbyid(t.typowner) AS owner
FROM pg_catalog.pg_type t
JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname <> 'information_schema'
  AND n.nspname !~ '^pg_'
  AND t.typrelid = 0
  AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_type e WHERE e.typarray = t.oid)
ORDER BY n.nspname, t.typname;

-- 5.11 Kullanıcı şemalarındaki fonksiyonlar / prosedürler (v1'den korunur)
--      from_extension = true ise nesne bir extension'a aittir.
--      prosecdef = true (SECURITY DEFINER) olanlar ayrıca incelenmelidir.
SELECT n.nspname,
       p.proname,
       pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
       p.prokind,
       p.prosecdef,
       pg_catalog.pg_get_userbyid(p.proowner)              AS owner,
       EXISTS (SELECT 1 FROM pg_catalog.pg_depend d
               WHERE d.classid = 'pg_catalog.pg_proc'::regclass
                 AND d.objid   = p.oid
                 AND d.deptype = 'e')                       AS from_extension
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname <> 'information_schema'
  AND n.nspname !~ '^pg_'
ORDER BY n.nspname, p.proname;

-- 5.12 Kullanıcı trigger'ları (iç/kısıt kaynaklı trigger'lar hariç)
--      (v1'den korunur)
SELECT c.relname AS table_name,
       tg.tgname,
       tg.tgenabled,
       tg.tgfoid::regprocedure AS trigger_function
FROM pg_catalog.pg_trigger tg
JOIN pg_catalog.pg_class c ON c.oid = tg.tgrelid
WHERE NOT tg.tgisinternal
ORDER BY c.relname, tg.tgname;

-- 5.13 Event trigger'lar (veritabanı düzeyi) (v1'den korunur)
SELECT evtname,
       evtevent,
       evtenabled,
       pg_catalog.pg_get_userbyid(evtowner) AS owner
FROM pg_catalog.pg_event_trigger
ORDER BY evtname;

-- 5.14 Kurulu extension'lar (yalnızca plpgsql beklenir) (v1'den korunur)
SELECT e.extname,
       e.extversion,
       pg_catalog.pg_get_userbyid(e.extowner) AS owner,
       n.nspname                              AS extension_schema
FROM pg_catalog.pg_extension e
JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
ORDER BY e.extname;

-- 5.15 Row-level security politikaları (v1'den korunur)
SELECT c.relname AS table_name,
       pol.polname,
       pol.polcmd,
       pol.polpermissive
FROM pg_catalog.pg_policy pol
JOIN pg_catalog.pg_class c ON c.oid = pol.polrelid
ORDER BY c.relname, pol.polname;

-- 5.16 Büyük nesneler: YALNIZCA metadata (sayı ve sahip) (v1'den korunur)
--      İçerik tablosu (pg_largeobject) ve büyük nesne fonksiyonları
--      kullanılmaz. Test veritabanında büyük nesne bulunması, parmak izi
--      verisinin yüklenmiş olabileceğine işaret eder; içerik incelenmez.
SELECT pg_catalog.pg_get_userbyid(m.lomowner) AS owner,
       count(*)                               AS large_object_count
FROM pg_catalog.pg_largeobject_metadata m
GROUP BY m.lomowner
ORDER BY owner;

-- 5.17 Özet: referans değerlerle karşılaştırma
--      Bu yalnızca hgs2_perftest_db içindir; hibrit_giris_db hakkında sonuç vermez.
--      v2 (S7): v1'deki tek "identity sequence" satırı (public şemasındaki her
--      'i' sequence) kaldırıldı; yerine ortak tanımı kullanan iki satır geldi:
--        * beklenen 4 tabloya bağlı olanlar,
--        * tüm kullanıcı şemalarındakiler (5.5'in satır sayısına eşit olmalı).
--      İki değer farklıysa beklenen tablolar dışında identity sequence vardır
--      (5.9'da "beklenmeyen tabloya bagli identity sequence" olarak görünür).
SELECT 'tablo (public: admins/devices/logs/users)' AS check_item,
       4 AS reference_value,
       (SELECT count(*) FROM pg_catalog.pg_class c
         WHERE c.relnamespace = pg_catalog.to_regnamespace('public')
           AND c.relkind IN ('r', 'p')
           AND c.relname IN ('admins', 'devices', 'logs', 'users')) AS observed_value
UNION ALL
SELECT 'identity sequence (beklenen 4 tabloya bagli)', 4,
       (SELECT count(*)
          FROM pg_catalog.pg_class s
          JOIN pg_catalog.pg_depend d
            ON d.classid     = 'pg_catalog.pg_class'::regclass
           AND d.objid       = s.oid
           AND d.refclassid  = 'pg_catalog.pg_class'::regclass
           AND d.deptype     = 'i'
           AND d.refobjsubid > 0
          JOIN pg_catalog.pg_class t     ON t.oid = d.refobjid
          JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
         WHERE s.relkind = 'S'
           AND a.attidentity IN ('a', 'd')
           AND t.relnamespace = pg_catalog.to_regnamespace('public')
           AND t.relkind = 'r'
           AND t.relname IN ('admins', 'devices', 'logs', 'users'))
UNION ALL
SELECT 'identity sequence (tum kullanici semalari; 5.5 satir sayisi)', 4,
       (SELECT count(*)
          FROM pg_catalog.pg_class s
          JOIN pg_catalog.pg_namespace sn ON sn.oid = s.relnamespace
          JOIN pg_catalog.pg_depend d
            ON d.classid     = 'pg_catalog.pg_class'::regclass
           AND d.objid       = s.oid
           AND d.refclassid  = 'pg_catalog.pg_class'::regclass
           AND d.deptype     = 'i'
           AND d.refobjsubid > 0
          JOIN pg_catalog.pg_class t     ON t.oid = d.refobjid
          JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
         WHERE s.relkind = 'S'
           AND a.attidentity IN ('a', 'd')
           AND sn.nspname <> 'information_schema'
           AND sn.nspname !~ '^pg_')
UNION ALL
SELECT 'primary key', 4,
       (SELECT count(*) FROM pg_catalog.pg_constraint con
          JOIN pg_catalog.pg_class t ON t.oid = con.conrelid
         WHERE t.relnamespace = pg_catalog.to_regnamespace('public') AND con.contype = 'p')
UNION ALL
SELECT 'unique', 3,
       (SELECT count(*) FROM pg_catalog.pg_constraint con
          JOIN pg_catalog.pg_class t ON t.oid = con.conrelid
         WHERE t.relnamespace = pg_catalog.to_regnamespace('public') AND con.contype = 'u')
UNION ALL
SELECT 'foreign key', 2,
       (SELECT count(*) FROM pg_catalog.pg_constraint con
          JOIN pg_catalog.pg_class t ON t.oid = con.conrelid
         WHERE t.relnamespace = pg_catalog.to_regnamespace('public') AND con.contype = 'f');

-- -----------------------------------------------------------------------------
-- Son: hiçbir değişiklik kalıcı hale getirilmez
-- -----------------------------------------------------------------------------
ROLLBACK;

-- v2: ROLLBACK sonrasında açık transaction kalmadığını doğrula; yalnızca o
-- zaman başarı işaretçisini yaz. (Bu SELECT örtük, tek komutluk bir
-- transaction'dır; katalog okumaz.)
SELECT pg_catalog.now() = pg_catalog.statement_timestamp() AS no_open_tx_after_rollback
\gset

\if :no_open_tx_after_rollback
  \echo 'HGS2_AUDIT_COMPLETE'
\else
  \echo 'HGS2_AUDIT_ABORT: transaction_open_after_rollback'
  SELECT 'HGS2_AUDIT_ABORT: transaction_open_after_rollback'::pg_catalog.int4;
  \quit
\endif
