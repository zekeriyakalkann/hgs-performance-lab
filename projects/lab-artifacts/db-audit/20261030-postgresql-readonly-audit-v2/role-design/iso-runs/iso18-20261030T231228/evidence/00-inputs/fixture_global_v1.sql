-- HGS2 V1 - global fixture (yalnizca izole test kumesi). Gercek veri YOK.
\set ON_ERROR_STOP on
SELECT current_setting('port') = '55438'
   AND current_setting('cluster_name') = 'hgs2iso18'
   AND current_database() = 'postgres' AS iso_ok \gset
\if :iso_ok
\else
  \echo 'DUR: izole test kumesi degil'
  SELECT 1/0;
\endif
CREATE ROLE hgs2_perftest LOGIN;
CREATE DATABASE hgs2_perftest_db OWNER hgs2_perftest;
CREATE DATABASE hibrit_giris_db OWNER postgres;
CREATE DATABASE other_db;
REVOKE CONNECT ON DATABASE hibrit_giris_db FROM PUBLIC;
SELECT datname, pg_get_userbyid(datdba) AS owner, datacl FROM pg_database ORDER BY 1;