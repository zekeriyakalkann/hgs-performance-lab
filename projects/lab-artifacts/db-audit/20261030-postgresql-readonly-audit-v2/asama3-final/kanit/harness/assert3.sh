SECRETS='SENTETIK-GIZLI-DEGER|SENTETIK-PAROLA-GUC|SENTETIK-PAROLA-UM|SENTETIK-TOKEN-FN|SENTETIK-TOKEN-POL|SENTETIK-TOKEN-AUDITROLE|sentetik-prod-host'
assert_catalog3() { local f="$1" tag="$2" pass=0 fail=0
  while IFS='|' read -r name re; do [ -z "$name" ] && continue; if grep -qaE "$re" "$f"; then pass=$((pass+1)); else fail=$((fail+1)); echo "  FAIL $tag: $name"; fi; done < "$S/h/assert_catalog3.txt"
  echo "$tag: pass=$pass fail=$fail secret_leaks=$(grep -aoE "$SECRETS" "$f" | wc -l)"; }
