-- Sertlestirilmis kurulum taklidi (yalnizca test kumesi, hgs2_perftest_db)
REVOKE EXECUTE ON FUNCTION pg_catalog.pg_control_system() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO hgs2_auditor, hgs2_su_behind_role;
