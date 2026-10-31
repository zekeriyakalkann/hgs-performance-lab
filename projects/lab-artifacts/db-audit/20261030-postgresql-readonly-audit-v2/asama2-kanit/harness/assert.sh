assert_catalog() { local f="$1" tag="$2" pass=0 fail=0
  while IFS='|' read -r name re; do [ -z "$name" ] && continue; if grep -qE "$re" "$f"; then pass=$((pass+1)); else fail=$((fail+1)); echo "  FAIL $tag: $name"; fi; done < "$S/h/assert_catalog.txt"
  echo "$tag: pass=$pass fail=$fail secret_leak=$(grep -c 'SENTETIK-GIZLI-DEGER' "$f")"; }
