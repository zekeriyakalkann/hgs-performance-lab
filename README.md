# HGS2 Performance Lab — birleşik depo

HGS2 (Hibrit Giriş Sistemi) uygulaması, ona karşı güvenli ve izole performans testi yapmak için geliştirilen
Performance Lab aracı ve bu çalışmanın denetim/test kanıtları tek bir depoda toplanmıştır.

| Bileşen | Dizin | Ne içerir | Dil / çalışma ortamı |
|---|---|---|---|
| **HGS2 uygulaması** | [`projects/hgs2/`](projects/hgs2/README.md) | Spring Boot REST API + web arayüzü, ESP32 / Arduino donanım kodları, `perftest` profili ve başlangıç güvenlik denetimi | Java 21, Spring Boot 4, PostgreSQL |
| **Performance Lab** | [`projects/performance-lab/`](projects/performance-lab/README.md) | `hgs2_lab` Python paketi ve `hgs2-lab` CLI: yük üretimi, sentetik deneyler, analiz, JUnit sınıflandırma, Robust Z-score dedektörü, HGS2'yi `perftest` profiliyle başlatma | Python ≥ 3.10 |
| **Lab Artifacts** | [`projects/lab-artifacts/`](projects/lab-artifacts/README.md) | PostgreSQL salt okunur denetim raporları (V2), rol tasarımı ve izole küme V1 yürütmesi, pytest kanıtları, SHA-256 manifestleri | Belgeler ve kanıt dosyaları |

## Bileşenlerin ilişkisi

```
                 ┌──────────────────────────────┐
                 │  projects/performance-lab    │
                 │  hgs2-lab CLI (Python)       │
                 └──────┬───────────────┬───────┘
      hgs2 run --app-dir│               │ run / synthetic / analyze
   (perftest profili)   ▼               ▼  (yalnızca loopback hedefler)
 ┌──────────────────────────────┐   ┌──────────────────────────┐
 │  projects/hgs2               │   │ yerel sentetik sunucu    │
 │  Spring Boot, 127.0.0.1:18080│   │ (test / deney amaçlı)    │
 │  PerfTestSafetyGuard         │   └──────────────────────────┘
 └──────┬───────────────────────┘
        │ yalnızca hgs2_perftest_db (izole test veritabanı)
        ▼
 ┌──────────────────────────────┐        ┌──────────────────────────────┐
 │ PostgreSQL (test kümesi)     │◄───────│ projects/lab-artifacts        │
 │ gerçek hibrit_giris_db'ye    │ denetim│ salt okunur katalog denetimi, │
 │ CONNECT yetkisi yok          │ kanıtı │ rol tasarımı, test kanıtları  │
 └──────────────────────────────┘        └──────────────────────────────┘
```

* Performance Lab, HGS2'yi yalnızca `perftest` profiliyle başlatır (`hgs2-lab hgs2 run`). Bu profilde
  `PerfTestSafetyGuard`, uygulama loopback adresine, ayrı test veritabanına ve ortam değişkenlerinden gelen kimlik
  bilgilerine bağlı değilse başlatmayı veritabanı bağlantısı açılmadan durdurur.
* Lab Artifacts, bu izolasyonun PostgreSQL tarafını (test rolünün gerçek veritabanına erişememesi) belgeleyen denetim
  raporlarını ve kanıtları içerir. Tüm kanıtlar izole, sentetik test kümelerinden üretilmiştir.

Ayrıntılar: [mimari](docs/architecture/ARCHITECTURE.md) · [güvenlik](docs/security/SECURITY.md) ·
[proje özeti](docs/project-overview/PROJECT_OVERVIEW.md) · [birleştirme raporu](docs/UNIFIED_REPOSITORY_REPORT.md)

## Depo yapısı

```
.
├── README.md                 bu dosya
├── .gitignore / .gitattributes
├── projects/
│   ├── hgs2/                 HGS2 uygulaması (içe aktarılmış geçmişiyle)
│   ├── performance-lab/      Performance Lab (deponun özgün geçmişi)
│   └── lab-artifacts/        denetim raporları ve onaylı kanıtlar
├── docs/
│   ├── architecture/
│   ├── security/
│   └── project-overview/
└── scripts/                  depo düzeyi yardımcı betikler
```

## Hızlı başlangıç

Performance Lab testleri (dış servise, gerçek veritabanına veya HGS2'ye bağlanmaz):

```powershell
cd projects/performance-lab
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt   # çekirdek + test, constraints.txt ile sabit sürümler
.\.venv\Scripts\python -m pytest                            # varsayılan: entegrasyon testleri hariç
```

Lab Artifacts SHA-256 manifest doğrulaması (salt okunur):

```powershell
python scripts/verify_lab_artifacts.py
```

HGS2 uygulamasını çalıştırma ve gerekli ortam değişkenleri için: [`projects/hgs2/README.md`](projects/hgs2/README.md).

## Git geçmişi

* Performance Lab'in özgün commit'leri olduğu gibi korunmuştur (`git log --follow projects/performance-lab/...`).
* HGS2'nin `main` dalı geçmişi (5 commit) yazar ve tarih bilgileriyle `projects/hgs2/` altına aktarılmıştır;
  aktarımdan önce geçmişteki kimlik bilgileri maskelenmiştir.
* Lab Artifacts bir Git deposu değildi; onaylı içerik tek bir anlık görüntü commit'iyle eklenmiştir.

Ayrıntılar: [`docs/UNIFIED_REPOSITORY_REPORT.md`](docs/UNIFIED_REPOSITORY_REPORT.md).

## Lisans ve sahiplik

`projects/hgs2/` altındaki HGS2 uygulama kodu ServetAlav001 ve ekibi tarafından geliştirilmiştir (özgün depo:
`github.com/ServetAlav001/hgs2`). Performance Lab, `perftest` profili ve belgeler Zekeriya Kalkan'a aittir.
Depoda henüz bir lisans dosyası yoktur.
