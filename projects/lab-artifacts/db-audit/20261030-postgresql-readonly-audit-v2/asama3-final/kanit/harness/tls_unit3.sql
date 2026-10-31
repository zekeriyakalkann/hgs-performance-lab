-- Birim testi: P6b (U4) siniflama ve karar ifadesinin AYNISI, sabit girdilerle.
-- Uctan uca test DEGILDIR; yalnizca ifade mantigini dogrular.
WITH c(host, server_addr, ssl, allow_flag, expected_ok) AS (VALUES
  ('127.0.0.1',            '127.0.0.1'::inet, false, '0', true),
  ('localhost',            '127.0.0.1'::inet, false, '0', true),
  ('LOCALHOST',            '::1'::inet,       false, '0', true),
  ('::1',                  '::1'::inet,       false, '0', true),
  ('::ffff:127.0.0.1',     '::ffff:127.0.0.1'::inet, false, '0', true),
  ('/var/run/postgresql',  NULL::inet,        NULL,  '0', true),
  ('@abstract',            NULL::inet,        NULL,  '0', true),
  ('C:/pgsock',            NULL::inet,        NULL,  '0', true),
  ('fake-remote.example',  '127.0.0.1'::inet, false, '0', false),
  ('fake-remote.example',  '127.0.0.1'::inet, true,  '0', true),
  ('fake-remote.example',  '127.0.0.1'::inet, false, '1', true),
  ('fake-remote.example',  '127.0.0.1'::inet, false, 'true', false),
  ('10.1.2.3',             '10.1.2.3'::inet,  false, '0', false),
  ('10.1.2.3',             '10.1.2.3'::inet,  true,  '0', true),
  ('127.0.0.1',            '10.1.2.3'::inet,  false, '0', false),
  ('a::1',                 '127.0.0.1'::inet, false, '0', false),
  ('127.0.0.1.evil.example','127.0.0.1'::inet, false, '0', false),
  ('2001:db8::5',          '2001:db8::5'::inet, false, '0', false),
  ('db.example',           NULL::inet,        NULL,  '0', false)
), t AS (
  SELECT c.*,
         CASE WHEN c.server_addr IS NULL THEN 'unix-socket'
              WHEN c.server_addr <<= '127.0.0.0/8'::inet
                OR c.server_addr <<= '::1/128'::inet
                OR c.server_addr <<= '::ffff:127.0.0.0/104'::inet THEN 'tcp-loopback'
              ELSE 'tcp-remote' END AS transport,
         CASE WHEN c.host ~ '^(/|@|[A-Za-z]:[^:])' THEN 'socket'
              WHEN pg_catalog.lower(c.host) IN ('localhost', '::1', '0:0:0:0:0:0:0:1')
                OR c.host ~ '^127[.][0-9]+[.][0-9]+[.][0-9]+$'
                OR pg_catalog.lower(c.host) ~ '^::ffff:127[.][0-9]+[.][0-9]+[.][0-9]+$' THEN 'loopback'
              ELSE 'remote' END AS client_host_class
  FROM c
), d AS (
  SELECT t.*, COALESCE(t.ssl OR (t.transport IN ('unix-socket', 'tcp-loopback')
                                 AND t.client_host_class IN ('socket', 'loopback')), false) AS transport_secure
  FROM t
)
SELECT host, server_addr, ssl, allow_flag, transport, client_host_class,
       COALESCE(transport_secure OR allow_flag = '1', false) AS transport_ok,
       expected_ok,
       COALESCE(transport_secure OR allow_flag = '1', false) = expected_ok AS matches
FROM d;
