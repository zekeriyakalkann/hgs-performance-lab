\pset format unaligned
\pset footer off
SELECT 'admins', md5(string_agg(t::text, ';' ORDER BY id)) FROM public.admins t
UNION ALL SELECT 'devices', md5(string_agg(t::text, ';' ORDER BY id)) FROM public.devices t
UNION ALL SELECT 'users', md5(string_agg(t::text, ';' ORDER BY id)) FROM public.users t
UNION ALL SELECT 'logs', md5(string_agg(t::text, ';' ORDER BY id)) FROM public.logs t;
SELECT 'seq', relname, (pg_sequence_last_value(c.oid))::text FROM pg_class c WHERE relkind='S' ORDER BY relname;
SELECT 'lo', oid::text, lomowner::regrole::text, lomacl::text FROM pg_largeobject_metadata ORDER BY oid;
SELECT 'db', datname, datacl::text FROM pg_database ORDER BY datname;
SELECT 'drs', setdatabase, setrole::regrole::text, setconfig::text FROM pg_db_role_setting ORDER BY 1,2,3;
SELECT 'roles', rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin, rolreplication, rolbypassrls FROM pg_roles ORDER BY rolname;
SELECT 'members', roleid::regrole::text, member::regrole::text, admin_option FROM pg_auth_members ORDER BY 2,3;
SELECT 'classes', count(*) FROM pg_class;
