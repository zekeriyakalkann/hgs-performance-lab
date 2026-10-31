"""Patch build_runner.py -> R2: (1) EK R1-8 path normalization substitutions, (2) runner not copied into evidence (EK R1-9)."""
p = 'build_runner.py'
s = open(p, encoding='utf-8').read()

# (1) helper defined right after block 1 (where $Data exists)
s = s.replace("LC_DEF = r'''\n", r"""LC_DEF = r'''
# [A-R1-8] ---- komut satiri / veri dizini karsilastirmasi: pg_ctl yolu '/' ile kanoniklestirir (postmaster.opts kaniti) ----
# Ayni anlam, iki ayirici bicimi de kabul edilir; bos komut satiri (baska kullanicinin sureci) asla eslesmez.
function Test-CmdLineHasData([string]$CommandLine) {
    if ([string]::IsNullOrEmpty($CommandLine)) { return $false }
    return ($CommandLine.Replace([char]47, [char]92).IndexOf([IO.Path]::GetFullPath($Data), [StringComparison]::OrdinalIgnoreCase) -ge 0)
}
""", 1)

# substitutions applied to specific blocks; recorded in provenance
s = s.replace("""READ_HOST = "$confirm""", """SUB_PM = ('$_.CommandLine -like "*$Data*"', '(Test-CmdLineHasData $_.CommandLine)')
SUB_CL = ('$cl -like "*$Data*"', '(Test-CmdLineHasData $cl)')
def subst(n, b):
    c1 = b.count(SUB_PM[0]); c2 = b.count(SUB_CL[0])
    return b.replace(SUB_PM[0], SUB_PM[1]).replace(SUB_CL[0], SUB_CL[1]), c1 + c2
READ_HOST = "$confirm""", 1)

s = s.replace("out += [banner(6), blocks[6][2], A25, lc('after-S2.5')]; use(6, 'AYNEN')",
              "b6, k6 = subst(6, blocks[6][2]); assert k6 == 2\nout += [banner(6), b6, A25, lc('after-S2.5')]; use(6, 'AYNEN, EK R1-8 ikamesi x2: CommandLine/cl -like *$Data* -> Test-CmdLineHasData')")
s = s.replace("out += [banner(14), blocks[14][2], A101]; use(14, 'AYNEN')",
              "b14, k14 = subst(14, blocks[14][2]); assert k14 == 1\nout += [banner(14), b14, A101]; use(14, 'AYNEN, EK R1-8 ikamesi x1')")
s = s.replace("b17 = blocks[17][2].replace(", "b17, k17 = subst(17, blocks[17][2]); assert k17 == 1\nb17 = b17.replace(")
s = s.replace("use(17, 'AYNEN, tek satir degisti: Read-Host -> Wait-DeleteConfirmation; blok try/catch icinde')",
              "use(17, 'AYNEN, Read-Host -> Wait-DeleteConfirmation; EK R1-8 ikamesi x1; blok try/catch icinde')")
# A25 / A101 own additions
s = s.replace("""test_postmaster={3}' -f $l.LocalAddress, $l.LocalPort, $l.OwningProcess, ($cl -like "*$Data*")""",
              """test_postmaster={3}' -f $l.LocalAddress, $l.LocalPort, $l.OwningProcess, (Test-CmdLineHasData $cl)""")
s = s.replace("""$__pf2 = @(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { $_.CommandLine -like "*$Data*" }).Count""",
              """$__pf2 = @(Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object { Test-CmdLineHasData $_.CommandLine }).Count""")
# verbatim check must skip substituted blocks
s = s.replace("for n in list(range(0, 17)) + [18, 19]:", "for n in [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 15, 16, 18, 19]:")
s = s.replace("for n in [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 15, 16, 18, 19]:\n    assert blocks[n][2].replace('\\n', '\\r\\n') in runner, n",
              "for n in [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 15, 16, 18, 19]:\n    assert blocks[n][2].replace('\\n', '\\r\\n') in runner, n\nassert '*$Data*' not in runner")

# (2) runner itself not copied into evidence (its text contains the 10.2 scan literal); only its SHA-256
s = s.replace("""Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $Inputs 'runner_v1_single_session.ps1')""",
              """# EK R1-9: betigin kendisi kanita KOPYALANMAZ (10.2 tarama sabitini icerir); yalnizca SHA-256'si yazilir, betik kosu sonrasi arsive eklenir
Write-TestFile (Join-Path $Inputs 'runner_v1_single_session.sha256') (((Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash.ToLower()) + '  runner_v1_single_session.ps1' + "`n")""")

for k in ['function Test-CmdLineHasData', 'def subst', 'assert k6 == 2', 'assert k14 == 1', 'assert k17 == 1',
          '(Test-CmdLineHasData $cl)""")' if False else 'Test-CmdLineHasData $cl)', "assert '*$Data*' not in runner", 'runner_v1_single_session.sha256']:
    assert k in s, k
open(p, 'w', encoding='utf-8').write(s)
print('patched')
