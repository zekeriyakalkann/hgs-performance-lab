-- ASAMA 3 SENTETIK fixture (kume geneli). Yalnizca gecici test kumelerinde.
\set ON_ERROR_STOP on
SELECT current_setting('data_directory') LIKE '%scratchpad%' AS is_scratch \gset
\if :is_scratch
\else
  SELECT 1/0;
\endif
-- Rol uyeligi yoluyla super kullanici olabilen denetim rolu
CREATE ROLE hgs2_member_of_su LOGIN;
GRANT pgadmin TO hgs2_member_of_su;
-- Tehlikeli onceden tanimli role uye denetim rolu (super kullanici degil)
CREATE ROLE hgs2_auditor_rsf LOGIN;
GRANT pg_read_server_files TO hgs2_auditor_rsf;
-- Gizli degerli kalici ayarlar (maskelenmeli)
ALTER ROLE hgs2_perftest SET hgs2.db_password = 'SENTETIK-PAROLA-GUC';
ALTER ROLE hgs2_auditor SET hgs2.audit_token = 'SENTETIK-TOKEN-AUDITROLE';
