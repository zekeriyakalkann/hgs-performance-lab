-- ASAMA 3 SENTETIK fixture (hgs2_perftest_db). Gercek veri YOK.
\set ON_ERROR_STOP on
SELECT current_setting('data_directory') LIKE '%scratchpad%' AND current_database() = 'hgs2_perftest_db' AS ok \gset
\if :ok
\else
  SELECT 1/0;
\endif
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO hgs2_member_of_su, hgs2_auditor_rsf;
-- Fonksiyon duzeyi ayarda gizli deger (proconfig) + izinli search_path
CREATE FUNCTION public.fn_with_secret() RETURNS int LANGUAGE sql
  SET hgs2.api_token = 'SENTETIK-TOKEN-FN' SET search_path = pg_catalog AS 'SELECT 1';
-- Politika ifadesinde gizli literal
CREATE POLICY logs_secret ON public.logs USING (device_id::text <> 'SENTETIK-TOKEN-POL');
-- Uretim veritabanina isaret eden foreign server + parolali user mapping
CREATE EXTENSION postgres_fdw;
CREATE SERVER prod_link FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host 'sentetik-prod-host.invalid', port '5432', dbname 'hibrit_giris_db');
CREATE USER MAPPING FOR hgs2_perftest SERVER prod_link OPTIONS (user 'x', password 'SENTETIK-PAROLA-UM');
