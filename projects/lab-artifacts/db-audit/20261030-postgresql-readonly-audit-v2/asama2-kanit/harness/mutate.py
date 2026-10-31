"""Build mutation copies of the audit script (scratchpad only) to test defence layers."""
import re
import sys

new_path, old_path, out_dir = sys.argv[1:4]
BS = "\\"


def load(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def save(name, text, base):
    assert text != base, name + ": mutation did not apply"
    with open(f"{out_dir}/{name}", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("ok", name)


def drop_if_block(text, var):
    """Remove the first top-level psql block that starts with '\\if :<var>' up to its '\\endif'."""
    pat = re.compile("^" + re.escape(BS + "if :" + var) + r"\n.*?^" + re.escape(BS + "endif") + r"\n",
                     re.S | re.M)
    out, n = pat.subn("", text, count=1)
    assert n == 1, var
    return out


new = load(new_path)
old = load(old_path)

# P2 gates removed (new): leaves only the P3 probe against open transactions
no_p2 = drop_if_block(drop_if_block(new, "open_tx_has_xid"), "no_open_tx_hint")
save("new_noP2.sql", no_p2, new)

# P2 gates and P3 probe removed (new): shows what the probe protects against
probe = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED;\nSET TRANSACTION ISOLATION LEVEL REPEATABLE READ;\n"
save("new_noP2_noprobe.sql", no_p2.replace(probe, ""), no_p2)

# Original v2 with its timestamp gate removed: its only barrier against psql -1
save("old_noP2.sql", drop_if_block(old, "no_open_tx"), old)

# ON_ERROR_STOP forced off: exercises the secondary \quit
save("new_onerrorstop_off.sql",
     new.replace(BS + "set ON_ERROR_STOP on\n", BS + "set ON_ERROR_STOP off\n", 1), new)
