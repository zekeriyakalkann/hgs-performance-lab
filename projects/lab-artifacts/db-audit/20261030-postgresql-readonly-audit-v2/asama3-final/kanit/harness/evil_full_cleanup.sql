\set ON_ERROR_STOP on
ALTER ROLE hgs2_auditor IN DATABASE hgs2_perftest_db RESET search_path;
DROP SCHEMA evil CASCADE;
SELECT count(*) AS evil_left FROM pg_namespace WHERE nspname = 'evil';
SELECT count(*) AS auditor_db_settings_left FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
 WHERE r.rolname = 'hgs2_auditor' AND s.setdatabase <> 0;
