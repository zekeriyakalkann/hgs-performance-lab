-- =============================================================================
-- HGS2 — PostgreSQL veritabanı izolasyonu: salt okunur katalog denetimi
-- Hazırlanma: 2026-10-30 (+03:00)
-- =============================================================================
--
-- UYARI
--   * Bu dosya henüz ÇALIŞTIRILMADI. Sorguların hiçbiri gerçek bir sunucuda
--     denenmedi; sözdizimi yalnızca elle (statik) incelendi.
--   * Bağlantı hedefi YALNIZCA hgs2_perftest_db olmalıdır.
--   * hibrit_giris_db veritabanına BAĞLANILMAMALIDIR (bu dosya için de, deneme
--     amacıyla da).
--   * Veritabanında DDL/DML, rol değişikliği veya yetki değişikliği
--     YAPILMAMALIDIR. Bu dosya bunların hiçbirini içermez.
--   * Çalıştırmadan önce PostgreSQL sürümü kontrol edilmelidir (Bölüm 1).
--     Dosya PostgreSQL 12 ve üzeri için yazıldı; daha eski sürümde durur.
--   * Sorgular salt okunur işlem içinde yürütülmelidir
--     (BEGIN TRANSACTION READ ONLY ... ROLLBACK).
--
-- KULLANIM
--   * psql ile çalıştırılmalıdır: dosya psql meta-komutları (\set, \gset, \if,
--     \echo, \quit) kullanır. Başka istemcilerde bu satırlar hata verir.
--   * Örnek (parola/bağlantı dizesi bilerek yazılmadı; kimlik bilgisi psql'in
--     kendi istemi veya yetkili oturumun mekanizmasıyla sağlanmalıdır):
--       psql -X -d hgs2_perftest_db -f postgresql_readonly_audit.sql
--   * Aşağıdaki veritabanı adı denetimi yalnızca YANLIŞ hedefte sorgu
--     çalışmasını engeller; bağlantı kurulduktan sonra çalıştığı için yanlış
--     veritabanına bağlanmayı ÖNLEYEMEZ. Hedefi doğru seçmek operatörün
--     sorumluluğudur.
--
-- KAPSAM VE SINIRLAR
--   * Yalnızca sistem katalogları (pg_catalog) ve yetki/ACL metaverisi okunur.
--   * Hiçbir kullanıcı tablosu satırı, parmak izi verisi veya büyük nesne
--     (large object) içeriği okunmaz; büyük nesneler için yalnızca
--     pg_largeobject_metadata üzerinden sayı ve sahip bilgisi alınır.
--   * pg_authid (parola özetleri) kullanılmaz; pg_roles.rolpassword seçilmez.
--   * Bölüm 2–4'teki pg_roles, pg_auth_members, pg_database ve
--     pg_db_role_setting PAYLAŞILAN kataloglardır: hgs2_perftest_db üzerinden
--     okunduklarında küme genelindeki durumu gösterirler. Bu yüzden
--     hibrit_giris_db'ye bağlanmak gerekmez.
--   * Bölüm 5 yalnızca BAĞLI OLUNAN veritabanının (hgs2_perftest_db) şemasını
--     gösterir. Buradan hibrit_giris_db'deki tablo yetkileri veya mevcut şema
--     durumu hakkında HİÇBİR sonuç çıkarılamaz.
--   * Yetki: Varsayılan PostgreSQL kurulumunda burada kullanılan kataloglar ve
--     has_*_privilege / pg_has_role fonksiyonları bağlanabilen her rol için
--     okunabilirdir; süper kullanıcı gerekmez. Sunucuda katalog erişimi
--     kısıtlanmışsa sorgular yetki hatası verir — bu durum DOĞRULANMADI.
--
-- ACL ile gerçek bağlantı davranışı AYRI konulardır
--   * Bu dosya veritabanı ACL'lerini (CONNECT/TEMPORARY vb.) inceler.
--   * Bir rolün gerçekten bağlanıp bağlanamayacağı ayrıca pg_hba.conf
--     kurallarına, datallowconn ve bağlantı sınırlarına bağlıdır.
--   * pg_hba.conf / pg_hba_file_rules bu dosyada SORGULANMAZ (varsayılan olarak
--     süper kullanıcı gerektirir). Gerçek bağlantı davranışı, yetkili bir
--     yönetici tarafından ayrı ve onaylı bir adımda doğrulanmalıdır.
--
-- BEKLENEN REFERANS DEĞERLER (gerçek durum DEĞİL; sonuçlarla doğrulanacak)
--   * 4 tablo: admins, devices, logs, users (şema: public varsayıldı)
--   * 4 identity sequence
--   * 4 primary key, 3 unique, 2 foreign key
--   * users.parmak_izi_sablonu türü: oid (23 Ekim Surefire günlüğündeki DDL'e göre)
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

-- İşlemin gerçekten salt okunur olduğunu göster (beklenen: on)
SHOW transaction_read_only;

-- -----------------------------------------------------------------------------
-- 0. Hedef veritabanı denetimi
--    Bağlı veritabanı hgs2_perftest_db değilse dosya burada durur
--    (oturum kapanır; açık işlem otomatik olarak geri alınır).
-- -----------------------------------------------------------------------------
SELECT current_database() AS connected_database,
       current_user       AS connected_role,
       current_database() = 'hgs2_perftest_db' AS on_target_db
\gset

\echo 'Bagli veritabani:' :connected_database ' rol:' :connected_role

\if :on_target_db
\else
  \echo 'DURDURULDU: Bagli veritabani hgs2_perftest_db degil.'
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 1. PostgreSQL sürümü
--    Soru: Sunucu sürümü nedir? Sürüme bağlı katalog alanları hangi dalda okunur?
-- -----------------------------------------------------------------------------
SELECT current_setting('server_version_num')::int AS server_version_num,
       current_setting('server_version')          AS server_version;

SELECT current_setting('server_version_num')::int >= 120000 AS pg12_or_newer,
       current_setting('server_version_num')::int >= 160000 AS pg16_or_newer
\gset

\if :pg12_or_newer
\else
  \echo 'DURDURULDU: Bu dosya PostgreSQL 12 ve uzeri icin hazirlandi.'
  \quit
\endif

-- -----------------------------------------------------------------------------
-- 2. Rol özellikleri — hgs2_perftest
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
-- -----------------------------------------------------------------------------

-- 3.1 Sahiplik ve bağlantı ayarları (pg_database paylaşılan katalogdur)
--     datallowconn = false ise hiçbir rol bağlanamaz.
--     datconnlimit = -1 sınırsız demektir.
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
--    Soru: hgs2_perftest rolüne veya iki veritabanına bağlı kalıcı oturum
--    ayarları (ör. search_path, default_transaction_read_only) var mı?
--    setdatabase = 0 veya setrole = 0 "tümü" anlamına gelir.
--    Yetki: varsayılan kurulumda okunabilir olduğu varsayıldı; DOĞRULANMADI.
-- -----------------------------------------------------------------------------
SELECT CASE WHEN s.setdatabase = 0 THEN '(tum veritabanlari)' ELSE d.datname END AS database_name,
       CASE WHEN s.setrole     = 0 THEN '(tum roller)'        ELSE r.rolname END AS role_name,
       s.setconfig
FROM pg_catalog.pg_db_role_setting s
LEFT JOIN pg_catalog.pg_database d ON d.oid = s.setdatabase
LEFT JOIN pg_catalog.pg_roles    r ON r.oid = s.setrole
WHERE (r.rolname = 'hgs2_perftest' AND (s.setdatabase = 0 OR d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db')))
   OR (s.setrole = 0 AND d.datname IN ('hibrit_giris_db', 'hgs2_perftest_db'))
ORDER BY database_name, role_name;

-- -----------------------------------------------------------------------------
-- 5. Test şeması — YALNIZCA bağlı veritabanı (hgs2_perftest_db)
--    Bu bölümün sonuçları hibrit_giris_db hakkında bilgi VERMEZ.
-- -----------------------------------------------------------------------------

-- 5.1 Kullanıcı şemaları, sahipleri ve şema ACL'leri
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

-- 5.3 Beklenen 4 tablonun varlığı (public şeması varsayıldı)
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

-- 5.4 hgs2_perftest'in beklenen tablolar üzerindeki açık ACL girdileri
--     (sahiplik yoluyla gelen yetkiler owner sütunundan okunmalıdır)
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

-- 5.5 Identity sequence'lar: bağlı oldukları tablo ve sütun (4 satır beklenir)
--     pg_depend.deptype = 'i' identity sütunu ile sequence arasındaki iç
--     bağımlılıktır. attidentity: 'a' = ALWAYS, 'd' = BY DEFAULT.
SELECT sn.nspname                             AS sequence_schema,
       s.relname                              AS sequence_name,
       pg_catalog.pg_get_userbyid(s.relowner) AS sequence_owner,
       t.relname                              AS table_name,
       a.attname                              AS column_name,
       a.attidentity
FROM pg_catalog.pg_class s
JOIN pg_catalog.pg_namespace sn ON sn.oid = s.relnamespace
JOIN pg_catalog.pg_depend d
  ON d.classid    = 'pg_catalog.pg_class'::regclass
 AND d.objid      = s.oid
 AND d.refclassid = 'pg_catalog.pg_class'::regclass
 AND d.deptype    = 'i'
JOIN pg_catalog.pg_class t     ON t.oid = d.refobjid
JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
WHERE s.relkind = 'S'
  AND sn.nspname <> 'information_schema'
  AND sn.nspname !~ '^pg_'
ORDER BY t.relname, a.attname;

-- 5.6 Kısıt sayıları: primary key / unique / foreign key
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

-- 5.7 Kısıt tanımları
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
--     ve bu tablolara identity bağımlılığıyla bağlı sequence'lar.
SELECT n.nspname,
       c.relname,
       c.relkind,
       pg_catalog.pg_get_userbyid(c.relowner) AS owner
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
        WHERE d.classid = 'pg_catalog.pg_class'::regclass
          AND d.objid   = c.oid
          AND d.deptype = 'i')
ORDER BY n.nspname, c.relkind, c.relname;

-- 5.10 Kullanıcı tanımlı bağımsız türler (tablo satır türleri ve diziler hariç)
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

-- 5.11 Kullanıcı şemalarındaki fonksiyonlar / prosedürler
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
SELECT c.relname AS table_name,
       tg.tgname,
       tg.tgenabled,
       tg.tgfoid::regprocedure AS trigger_function
FROM pg_catalog.pg_trigger tg
JOIN pg_catalog.pg_class c ON c.oid = tg.tgrelid
WHERE NOT tg.tgisinternal
ORDER BY c.relname, tg.tgname;

-- 5.13 Event trigger'lar (veritabanı düzeyi)
SELECT evtname,
       evtevent,
       evtenabled,
       pg_catalog.pg_get_userbyid(evtowner) AS owner
FROM pg_catalog.pg_event_trigger
ORDER BY evtname;

-- 5.14 Kurulu extension'lar (yalnızca plpgsql beklenir)
SELECT e.extname,
       e.extversion,
       pg_catalog.pg_get_userbyid(e.extowner) AS owner,
       n.nspname                              AS extension_schema
FROM pg_catalog.pg_extension e
JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
ORDER BY e.extname;

-- 5.15 Row-level security politikaları
SELECT c.relname AS table_name,
       pol.polname,
       pol.polcmd,
       pol.polpermissive
FROM pg_catalog.pg_policy pol
JOIN pg_catalog.pg_class c ON c.oid = pol.polrelid
ORDER BY c.relname, pol.polname;

-- 5.16 Büyük nesneler: YALNIZCA metadata (sayı ve sahip)
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
SELECT 'tablo (public: admins/devices/logs/users)' AS check_item,
       4 AS reference_value,
       (SELECT count(*) FROM pg_catalog.pg_class c
         WHERE c.relnamespace = pg_catalog.to_regnamespace('public')
           AND c.relkind IN ('r', 'p')
           AND c.relname IN ('admins', 'devices', 'logs', 'users')) AS observed_value
UNION ALL
SELECT 'identity sequence', 4,
       (SELECT count(*) FROM pg_catalog.pg_depend d
          JOIN pg_catalog.pg_class s ON s.oid = d.objid
         WHERE d.classid    = 'pg_catalog.pg_class'::regclass
           AND d.refclassid = 'pg_catalog.pg_class'::regclass
           AND d.deptype    = 'i'
           AND s.relkind    = 'S'
           AND s.relnamespace = pg_catalog.to_regnamespace('public'))
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
