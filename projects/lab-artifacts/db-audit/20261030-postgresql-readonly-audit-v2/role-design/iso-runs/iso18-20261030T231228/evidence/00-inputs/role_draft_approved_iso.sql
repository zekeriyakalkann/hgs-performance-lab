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
