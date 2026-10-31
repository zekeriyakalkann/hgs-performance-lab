--
-- PostgreSQL database cluster dump
--

\restrict ECIliGmUn744hCEVhfencSg4LMehWYCtURdy5y9FhogyQ592cc6XxEgi8LbjPLt

SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

--
-- Roles
--

CREATE ROLE grp_nested;
ALTER ROLE grp_nested WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB NOLOGIN NOREPLICATION NOBYPASSRLS;
CREATE ROLE grp_reader;
ALTER ROLE grp_reader WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB NOLOGIN NOREPLICATION NOBYPASSRLS;
CREATE ROLE hgs2_auditor;
ALTER ROLE hgs2_auditor WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS;
CREATE ROLE hgs2_auditor_nosysid;
ALTER ROLE hgs2_auditor_nosysid WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS;
CREATE ROLE hgs2_perftest;
ALTER ROLE hgs2_perftest WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS;
CREATE ROLE hgs2_su_behind_role;
ALTER ROLE hgs2_su_behind_role WITH SUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS;
CREATE ROLE pgadmin;
ALTER ROLE pgadmin WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS;

--
-- User Configurations
--

--
-- User Config "hgs2_perftest"
--

ALTER ROLE hgs2_perftest SET search_path TO 'public', 'pg_catalog';

--
-- User Config "hgs2_su_behind_role"
--

ALTER ROLE hgs2_su_behind_role SET role TO 'hgs2_auditor';


--
-- Role memberships
--

GRANT grp_nested TO hgs2_perftest WITH INHERIT TRUE GRANTED BY pgadmin;
GRANT grp_reader TO grp_nested WITH INHERIT TRUE GRANTED BY pgadmin;






\unrestrict ECIliGmUn744hCEVhfencSg4LMehWYCtURdy5y9FhogyQ592cc6XxEgi8LbjPLt

--
-- PostgreSQL database cluster dump complete
--

