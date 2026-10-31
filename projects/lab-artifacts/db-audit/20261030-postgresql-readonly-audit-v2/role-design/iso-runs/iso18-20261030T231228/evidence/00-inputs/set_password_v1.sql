-- HGS2 V1 - test rolune rastgele test parolasi (plan 3.3 test kumesi yolu b). Parola bu dosyada YOK.
\set ON_ERROR_STOP on
SELECT current_setting('port') = '55438'
   AND current_setting('cluster_name') = 'hgs2iso18' AS iso_ok \gset
\if :iso_ok
\else
  \echo 'DUR: izole test kumesi degil'
  SELECT 1/0;
\endif
\getenv pw HGS2_ISO_PW
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
ALTER ROLE :"target_role" PASSWORD :'pw';
RESET log_min_error_statement;
RESET log_statement;
\unset pw