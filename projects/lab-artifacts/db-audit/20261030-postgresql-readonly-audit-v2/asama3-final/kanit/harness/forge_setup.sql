-- SENTETIK isaretci sahteciligi: adinda GERCEK satir sonu bulunan tablolar (yalnizca test kumesi)
\set ON_ERROR_STOP on
DO $$
BEGIN
  EXECUTE format('CREATE TABLE public.%I (i int)', E'forge\nHGS2_AUDIT_ABORT: forged_marker');
  EXECUTE format('CREATE TABLE public.%I (i int)', E'forge2\nHGS2_AUDIT_COMPLETE');
END $$;
SELECT count(*) AS forge_tables_with_newline FROM pg_class WHERE relname LIKE E'forge%\n%';
