-- HGS2 V1 - hgs2_audit bagimsiz yetki dogrulamasi (SALT OKUNUR)
-- Olcutler: AUDIT_ROLE_PRIVILEGE_MATRIX.md 11 (6-9, 10 all_ok) + ISOLATED_CLUSTER_TEST_PLAN.md T1 kontrol sorgusu
-- Yalnizca izole test kumesinde (port 55438, cluster_name hgs2iso18), super kullaniciyla, hgs2_perftest_db icinde.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL search_path = pg_catalog, pg_temp;

SELECT current_setting('port') = '55438'
   AND current_setting('cluster_name') = 'hgs2iso18'
   AND current_database() = 'hgs2_perftest_db'
   AND EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname = 'hgs2_audit') AS iso_ok
\gset
\if :iso_ok
\else
  \echo 'HGS2_V1_ROLE_VERIFY_FAIL: izole kume / hedef DB / hgs2_audit kosulu saglanmadi'
  SELECT 1/0;
\endif

-- A. Oznitelikler: SUPERUSER yok; CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS/INHERIT yok
SELECT NOT r.rolsuper AS not_superuser,
       (NOT r.rolcreatedb AND NOT r.rolcreaterole AND NOT r.rolreplication
        AND NOT r.rolbypassrls AND NOT r.rolinherit
        AND r.rolcanlogin AND r.rolconnlimit = 2) AS attrs_ok
FROM pg_roles r WHERE r.rolname = 'hgs2_audit'
\gset

-- B. Rol uyeligi yok (matris 7)
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

-- C. Sahiplik yok (matris 8). Her olcutun KAPSAMI ayridir:
--    no_owned_db, no_owned_tablespace : pg_database / pg_tablespace paylasilan katalog -> kume geneli, dogrudan.
--    no_owned_schema_this_db          : pg_namespace -> YALNIZCA bu oturumun DB'si (hgs2_perftest_db), dogrudan.
--    no_owner_shdep_records           : pg_shdepend 'o' KAYITLARI (matristeki adi: no_owned_objects_any_db).
--      Bu yalnizca paylasilan bagimlilik kaydinin yoklugunu olcer; diger DB'lerin pg_namespace/pg_class
--      kataloglari bu oturumdan OKUNMAZ ve oradaki nesneler dogrudan dogrulanmaz.
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT (SELECT count(*) FROM pg_database d WHERE d.datdba = a.oid) = 0     AS no_owned_db,
       (SELECT count(*) FROM pg_namespace n WHERE n.nspowner = a.oid) = 0  AS no_owned_schema_this_db,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype = 'o') = 0                  AS no_owner_shdep_records,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype NOT IN ('o', 'a')) = 0      AS no_other_shdeps,
       (SELECT count(*) FROM pg_tablespace t WHERE t.spcowner = a.oid) = 0 AS no_owned_tablespace
FROM a
\gset

-- D. Kullanici tablosu / sequence / LO / default ACL erisimi yok (matris 6)
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT (SELECT count(*) FROM pg_class c
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
       NOT has_table_privilege(a.oid, 'public.users'::regclass, 'SELECT')   AS no_select_users,
       (SELECT count(*) FROM pg_largeobject_metadata m
          CROSS JOIN LATERAL aclexplode(m.lomacl) x
         WHERE x.privilege_type IN ('SELECT', 'UPDATE')
           AND x.grantee IN (0, a.oid))                                     AS lo_public_or_audit_count,
       (SELECT count(*) FROM pg_default_acl da
          CROSS JOIN LATERAL aclexplode(da.defaclacl) x
         WHERE x.grantee = a.oid
            OR (x.grantee = 0 AND da.defaclobjtype IN ('r', 'S', 'L')))      AS defacl_risk_count
FROM a
\gset

-- E. Gereksiz CREATE yok (tum DB'ler + bu DB'nin semalari); TEMPORARY yalnizca kayit
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT NOT EXISTS (SELECT 1 FROM pg_database d
                    WHERE has_database_privilege(a.oid, d.oid, 'CREATE'))   AS no_db_create_any,
       NOT EXISTS (SELECT 1 FROM pg_namespace n
                    WHERE has_schema_privilege(a.oid, n.oid, 'CREATE'))     AS no_schema_create,
       has_database_privilege(a.oid, 'hgs2_perftest_db', 'TEMPORARY')       AS has_db_temporary
FROM a
\gset

-- F. Yalnizca gerekli baglanti ve katalog okuma yetkileri (matris 2-5; stokta hepsi PUBLIC'ten)
WITH a AS (SELECT r.oid FROM pg_roles r WHERE r.rolname = 'hgs2_audit')
SELECT has_database_privilege(a.oid, 'hgs2_perftest_db', 'CONNECT')          AS connect_target,
       NOT has_database_privilege(a.oid, 'hibrit_giris_db', 'CONNECT')       AS hibrit_acl_closed,
       has_schema_privilege(a.oid, 'pg_catalog', 'USAGE')                    AS usage_pg_catalog,
       has_schema_privilege(a.oid, 'public', 'USAGE')                        AS usage_public,
       has_function_privilege(a.oid, 'pg_catalog.pg_control_system()', 'EXECUTE') AS ctrl_exec,
       (SELECT count(*) FROM pg_shdepend s
         WHERE s.refclassid = 'pg_catalog.pg_authid'::regclass
           AND s.refobjid = a.oid AND s.deptype = 'a')                      AS acl_ref_count,
       (SELECT count(*) FROM pg_db_role_setting s WHERE s.setrole = a.oid)  AS role_setting_count,
       (SELECT count(*) FROM pg_parameter_acl pa
          CROSS JOIN LATERAL aclexplode(pa.paracl) x
         WHERE x.grantee = a.oid)                                           AS parameter_acl_count,
       current_setting('lo_compat_privileges') = 'off'                      AS lo_compat_off,
       (SELECT count(*) FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE p.prosecdef
           AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
           AND has_schema_privilege(a.oid, n.oid, 'USAGE')
           AND has_function_privilege(a.oid, p.oid, 'EXECUTE'))             AS secdef_callable_count
FROM a
\gset

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
  ('pg_catalog.pg_stat_get_activity(integer)'), ('pg_catalog.pg_has_role(oid,text)'),
  ('pg_catalog.has_server_privilege(oid,text)')
) AS v(sig)
WHERE to_regprocedure(v.sig) IS NULL
   OR NOT has_function_privilege('hgs2_audit', to_regprocedure(v.sig)::oid, 'EXECUTE')
\gset

-- G. pg_hba katmani (matris 9.2)
SELECT NOT EXISTS (SELECT 1 FROM pg_hba_file_rules r WHERE r.error IS NOT NULL) AS hba_no_errors,
       COALESCE((SELECT r.auth_method FROM pg_hba_file_rules r
                  WHERE r.error IS NULL
                    AND r.type IN ('host', 'hostssl', 'hostnossl', 'hostgssenc', 'hostnogssenc')
                    AND ('hgs2_audit' = ANY (r.user_name) OR 'all' = ANY (r.user_name))
                    AND ('hibrit_giris_db' = ANY (r.database) OR 'all' = ANY (r.database))
                  ORDER BY r.line_number LIMIT 1) = 'reject', false)            AS hba_hibrit_rejected
\gset

-- Rapor: veritabani bazinda ACL CONNECT (matris 9.1; hgs2_perftest_db disindaki 't' satirlari yalnizca pg_hba ile kapali)
SELECT d.datname, d.datallowconn,
       has_database_privilege('hgs2_audit', d.oid, 'CONNECT') AS acl_connect,
       (d.datname = 'hgs2_perftest_db')                      AS expected_connect
FROM pg_database d ORDER BY d.datname;

\echo 'A not_superuser=' :not_superuser ' attrs_ok=' :attrs_ok
\echo 'B no_member_of=' :no_member_of ' no_members_in_audit=' :no_members_in_audit ' no_effective_membership=' :no_effective_membership ' not_member_perftest=' :not_member_perftest ' not_member_postgres=' :not_member_postgres
\echo 'C no_owned_db=' :no_owned_db ' no_owned_schema_this_db=' :no_owned_schema_this_db ' no_owner_shdep_records=' :no_owner_shdep_records ' no_other_shdeps=' :no_other_shdeps ' no_owned_tablespace=' :no_owned_tablespace
\echo 'D user_rel_access_count=' :user_rel_access_count ' no_select_users=' :no_select_users ' lo_public_or_audit_count=' :lo_public_or_audit_count ' defacl_risk_count=' :defacl_risk_count
\echo 'E no_db_create_any=' :no_db_create_any ' no_schema_create=' :no_schema_create ' has_db_temporary(kayit)=' :has_db_temporary
\echo 'F connect_target=' :connect_target ' hibrit_acl_closed=' :hibrit_acl_closed ' usage_pg_catalog=' :usage_pg_catalog ' usage_public=' :usage_public ' ctrl_exec=' :ctrl_exec
\echo 'F acl_ref_count=' :acl_ref_count ' role_setting_count=' :role_setting_count ' parameter_acl_count=' :parameter_acl_count ' lo_compat_off=' :lo_compat_off ' secdef_callable_count(kayit)=' :secdef_callable_count
\echo 'F catalogs_ok=' :catalogs_ok ' eksik:' :catalogs_missing
\echo 'F functions_ok=' :functions_ok ' eksik:' :functions_missing
\echo 'G hba_no_errors=' :hba_no_errors ' hba_hibrit_rejected=' :hba_hibrit_rejected

SELECT (:'not_superuser')::boolean AND (:'attrs_ok')::boolean
   AND (:'no_member_of')::boolean AND (:'no_members_in_audit')::boolean
   AND (:'no_effective_membership')::boolean AND (:'not_member_perftest')::boolean
   AND (:'not_member_postgres')::boolean
   AND (:'no_owned_db')::boolean AND (:'no_owned_schema_this_db')::boolean
   AND (:'no_owner_shdep_records')::boolean AND (:'no_other_shdeps')::boolean
   AND (:'no_owned_tablespace')::boolean
   AND :user_rel_access_count = 0 AND (:'no_select_users')::boolean
   AND :lo_public_or_audit_count = 0 AND :defacl_risk_count = 0
   AND (:'no_db_create_any')::boolean AND (:'no_schema_create')::boolean
   AND (:'connect_target')::boolean AND (:'hibrit_acl_closed')::boolean
   AND (:'usage_pg_catalog')::boolean AND (:'usage_public')::boolean
   AND (:'ctrl_exec')::boolean AND (:'catalogs_ok')::boolean AND (:'functions_ok')::boolean
   AND :acl_ref_count = 0 AND :role_setting_count = 0 AND :parameter_acl_count = 0
   AND (:'lo_compat_off')::boolean
   AND (:'hba_no_errors')::boolean AND (:'hba_hibrit_rejected')::boolean AS v1_role_ok
\gset
\if :v1_role_ok
  \echo 'HGS2_V1_ROLE_VERIFY_OK'
\else
  \echo 'HGS2_V1_ROLE_VERIFY_FAIL'
  SELECT 1/0;
\endif
ROLLBACK;