WITH c(server_addr, ssl, allow_flag) AS (VALUES
  (NULL::inet, NULL::bool, '0'), ('127.0.0.1', false, '0'), ('127.8.9.10', false, '0'), ('::1', false, '0'),
  ('::ffff:127.0.0.1', false, '0'), ('10.1.2.3', false, '0'), ('10.1.2.3', true, '0'), ('10.1.2.3', false, '1'),
  ('10.1.2.3', false, 'true'), ('2001:db8::5', false, '0'), ('2001:db8::5', true, '0'), ('192.168.1.10', NULL, '0')
), t AS (
  SELECT c.*, CASE WHEN c.server_addr IS NULL THEN 'unix-socket'
                WHEN c.server_addr <<= '127.0.0.0/8'::inet
                  OR c.server_addr <<= '::1/128'::inet
                  OR c.server_addr <<= '::ffff:127.0.0.0/104'::inet THEN 'tcp-loopback'
                ELSE 'tcp-remote' END AS transport FROM c)
SELECT server_addr, ssl, allow_flag, transport,
       COALESCE(t.transport <> 'tcp-remote' OR t.ssl OR allow_flag = '1', false) AS transport_ok FROM t;
