# Birleşik Depo Raporu — HGS2 Unified Repository

- Tarih: 2026-10-31
- Hazırlayan: Zekeriya Kalkan (Claude Code ile)
- Hedef depo: `github.com/zekeriyakalkann/hgs-performance-lab` (public, varsayılan dal `main`)
- SSH uzak adresi: `git@github.com:zekeriyakalkann/hgs-performance-lab.git`

> **Depo adı notu:** Görev tanımındaki `zekeriyakalkann/hgs2-performance-lab` adresi GitHub API'de 404 döndürdü
> (mevcut değil ya da özel). Mevcut `origin` olan `hgs-performance-lab` deposu kullanıcı onayıyla hedef seçildi.
> Depo GitHub'da sonradan `hgs2-performance-lab` olarak yeniden adlandırılabilir (GitHub eski adresi yönlendirir).

## 1. Birleştirilen depolar

| Kaynak | Tür | Durum (birleştirme öncesi) | Aktarım |
|---|---|---|---|
| `Projects\hgs2-performance-lab` | Git, `origin` = `zekeriyakalkann/hgs-performance-lab` | `main`, 8 commit, temiz, etiket yok | Ana depo; geçmiş olduğu gibi korundu |
| `Projects\hgs2` | Git, `origin` = `ServetAlav001/hgs2` (başka bir kullanıcının açık deposu) | `main` 5 commit (`ad255a4`) + ilişkisiz `origin/master` 3 commit; 1 değiştirilmiş + 5 izlenmeyen dosya | `main` geçmişi maskelenerek aktarıldı; izlenmeyen `perftest` çalışması ayrı commit |
| `Projects\hgs2-lab-artifacts` | Git deposu değil; 5327 dosya, 51 MB | — | Onaylı alt küme (421 dosya, 4.8 MB) anlık görüntü commit'i |

Özgün üç dizin ve `.git` klasörleri **değiştirilmedi ve silinmedi** (`hgs2` çalışma ağacındaki değişiklikler de
yerinde duruyor). Birleştirme öncesi durum yerel `backup/pre-unify-66518c6` dalında da tutuluyor (GitHub'a gönderilmedi).

## 2. Nihai klasör yapısı

```
hgs2-performance-lab/
├── README.md, .gitignore, .gitattributes
├── projects/
│   ├── hgs2/                 README.md + hgs2-main/HGS-main/{HGS (Spring Boot), donanım kodları}
│   ├── performance-lab/      README.md, pyproject.toml, requirements.txt, constraints.txt, src/hgs2_lab, tests, configs
│   └── lab-artifacts/        README.md, db-audit/, test-evidence/, hgs2-evidence/, tools/
├── docs/
│   ├── architecture/ARCHITECTURE.md
│   ├── security/SECURITY.md
│   ├── project-overview/PROJECT_OVERVIEW.md
│   └── UNIFIED_REPOSITORY_REPORT.md   (bu dosya)
└── scripts/
    ├── README.md
    └── verify_lab_artifacts.py
```

## 3. Git geçmişinin aktarımı

### Performance Lab — geçmiş korundu (yeniden yazma yok)

Tüm izlenen dosyalar `git mv` ile `projects/performance-lab/` altına taşındı (153 yeniden adlandırma, tek commit).
Özgün 8 commit'in kimlikleri değişmedi; `origin/main` ile hızlı ileri sarma (fast-forward) ilişkisi korundu.
Dosya geçmişi: `git log --follow -- projects/performance-lab/src/hgs2_lab/cli.py` → `a2f5d9f`'ye kadar.

`pyproject.toml` (`pythonpath = ["src"]`, `testpaths = ["tests"]`) ve testlerdeki yollar (`Path(__file__).parent…`)
proje dizinine göreli olduğu için değişiklik gerekmedi. Proje `.gitignore` / `.gitattributes` dosyaları
(`tests/golden/** -text` dahil) yerinde çalışmaya devam ediyor.

### HGS2 — geçmiş korundu, kimlik bilgileri maskelendi

Seçenekler değerlendirildi:

| Yöntem | Sonuç |
|---|---|
| `git subtree add --prefix` | Reddedildi: eski commit'lerde dosyalar kökte kalır, `git log -- projects/hgs2` eski commit'leri göstermez; kimlik bilgileri geçmişte kalırdı |
| Doğrudan `merge --allow-unrelated-histories` | Reddedildi: dosyalar kök dizinle karışır; kimlik bilgileri geçmişte kalırdı |
| **Geçici klonda yeniden yazma + `merge --allow-unrelated-histories`** | **Seçildi** |

Uygulama:

1. `hgs2` deposunun `main` dalı oturuma özgü geçici dizine klonlandı (`--no-local --single-branch`; özgün depo yalnızca okundu).
2. Klonda `git filter-branch --tree-filter` ile her commit'te: `spring.datasource.password` → `${HGS_DB_PASSWORD}`;
   ESP32 sketch'inde `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_IP` → yer tutucular; tüm dosyalar `projects/hgs2/` altına.
   (`git filter-repo` kurulu değildi.)
3. Doğrulama: özgün geçmişten toplanan gerçek değerlerin hiçbiri yeniden yazılmış commit'lerde yok. Son ağaçtaki tek
   içerik farkı maskelenen 4 satır.
4. Yeniden yazılmış dal ana depoya alınıp `--no-ff --allow-unrelated-histories` ile birleştirildi; geçici başvuru silindi.
   Özgün (maskesiz) commit ve blob nesneleri ana deponun nesne veritabanında **bulunmuyor** (doğrulandı).

Yazar, tarih ve mesajlar korundu; maskeleme nedeniyle commit kimlikleri değişti:

| Özgün (`ServetAlav001/hgs2`) | Bu depoda | Mesaj |
|---|---|---|
| `ad255a4` | `8c50c1e` | Delete HGS-main directory |
| `728c888` | `4f0de8e` | proje yüklendi |
| `1197802` | `08f27c9` | proje dosyalari eklendi |
| `f955900` | `2fb7c9a` | düzeltme |
| `e06b7e1` | `7b79bad` | düzeltme yapıldı |

`origin/master` (ilişkisiz geçmiş, `ffe0849..9bbe2cd`, ESP entegrasyon güncellemeleri) kullanıcı kararıyla
**aktarılmadı**: Performance Lab ve `perftest` çalışması `main` üzerine kurulmuştu.

`hgs2` çalışma ağacındaki işlenmemiş `perftest` değişiklikleri (1 değiştirilmiş, 5 yeni dosya) özgün dizinden
**kopyalanarak** ayrı bir commit'e alındı; altı dosya da baytı baytına aynı (`cmp`), değiştirilmiş dosyanın diff'i
özgün depodakiyle aynı.

### Lab Artifacts — anlık görüntü

Git deposu olmadığından aktarılacak geçmiş yoktu. Onaylı alt küme tek commit'le eklendi; 421 dosyanın tamamı özgün
dosyalarla baytı baytına aynı. Kök `.gitattributes` bu dizini `-text -whitespace` olarak işaretler.

## 4. Oluşturulan commit'ler

Özgün 8 Performance Lab commit'inin üzerine (`66518c6`):

| Commit | Mesaj |
|---|---|
| `4a9b27f` | chore: establish unified repository structure and move performance lab |
| `7b79bad` … `8c50c1e` | HGS2 `main` geçmişi (5 commit, yukarıdaki tablo) |
| `477dc0f` | Merge HGS2 application history into projects/hgs2 |
| `2c8846e` | feat(hgs2): add perftest profile and startup safety guard |
| `bf9718b` | docs: add lab artifacts (audit reports and approved evidence) |
| `a536cea` | docs: add unified repository documentation and report |
| (bu commit) | docs: record push result in unified repository report |

## 5. Test sonuçları

Performance Lab, `projects/performance-lab` dizininden, Python 3.15.0 / pytest 9.1.1:

| Çalıştırma | Sonuç |
|---|---|
| Taşıma öncesi temel çizgi (`66518c6`, depo kökü) | 1677 passed, 1 skipped, 114 deselected |
| Taşıma sonrası (`4a9b27f`) | 1677 passed, 1 skipped, 114 deselected |
| Son ağaç, varsayılan çalıştırma | 1677 passed, 1 skipped, 114 deselected |
| Son ağaç, `-m integration` | 114 passed, 1678 deselected |

* Testler `tests/isolation_guard.py` ile korunur (yalnızca test sürecinin kendi açtığı loopback soketleri);
  entegrasyon testleri yalnızca 127.0.0.1 üzerindeki yerel test sunucularını kullanır. Dış servise, gerçek veritabanına
  veya HGS2'ye bağlanan test yoktur.
* HGS2 (Maven) testleri **çalıştırılmadı**: `perftest` profili izole test veritabanı ve ortam değişkenleri gerektirir;
  görev kuralları gereği HGS2 başlatılmadı, PostgreSQL'e dokunulmadı, SQL çalıştırılmadı.
* Lab Artifacts manifest doğrulaması (`scripts/verify_lab_artifacts.py`): 415 dosya OK, **0 uyuşmazlık**
  (ayrıntı: `projects/lab-artifacts/README.md`).
* Not: kök `.venv`'deki eski düzenlenebilir kurulum (`__editable__…pth`) artık var olmayan `src/` yolunu gösteriyor;
  testler `pythonpath = ["src"]` sayesinde etkilenmez. CLI'yi kullanmak için `projects/performance-lab` içinde
  `pip install -e .` yeniden çalıştırılmalı.

## 6. Güvenlik taraması

Gönderilecek 17 commit'in tamamı ve çalışma ağacı tarandı:

| Denetim | Sonuç |
|---|---|
| HGS2 gerçek değerleri (DB parolası, Wi-Fi SSID/parola, yerel IP) | Geçmişte 0, çalışma ağacında 0 eşleşme |
| `spring.datasource.password` satırları | Yalnızca `${HGS_DB_PASSWORD}` ve `${HGS_PERFTEST_DB_PASSWORD}` |
| Özel anahtar, GitHub/AWS/Slack token, tam SCRAM doğrulayıcısı | 0 |
| Yasak dosya adları (`.env*`, `*.pem/key/p12/pfx`, `pgpass`, `netrc`, `id_*`, döküm) | Hiçbir commit'te yok |
| Kimlik bilgili bağlantı dizesi | Yalnızca test verisi `postgresql://fake:FAKE-SECRET-123@db.example.invalid` |
| En büyük dosya | 392 KB (`asama3-final/FINAL_SHA256SUMS.txt`); büyük dosya yok |
| `git diff --check` | Yeni yazılan dosyalar temiz. `origin/main..HEAD` aralığında yalnızca içe aktarılan HGS2 kaynağındaki **özgün** satır sonu boşlukları raporlanır (`script.js`, `style.css`, entity sınıfları vb.; upstream kod, bilinçli olarak değiştirilmedi). Lab-artifacts kanıtları `-whitespace` ile muaf |
| Silinen dosyalar | `origin/main..HEAD` aralığında 0 (yalnızca yeniden adlandırma ve ekleme) |

**Depo dışı gerekli eylem:** HGS2 PostgreSQL `postgres` parolası ve ESP32 Wi-Fi parolası özgün açık depoda
(`ServetAlav001/hgs2`) görünür durumda; değiştirilmeleri önerilir. Ayrıntılar: `docs/security/SECURITY.md`.

## 7. Dışarıda bırakılan dosyalar

| Dosya / dizin | Gerekçe |
|---|---|
| `hgs2`: `origin/master` dalı | İlişkisiz geçmiş; Performance Lab `main` üzerine kurulu (kullanıcı kararı) |
| `hgs2`: `HGS/target/` | Derleme çıktısı (zaten yok sayılıyordu) |
| `hgs2-lab-artifacts/backups/` | Bu deponun eski çalışma ağacı kopyaları, iç içe `.git` dizinleri |
| `hgs2-lab-artifacts/evidence-backups/` | `test-evidence/` + `tools/` kopyası |
| `*/server-logs/` | ~20 MB test kümesi günlükleri; yeniden üretilebilir |
| `runs-final/`, `runs-trial/`, `runs-discovery/`, `asama2-kanit/runs/` (MATRIX.md hariç) | ~3700 ham çıktı, ~15 MB; yeniden üretilebilir |
| Surefire `TEST-…HgsApplicationTests.xml` | Makineye özgü JVM sistem özellikleri |
| `.venv/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/` | Yerel ortam / önbellek (`.gitignore`) |

## 8. SSH bağlantı durumu

* `origin` zaten SSH biçimindeydi: `git@github.com:zekeriyakalkann/hgs-performance-lab.git` (değiştirilmedi).
* `~/.ssh/config`: `github.com` → `ssh.github.com:443`, `IdentityFile ~/.ssh/id_ed25519`, `IdentitiesOnly yes`.
* Anahtar (`ED25519`, `SHA256:RZ62eTh7dFbv/b4n3oBTw54gwey1kdRy2sGBl2kHaNY`) parola korumalı, ssh-agent çalışmıyor.
  Etkileşimsiz deneme (`ssh -o BatchMode=yes -T git@github.com`) beklendiği gibi `Permission denied (publickey)`
  verdi; bu yüzden `ssh -T` ve `git push` kullanıcı tarafından kendi terminalinde, parolası elle girilerek çalıştırıldı.
  Parola hiçbir dosyaya veya komut satırına yazılmadı.

## 9. Push sonucu

* Gönderim öncesi uzak durum (HTTPS, salt okunur `git ls-remote`): `refs/heads/main` = `66518c6`, yerel
  `origin/main` ile aynı; `origin/main`, `HEAD`'in atası → hızlı ileri sarma.
* Komut: `git push -u origin main` (normal push; force / `--force-with-lease` kullanılmadı). Yalnızca `main` gönderildi;
  yerel `backup/pre-unify-66518c6` dalı gönderilmedi.
* Sonuç: `66518c6..a536cea  main -> main` (10 yeni commit), `main` → `origin/main` izleme ayarlandı.
* GitHub üzerinden doğrulama: maskelenmiş `application.properties` (`${HGS_DB_PASSWORD}`) ve ESP32 sketch'i
  (`YOUR_WIFI_SSID` / `YOUR_WIFI_PASSWORD` / `YOUR_SERVER_IP`) yayımlanan sürümde görüldü; lab-artifacts raporları erişilebilir.

## 10. GitHub üzerinde doğrulanan son commit

| Öğe | Değer |
|---|---|
| Depo | `github.com/zekeriyakalkann/hgs-performance-lab`, dal `main` |
| Commit | `a536cead398dead4a2be528ff71157645e063c56` — docs: add unified repository documentation and report |
| Doğrulama | `git ls-remote https://github.com/zekeriyakalkann/hgs-performance-lab.git` → `refs/heads/main` = yerel `HEAD`; GitHub API commit tarihi 2026-10-31T12:44:15Z |

Bu raporu güncelleyen commit, yukarıdaki commit'in üzerine ikinci bir normal push ile gönderilir.
