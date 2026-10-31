\set ON_ERROR_STOP on
DROP EVENT TRIGGER evt_noop;
DROP FUNCTION public.evt_noop();
DROP TRIGGER logs_noop ON public.logs;
DROP FUNCTION public.trg_noop();
DROP FUNCTION public.secdef_no_path();
DROP USER MAPPING FOR hgs2_perftest SERVER prod_link;
DROP SERVER prod_link;
DROP EXTENSION postgres_fdw;
SELECT lo_unlink(oid) FROM pg_largeobject_metadata WHERE lomacl IS NOT NULL;
