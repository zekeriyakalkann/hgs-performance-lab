-- SENTETIK test fixture (kume geneli). Yalnizca gecici test kumelerinde calistirilir.
\set ON_ERROR_STOP on
SELECT current_setting('data_directory') LIKE '%scratchpad%' AS is_scratch \gset
\if :is_scratch
\else
  \echo 'GUARD: not a scratchpad cluster'
  SELECT 1/0;
\endif
CREATE ROLE hgs2_perftest LOGIN;
CREATE ROLE hgs2_auditor LOGIN;               -- denetim rolu (super degil)
CREATE ROLE hgs2_auditor_nosysid LOGIN;       -- pg_control_system yetkisi YOK
CREATE ROLE hgs2_su_behind_role LOGIN SUPERUSER;  -- session_user super, role ayari ile current_user siradan
CREATE ROLE grp_reader NOLOGIN;
CREATE ROLE grp_nested NOLOGIN;
GRANT grp_reader TO grp_nested;               -- dolayli uyelik: perftest -> grp_nested -> grp_reader
GRANT grp_nested TO hgs2_perftest;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO hgs2_auditor, hgs2_su_behind_role;
CREATE DATABASE hgs2_perftest_db;
CREATE DATABASE hibrit_giris_db;              -- yalnizca AD olarak sentetik; ici bos
CREATE DATABASE other_db;
REVOKE ALL ON DATABASE hibrit_giris_db FROM PUBLIC;
GRANT CONNECT ON DATABASE hibrit_giris_db TO hgs2_auditor;
-- Kalici oturum ayarlari (Bolum 4 senaryolari)
ALTER ROLE ALL SET hgs2.test_secret = 'SENTETIK-GIZLI-DEGER';             -- kapsam 4, maskelenmeli
ALTER ROLE hgs2_perftest SET search_path = public, pg_catalog;            -- kapsam 2
ALTER ROLE hgs2_perftest IN DATABASE hgs2_perftest_db SET statement_timeout = '15s';  -- kapsam 1
ALTER DATABASE hgs2_perftest_db SET work_mem = '8MB';                     -- kapsam 3, maskelenmeli
ALTER ROLE hgs2_su_behind_role SET role = 'hgs2_auditor';
