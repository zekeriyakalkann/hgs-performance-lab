-- SENTETIK saldiri: text = text operatorunu golgeleyen sahte operator (yalnizca PG18 test kumesi)
\set ON_ERROR_STOP on
CREATE SCHEMA evil;
CREATE FUNCTION evil.always_true(text, text) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true';
CREATE OPERATOR evil.= (LEFTARG = text, RIGHTARG = text, FUNCTION = evil.always_true);
GRANT USAGE ON SCHEMA evil TO PUBLIC;
