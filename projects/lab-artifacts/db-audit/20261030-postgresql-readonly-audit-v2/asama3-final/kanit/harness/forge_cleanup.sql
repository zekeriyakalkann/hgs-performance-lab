\set ON_ERROR_STOP on
DO $$
BEGIN
  EXECUTE format('DROP TABLE public.%I', E'forge\nHGS2_AUDIT_ABORT: forged_marker');
  EXECUTE format('DROP TABLE public.%I', E'forge2\nHGS2_AUDIT_COMPLETE');
END $$;
SELECT count(*) AS forge_tables_left FROM pg_class WHERE relname LIKE 'forge%';
