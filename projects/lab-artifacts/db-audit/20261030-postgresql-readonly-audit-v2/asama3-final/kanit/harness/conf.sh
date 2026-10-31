# Append test-only settings to a temp cluster's postgresql.conf: $1=version
conf_cluster() { local v="$1" d="$S/c$1"; cat >> "$d/postgresql.conf" <<EOC
# --- HGS2 audit test cluster (temporary, isolated) ---
port = 554$v
listen_addresses = '127.0.0.1'
unix_socket_directories = ''
cluster_name = 'hgs2test$v'
log_statement = 'all'
log_line_prefix = '%m [%p] user=%u db=%d app=%a '
ssl = on
ssl_cert_file = '$(cygpath -m "$S/certs/server.crt")'
ssl_key_file = '$(cygpath -m "$S/certs/server.key")'
EOC
}
hba_cluster() { printf '%s\n' '# HGS2 test cluster: loopback IPv4 only' 'host all all 127.0.0.1/32 trust' > "$S/c$1/pg_hba.conf"; }
start_cluster() { "$(binof "$1")/pg_ctl.exe" -D "$S/c$1" -l "$S/c$1.log" -w -t 60 start; }
stop_cluster() { "$(binof "$1")/pg_ctl.exe" -D "$S/c$1" -m fast -w stop; }
