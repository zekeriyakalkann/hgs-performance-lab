-- Ek SENTETIK nesneler: foreign server + user mapping, trigger, event trigger, LO ACL, SECURITY DEFINER
\set ON_ERROR_STOP on
CREATE EXTENSION postgres_fdw;
CREATE SERVER prod_link FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host '127.0.0.1', dbname 'hibrit_giris_db');
CREATE USER MAPPING FOR hgs2_perftest SERVER prod_link OPTIONS (user 'x', password 'SENTETIK-PAROLA-UM');
CREATE FUNCTION public.trg_noop() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END';
CREATE TRIGGER logs_noop BEFORE INSERT ON public.logs FOR EACH ROW EXECUTE FUNCTION public.trg_noop();
CREATE FUNCTION public.evt_noop() RETURNS event_trigger LANGUAGE plpgsql AS 'BEGIN END';
CREATE EVENT TRIGGER evt_noop ON ddl_command_end EXECUTE FUNCTION public.evt_noop();
CREATE FUNCTION public.secdef_no_path() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1';
SELECT lo_from_bytea(0, '\x4c4f32'::bytea) AS lo2 \gset
GRANT SELECT ON LARGE OBJECT :lo2 TO hgs2_perftest;
