# Lab Artifacts — denetim raporları ve onaylı kanıtlar

HGS2 Performance Lab çalışmasının denetim raporları, test kanıtları ve bütünlük manifestleri. İçerik, yerel
`hgs2-lab-artifacts` dizininin (Git deposu değildi) **güvenlik incelemesinden geçmiş bir alt kümesidir** ve bayt bayt
korunur (`.gitattributes`: `projects/lab-artifacts/** -text -whitespace`), böylece SHA-256 manifestleri doğrulanabilir.

> Tüm veritabanı kanıtları **izole, sentetik PostgreSQL test kümelerinden** üretilmiştir (ör. V1 yürütmesi: port 55438,
> `cluster_name = hgs2iso18`). Gerçek (production) veritabanından veri, döküm veya kullanıcı kaydı içermez. Belgelerde
> geçen parolalar bilinçli sahte değerlerdir (`SENTETIK-PAROLA…`, `S3-perftest-…`, `S4-audit-…`,
> `FAKE-SECRET-123`); SCRAM çıktıları yalnızca `SCRAM-SHA-256$` önekini gösterir.

## İçerik

```
projects/lab-artifacts/
├── db-audit/20261030-postgresql-readonly-audit-v2/
│   ├── ASAMA2_RAPORU.md, postgresql_readonly_audit_v2.sql
│   ├── asama2-kanit/          2. aşama: harness, mutantlar, anlık görüntüler, runs/MATRIX.md, SHA256SUMS.txt
│   ├── asama3-final/          3. aşama nihai teslim
│   │   ├── FINAL_SECURITY_AUDIT.md, FINAL_TEST_MATRIX.md, KNOWN_LIMITATIONS.md
│   │   ├── FINAL_DELIVERY.md, CHANGELOG_FINAL.md, MINIMUM_PRIVILEGE_ANALYSIS.md
│   │   ├── FINAL_SHA256SUMS.txt, postgresql_readonly_audit_v2.sql
│   │   └── kanit/             harness, mutants, snapshots, certs-public (yalnızca açık sertifikalar), runs-final/MATRIX.md
│   ├── asama4-v1-execution/   izole küme V1 yürütmesi
│   │   ├── FINAL_EXECUTION_REPORT.md, FINAL_SECURITY_AUDIT.md, FINAL_TEST_MATRIX.md
│   │   ├── KNOWN_LIMITATIONS.md, DOCUMENTATION_CLOSURE_REPORT.md
│   │   └── FINAL_SHA256SUMS.txt
│   └── role-design/           rol/yetki tasarımı ve yürütme kılavuzu
│       ├── AUDIT_ROLE_PRIVILEGE_MATRIX.md, ISOLATED_CLUSTER_TEST_PLAN.md
│       ├── EXECUTION_RUNBOOK_V1.md, EXECUTION_RUNBOOK_V1_ADDENDUM_R1.md
│       ├── iso-runs/iso18-20261030T231228/          geçerli V1 çalıştırması (SONUC: V1 TAMAMLANDI)
│       └── iso-runs-incomplete/                     tamamlanmamış iki çalıştırma ve durum notları
├── hgs2-evidence/surefire-20261023T180529-HgsApplicationTests-default-profile/
│                              Surefire özeti, SHA256SUMS.txt, özgün denetim SQL'i
├── test-evidence/             Performance Lab pytest kanıt çalıştırmaları (N12)
└── tools/                     kanıt üreten pytest çalıştırıcısı ve yarış yeniden üretim eklentisi
```

Önerilen okuma sırası: `asama4-v1-execution/FINAL_EXECUTION_REPORT.md` → `asama4-v1-execution/FINAL_SECURITY_AUDIT.md`
→ `asama4-v1-execution/FINAL_TEST_MATRIX.md` → `KNOWN_LIMITATIONS.md` → `role-design/EXECUTION_RUNBOOK_V1_ADDENDUM_R1.md`.

## Bütünlük doğrulaması

Depo kökünden (salt okunur; ters eğik çizgili yolları ve farklı manifest köklerini çözer):

```powershell
python scripts/verify_lab_artifacts.py
```

Birleştirme sırasında elde edilen sonuç (0 uyuşmazlık):

| Manifest | Doğrulanan | Uyuşmazlık | Depoda olmayan (bilinçli dışlanan) |
|---|---:|---:|---:|
| `asama4-v1-execution/FINAL_SHA256SUMS.txt` | 142 | 0 | 0 |
| `role-design/iso-runs/iso18-20261030T231228/SHA256SUMS.txt` | 95 | 0 | 0 |
| `role-design/iso-runs-incomplete/…T223605/SHA256SUMS.txt` | 10 | 0 | 0 |
| `role-design/iso-runs-incomplete/…T230745/SHA256SUMS.txt` | 17 | 0 | 0 |
| `asama3-final/FINAL_SHA256SUMS.txt` | 87 | 0 | 3027 |
| `asama2-kanit/SHA256SUMS.txt` | 63 | 0 | 680 |
| `hgs2-evidence/…/SHA256SUMS.txt` | 1 | 0 | 1 |

`asama2` ve `asama3` manifestlerindeki "depoda olmayan" girdiler aşağıda dışlanan ham çalıştırma çıktıları ve sunucu
günlükleridir; özgün yerel dizinde durmaktadırlar.

## Depoya alınmayan içerik

| İçerik | Boyut | Gerekçe |
|---|---|---|
| `backups/` | 9.7 MB, 1071 dosya | Bu deponun eski çalışma ağacı kopyaları (iç içe `.git` dizinleri dahil); Git geçmişiyle yinelenir |
| `evidence-backups/` | 1.2 MB | `test-evidence/` ve `tools/` dizinlerinin birebir kopyası |
| `*/server-logs/` | ~20 MB | Test kümesi sunucu günlükleri; büyük ve yeniden üretilebilir |
| `asama3-final/kanit/runs-final/`, `runs-trial/`, `runs-discovery/`, `asama2-kanit/runs/` (MATRIX.md hariç) | ~15 MB, ~3700 dosya | Ham stdout/stderr çıktıları; harness ile yeniden üretilebilir, özetleri MATRIX.md'de |
| `hgs2-evidence/…/TEST-com.HibritGirisSistemi.HGS.HgsApplicationTests.xml` | 41 KB | Makineye özgü JVM sistem özellikleri (tam PATH, kullanıcı ve dizin yolları) |

## Bilinen notlar

* Kanıt dosyalarında yerel makine adı ve Windows kullanıcı dizini yolları geçer. Gizli bilgi değildir; dosyalar
  SHA-256 ile mühürlü olduğundan değiştirilmemiştir.
* Bazı kanıt dosyalarında satır sonu boşlukları ve CRLF vardır (özgün komut çıktısı); bu nedenle bu dizin
  `git diff --check` denetiminden muaf tutulur.
* `test-evidence/*/tree-manifest.sha256` dosyaları, kanıtın üretildiği andaki Performance Lab çalışma ağacına aittir
  (o zamanki depo kökü); bu depodaki dizin düzeniyle doğrulanmaları beklenmez.

## test-evidence/ ve tools/ (özgün açıklama, 2026-10-29)

Her pytest çalıştırması kendi dizininde: `command.txt`, `environment.json`, `summary.json` (başlangıç/bitiş UTC,
çıkış kodu, JUnit sayıları, test edilen ağacın manifest özeti), `git-head.txt`, `git-status-short.txt`,
`git-diff-stat.txt`, `tree-manifest.sha256`, `junit.xml`, `console.txt`. Ayrıntılı tablo: Performance Lab
README.md, "N12 kapanış kaydı".

* `*-baseline-pre-change-*` — değişiklik ÖNCESİ kod (ağaç özeti `67389db4…`).
* `*-step1..6-*` — değişiklik SONRASI kod (ağaç özeti `894c216f…`); son ağaçtan tek farkı README.md.
* `*-flaky-candidate-*` — kararsız test adayı; `race-repro` bir yeniden üretim deneyidir (bkz. `NOTE.txt`).
* `tools/run_pytest_evidence.py` — kanıt üreten pytest çalıştırıcısı (hiçbir dizinin üzerine yazmaz).
* `tools/delay_finish_plugin.py` — yalnızca yarış yeniden üretimi için pytest eklentisi.
