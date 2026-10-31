# hgs2-lab-artifacts

Depo dışı koruma ve test kanıtları (hgs2-performance-lab, N12, 2026-10-29). Git deposunun parçası değildir.

## backups/backup-20261029T182428-pre-f1-f3/

N12 (F-1/F-3) değişikliklerinden ÖNCEKİ çalışma ağacı. HEAD `1fe78f482c8f430b125db853c73b1423d80f593a` (`main`),
14 değiştirilmiş + 62 izlenmeyen dosya; `.git` dahil, `.venv` / `__pycache__` / egg-info hariç (337 dosya).

* `tree/` — kopya. `git -C tree status --short` başlangıçtaki 45 satırı verir.
* `MANIFEST-source.sha256` — 144 kaynak dosyanın SHA-256'sı (`.git` hariç); manifestin kendi özeti
  `bc310a549f2112bbeee9e4c28f8e8a140b71d4c1898c9ddbe8fcd00cc4433495`. Doğrulama:
  `cd tree && sha256sum -c ../MANIFEST-source.sha256`.
* `git-state/` — `HEAD.txt`, `branch.txt`, `status-short.txt`, `diff-stat.txt`, `tracked-changes.patch` (ikili),
  `modified-files.txt`, `untracked-files.txt`, `files-all.txt`.

Bu yedek değişiklik öncesi aşamaya aittir; depodaki mevcut çalışma ağacı N12 sonrasıdır.

## test-evidence/

Her pytest çalıştırması kendi dizininde: `command.txt`, `environment.json`, `summary.json` (başlangıç/bitiş UTC,
çıkış kodu, JUnit sayıları, test edilen ağacın manifest özeti), `git-head.txt`, `git-status-short.txt`,
`git-diff-stat.txt`, `tree-manifest.sha256`, `junit.xml`, `console.txt`. Ayrıntılı tablo: depodaki README.md,
"N12 kapanış kaydı".

* `*-baseline-pre-change-*` — değişiklik ÖNCESİ kod (ağaç özeti `67389db4…`, yedekle aynı).
* `*-step1..6-*` — değişiklik SONRASI kod (ağaç özeti `894c216f…`); son ağaçtan tek farkı README.md.
* `*-flaky-candidate-*` — kararsız test adayı; `race-repro` bir yeniden üretim deneyidir (bkz. `NOTE.txt`).

## tools/

* `run_pytest_evidence.py` — kanıt üreten pytest çalıştırıcısı (hiçbir dizinin üzerine yazmaz; depoya yazmaz).
* `delay_finish_plugin.py` — yalnızca yarış yeniden üretimi için pytest eklentisi (depo dışı).
