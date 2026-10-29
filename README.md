# hgs2-performance-lab

HGS2 Spring Boot API'si için akademik performans testi ve analiz aracı (bağımsız Python projesi).

**Durum:** Yapılandırmadan sonuç dosyalarına kadar çalıştırma akışı ve `run` komutu etkindir, ama **yalnızca loopback
hedeflere** (`127.0.0.1`, `::1`, `localhost`) istek gönderir. Kaydedilmiş sonuçlar `analyze` komutuyla çevrimdışı
analiz edilir (betimleyici istatistikler; ağ erişimi yok). `synthetic` komutları, uygulamanın kendi yerel test
sunucusuna (yalnızca `127.0.0.1`) karşı planlı hatalarla **sentetik** ve etiketli deneyler üretir; bunlar gerçek
HGS2 ölçümü değildir ve sonuçlarda `dataset_kind = "synthetic"` ile ayrılır. Araç bugüne kadar yalnızca testlerdeki
ve kendi sentetik yerel HTTP sunucularına karşı çalıştırıldı. **Gerçek HGS2 API'sine karşı hiçbir test veya ölçüm yapılmadı**; loopback dışı bir
hedefe izin veren bir ayar da yoktur. **Eğitilmiş bir makine öğrenmesi modeli yoktur.** Tek dedektör, sentetik
özellik tablosu üzerinde çalışan istatistiksel Robust Z-score'dur (F5); gerçek HGS2 verisiyle değerlendirilmedi.
`junit classify`, JUnit/Surefire XML test raporlarını çevrimdışı olarak ortak bir kayıt modeline (`TestRecord`)
dönüştürür ve **kural tabanlı**, kanıt gösteren bir sınıflandırıcıyla yorumlar (bkz. "Test sonucu analizi").
`run`/`synthetic run` yanıt gövdesinden tanınan iş sonucunu (`REDDEDILDI`, `HATA` …) çıkarır; `results classify`
kaydedilmiş bir çalıştırmayı aynı sınıflandırıcıyla yorumlar. Kurallar gerçek HGS2 hata örnekleriyle doğrulanmadı.

## Mimari

```
Ölçüm:  Config -> Scenarios -> ön kontrol -> Metadata -> Runner (+ saat çapası) -> HTTP Transport -> Storage
Analiz: Storage dosyaları (CSV + JSON) -> Reader (doğrulama, SHA-256) -> Analysis -> results/analysis/*.analysis.json
Sentetik: Manifest -> Plan (seed) -> SyntheticServer (127.0.0.1) <- Ölçüm akışı (değişmeden) -> Storage
          + sunucu olayları (ayrı kaynak) + etiketler (beklenen / gözlenen / uyum) -> results/synthetic/
Kampanya: Kampanya manifesti -> (plan x seed) deney manifestleri -> her biri Sentetik akış -> campaign.json (katalog)
Veri seti: campaign.json -> doğrulama (SHA-256, etiket/plan tutarlılığı) -> grup bazlı train/validation/test manifesti
Telemetri: (isteğe bağlı, --telemetry) TelemetryRecorder (arka plan iş parçacığı) -> <sonuç dizini>/telemetry/ (ayrı dosya)
```

Analiz katmanı ölçüm katmanından ayrıdır: `reader.py`, `analysis.py` ve `clock.py` ağ koduna (`requests`, `urllib3`,
`http_transport`, `execution`, `target_guard`) bağımlı değildir; bu, bir testle (alt süreçte içe aktarma) denetlenir.

| Modül | Sorumluluk |
|---|---|
| `config.py` | JSON yapılandırmasını ve güvenlik sınırlarını (`limits`) yükler, doğrular |
| `scenarios.py` | Senaryo tanımı, doğrulama, yükleme |
| `execution.py` | Uçtan uca çalıştırma: ön kontrol, güvenlik koruması, metadata, kayıt; çalıştırma durumu |
| `target_guard.py` | Hedef güvenliği: şema/ad izin listesi, ad çözümlemesi, loopback denetimi |
| `runner.py` | Senaryoları yürütür: ısınma + ölçüm istekleri, `seq`/`offset_ms`, süre ölçümü, güvenlik kancaları, saat çapası |
| `clock.py` | `ClockAnchor`: monotonik başlangıç referansı ile UTC duvar saatinin birlikte kaydı |
| `telemetry.py` | Sistem telemetrisi (F4): CPU, bellek, disk, TCP sayaçlarının zaman damgalı örneklenmesi; ayrı dosya (ağ kodu yok) |
| `transport.py` | Taşıyıcı arayüzü (`Transport.send`) ve taşıma istisnaları |
| `http_transport.py` | `RequestsTransport`: requests tabanlı taşıyıcı, bağlantı katmanında loopback koruması, hata çevirisi |
| `models.py` | `RawResult`: girişim başına ham sonuç kaydı, `run_id` doğrulaması |
| `metadata.py` | JSON üst verisi: çalıştırma durumu, kod/bağımlılık/ortam bilgisi, girdi özetleri, maskelenmiş görüntüler |
| `sanitize.py` | Hassas ve kişisel değerleri maskeler: URL sorgusu, form gövdesi, JSON yapısı, serbest metin (log, hata, iz) |
| `storage.py` | CSV/JSON yazma ve okuma; şema sürüm politikası; üzerine yazmaz, atomik yayımlar, kısmi sonuçları ayrı adla yazar |
| `reader.py` | Analiz için okuma: dosya keşfi, SHA-256, CSV/JSON tutarlılığı, kayıt bütünlüğü, en küçük metadata doğrulaması |
| `analysis.py` | Çevrimdışı istatistiksel baseline: sayımlar, oranlar, yüzdelikler, bootstrap güven aralıkları, throughput |
| `synthetic.py` | Sentetik deney manifesti, doğrulama, seed'li deterministik plan, beklenen/gözlenen etiketleme (ağ yok) |
| `synthetic_server.py` | Yerel sentetik test sunucusu: yalnızca `127.0.0.1`, planlı hatalar, sınırlı kaynak, sunucu olayları |
| `synthetic_experiment.py` | Sentetik deney akışı: sunucuyu başlat → mevcut `execute_run` → sunucuyu kapat → etiket/olay dosyaları |
| `campaign.py` | Kampanya manifesti, (plan x seed) deterministik açılım, katalog doğrulaması, güvenli göreli yollar (ağ yok) |
| `campaign_runner.py` | Kampanyayı yürütür: her deney mevcut sentetik akışla, hata yalıtımlı; `campaign.json` katalog |
| `dataset.py` | Doğrulanmış katalogdan grup bazlı train/validation/test veri seti manifesti, sızıntı ve bütünlük denetimleri (ağ yok) |
| `features.py` | Doğrulanmış veri setinden deterministik özellik tablosu: `features.csv` (gözlemler) + `labels.csv` (tasarım/hedef) + manifest (ağ yok) |
| `robust_z.py` | Robust Z-score dedektörü (F5): yalnızca `duration_ms` listesinden kalibrasyon ve skor; tablo/etiket görmez (ağ yok) |
| `detection.py` | Özellik tablosunun doğrulanması, train normal kalibrasyonu, bölüm bazında değerlendirme ve metrikler (ağ yok) |
| `records.py` | Birleşik test kaydı `TestRecord`: kaynak sonucu, beklenen/gözlenen, hata bilgisi, veri kalitesi, analiz; JSON gidiş-dönüş; maskeleme sınırı (ağ yok) |
| `junit_report.py` | JUnit/Surefire XML ayrıştırıcısı: güvenli XML (DOCTYPE/varlık reddi, boyut sınırı), her testcase → `TestRecord` (ağ yok) |
| `classify.py` | Kanıta dayalı kural tabanlı test sonucu sınıflandırıcısı ve ortak sınıflandırma belgesi (ağ yok, model yok, F5'ten bağımsız) |
| `response_parser.py` | HTTP yanıt gövdesi ayrıştırıcısı: içerik türü, boyut sınırı, tanınan iş sonucu; gövde içeriği yazılmaz (ağ yok) |
| `result_analysis.py` | Kaydedilmiş çalıştırma → beklenti dosyası + ayrıştırma özetleri → `TestRecord` → sınıflandırıcı (ağ yok) |
| `readiness.py` | Gerçek entegrasyon hazırlığı: rapor alan envanteri, beklenti hazırlığı, önkoşul denetimi (READY / READY_WITH_WARNINGS / BLOCKED); ağ yok |
| `ingestion.py` | Test sonucu örnekleri için veri alım sözleşmesi (`ingestion_version 1`): kaynak kimliği, kaynak kanıtı, etiket incelemesi, tekrar ve kapsam kuralları; mevcut hatta aktarım (ağ yok) |
| `junit_analysis.py` | Toplu JUnit/Surefire analizi: raporlar → TestRecord → senaryo çözümlemesi → beklenti eşleştirme → sınıflandırıcı → sayaçlı JSON belge + kayıt başına iz (`scenario_trace`) (ağ yok) |
| `scenario_mapping.py` | Senaryo eşleme sözleşmesi (`scenario_mapping_version 1`): kararlı test tanımlayıcısı (`classname#name`) → senaryo kimliği; metadata ile birleşik çözümleme, çelişki ve belirsizlikte kimlik seçilmez (ağ yok) |
| `expectations.py` | Beklenti sözleşmesi (`expectations_version 2`): sürümlü beklentiler, doğrulama durumu, kapsam, kanıt referansları, kanıt yeterliliği, deterministik registry ve senaryo kimliğiyle eşleştirme (ağ yok) |
| `cli.py` | `validate`, `list`, `run`, `analyze`, `synthetic validate/plan/run`, `campaign validate/run/verify`, `dataset build`, `junit classify`, `results classify` |
| `webui.py` | Yerel web arayüzü (yalnızca `127.0.0.1`, standart kütüphane `http.server`): senaryo listesi, kullanıcı isteğiyle sentetik deney (`run_synthetic_experiment`), mevcut analiz/sınıflandırıcıyla sonuç görünümü |
| `_validate.py` | Ortak doğrulama yardımcıları |

## Kurulum

Bağımlılık tanımlarının kaynağı `pyproject.toml`'dur; geliştirme ortamının kesin sürümleri `constraints.txt`'dedir
(requests, urllib3, pytest ve geçişli bağımlılıkları). Yeni çalışma zamanı bağımlılığı yoktur.

```
pip install -r requirements.txt    # -c constraints.txt ile çekirdek + test ("dev" eki), sabit sürümlerle
```

`analyze` komutu yalnızca Python standart kütüphanesini kullanır (`statistics` yerine kendi tip 7 yüzdelik
hesabı, `random`, `fractions`, `hashlib`); ek bağımlılık gerekmez. `pyproject.toml`'daki `analysis` eki (pandas,
numpy, matplotlib) bu komut tarafından kullanılmaz ve sabitlenmemiştir.

Araç sürümünün kaynağı `src/hgs2_lab/__init__.py` içindeki `__version__`'dır; `pyproject.toml`'daki
`version` ile eşitliği bir birim testiyle denetlenir.

## Hızlı başlangıç (yalnızca yerel deneme)

Gerçek bir sistem yerine boş bir dizini sunan Python'un yerleşik sunucusuyla deneme:

```
# 1. terminal: yalnızca 127.0.0.1'de dinleyen, boş bir dizini sunan yerel sunucu
python -m http.server 18080 --bind 127.0.0.1 --directory <boş-bir-dizin>

# 2. terminal: proje kökünde
copy configs\config.example.json configs\config.json        # base_url: http://127.0.0.1:18080
```

Bu sunucu Lab'den ayrı bir süreçtir; örnek yapılandırma onu `"target_process": "python.exe"` ile açıkça bildirir
(bkz. "Güvenlik sınırları" → dinleyici kimliği). Bildirim yoksa ya da 18080'i başka bir süreç (ör. bir JVM) dinliyorsa
`run` hiçbir istek göndermeden reddedilir.

`configs/demo.json` (yerel dosya; `configs/*.json` Git dışında tutulur):

```json
{"scenarios": [{"name": "kok", "method": "GET", "path": "/", "warmup_repetitions": 1, "repetitions": 5}]}
```

```
hgs2-lab validate --config configs/config.json --scenarios configs/demo.json
hgs2-lab run --config configs/config.json --scenarios configs/demo.json --target-label yerel-deneme
```

Sonuç: `results/<run_id>.csv` ve `results/<run_id>.json` (örnek yapılandırmada `output_dir` = `../results`).
Çevrimdışı analiz (istek göndermez): `hgs2-lab analyze --config configs/config.json --run-id <run_id>` →
`results/analysis/<run_id>.analysis.json`.

## Yapılandırma

| Anahtar | Zorunlu | Açıklama |
|---|---|---|
| `base_url` | evet | `http://` veya `https://`; kimlik bilgisi, sorgu ve parça içeremez. `run` yalnızca loopback kabul eder. |
| `timeout_seconds` | hayır (10) | İstek başına zaman aşımı; sonlu, pozitif sayı |
| `output_dir` | hayır (`results`) | Sonuç dizini |
| `scenarios_file` | hayır (`scenarios.json`) | Senaryo dosyası (`--scenarios` ile değiştirilebilir) |
| `limits` | hayır | Güvenlik sınırları; bkz. "İstek bütçesi ve kontrollü durdurma" |
| `target_process` | hayır | Hedef portu Lab süreci dışında bir süreç dinliyorsa o sürecin dosya adı (ör. `python.exe`). Yüklemede biçimi denetlenir; JVM/PostgreSQL adları (`java.exe`, `javaw.exe`, `postgres.exe` …) reddedilir. Verilmezse `run` yalnızca Lab'in kendi süreç içi sunucularına gider. Bkz. "Güvenlik sınırları" |

**Göreli yollar yapılandırma dosyasının bulunduğu dizine göre çözülür**, çalışma dizinine göre değil.
Örneğin `configs/config.json` içindeki `"output_dir": "../results"` her zaman proje kökündeki `results/`
dizinini verir. Mutlak yollar olduğu gibi kullanılır. `--config` ve `--scenarios` yolları ise çalışma dizinine görelidir.

Bilinmeyen anahtarlar (`limits` içindekiler dahil) reddedilir.

## Senaryolar

`scenarios` listesi boş olamaz; adlar benzersizdir. Alanlar: `name`, `method` (GET, POST, PUT, PATCH, DELETE),
`path` (zorunlu); `repetitions` (pozitif tam sayı, varsayılan 1), `warmup_repetitions` (negatif olmayan tam sayı,
varsayılan 0), `delay_seconds` (>= 0), `headers`, `body` (nesne), `expected_status` (durum kodu listesi).
`expected_status` boşsa 2xx başarılı sayılır.

**Isınma:** her senaryoda önce `warmup_repetitions` ısınma isteği, sonra `repetitions` ölçüm isteği gönderilir.
Isınma istekleri ölçümlerle aynı yoldan geçer ve aynı kurallarla kaydedilir, ama `warmup=true` olarak işaretlenir;
analizde ayrılmalıdır. `delay_seconds` ısınma dahil ardışık istekler arasında uygulanır.

`path` sorgu parametresi içerebilir (`/items?page=2`). Hassas adlı parametrelerin değerleri sonuçlara ve metadata'ya
maskelenerek yazılır; istek ise değiştirilmeden gönderilir.

## Komutlar

```
hgs2-lab validate [--config DOSYA] [--scenarios DOSYA]
hgs2-lab list     [--config DOSYA] [--scenarios DOSYA]
hgs2-lab run      [--config DOSYA] [--scenarios DOSYA] [--target-label ETİKET]
                  [--telemetry [--telemetry-interval-ms N]]
hgs2-lab analyze  --run-id RUN_ID [--results-dir DİZİN | --config DOSYA] [--output DOSYA]
                  [--seed N] [--bootstrap-resamples N] [--confidence C] [--min-tail-samples N]
hgs2-lab synthetic validate --manifest DOSYA
hgs2-lab synthetic plan     --manifest DOSYA [--output DOSYA]
hgs2-lab synthetic run      --manifest DOSYA --results-dir DİZİN [--run-id RUN_ID]
                            [--telemetry [--telemetry-interval-ms N]]
hgs2-lab campaign validate  --manifest DOSYA
hgs2-lab campaign run       --manifest DOSYA --output-dir DİZİN
hgs2-lab campaign verify    --campaign-dir DİZİN
hgs2-lab dataset build      --campaign-dir DİZİN --output DOSYA [--split-seed N] [--ratios 0.6,0.2,0.2]
                            [--invalid-policy exclude|fail]
hgs2-lab dataset features   --campaign-dir DİZİN --dataset DOSYA --output-dir DİZİN [--policy observed-v1]
hgs2-lab detect robust-z    --features-dir DİZİN --output DOSYA
hgs2-lab junit classify     --report DOSYA [--report DOSYA ...] --output DOSYA
                            [--dataset-kind real|synthetic|fixture|unknown] [--expectations DOSYA]
                            [--scenario-map DOSYA]
hgs2-lab results classify   --run-id RUN_ID --results-dir DİZİN --output DOSYA [--expectations DOSYA]
                            [--dataset-kind real|synthetic|fixture|unknown]
hgs2-lab readiness check     --report DOSYA [--report DOSYA ...] [--expectations DOSYA] [--scope real|synthetic]
                            [--scenario-map DOSYA] [--output DOSYA]
hgs2-lab ingest analyze     --file DOSYA [--expectations DOSYA] --output DOSYA
hgs2-lab expectations validate --file DOSYA
hgs2-lab expectations show     --file DOSYA [--scenario SENARYO]
hgs2-lab scenario-map validate --file DOSYA
```

* `validate`: yapılandırma ve senaryoları doğrular, çözülen yolları ve hedefin `run` için izinli olup olmadığını
  (yalnızca URL metnine bakarak) gösterir. İstek göndermez.
* `list`: senaryoları listeler. İstek göndermez.
* `run`: ön kontrolden sonra senaryoları sırayla çalıştırır, sonuçları ve metadata'yı kaydeder, bir özet yazdırır
  (istek sayıları, HTTP/taşıma hatası sayıları, ölçüm isteklerinin `duration_ms` medyan/en az/en çok değeri,
  sonuç dosyalarının yolu). `--target-label` metadata'ya `target_label` olarak yazılır. `--telemetry` (`run` ve
  `synthetic run`): sistem telemetrisini ayrı bir dosyaya yazar; bkz. "Sistem telemetrisi (F4)".
* `analyze`: kaydedilmiş bir çalıştırmanın CSV ve JSON dosyalarını okur, doğrular ve analiz dosyası yazar. **İstek
  göndermez, ağa erişmez.** Ayrıntılar: "Analiz (`analyze`)".
* `synthetic validate` / `synthetic plan`: sentetik deney manifestini doğrular, deterministik planın özetini ve
  `plan_sha256` değerini gösterir; `plan --output` planın tamamını yazar. İstek göndermez.
* `synthetic run`: yerel sentetik sunucuyu `127.0.0.1`'de başlatır, deneyi mevcut çalıştırma akışıyla yürütür, sunucuyu
  kapatır ve etiket/sunucu olayı dosyalarını yazar. Ayrıntılar: "Sentetik deneyler (`synthetic`)".
* `campaign validate` / `campaign run` / `campaign verify` ve `dataset build`: toplu sentetik deneyler, katalog ve veri
  seti. Ayrıntılar: "Sentetik kampanyalar ve veri seti".
* `junit classify`: verilen JUnit/Surefire XML raporlarını toplu olarak okur. İsteğe bağlı beklenti dosyasıyla açık
  senaryo kimliği üzerinden eşleştirir, her testi sınıflandırır ve sayaçlı tek bir JSON belgesi yazar. Hedef sisteme
  erişmez, test çalıştırmaz. Ayrıntılar: "Toplu JUnit analizi".
* `results classify`: kaydedilmiş bir çalıştırmanın ölçüm isteklerini (durum kodu, iş sonucu, taşıma hatası, yanıt
  ayrıştırma özeti) beklenti dosyasıyla birlikte sınıflandırır. İstek göndermez; sonuç dosyalarını değiştirmez.
* `readiness check`: gerçek entegrasyon önkoşullarını çevrimdışı denetler; `ingest analyze`: veri alım paketini
  doğrulayıp mevcut analiz hattından geçirir. Ayrıntılar: "Gerçek HGS2 entegrasyon hazırlığı".
* `expectations validate` / `expectations show`: beklenti sözleşmesini doğrular veya beklentileri, durumlarını ve kanıt
  referanslarını listeler. Dosyayı yalnızca okur. Ayrıntılar: "Beklenti sözleşmesi".
* `scenario-map validate`: senaryo eşleme dosyasını doğrular; `junit classify` ve `readiness check` için
  `--scenario-map`: senaryo kimliklerini testcase özelliği ve eşleme dosyasından çözer. Ayrıntılar: "Senaryo
  eşleştirme ve uçtan uca kabul (N10)".

`--config` varsayılanı `configs/config.json`'dır. Windows'ta kurulum yapılmadan: `.\.venv\Scripts\python.exe -m hgs2_lab.cli ...`.

### Çıkış kodları

| Kod | Anlam |
|---|---|
| 0 | Başarılı (`run`: planlanan tüm istekler yapıldı; HTTP 5xx ve taşıma hataları sonuçlarda kayıtlıdır; `analyze`: analiz dosyası yazıldı; `synthetic run`: deney tamamlandı ve tüm etiketler doğrulandı) |
| 1 | Yapılandırma, senaryo veya sentetik manifest hatası (hiç istek yok); `analyze`: sonuç dosyaları eksik, bozuk, tutarsız veya desteklenmeyen şemada |
| 2 | Komut satırı kullanım hatası (argparse); `analyze`: geçersiz analiz parametresi |
| 3 | `run`/`synthetic run` ön kontrolde reddedildi: hedef, bütçe, `target_label` veya dosya çakışması (hiç istek yok) |
| 4 | `run`/`synthetic run` güvenlik sınırıyla durduruldu; kısmi sonuçlar `.partial` dosyalarında (sentetik deney geçersiz sayılır) |
| 5 | Sonuçlar kaydedilemedi; `analyze`/`synthetic plan --output`: çıktı dosyası zaten var (üzerine yazılmaz) veya yazılamadı |
| 6 | `synthetic run` tamamlandı ama deney geçersiz: gözlenen sonuçlar veya sunucu kayıtları planla uyuşmadı (gerekçeler etiket dosyasında); `campaign run`: en az bir deney geçersiz/başarısız (katalogda nedenleriyle) |

Kampanya ve veri seti komutları: `campaign run` 0 (tüm deneyler geçerli), 6 (en az biri geçersiz), 3 (çıktı dizini boş
değil; hiç deney çalışmadı), 1 (manifest hatası), 130 (Ctrl+C); `campaign verify` 0 (sorun yok) / 1 (sorun var);
`dataset build` 0 (yazıldı; uyarılar dosyada), 1 (doğrulama, politika veya bütünlük hatası), 5 (çıktı dosyası var);
`dataset features` 0 (yazıldı), 1 (doğrulama hatası; hiçbir dosya yazılmaz), 5 (çıktı dizini boş değil veya yazılamadı).
`junit classify` 0 (yazıldı, tüm raporlar okundu), 1 (yazıldı ama en az bir rapor reddedildi, belgede `file_errors`;
ya da beklenti dosyası okunamadı/geçersiz, bu durumda hiçbir dosya yazılmaz), 5 (çıktı dosyası var veya yazılamadı). `results classify` 0 (yazıldı), 1 (sonuç veya beklenti dosyası okunamadı/geçersiz;
hiçbir dosya yazılmaz), 5 (çıktı dosyası var veya yazılamadı). `expectations validate` 0 (geçerli; aynı senaryo için
birden fazla etkin beklenti UYARI olarak listelenir), 1 (geçersiz; tüm bulgular listelenir); `expectations show` 1 (dosya
geçersiz veya senaryo için beklenti yok). `readiness check` 0 (READY veya READY_WITH_WARNINGS), 1 (BLOCKED), 5 (çıktı
dosyası var); `scenario-map validate` 0 (geçerli; aynı test için farklı senaryolara giden eşlemeler UYARI olarak
listelenir), 1 (geçersiz; tüm bulgular listelenir); `junit classify --scenario-map` geçersiz eşleme dosyasında 1 döner ve
hiçbir dosya yazmaz; `ingest analyze` 0 (yazıldı), 1 (yazıldı ama girdi reddedildi; ya da paket/beklenti dosyası geçersiz, bu
durumda hiçbir şey yazılmaz), 5 (çıktı dosyası var).
| 130 | `run` Ctrl+C ile durduruldu; kısmi sonuçlar `.partial` dosyalarında |

Beklenmeyen bir istisnada (programlama hatası) kısmi sonuçlar `execution.status = "failed"` ile kaydedilir ve istisna
hata ayıklama için yeniden fırlatılır (Python izi, çıkış kodu 1).

## Yerel web arayüzü (`webui.py`)

```
python -m hgs2_lab.webui [--port 8765] [--configs-dir configs] [--results-dir results]
```

Adres: `http://127.0.0.1:8765/`. Sunucu her zaman `127.0.0.1`'e bağlanır (bağlanma adresi seçeneği yoktur); 8080 ve
5432 arayüz portu olarak reddedilir. Yeni bağımlılık yoktur (standart kütüphane `http.server`).

* **Dashboard:** uygulama durumu, senaryo sayıları, son çalıştırmanın durumu ve temel sonuçları (kayıt yoksa açıkça
  belirtilir).
* **Test senaryoları:** `--configs-dir` altındaki sentetik manifestler, HTTP senaryo dosyaları ve kampanyalar mevcut
  yükleyicilerle okunur. **Yalnızca sentetik manifestler** arayüzden çalıştırılabilir ("Deneyi başlat"): mevcut
  `run_synthetic_experiment` aynen çağrılır (uygulamanın kendi `127.0.0.1` sunucusu, ön kontrol, hedef/dinleyici
  doğrulaması, güvenlik sınırları). Harici hedef gerektiren HTTP senaryoları (`run`) ve kampanyalar yalnızca listelenir.
* **Sonuçlar:** `--results-dir` altındaki çalıştırmalar `load_run`, `build_analysis` ve `build_run_document` (beklenti
  dosyasız) ile bellekte gösterilir; sentetik deneylerde etiket dosyasının özeti ve `verdict` eklenir. Arayüz, deneyin
  kendi sonuç dosyaları dışında dosya yazmaz.
* Hiçbir deney kendiliğinden başlamaz; aynı anda tek deney çalışır. POST istekleri süreç başına form belirteci ister;
  `Host`/`Origin` yalnızca `127.0.0.1:<port>` / `localhost:<port>` olabilir. Çalıştırılacak dosya sunucu tarafındaki
  listeden seçilir; kullanıcı girdisi yol veya komut olarak kullanılmaz.
* **Kapanış (Ctrl+C):** yeni deney başlatılmaz; çalışan deney kesilmez, bitmesi beklenir (süresi manifestteki
  `limits.max_duration_seconds` ile sınırlıdır). Arayüzden deney iptali yoktur.

## Çalıştırma akışı ve durumlar

1. Yapılandırma ve senaryoların tamamı yüklenip doğrulanır. Hata varsa çıkış 1; taşıyıcı bile oluşturulmaz.
2. **Ön kontrol** (`execution.preflight`): hedef (metin + ad çözümlemesi), istek bütçesi, gecikmelerden gelen en kısa
   süre ve sonuç dosyası çakışması. Uymazsa çıkış 3; hiçbir HTTP isteği gönderilmez.
3. Git bilgisi ve girdi dosyalarının SHA-256 özetleri, istekler başlamadan alınır.
4. Runner, güvenlik koruması (`SafetyGuard`) ile çalışır.
5. Sonuç ne olursa olsun taşıyıcı (HTTP oturumu) kapatılır ve tamamlanan kayıtlar metadata ile kaydedilir.

| `execution.status` | Ne zaman | Dosyalar |
|---|---|---|
| `completed` | Planlanan tüm istekler yapıldı | `<run_id>.csv`, `<run_id>.json` |
| `aborted` | Güvenlik sınırı veya çalışma anında reddedilen hedef | `<run_id>.partial.csv`, `<run_id>.partial.json` |
| `interrupted` | Ctrl+C | `<run_id>.partial.*` |
| `failed` | Beklenmeyen istisna | `<run_id>.partial.*` |

Yarım sonuçlar hem dosya adından (`.partial`) hem JSON'daki `execution.status`'tan anlaşılır; `load_json(run_id)`
kısmi dosyayı okumaz, `load_json(run_id, partial=True)` gerekir. Kesilen (yanıtı alınmamış) istek kaydedilmez.

`run_id` otomatik üretilir: `run-<UTC zaman damgası>-<6 onaltılık rastgele>` (ör. `run-20261023T101530Z-a1b2c3`).

## Güvenlik sınırları

**Varsayılan ve tek izinli hedefler:** `127.0.0.1`, `::1`, `localhost`. Loopback dışı hedefe izin veren bir ayar,
seçenek veya otomatik geri dönüş yoktur.

Kontrol üç katmanda yapılır (`target_guard.py`, `http_transport.py`):

1. **URL metni:** şema yalnızca `http`/`https` (`file://`, `ftp://` vb. reddedilir); ana makine adı izin listesinde
   olmalıdır (`127.0.0.2`, `localhost.example.com`, IP'li alan adları vb. reddedilir).
2. **Ad çözümlemesi:** ad çözümlenir; dönen adreslerin **tamamı** loopback olmalıdır (IPv4-mapped IPv6 dahil).
   Ön kontrolde ve her `send` çağrısında yapılır.
3. **Bağlantı katmanı:** oturuma takılan adaptör, urllib3 soketi açmadan hemen önce adı yeniden çözümler, aynı
   denetimi uygular ve **yalnızca doğrulanmış IP adresine** bağlanır. İki çözümleme arasında adresin değişmesi
   (DNS rebinding) bağlantı kurulmadan `TargetNotAllowed` ile yakalanır; çalıştırma `aborted` olur.

Ayrıca:

* **Loopback, yalıtım değildir (N11).** Aynı makinede çalışan gerçek HGS2 de `127.0.0.1`'dedir; yukarıdaki üç katman
  onu yalıtılmış bir test sunucusundan ayıramaz. Ek korumalar:
  * **Ayrılmış portlar** (`target_guard.RESERVED_PORTS`): `8080` (gerçek HGS2 `server.port`) ve `5432` (gerçek HGS2
    PostgreSQL portu). `RequestsTransport.send` ve bağlantı katmanı bu portlara loopback'te bile bağlanmaz
    (`TargetNotAllowed`; `run` bağlantı kurulmadan `aborted` / `target_not_allowed` olur). Açan bir ayar yoktur.
    Bu bir alt korumadır: gerçek HGS2 başka bir portta başlatılırsa tanınmaz. Örnek yapılandırmanın hedefi bu
    nedenle `http://127.0.0.1:18080`'dir. N12'den beri `run` ayrılmış portu ilk istekten önce reddeder
    (`PreflightError`, dosya yazılmaz).
  * **Dinleyici kimliği (N12, `target_guard.check_listener`, `port_owner.py`; yalnızca Windows):** gerçek ağ
    taşıyıcısıyla her çalıştırmada, ilk istekten ÖNCE hedef portu dinleyen süreç(ler) işletim sisteminin TCP
    dinleyici tablosundan okunur (`GetExtendedTcpTable`; ağ trafiği yok). İzin yalnızca: (a) dinleyicinin tamamı bu
    Lab sürecidir (sentetik sunucu, test sunucuları), ya da (b) dinleyici başka bir süreçtir ve dosya adı
    yapılandırmadaki `target_process` ile eşleşir. **JVM ve PostgreSQL süreçleri bildirilse bile reddedilir**: gerçek
    HGS2 (Spring Boot) bir JVM'de çalıştığı için, hangi portta başlatılırsa başlatılsın hedef olamaz. Dinleyici yoksa,
    süreç adı okunamıyorsa (ör. hizmet olarak çalışan süreç; bu makinedeki PostgreSQL böyledir) ya da tablo
    okunamıyorsa hedef doğrulanmamış sayılır ve `run` `PreflightError` ile reddedilir; hiçbir istek gönderilmez ve
    dosya yazılmaz. Sonuç metadata'da `execution.target_verification` (`{"port", "listener": "in_process" |
    "declared_external"}`) olarak kaydedilir. Bağlantı katmanı her yeni bağlantıda aynı denetimi yapar; doğrulanan
    port taşıyıcının ömrü boyunca önbellekte tutulur (ölçüme ek süre girmesin diye; okuma ~0,1 ms).
    **Sınırlar:** süreç adı kimlik kanıtı değildir (JVM olmayan bir vekil/proxy süreç gerçek sisteme iletebilir;
    `python.exe` adını taşıyan herhangi bir Python süreci bildirimle eşleşir); denetim okunduğu ana aittir (doğrulama
    ile bağlantı arasında ya da çalıştırma sırasında dinleyici değişirse yakalanmaz); yalnızca Windows'ta uygulanır,
    diğer platformlarda tablo okunamadığı için gerçek ağ çalıştırmaları reddedilir. Sahte taşıyıcılar (birim
    testleri) ağ kullanmadığı için denetlenmez. Yapılandırma yüklenirken yalnızca `target_process` biçimi denetlenir:
    `LabConfig` sahte taşıyıcılı testlerde de kullanılır ve dinleyici ancak çalıştırma anında okunabilir.
  * **Test süreci yalıtımı** (`tests/conftest.py`, `tests/isolation_guard.py`): testlerde her giden bağlantı,
    hedef loopback IP'si değilse ya da port bu test sürecinde bind edilmiş ve **hâlâ açık** bir sokete ait değilse
    kurulmadan engellenir ve test başarısız sayılır. N12: soket kapanınca port "bırakılmış" sayılır; bırakılmış porta
    yalnızca o anda hiçbir süreç dinlemiyorsa bağlanılabilir (kapalı sunucu testleri). Bırakılan portu başka bir süreç
    (ör. gerçek HGS2) dinlemeye başlarsa bağlantı engellenir. **Sınırlar:** bu, işletim sistemi düzeyinde ağ
    yalıtımı değildir; yalnızca bu Python sürecindeki `socket.socket` çağrılarını görür. Alt süreçler, C
    uzantılarının kendi soketleri, `--noconftest` ya da pytest dışında çalıştırma ve Windows'ta asyncio Proactor
    (`ConnectEx`) yolu kapsam dışıdır. Mevcut alt süreç testleri yalnızca modül içe aktarma denetimi yapar ya da
    (N12 hedef kimliği testleri) bağlantı kurmayan bir dinleyici başlatır.
  * `hgs2-lab run`'ın hedefinin gerçekten yalıtılmış bir test sunucusu olduğunu Lab **kanıtlayamaz**: dinleyici
    kimliği denetimi gerçek HGS2'yi (JVM) her portta reddeder, ama bildirilen bir dış sürecin (ör. `python.exe`)
    gerçek sisteme iletmediğini kanıtlamaz. Gerçek HGS2'ye karşı test için HGS2 tarafında ayrı bir test profili, ayrı
    test veritabanı ve doğrulanabilir bir kimlik işareti gerekir (uygulanmadı; bkz. "Gerçek HGS2 API sözleşmesi").
    Bunlar tamamlanana kadar gerçek HGS2 testleri **engellidir**.
* Yönlendirmeler izlenmez (`allow_redirects=False`); 3xx olduğu gibi raporlanır.
* `trust_env=False`: ortam proxy'leri, `.netrc` ve CA ayarları okunmaz. Adaptör proxy kullanımını da reddeder;
  dışarıdan verilen bir `requests.Session` `trust_env=True` ise veya proxy içeriyorsa kabul edilmez.
* Hassas değerler sonuçlara, metadata'ya ve hata mesajlarına maskelenerek yazılır (bkz. "Gizlilik").

## İstek bütçesi ve kontrollü durdurma

`limits` (yapılandırmada isteğe bağlı nesne):

| Anahtar | Varsayılan | Sabit tavan | Davranış |
|---|---|---|---|
| `max_requests` | 1000 | 10 000 | Ön kontrol: tüm senaryolar için `warmup_repetitions + repetitions` toplamı aşarsa hiçbir istek gönderilmez |
| `max_duration_seconds` | 600 | 3600 | Ön kontrol: gecikmeler tek başına aşarsa reddedilir. Çalışırken: süre dolunca yeni istek başlatılmaz |
| `max_consecutive_transport_errors` | 5 | — | Art arda bu kadar taşıma hatası (timeout, bağlantı hatası) olursa durulur |
| `max_error_rate` | 0.5 | — | Başarısız oran (taşıma hatası **veya** beklenmeyen HTTP durumu) bu değeri aşarsa durulur |
| `error_rate_min_requests` | 20 | — | Hata oranı en az bu kadar istekten sonra değerlendirilir |

* Sayımlara ısınma istekleri de dahildir (hepsi hedefe yük bindirir).
* HTTP 5xx bir yanıttır: ardışık taşıma hatası sayacını artırmaz, ama hata oranına girer.
* Süre sınırı yeni istek başlamadan denetlenir; devam eden bir istek `timeout_seconds` kadar daha sürebilir.
* Durduran isteğin kaydı korunur; durdurma nedeni `execution.stop_reason` alanına yazılır
  (`duration_limit`, `consecutive_transport_errors`, `error_rate`, `target_not_allowed`, `keyboard_interrupt`,
  `unexpected_error`).

## Sonuç modeli (şema 2)

Her istek girişimi bir `RawResult` kaydıdır. Alan sırası (CSV sütun sırası da budur):

`run_id`, `seq`, `scenario`, `iteration`, `warmup`, `method`, `url`, `started_at`, `offset_ms`, `elapsed_ms`,
`duration_ms`, `status_code`, `http_ok`, `business_outcome`, `error_type`, `error`, `response_bytes`

| Alan | Anlam |
|---|---|
| `seq` | Çalıştırma genelinde 1'den başlayan, senaryolar ve ısınma istekleri boyunca kesintisiz artan sıra |
| `iteration` | Senaryo içinde, kendi türünde (ısınma ya da ölçüm) 1'den başlayan sıra |
| `warmup` | Isınma isteği mi (`true`/`false`) |
| `url` | İstek URL'si; hassas sorgu değerleri `***REDACTED***` |
| `started_at` | Girişimin başladığı UTC duvar saati zamanı (ISO 8601) |
| `offset_ms` | Girişimin başlangıcı; çalıştırmanın ortak monotonik başlangıç referansına (ilk `run()` çağrısı) göre |

Taşıma düzlemi ile HTTP düzlemi ayrıdır:

| Durum | `error_type` | `status_code` | `http_ok` | `duration_ms` | `elapsed_ms` |
|---|---|---|---|---|---|
| HTTP yanıtı alındı (500 dahil) | boş | dolu | `true`/`false` | dolu | dolu |
| Zaman aşımı / bağlantı hatası | `timeout` / `connection_error` / `transport_error` | boş | boş | boş | dolu |

* `elapsed_ms`: girişimden taşıyıcının sonuç döndürmesine veya hata vermesine kadar, monotonik saatle (`perf_counter_ns`).
* `duration_ms`: HTTP yanıtı alındıysa HTTP süresi; taşıyıcı kendi değerini vermezse `elapsed_ms` kullanılır.
* `business_outcome`: yanıt gövdesinden çıkarılan, tanınan iş sonucu değeri (`ONAYLANDI`, `REDDEDILDI`, `OK`, `HATA`,
  `NONE`, `SCAN_CARD`, `SCAN_FP`, `SCAN_SCHOOL_NO`, `WAITING`, `READY`, `KAYDEDILDI`; bkz. "Gerçek HGS2 API
  sözleşmesi"); tanınmazsa veya gövde ayrıştırılamazsa boş. Gövdenin kendisi yazılmaz (bkz. "Yanıt
  ayrıştırma ve iş sonucu"). Bu alanı dolduran sürümden önce yazılmış dosyalarda her zaman boştur.
* `error`: hata mesajı; hassas sorgu değerleri, URL parolaları ve isteğin hassas header değerleri maskelenir.

## HTTP taşıyıcısı ve ölçüm sınırları

`RequestsTransport` her `send` çağrısında:

1. **Hazırlık (ölçüm dışı):** metot, timeout ve hedef (metin + ad çözümlemesi) doğrulanır; `body` varsa JSON olarak
   serileştirilir (`Content-Type: application/json`, senaryo kendi değerini vermediyse).
2. **İstek:** `session.request(..., stream=True, allow_redirects=False, timeout=timeout_seconds)`.
3. **Gövde:** `response.content` ile yanıt gövdesinin tamamı okunur, ardından yanıt kapatılır. Gövde ve
   `Content-Type` başlığı runner'a taşınır; runner, süre ölçümü bittikten **sonra** gövdeyi iş sonucu için
   ayrıştırır (ölçüme dahil değildir; bkz. "Yanıt ayrıştırma ve iş sonucu").

| Alan | Başlangıç | Bitiş |
|---|---|---|
| `duration_ms` | `session.request` çağrısından hemen önce | Yanıt gövdesinin **tamamı** okunduktan hemen sonra |
| `elapsed_ms` (runner) | `Transport.send` çağrısından önce | `send` dönünce/hata verince; hazırlık (hedef denetimi, JSON) dahil |

Bağlantı katmanındaki ad çözümlemesi (yeni bağlantı açılırken) `duration_ms` içindedir.

**Yanıt boyutu** (`response_bytes`): içerik kodlaması (gzip/deflate) çözüldükten sonraki gövdenin bayt sayısıdır.

| requests hatası | Sonuç |
|---|---|
| HTTP yanıtı (500 dahil) | Hata değil; `status_code` dolu, `error_type` boş |
| `ConnectTimeout`, `ReadTimeout`, gövde okurken okuma zaman aşımı | `timeout` |
| `ConnectionError` (`SSLError`, `ProxyError` dahil), `ChunkedEncodingError` | `connection_error` |
| Diğer `RequestException` (ör. `ContentDecodingError`) | `transport_error` |
| `TargetNotAllowed`, girdi hataları (`InvalidURL`, `InvalidHeader`, serileştirilemeyen body), desteklenmeyen metot, diğer istisnalar | **Yakalanmaz**, olduğu gibi yayılır |

## Sonuç dosyaları ve metadata

`<output_dir>/<run_id>.csv` ve `<output_dir>/<run_id>.json` (kısmi çalıştırmada `<run_id>.partial.*`).
`run_id` harf/rakamla başlar; yalnızca harf, rakam, `.`, `_`, `-` içerir (en çok 64 karakter). Bir `run_id` için tam ya
da kısmi dosyalardan herhangi biri varsa `run` ön kontrolde reddeder ve hiçbir dosyanın üzerine yazılmaz.
Yazım önce geçici dosyalara yapılır, sonra atomik olarak yayımlanır.

**Şema sürümü:** `2`. Yetkili kaynak JSON'daki üst düzey `schema_version`'dır; CSV'de sürüm sütunu yoktur.
Şema 1 dosyaları `UnsupportedSchemaError` ile reddedilir; v1 → v2 dönüştürme yoktur.

### Şema sürüm politikası

| Değişiklik | Sürüm | Gerekçe |
|---|---|---|
| Metadata'ya yeni üst düzey anahtar (ör. `clock`) | **Değişmez** | Okuyucular tanımadıkları metadata anahtarlarını yok sayar; eski v2 okuyucular yeni dosyaları okur |
| `RawResult` alan kümesinde herhangi bir değişiklik (alan ekleme dahil) | **Yeni ana sürüm** | CSV başlığı ve `RawResult.from_dict` alan kümesinin birebir eşleşmesini ister |

* Yazılan sürüm `storage.SCHEMA_VERSION`, okunabilen sürümler `storage.READABLE_SCHEMA_VERSIONS`'dır (şu an `{2}`).
* Yeni bir ana sürüm eklendiğinde eski sürümler okunmaya devam eder: eski kayıtlar açık bir dönüştürücüyle yeni modele
  yükseltilir ve sürüm `READABLE_SCHEMA_VERSIONS`'a eklenir. Dönüştürücüsüz sürüm eklenmez.
* `schema_version` tam sayı olmalıdır: `"2"`, `2.0` ve `true` reddedilir.
* **Şema v3'e geçilmedi**: istek düzeyinde yeni alan gerekmedi. Saat çapası (`clock`), veri türü (`dataset_kind`),
  sentetik deney kimliği (`synthetic`) ve yanıt ayrıştırma özetleri (`response_parsing`) metadata anahtarı olarak
  eklendi; iş sonucu mevcut `business_outcome` alanına yazılır. Sentetik etiketler bilinçli olarak sonuç
  dosyalarına değil ayrı dosyalara yazılır (bkz. "Sentetik deneyler").
* Uyumluluk, `tests/golden/` altındaki gerçek eski yazıcılarla üretilmiş dosyalarla sınanır (bkz. `tests/golden/README.md`).
  a1331fd'nin okuyucusunun (`ResultStore.load_json/load_csv`) yeni yazılan dosyaları `clock` anahtarıyla birlikte
  okuduğu da elle doğrulandı.

* **CSV:** yalnızca sonuç satırları (`RawResult` alanları). Boş hücre = null, bool = `true`/`false`.
* **JSON:** `schema_version`, `run_id`, aşağıdaki metadata alanları ve `results`.

| Alan | İçerik |
|---|---|
| `tool_version` | `hgs2_lab.__version__` |
| `dataset_kind` | `measurement` (`run`: yapılandırılmış hedefe karşı ölçüm) veya `synthetic` (`synthetic run`); bu alandan önce yazılmış dosyalarda yoktur (bilinmiyor) |
| `synthetic` | Yalnızca sentetik deneyde: `experiment_id`, `seed`, `manifest_sha256`, `plan_sha256`, sürümler, `created_at_utc`. Planlanan hataları **içermez** |
| `target_label` | `--target-label` değeri; verilmezse `null` (`synthetic run`: `synthetic:<experiment_id>`) |
| `started_at`, `finished_at` | Çalıştırmanın UTC duvar saati başlangıç/bitişi |
| `monotonic_duration_ms` | İlk isteğin başlangıcından son isteğin bitişine (kesintide kesildiği ana) kadar monotonik süre |
| `clock` | Saat çapası (bkz. "Saat çapası"); hiç istek başlamadıysa `null`. Bu alandan önce yazılmış v2 dosyalarında yoktur |
| `execution` | `status`, `stop_reason`, `message` (maskeli), `planned_requests`, `completed_requests`, `limits` |
| `code.git_commit`, `code.git_dirty` | HEAD commit kimliği ve çalışma ağacı temizliği; alınamazsa `null`. Dosya adları yazılmaz. |
| `dependencies` | `requests` ve `urllib3` kurulu sürümleri |
| `environment` | Python sürümü/uygulaması, platform, işlemci, CPU sayısı |
| `inputs` | Yapılandırma/senaryo dosya adları (yol değil), orijinal baytların SHA-256 özeti, `hash_errors` |
| `config` | `base_url`, `timeout_seconds`; `output_dir` ve `scenarios_file` yalnızca ad olarak |
| `scenarios` | Senaryoların maskelenmiş görüntüsü |
| `response_parsing` | Yanıt ayrıştırıcısının sürümü, `max_parse_bytes`, tanınan iş sonucu değerleri, kural sayıları ve HTTP yanıtı alınan her istek için `seq` + özet (durum kodu, medya türü, gövde durumu, bayt sayısı, kural, iş sonucu, uyarılar). Gövde içeriği yoktur. Bu alandan önce yazılmış dosyalarda yoktur |

**Gizlilik:**

* Adı hassas görünen header/body alanları ve sorgu parametreleri (`token`, `access_token`, `api_key`, `apikey`,
  `password`, `passwd`, `secret`, `authorization`, `cookie`, `session` vb.; büyük/küçük harf duyarsız) `***REDACTED***`
  olarak yazılır. URL'nin path kısmı ve hassas olmayan parametreleri olduğu gibi korunur.
* Kişisel veri ve bağlantı alanları da hassastır: HGS2 parametreleri `kartNo`, `ogrenciNo`/`öğrenciNo`, `parmakIzi`
  (ve `kart_no`, `KARTNO`, `parmakIziId` gibi varyasyonları), `cardNumber`, `studentId`, `fingerprint`, biyometri,
  `tcKimlikNo`/`tckn`, `connectionString`, `dsn`, `jdbcUrl`, `datasource.url`. Değer kısmen gösterilmez; tamamı maskelenir.
  `deviceId`, `kartTipi`, `ogrenciSayisi` gibi benzer görünen alanlar maskelenmez.
* Hata mesajlarında ve `execution.message` alanında da aynı maskeleme uygulanır. Serbest metinde (`sanitize_text`)
  `anahtar=değer` (tırnaklı değer dahil), `"anahtar": değer`, `anahtar: değer` (log/header satırı), `Bearer`/`Basic`
  kimlik bilgileri, URL kullanıcı bilgisi parolası ve `jdbc:`/`postgresql://` gibi bağlantı URL'leri maskelenir. Java sınıf
  adları ve `Dosya.java:45` satır numaraları korunur. Yapılandırılmış veride (`sanitize_data`, `sanitize_json_text`)
  maskeleme JSON yapısı üzerinden yapılır: hassas anahtarın değeri iç içe nesne veya liste olsa da bütünüyle maskelenir.
  Form gövdeleri için `sanitize_form` vardır. Bozuk JSON metin kurallarına düşer; desteklenmeyen tür `TypeError` verir ve
  hata mesajına değer yazılmaz.
* Metadata mutlak yerel yol içermez. Dosya içerikleri metadata'ya kopyalanmaz.
* Maskeleme anahtar adına dayanır: masum adlı bir alana yazılmış gizli değer maskelenmez. Senaryo dosyalarına gerçek
  parola veya token yazmayın.

## Saat çapası

`offset_ms` monotonik saate (`time.perf_counter_ns`), `started_at` duvar saatine göredir. İkisini ilişkilendirmek için
runner, ilk `run()` çağrısında (ilk istekten önce) çapayı alır ve metadata'ya `clock` olarak yazılır:

| Alan | Anlam |
|---|---|
| `anchor_event` | `runner_origin`: çalıştırmanın monotonik başlangıç referansı (`offset_ms = 0`) |
| `monotonic_source`, `monotonic_ns` | Monotonik saat kaynağı ve başlangıç referansının değeri |
| `monotonic_scope` | `process`: monotonik değer yalnızca aynı süreç içinde anlamlıdır |
| `wall_source`, `wall_time_ns`, `wall_time_utc` | Duvar saati kaynağı (`time.time_ns`), Unix epoch ns ve ISO 8601 UTC karşılığı (µs) |
| `read_window_ns` | Okuma sırası monotonik (m0) → duvar saati → monotonik (m1); `m1 - m0` duvar saati okumasının belirsizlik üst sınırı |

Bir isteğin yaklaşık UTC zamanı: `wall_time_ns + offset_ms × 10⁶` (± `read_window_ns`). **Sınırlar:** monotonik saatin
başlangıç noktası tanımsızdır; başka bir süreçteki veya makinedeki saatlerle eşitlik **kanıtlanmış değildir** ve NTP
gibi senkronizasyon kaydedilmez. `clock` alanı yoksa (eski v2 dosyaları) analiz bunu `clock_anchor_missing` uyarısıyla
belirtir; hata vermez, yalnızca UTC dönüşümü ve telemetri hizalaması kullanılamaz.

## Analiz (`analyze`)

```
hgs2-lab analyze --results-dir results --run-id run-20261023T101530Z-a1b2c3
hgs2-lab analyze --config configs/config.json --run-id run-20261023T101530Z-a1b2c3      # output_dir yapılandırmadan
hgs2-lab analyze --results-dir results --run-id RUN --output rapor.json --seed 7 --confidence 0.9
```

* Girdi: `<sonuç dizini>/<run_id>.csv` + `.json` ya da `<run_id>.partial.csv` + `.json` (otomatik bulunur). İkisinden
  biri eksikse veya hem tam hem kısmi dosyalar varsa reddedilir. Yapılandırma yalnızca `output_dir` için okunur;
  senaryo dosyası gerekmez.
* Çıktı: varsayılan `<sonuç dizini>/analysis/<run_id>[.partial].analysis.json` (ham sonuçlardan ayrı dizin).
  **Var olan dosyanın üzerine yazılmaz** (çıkış 5). Yazım geçici dosya + sabit bağlantı (`os.link`) ile atomiktir;
  sabit bağlantı desteklenmeyen dosya sistemlerinde yalnızca hedef yoksa oluşturan özel kip kullanılır. Farklı
  parametrelerle yeniden analiz için `--output` ile başka bir ad verin.
* Ağ: yok. Analiz yolu soket, ad çözümlemesi ve HTTP oturumu engellenmiş halde test edilir.

### Doğrulama (okuyucu)

* `schema_version` desteklenen bir tam sayı olmalı; JSON'daki `run_id` istenenle aynı olmalı.
* JSON ve CSV aynı kayıtları aynı sırayla taşımalı (fark varsa kayıt numarası ve alanlar bildirilir).
* Her kaydın `run_id`'si dosyanınkiyle aynı; `seq` 1'den başlayıp kesintisiz artar.
* Metadata için en küçük doğrulama: `tool_version`/`target_label` metin; `started_at`/`finished_at` saat dilimli ISO 8601;
  `monotonic_duration_ms` negatif olmayan sayı; `code`, `inputs` türleri; `scenarios` varsa sonuçlardaki senaryo adları
  burada tanımlı olmalı; `clock` varsa tam ve tutarlı olmalı.
* `execution` varsa: bilinen `status`; `completed_requests` = kayıt sayısı ≤ `planned_requests`; `completed` ise
  dosya kısmi olamaz, tüm planlanan istekler kaydedilmiş ve `stop_reason` boş olmalı; diğer durumlarda dosya `.partial`
  olmalı. `execution` yoksa (76d15bb dönemi v2 dosyaları) kabul edilir ve uyarılır.
* Tanınmayan metadata anahtarları yok sayılır (ileriye uyumluluk). Girdi dosyaları her biri tek kez bayt olarak okunur;
  SHA-256 özeti ve ayrıştırma aynı baytlardan yapılır.

### Metrik tanımları

Her metrik `overall` (tüm senaryolar) ve her senaryo için ayrı hesaplanır. Senaryolar ilk görüldükleri sırada listelenir.

| Metrik | Tanım |
|---|---|
| `requests.total/warmup/measured` | Kayıtlı istek sayıları; ısınma ve ölçüm ayrı |
| `warmup.*`, `measured.*` | `total`, `http_responses` (yanıt alındı), `successful` (`http_ok=true`), `http_errors` (yanıt var, durum kodu beklenmeyen: `http_ok=false`), `transport_errors` (yanıt yok: timeout/bağlantı/diğer), `failed` = `http_errors + transport_errors`, durum koduna ve hata türüne göre dağılım |
| `rates.*` | Ölçüm istekleri üzerinden `success_rate`, `failure_rate`, `http_error_rate`, `transport_error_rate`; ölçüm isteği yoksa `null` (`status: no_data`) |
| `response_time_ms` | Ölçüm istekleri içinde `http_ok=true` olanların `duration_ms` değerleri: `n`, `min`, `max`, `median`, `p90`, `p95`, `p99` |
| Yüzdelik yöntemi | Doğrusal interpolasyon (Hyndman-Fan tip 7, numpy varsayılanı, `statistics.quantiles(method="inclusive")` ile aynı); kesirli ağırlık `fractions` ile tam hesaplanır |
| Güven aralığı (`ci`) | Yüzdelik bootstrap (yerine koyarak yeniden örnekleme), varsayılan 2000 örnek, %95 |
| `throughput` | `measured / (son ölçüm isteğinin bitişi − ilk ölçüm isteğinin başlangıcı)` (`offset_ms`, `elapsed_ms`); `successful_per_second` aynı pencerede başarılılar |

Isınma istekleri yalnızca sayılır; hiçbir süre, oran veya throughput metriğine girmez. HTTP hata yanıtlarının ve taşıma
hatalarının süreleri yanıt süresi dağılımına girmez (sayıları ayrıca raporlanır). `run` komutunun ekrana yazdığı özet
farklıdır: oradaki medyan/en az/en çok tüm HTTP yanıtlarını kapsar.

### Örneklem yetersizliği ve eksik veri

* Kuyruk yüzdeliği p (> 50) için en az `ceil(min_tail_samples / (1 − p/100))` gözlem gerekir; varsayılan
  `min_tail_samples = 10` ile p90 ≥ 100, p95 ≥ 200, p99 ≥ 1000. Medyan için n ≥ 1. Altında değer **üretilmez**:
  `value: null`, `status: "insufficient_sample"`, `min_samples` gereken sayıdır.
* Güven aralığı için ayrıca `n ≥ max(yüzdeliğin gerektirdiği n, min_bootstrap_samples = 20)`.
* Throughput yalnızca grubun ölçüm istekleri kesintisiz bir `seq` bloğuysa (pencerede ısınma veya başka senaryo isteği
  yoksa), `offset_ms` artıyorsa ve en az 10 ölçüm isteği varsa hesaplanır; aksi halde `status` ve `reason` açıklar.
  Birden çok senaryolu ve ısınmalı çalıştırmalarda `overall` throughput'u bu nedenle hesaplanmaz.
* Hiçbir metrik uydurulmaz: hesaplanamayan her değer `null` ve bir durum kodu taşır.

Uyarılar (`warnings`: `code`, `scope`, `message`):

| Kod | Anlam |
|---|---|
| `run_incomplete` | Kısmi çalıştırma (`.partial` veya `execution.status ≠ completed`); `limitations`'a da eklenir |
| `execution_metadata_missing` | Eski v2 dosyası: planlanan istek sayısı ve tamamlanma durumu bilinmiyor |
| `clock_anchor_missing` | Saat çapası yok: UTC dönüşümü ve telemetri hizalaması kullanılamaz |
| `code_state_unknown` / `working_tree_dirty` | Ölçümü yapan kodun commit'i bilinmiyor / commit edilmemiş değişiklik vardı |
| `input_hash_unavailable` | Ölçümdeki yapılandırma/senaryo dosyalarının özetleri eksik |
| `offsets_not_monotonic` | `offset_ms` seq sırasıyla artmıyor |
| `pooled_scenarios` | `overall` birden çok senaryoyu birleştiriyor; yorum senaryo bazında yapılmalı |
| `no_measured_requests`, `no_successful_responses` | Grup için veri yok |
| `http_errors_present`, `transport_errors_present` | Hatalı istekler var (süreleri dağılıma girmedi) |
| `insufficient_sample`, `insufficient_sample_ci` | Yüzdelik veya güven aralığı örneklem yetersizliği nedeniyle üretilmedi |
| `throughput_not_computed` | Throughput hesaplanmadı; neden mesajda |
| `synthetic_data` | Sentetik deney verisi; gerçek HGS2 ölçümü değildir (`limitations`'a da eklenir). Analiz etiket dosyalarını okumaz |

### Çıktı biçimi, determinizm ve yeniden üretilebilirlik

```
{ "format": "hgs2-lab-analysis", "analysis_schema_version": 1,
  "generated_at": "...",            <- tek değişken alan; determinizm garantisinin dışında
  "content_sha256": "...",          <- analysis içeriğinin kanonik JSON özeti
  "analysis": { "tool", "input", "method", "run", "clock", "overall", "scenarios", "warnings", "limitations" } }
```

* `analysis.input`: `run_id`, şema sürümü, kısmi mi, girdi dosyalarının adı (yol değil), SHA-256 özeti ve boyutu.
* `analysis.method`: tüm parametreler (`seed`, `bootstrap_resamples`, `confidence`, `min_tail_samples`,
  `min_bootstrap_samples`, `min_throughput_requests`) ve yöntem tanımları.
* Aynı girdi dosyaları ve aynı parametrelerle `analysis` içeriği ve `content_sha256` aynıdır. Kanonik JSON:
  anahtarlar sıralı, boşluksuz, UTF-8.
* Bootstrap: her grup kendi tohumunu `sha256("<seed>:<grup>")`'tan türetir (bir senaryo eklemek diğerinin sonucunu
  değiştirmez). İndeksler yalnızca `random.Random(tohum).random()` ile seçilir; Python bu fonksiyonun aynı tohumla aynı
  diziyi üretmesini sürümler arasında garanti eder (`choices` gibi yardımcılar için böyle bir garanti yoktur). Python
  3.13.16 ve 3.15.0 ile aynı girdiler için aynı `content_sha256` elde edildiği doğrulandı.
* Süre: 10 000 ölçüm isteğinde varsayılan 2000 yeniden örneklemle analiz bu geliştirme makinesinde yaklaşık 13 sn sürdü.

## Sentetik deneyler (`synthetic`)

**Amaç:** Ölçüm motorunu, gerçek bir sisteme dokunmadan, önceden planlanmış hatalarla sınamak ve gelecekteki anomali
tespiti çalışmaları için **etiketli** veri üretmek. Hatalar yalnızca uygulamanın kendi yerel sentetik sunucusunda
(`synthetic_server.py`) üretilir. **Sentetik sonuçlar gerçek HGS2 performans ölçümü değildir**; HGS2 projesine,
veritabanına veya herhangi bir dış hedefe erişilmez. Henüz makine öğrenmesi modeli yoktur.

### Çalıştırma ve analiz

```
hgs2-lab synthetic validate --manifest configs/synthetic.example.json
hgs2-lab synthetic plan     --manifest configs/synthetic.example.json --output plan.json
hgs2-lab synthetic run      --manifest configs/synthetic.example.json --results-dir results --run-id syn-demo-1
hgs2-lab analyze            --results-dir results --run-id syn-demo-1
```

Örnek manifestle gerçek bir çalıştırmanın çıktısı (yollar kısaltıldı; süreler her çalıştırmada farklıdır):

```
Çalıştırma: syn-demo-1  durum: completed
  istekler: planlanan 55, tamamlanan 55 (ısınma 2, ölçüm 53)
  HTTP yanıtı: beklenen durum 45, beklenmeyen durum 5; taşıma hatası: connection_error 3, timeout 2
  ...
Sentetik deney: syn-fault-mix-001  (dataset_kind: synthetic; gerçek HGS2 ölçümü değildir)
  etiketler: planlanan 55, doğrulanan 55, çelişen 0, yürütülmeyen 0
  deney geçerli: evet
  etiket dosyası:        results/synthetic/syn-demo-1.labels.json
  sunucu olayları:       results/synthetic/syn-demo-1.server-events.json
```

### Sunucunun başlatılması ve kapatılması

`synthetic run` sunucuyu kendisi yönetir: deneyden hemen önce `127.0.0.1`'de, işletim sisteminin seçtiği boş bir
portta başlatır; deney bitince (hata veya Ctrl+C dahil, `finally` içinde) kapatır. Python'dan doğrudan kullanım:

```python
from hgs2_lab.synthetic import build_plan, load_manifest
from hgs2_lab.synthetic_server import SyntheticServer

manifest, _ = load_manifest("configs/synthetic.example.json")
with SyntheticServer(build_plan(manifest)) as server:   # start() ... stop()
    print(server.base_url)                              # http://127.0.0.1:<port>
```

* Bind adresi her zaman `127.0.0.1`'dir (değiştirilemez). `port=0` (varsayılan) boş port seçer; sabit port
  1024–65535 arasında olmalıdır. Adres yeniden kullanımı kapalıdır (Windows'ta `SO_EXCLUSIVEADDRUSE`): dolu bir port
  başka dinleyiciyle paylaşılmaz, açık bir hatayla reddedilir.
* `stop()` bekletilen istekleri en çok bir uyku dilimi (20 ms) içinde serbest bırakır, dinleyen soketi kapatır, iş parçacıklarını süre sınırıyla bekler
  ve kapanmayanları döndürür (boş liste = temiz kapanış; `synthetic run` kapanmayan iş parçacığı varsa deneyi geçersiz sayar).
* Kaynak sınırları: en çok 8 eşzamanlı bağlantı (fazlası hemen kapatılır), istek gövdesi en çok 64 KiB, boşta bağlantı
  en çok 5 sn, bekletme en çok 30 sn, olay kaydı plan uzunluğu + 1000 ile sınırlı (aşılan olaylar sayılır).
* Sunucu hedef korumasını atlatmaz: motor ona normal bir `base_url` ile bağlanır; ön kontrol (metin + ad çözümlemesi),
  bağlantı katmanındaki loopback koruması, proxy reddi ve yönlendirme izlememe **aynen** uygulanır.

### Desteklenen hata senaryoları

Her senaryo `/synthetic/<ad>` rotasına gider; sunucu o rotaya gelen k. isteğe planın k. girdisini uygular.

| `fault.type` | Parametreler | Sunucu davranışı | Beklenen (istemci) |
|---|---|---|---|
| `none` | — | 200 | `success` |
| `fixed_delay` | `delay_ms` | `delay_ms` bekler, sonra 200 | `success`, `duration_ms ≥ delay_ms` |
| `random_delay` | `min_delay_ms`, `max_delay_ms` | Planda seed ile çekilmiş gecikme, sonra 200 | `success`, `duration_ms ≥` planlanan gecikme |
| `http_error` | `status` (400–599) | O durum koduyla yanıt | `http_error` + durum kodu |
| `connection_drop` | — | Yanıt yazmadan bağlantıyı kapatır | `transport_error` / `connection_error` |
| `timeout` | — | İstemci zaman aşımının en az 1,5 katı (ve +250 ms) bekletir, yanıtsız kapatır | `transport_error` / `timeout` |

Her hata türü (`none` hariç) isteğe bağlı `onset_after: N` alır: senaryonun ilk N isteği (ısınma dahil) normal,
sonrakiler hatalıdır ("belirli sayıda istekten sonra hata"). Sunucu her isteği ve uyguladığı hatayı ayrı bir olay
kaydına yazar (istek sayısı, rota sırası, gönderilen durum, gerçek bekleme süresi, sonuç).

Plan dışı istekler (bilinmeyen rota → 404, plan tükenmiş → 410, metot uyuşmazlığı → 405, 64 KiB'tan büyük gövde → 413,
aşırı eşzamanlılık → bağlantı kapatılır) plan girdisi tüketmeden reddedilir ve "unexpected" olarak kaydedilir; sentetik
deneyi geçersiz kılar.

### Manifest yapısı

`configs/synthetic.example.json` (Git'te izlenir). Bilinmeyen veya eksik alanlar her düzeyde reddedilir.

| Alan | Zorunlu | Kural |
|---|---|---|
| `manifest_version` | evet | `1` |
| `experiment_id` | evet | `run_id` ile aynı güvenli ad kuralı |
| `experiment_type` | evet | `fault_injection` |
| `dataset_kind` | evet | Yalnızca `synthetic` |
| `seed` | evet | 0 … 2⁶³−1 tam sayı |
| `timeout_seconds` | evet | İstemci zaman aşımı, 0,1–10 sn |
| `limits` | hayır | `RunLimits` alanları (`config.json` ile aynı anlam ve tavanlar) |
| `description` | hayır | En çok 500 karakter |
| `scenarios[]` | evet | 1–20 senaryo: `name` (`a-z0-9_-`, benzersiz), `method` (GET/POST), `warmup_repetitions` (0–100), `repetitions` (1–1000), `delay_seconds` (0–10), `fault` |

Ek sınırlar: toplam en çok 5000 istek ve `limits.max_requests`'ten az; gecikmeler 0–5000 ms ve **istemci zaman
aşımının yarısını aşamaz** (yoksa "başarılı ama yavaş" ile "zaman aşımı" ayırt edilemez); `onset_after` senaryonun
istek sayısından küçük olmalı; planın tahmini en kısa süresi `limits.max_duration_seconds`'tan kısa olmalı.
`expected_behavior` manifestte yazılmaz: beklenen davranış hata türü ve zaman aşımından **deterministik olarak
türetilir**, böylece manifestle çelişemez. `created_at_utc` ve `generator_version` çalıştırma anında sonuç
metadata'sına (`synthetic`) yazılır. Beklenen hatalar güvenlik sınırlarını (`max_consecutive_transport_errors`,
`max_error_rate`) tetikleyecekse `validate`/`plan` bir UYARI verir; hata yoğun deneylerde `limits` ayarlanmalıdır.

### Çıktılar ve etiketler

| Dosya | Kaynak | İçerik |
|---|---|---|
| `<run_id>.csv/json` | İstemci | Normal sonuç dosyaları (şema v2). `dataset_kind = "synthetic"` ve `synthetic` metadata'sı; **planlanan hata yok** |
| `synthetic/<run_id>.server-events.json` | Sunucu | Sunucunun aldığı her istek ve uyguladığı hata; zaman damgaları istemcinin saat çapasına göre `*_offset_ms` (aynı süreç, aynı saat) |
| `synthetic/<run_id>.labels.json` | Türetilmiş | Normalleştirilmiş manifest, `plan_sha256`, her istek için `planned`, `expected`, `observed`, `agreement`, `label_status`, `server`; özet ve `verdict` |

Kısmi çalıştırmada adlar `<run_id>.partial.*` olur. Hiçbir dosyanın üzerine yazılmaz; herhangi biri varsa deney
hiçbir istek gönderilmeden reddedilir (çıkış 3).

Her istek için dört şey ayrı izlenir: (1) planlanan hata (`planned`), (2) istemcinin gözlediği sonuç (`observed`, sonuç
dosyasından), (3) uyum (`agreement.match` ve nedenleri; `label_status`: `confirmed`, `contradicted`, `not_executed`,
`unjoinable`), (4) deneyin geçerliliği (`verdict.valid` ve gerekçe kodları: `run_incomplete`, `result_plan_mismatch`,
`expectation_mismatch`, `server_missing_arrival`, `server_fault_mismatch`, `server_extra_arrivals`,
`unexpected_server_requests`, `server_events_truncated`, `server_errors`, `server_threads_leftover`). Beklenen etiket
hiçbir zaman gözlenen sonucun yerine yazılmaz.

**Etiket sızıntısına karşı:** etiket dosyasındaki `field_roles`, sonuç alanlarını ayırır: model girdisi adayları
(`warmup`, `offset_ms`, `elapsed_ms`, `duration_ms`, `status_code`, `http_ok`, `error_type`, `response_bytes`),
özellik olmayan tanımlayıcılar (`run_id`, `seq`, `scenario`, `iteration`, `method`, `url`, `started_at`), dışlananlar
(`business_outcome`, serbest metin `error`) ve yalnızca gerçek etiket alanları (`planned.*`, `expected.*`,
`agreement.*`, `label_status`). Senaryo adı/URL ve sunucu olayları uygulanan hatayı yansıtır; model girdisi olarak
kullanılmamalıdır. `analyze` etiket dosyalarını okumaz.

### Gerçek ölçümden farkı, seed ve tekrarlanabilirlik

* Sentetik sunucu, istemciyle **aynı süreçte ve aynı makinede** çalışır; gecikmeler yapaydır. Sonuçlar ölçüm
  aracının ve etiketleme hattının doğruluğunu sınar; HGS2'nin davranışı hakkında bilgi vermez.
* **Aynı manifest (ve dolayısıyla aynı seed) → aynı plan**: hangi istekte hangi hata, hangi gecikme ve beklenen sonuç
  aynıdır; `plan_sha256` ve `synthetic plan --output` dosyası bayt bayt aynıdır. Rastgele gecikmeler senaryo başına
  `sha256("<seed>:<senaryo>")` tohumlu `random.Random(...).random()` ile çekilir (senaryo eklemek diğerlerini değiştirmez).
* **Aynı olmayanlar:** gerçek yanıt süreleri, işletim sistemi zamanlaması, sunucudaki gerçek bekleme süresi (planlanandan
  kısa olamaz, uzun olabilir; bkz. "Gecikme alanları ve bekleme yöntemi"), zaman damgaları, `run_id`. Uyum denetimi bu
  yüzden yalnızca alt sınır kullanır (gözlenen süre ≥ planlanan gecikme − 1 ms).

### Ölçüm yalıtımı: sunucu ve istemci aynı süreçte

`synthetic run`'da sentetik sunucu, istemciyle **aynı işletim sistemi sürecinde** çalışır: `serve_forever` bir arka plan
iş parçacığında, her bağlantı ayrı bir iş parçacığında; istemci (`execute_run`) ana iş parçacığındadır. Hepsi aynı GIL'i
paylaşır. Bunun etkisi, sunucunun aynı kodla ayrı bir süreçte çalıştırıldığı bir **deney prototipiyle** karşılaştırıldı
(prototip depoya eklenmedi). Koşullar: Windows, Python 3.15.0, yalnızca `127.0.0.1`; senaryo başına 250 ölçüm isteği,
her model 3 çalıştırma (sıra A B B A A B), model başına 750 eşleştirilmiş istek. Bu ölçümler **eski bekleme yöntemiyle**
(`threading.Event.wait`) yapıldı; gecikmeli satırlar F3-B'de değiştirilen yöntemi yansıtır (bkz. bir sonraki bölüm).

| Ölçüm (birleşik, ms) | Aynı süreç (A) medyan / p90 / p95 | Ayrı süreç (B) medyan / p90 / p95 |
|---|---|---|
| İstemci `duration_ms`, normal 200 | 0,920 / 1,283 / 1,405 | 0,887 / 1,052 / 1,159 |
| İstemci `duration_ms`, sabit 5 ms gecikme | 15,385 / 17,337 / 20,167 | 15,305 / 16,448 / 18,690 |
| İstemci `duration_ms`, sabit 20 ms gecikme | 31,005 / 34,694 / 36,169 | 31,172 / 34,636 / 36,013 |
| Sunucu `completed − received`, normal 200 | 0,382 / 0,892 / 1,080 | 0,087 / 0,114 / 0,124 |
| Sunucu bekleme aşımı (`hold_ms_actual − delay_ms`), 5 ms | 8,780 / 10,864 / 13,775 | 8,861 / 10,055 / 12,227 |

Bulgular (az sayıda çalıştırmaya dayanır; genellenmemelidir):

* **İstemci süreleri** (sonuç dosyalarındaki ve `analyze`'daki veri) iki modelde gecikmeli senaryolarda pratikte aynıdır
  (medyan farkları çalıştırmalar arası yayılım içinde). Milisaniye altı normal yanıtlarda aynı süreçte p90/p95 yaklaşık
  0,2 ms daha yüksektir.
* **Sunucu tarafı zaman damgaları aynı süreçte güvenilir değildir:** `completed_ns` yanıt yazıldıktan sonra GIL yeniden
  alınınca damgalanır. A'da sunucu "servis süresi" şişer (medyan 0,38 ms, B'de 0,09 ms) ve 2250 isteğin 99'unda
  istemcinin ölçtüğü toplam süreden **uzun** görünür (fiziksel olarak imkânsız; B'de 0). Bu yüzden sunucu olay dosyası
  `process_model: "same_process"` ve `timing_caveats` taşır; `completed_ns − received_ns` sunucu servis süresi olarak
  kullanılmamalıdır.
* **En büyük sapma süreç modelinden bağımsızdı:** eski yöntemle sunucu beklemesi Windows'ta zamanlayıcı çözünürlüğü
  nedeniyle planlanandan medyan ~9 ms uzun sürüyordu (5 ms planlanan gecikme istemcide medyan ~15,4 ms). Ayrı süreç bunu
  çözmez; F3-B'de bekleme yöntemi değiştirildi ve aşım medyanı 1 ms'nin altına indi (bkz. bir sonraki bölüm). Enjekte
  edilen gerçek bekleme için `delay_ms` değil, sunucu olayındaki `hold_ms_actual` esas alınmalıdır.
* Zaman aşımı hatasında istemci devam eder, sunucu önceki isteği bekletmeyi sürdürür; sonraki istekler eşzamanlı işlenir.
  Rota içi sıra geliş anında kilit altında atandığı için istek–olay eşleştirmesi bozulmaz (entegrasyon testiyle sınanır).
* **Kaynak temizliği hatası bulundu ve düzeltildi:** urllib3 2.x'te `PoolManager.clear()` havuzları kapatmaz; bu yüzden
  `RequestsTransport.close()` sonrasında boştaki keep-alive soketleri ancak nesneler serbest kalınca kapanıyordu. Zaman
  aşımı istisnalarının referans döngülerinde bu çöp toplamaya kalıyor, sentetik sunucunun `stop()`'u boşta bağlantı
  süresi (5 sn) kadar bekliyordu. Loopback adaptörü artık kapanışta havuzları açıkça kapatır (`http_transport.py`,
  `_LoopbackOnlyAdapter.close`); hedef, proxy ve yönlendirme denetimleri değişmedi.

**Karar:** Mevcut aynı süreç modeli korunur. Ayrı süreç, sunucu tarafı zaman damgalarını temizler ama istemci
ölçümlerinde anlamlı bir fark göstermedi; buna karşılık süreç yaşam döngüsü (hazır olma bildirimi, öksüz süreç temizliği,
Windows'ta Ctrl+C ve sonlandırma), süreçler arası olay aktarımı ve süreçler arası saat hizalaması (aynı süreçteki
`*_offset_ms` geçerliliğini yitirir) gerektirir. Sunucu tarafı servis süresi model girdisi ya da etiket olarak gerekirse
ayrı süreç modeli yeniden değerlendirilmelidir.

### Gecikme alanları ve bekleme yöntemi

Dört kavram ayrı alanlarda tutulur ve birbirinin yerine kullanılmaz:

| Kavram | Alan (dosya) | Kapsadığı zaman aralığı |
|---|---|---|
| 1. Planlanan gecikme | `planned.delay_ms` (etiket), `hold_ms_planned` (sunucu olayı) | Ölçüm değil; manifest + seed'den üretilen bekleme talimatı. `expected.min_duration_ms` başarılı gecikmeli yanıtta buna eşittir |
| 2. Sunucuda gerçekleşen bekleme | `hold_ms_actual` (sunucu olayı; etikette `server.hold_ms_actual`), `hold_started_ns`/`hold_ended_ns` | Yalnızca bekleme döngüsü (`_hold`): hemen öncesinden hemen sonrasına. İstek okuma ve yanıt yazma dahil değil. Bekleme yoksa `null`; `outcome = "stopped"` ise kapanışta kesilmiştir |
| 3. Sunucu tarafı toplam işleme | `completed_ns − received_ns` (sunucu olayı; ayrı alan olarak saklanmaz) | Plan girdisinin ayrıldığı andan (istek ve gövde okunduktan sonra) yanıt yazılıp kayıt kilidi alınana kadar: bekleme + yanıt yazma. Aynı süreçte GIL nedeniyle şişebilir; servis süresi olarak kullanılmamalı |
| 4. İstemcinin ölçtüğü toplam süre | `duration_ms` (sonuç dosyası, `RawResult`; etikette `observed.duration_ms`) | `session.request` çağrısından yanıt gövdesinin tamamı okunana kadar; yeni bağlantıda bağlantı kurulumu, istek gönderimi, sunucu işleme (beklemeyi içerir) ve yanıt okuma |

Sonuç dosyaları (şema v2) değişmedi: 2 ve 3 yalnızca sunucu olay ve etiket dosyalarında bulunur (gerçek etiket bilgisidir,
model girdisi değildir). Sunucu olay dosyası ve etiket dosyası bu tanımları `timing_fields` olarak kendileri de taşır.
Bu dosyalara alan **eklemek** sürüm değiştirmez (`schema_version`/`labels_schema_version` 1 kalır); alan silmek veya bir
alanın anlamını değiştirmek yeni sürüm gerektirir. Etiket doğrulaması ek olarak gecikme hatalarında
`hold_ms_actual ≥ hold_ms_planned` koşulunu denetler (aksi halde `server_hold_short`, deney geçersiz).

**Bekleme yöntemi:** `_hold`, son tarihi `time.perf_counter_ns` ile belirler ve en çok 20 ms'lik `time.sleep` dilimleriyle
bekler; her dilim arasında durdurma işaretini denetler (kapanış tepki süresi ≤ ~20 ms). Önceki yöntem
`threading.Event.wait` idi: Windows'ta bu bekleme sistem zamanlayıcı adımına (~15,6 ms) yuvarlanıyordu. `time.sleep`,
Python belgelerine göre 3.11'den beri Windows'ta yüksek çözünürlüklü zamanlayıcı kullanır. Değerlendirilen seçenekler
(mikro ölçüm, Windows 11, Python 3.15.0 ve 3.13.16; hedef 1/5/20/100 ms): `Event.wait` aşım medyanı 7,7–14,7 ms;
`time.sleep` ve dilimli `time.sleep` 0,35–0,7 ms (p95 ≤ 0,9 ms); meşgul bekleme ~0 ms ama %86–100 CPU (reddedildi); sistem zamanlayıcı
çözünürlüğünü değiştirmek (`timeBeginPeriod`) tüm sistemi etkilediği için değerlendirme dışı bırakıldı.

**Deney** (yalnızca yerel sentetik sunucu, aynı süreç mimarisi; çıktılar geçici dizinde): beklemesiz, 1 ms, 5 ms, 20 ms
(her biri 250 istek) ve 100 ms (120 istek); yöntem başına 6 çalıştırma (2 tur × sıra E Y Y E E Y), yöntem ve senaryo
başına 1500 (100 ms için 720) istek. Tüm çalıştırmalar geçerli; hiçbir bekleme planlanandan kısa değil.

| Planlanan | Sunucu bekleme aşımı medyan / p95 (ESKİ → YENİ) | İstemci `duration_ms` medyan / p95 (ESKİ → YENİ) | İstemci − bekleme medyanı (ESKİ / YENİ) |
|---|---|---|---|
| beklemesiz | — | 0,878 / 1,351 → 0,892 / 1,227 | — |
| 1 ms | 11,97 / 15,71 → 0,18 / 0,65 | 15,54 / 19,37 → 2,39 / 3,61 | 2,56 / 1,07 |
| 5 ms | 8,00 / 13,40 → 0,43 / 0,74 | 15,59 / 20,83 → 7,65 / 8,40 | 2,61 / 2,22 |
| 20 ms | 8,78 / 13,80 → 0,49 / 0,78 | 31,40 / 36,46 → 23,10 / 23,61 | 2,68 / 2,65 |
| 100 ms | 7,43 / 11,58 → 0,50 / 0,79 | 109,93 / 113,95 → 103,16 / 103,63 | 2,63 / 2,70 |

* Çalıştırmalar arası değişkenlik (çalıştırma medyanlarının aralığı): sunucu beklemesi ESKİ 0,9–3,0 ms → YENİ ≤ 0,12 ms.
  İstemci süresi YENİ'de 0,2–1,4 ms aralığında değişir (5 ms senaryosunda çalıştırma medyanları 6,53–7,98 ms).
* **İstemci süresi, sunucu beklemesine eşit değildir:** gecikmeli isteklerde istemci süresi gerçekleşen beklemeden medyan
  ~2,2–2,7 ms uzundur (1 ms'de ~1,1 ms); beklemesiz bir isteğin tamamı ise ~0,9 ms sürer. Bu fark iki yöntemde de aynıdır;
  istemcinin uzun beklemeden sonra uyanma maliyeti (ör. işlemci boşta durumları, iş parçacığı uyandırma) olabilir —
  nedeni doğrulanmadı.
* **CPU:** Windows'ta `time.process_time` saat adımıyla örneklendiği için bu karşılaştırmada güvenilir değildir (aynı
  ESKİ yapılandırma iki turda 1,1 ve 2,3 sn gösterdi). Gerçek işlemci çevrimiyle (`QueryProcessCycleTime`) çalıştırma
  başına toplam CPU YENİ'de 2,50–2,65, ESKİ'de 2,67–3,13 saniye-eşdeğeridir (daha fazla değil). Yalnız bekleme ölçümünde
  dilimli uyku 100 ms başına ~0,3 ms CPU harcar (`Event.wait` ~0,1 ms); 20 ms'lik dilim uyanmalarından gelir.
* Sınırlar: tek makine (Windows 11, Python 3.15.0; mikro ölçüm ayrıca 3.13.16); hassasiyet işletim sistemi
  zamanlayıcısına ve Python sürümüne bağlıdır. `pyproject.toml`'daki en düşük sürüm olan 3.10'da Windows `time.sleep`'in
  bu hassasiyete ulaşacağı varsayılmamalıdır (sınanmadı). Linux'ta ölçülmedi. Yoğun yük altında bekleme yine uzayabilir;
  bu yüzden gerçekleşen değer her istekte kaydedilir.

## Sentetik kampanyalar ve veri seti

Bir **kampanya**, tek manifestten çok sayıda sentetik deney üretir ve sonuçlarını, gelecekteki model değerlendirmesine
uygun, sızıntıya karşı denetlenmiş bir **veri seti manifestine** dönüştürür. Hiçbir model eğitilmez; veri gerçek HGS2
ölçümü değildir.

```
hgs2-lab campaign validate --manifest configs/campaign.example.json
hgs2-lab campaign run      --manifest configs/campaign.example.json --output-dir work/camp-mix-001
hgs2-lab campaign verify   --campaign-dir work/camp-mix-001
hgs2-lab dataset build     --campaign-dir work/camp-mix-001 --output work/camp-mix-001.dataset.json --split-seed 7
hgs2-lab analyze           --results-dir work/camp-mix-001/runs --run-id camp-mix-001.mix-a.s11
```

(`work/` yalnızca bir örnektir ve `.gitignore` kapsamında değildir; proje içinde Git dışı kalması için `results/` altında
bir dizin ya da proje dışı bir dizin kullanın. Kampanya dizini yoksa oluşturulur, varsa boş olmalıdır.)

### Kampanya manifesti ve deterministik açılım

`configs/campaign.example.json`: `campaign_version` (1), `campaign_id` (harf/rakam/`_`/`-`, en çok 24, nokta yok),
`dataset_kind` (`synthetic`), `seeds` (1–50 benzersiz tam sayı, 0–999999), `timeout_seconds`, isteğe bağlı `limits` ve
`description`, `plans[]` (1–50): `plan_id` (`a-z0-9-`, en çok 24), isteğe bağlı `group` (varsayılan `plan_id`) ve
sentetik manifestle aynı biçimde `scenarios`. Bilinmeyen alanlar reddedilir; en çok 200 deney ve 50 000 istek.

Her (plan, seed) çifti bir deneye açılır: kimlik ve run_id `<campaign_id>.<plan_id>.s<seed>`; sıra planlar × seed'ler.
Açılan her deney manifesti mevcut sentetik manifest kurallarıyla (`synthetic.parse_manifest`, plan sınırları) doğrulanır;
hata mesajı planı ve seed'i adlandırır. Aynı kampanya manifesti → aynı deney listesi, aynı deney manifestleri, aynı
`campaign_plan_sha256`. Seed, sentetik planda yalnızca rastgele gecikme çekilişlerini değiştirir; gerçek yanıt süreleri
her çalıştırmada farklıdır (aynı olduğu iddia edilmez).

### Kampanya dizini ve katalog

```
<kampanya dizini>/
  campaign-manifest.json        kampanya manifestinin bayt bayt kopyası
  manifests/<deney>.json        açılan deney manifestleri (çalıştırmadan önce yazılır)
  runs/                         tüm deneylerin sonuçları (şema v2) + runs/synthetic/ etiket ve sunucu olayları
  campaign.json                 katalog (sonunda; Ctrl+C'de de yazılır)
```

Her deney mevcut tek deney akışıyla (`run_synthetic_experiment`) aynen yürütülür: yerel sentetik sunucu yalnızca
`127.0.0.1`, ön kontrol + loopback koruması + proxy reddi + yönlendirme izlememe değişmeden. Her deney kendi try bloğunda
çalışır; reddedilen (`rejected`), hata veren (`error`) veya güvenlik sınırıyla durdurulan (`aborted`) bir deney diğerlerini
etkilemez ve katalogda nedeniyle gösterilir. Ctrl+C kampanyayı durdurur; kalanlar `not_run` olur.

Katalog (`campaign.json`, `format: hgs2-lab-synthetic-campaign`, `catalog_schema_version: 1`) alanları: `campaign_id`,
`campaign_plan_sha256`, `campaign_manifest` (yol + SHA-256), `seeds`, `groups`, `tool`, `environment`, `dependencies`,
`code`, `process_model`, `hold_method`, başlangıç/bitiş zamanı, durum, özet ve her deney için: `experiment_id`, `run_id`,
`plan_id`, `group`, `seed`, `plan_sha256`, `design_fingerprint` (seed ve kimlikten bağımsız tasarım özeti), senaryo ve
hata parametreleri, `status`, `valid`, `invalid_reasons`, `error` (tür + mesaj; yerel yol `<campaign_dir>` ile
maskelenir), başlangıç/bitiş zamanı, istek sayıları (`planned`, `recorded`, `http_errors`, `transport_errors`),
`labels_summary` ve `files` (rol, kampanya dizinine göre göreli yol, SHA-256, boyut). Etiket ayrıntıları kopyalanmaz;
yetkili kaynak etiket dosyasıdır, katalog yalnızca dizin ve özettir.

`campaign verify` (ve her `dataset build`) kataloğu doğrular ve sorunları deney kimliği + kural koduyla listeler:
`path_unsafe` (mutlak yol, `..`, `.`, ters eğik çizgi, sürücü harfi veya kampanya dizini dışı — dosya okunmaz),
`file_missing`, `file_size_mismatch`, `file_hash_mismatch`, `manifest_invalid` (manifestten yeniden üretilen plan
katalogla aynı olmalı), `results_invalid` (sonuçlar mevcut okuyucuyla yeniden okunur), `results_inconsistent`
(`dataset_kind`/`synthetic` metadata'sı), `labels_invalid`, `labels_inconsistent` (biçim, run_id, plan_sha256, geçerlilik
kararı, istek sayısı ve özet sayıları), `campaign_manifest_invalid` (kopyanın özeti ve yeniden açılımı katalogla aynı
olmalı), `catalog_format`.

### Veri seti bölme ve gruplama politikası

* **Bölme birimi:** deney çalıştırması (run_id). Bir çalıştırmanın istekleri asla farklı bölümlere dağıtılmaz.
* **Gruplama anahtarı:** `group` (varsayılan `plan_id`). Aynı temel planın farklı seed'li tekrarları — ve aynı `group`
  altında toplanan benzer planlar — her zaman aynı bölümdedir.
* **Atama:** gruplar `sha256("<split_seed>:<group>")` sırasıyla, hedef orana göre en büyük açığı olan bölüme atanır
  (eşitlikte train > validation > test; ağırlık = gruptaki geçerli deney sayısı). Deterministiktir; aynı katalog ve
  parametreler → aynı bölmeler ve aynı `content_sha256`.
* **Oranlar** (`--ratios`, varsayılan 0,6/0,2/0,2, kesirli olarak tam toplanır): grup bütünlüğü yüzünden tutmazsa kayıtlar
  başka bölüme **taşınmaz**; `ratio_deviation` (sapma > 0,1) veya `empty_split` uyarısı verilir.
* **Geçersiz deneyler:** `--invalid-policy exclude` (varsayılan) tamamlanmamış veya geçersiz deneyleri dışarıda bırakır ve
  `invalid_experiments.excluded` altında durum ve nedenleriyle listeler; `fail` böyle bir deney varsa veri setini üretmez.
  Bir planın yalnızca bazı seed'leri geçersizse geçerli olanlar grubuyla birlikte kalır.
* **Hedefler ayrıdır:** sınıflandırma `planned.fault` (ölçüm istekleri), gecikme regresyonu `server.hold_ms_actual`
  (yalnızca `fixed_delay`/`random_delay`). `planned.delay_ms` ve istemci `duration_ms` hedef değildir. Bir bölümde
  bulunmayan sınıflar `missing_classes`, regresyon örneği olmayan bölüm `missing_regression_samples` olarak raporlanır;
  sayımlar yalnızca gerçekten bulunan sınıfları içerir.
* Veri seti manifesti kayıt kopyalamaz: her deney için özellik dosyaları (`features.results_csv/json`) ve etiket dosyası
  (`labels`) ayrı ayrı yol + SHA-256 ile; kaynak deney kimlikleri, katalog özeti, parametreler, hedef tanımları,
  özellik sözleşmesi, ulaşılan oranlar, bütünlük denetimleri ve uyarılar kaydedilir.

### Veri sızıntısına karşı önlemler

Bütünlük denetimleri (`integrity.checks`; "hata" düzeyindekiler başarısızsa veri seti **üretilmez**):

| Kural | Düzey | Denetim |
|---|---|---|
| `run_in_single_split`, `experiment_in_single_split` | hata | Her çalıştırma / deney tek bölümde |
| `group_in_single_split` | hata | Her grup (temel plan) tek bölümde |
| `labels_absent_from_features` | hata | Sonuç (özellik) dosyalarında etiket anahtarı yok (`planned`, `expected`, `hold_ms_actual`, `delay_ms`, …) |
| `feature_fields_are_observations` | hata | Özellik alanları yalnızca `RawResult` gözlem alanları; etiket alanlarıyla kesişmez |
| `design_in_single_split` | uyarı | Seed hariç özdeş tasarım farklı gruplar üzerinden farklı bölümlere düşmüş mü (öyleyse aynı `group` altında toplayın) |

Ayrıca: özellikler yalnızca sonuç dosyalarından, etiketler yalnızca etiket dosyalarından okunur; sunucu olay dosyaları
(uygulanan hatayı içerir) ve katalog/manifest alanları özellik kaynağı değildir; birleştirme anahtarı sonuç
`(run_id, seq)` = etiket `(run.run_id, requests[].index)`. Senaryo adı ve URL deney tasarımını yansıttığı için
özellik değil tanımlayıcıdır. `analyze` etiket dosyalarını okumaz.

### Örnek: küçük sentetik veri seti

`configs/campaign.example.json` (5 karma temel plan × 2 seed = 10 deney; her plan altı hata türünü farklı parametrelerle
içerir) bu makinede ~10 sn'de çalıştı: 10/10 deney geçerli, `campaign verify` sorunsuz.

**İstek sayıları:** planlanan ve gerçekleştirilen 220 istek = 10 ısınma (deney başına 1) + 210 ölçüm isteği (deney
başına 21). Katalogdaki `requests.planned`/`recorded`, sonuç dosyası satırları ve etiket kayıtları 220'dir (ısınma
dahil); veri setindeki `measured_requests` ve özellik tablosu satırları **ısınma hariç** sayılır (`dataset.py`
`_label_counts`: `warmup=false`), bu yüzden bölümlerin toplamı 210'dur.

`dataset build --split-seed 7` (iki kez, aynı `content_sha256`):

| Bölüm | Gruplar | Deney | Ölçüm isteği | Sınıflar (connection_drop / fixed_delay / http_error / none / random_delay / timeout) | Regresyon örneği |
|---|---|---|---|---|---|
| train | mix-a, mix-c, mix-e | 6 | 126 | 12 / 24 / 14 / 46 / 24 / 6 | 48 |
| validation | mix-b | 2 | 42 | 4 / 8 / 4 / 16 / 8 / 2 | 16 |
| test | mix-d | 2 | 42 | 4 / 8 / 4 / 16 / 8 / 2 | 16 |

Ulaşılan oran (deney sayısına göre) 0,6 / 0,2 / 0,2; altı bütünlük denetiminin tamamı geçti; uyarı yok. Bu sayılar
bölme mekanizmasını gösterir; az sayıda gruptan oluşan bir veri setinin model değerlendirmesi için yeterli olduğu
anlamına gelmez.

### Determinizm türleri (birbirinin yerine kullanılmaz)

| Tür | Garanti | Kanıt |
|---|---|---|
| Plan determinizmi | Aynı kampanya manifesti → aynı deney manifestleri, `plan_sha256` ve `campaign_plan_sha256` | İki ayrı kampanya çalıştırmasında manifestler bayt bayt aynı; etiketlerin `planned`/`expected` kısmı aynı, `observed` farklı |
| Bölme determinizmi | Aynı gruplar, aynı gruptaki geçerli deney sayıları ve aynı `split_seed` → aynı bölmeler | İki ayrı kampanyada (her ikisinde 10/10 geçerli) aynı gruplar ve deneyler aynı bölümlerde. Geçerlilik farklı olursa ağırlıklar ve bölmeler değişebilir |
| Dosya bütünlüğü | Katalog ve veri seti başvurduğu her dosyanın SHA-256 özetini tutar ve doğrular | Tek baytlık değişiklik `file_hash_mismatch` ile reddedilir |
| Veri seti içerik determinizmi | Aynı katalog + aynı parametreler → aynı `dataset` içeriği ve `content_sha256` (`sha256(canonical_json(dataset))`; `format`, `dataset_schema_version`, `generated_at` kapsam dışı) | Aynı katalogdan iki üretim aynı; farklı kampanyalarda farklıdır, çünkü içerik somut dosyaların özetlerine başvurur |

### Özellik tablosu (`dataset features`)

```
hgs2-lab dataset features --campaign-dir work/camp-mix-001 --dataset work/camp-mix-001.dataset.json \
                          --output-dir work/camp-mix-001.features
```

Çıktı dizini yoksa oluşturulur; varsa **boş** olmalıdır (çıkış 5; hiçbir dosyanın üzerine yazılmaz). Dosyalar:

| Dosya | İçerik |
|---|---|
| `features.csv` | Anahtar + tanımlayıcılar + **yalnızca istemcinin gözlediği** alanlar |
| `labels.csv` | Aynı anahtar ve aynı satır sırası + deney tasarımı metadata'sı + etiket/hedef alanları |
| `feature-manifest.json` | `dataset_id` (veri seti `content_sha256`), kampanya, bölme parametreleri, politika ve sütun rolleri, özellik olarak kullanılmaması gereken sütunlar, dahil edilen ve dışarıda bırakılan deneyler, bölüm başına sayımlar, CSV'lerin SHA-256 özetleri, biçim kuralları, `generated_at`, yazılım sürümü |

Sütunlar (`observed-v1` politikası; rol manifestte her sütun için yazılır):

| Dosya | Sütun | Rol |
|---|---|---|
| her ikisi | `split`, `run_id`, `seq` | anahtar (birleştirme; özellik değil) |
| features | `campaign_id`, `group_id`, `plan_id`, `seed`, `iteration` | tanımlayıcı (özellik değil) |
| features | `offset_ms`, `elapsed_ms`, `duration_ms`, `status_code`, `success`, `error_type`, `response_bytes` | gözlenen özellik |
| labels | `scenario`, `planned_status`, `planned_delay_ms`, `expected_outcome` | deney tasarımı metadata'sı |
| labels | `planned_fault` (sınıflandırma hedefi), `hold_ms_actual` (gecikme regresyonu hedefi) | hedef |
| labels | `label_status` | etiket güvenilirliği |

`success` = `http_ok` doğruysa `true`; HTTP hatası veya taşıma hatasında `false`. `hold_ms_actual` varsayılan özellik
dosyasında **yoktur** (gerçekleşen enjeksiyon = hedef; özellik olarak kullanılması sızıntıdır). Senaryo adı tasarımı
yansıttığı için `labels.csv`'dedir. Yeni görevler için `features.py`'deki `FEATURE_POLICIES`'e yeni bir politika eklenir.

Biçim: UTF-8 (BOM yok), LF, virgül, `csv.QUOTE_MINIMAL`, ilk satır başlık; boş hücre = null; bool `true`/`false`;
tam sayılar ondalık; ondalık sayılar Python `repr(float)` (kaynak JSON değeriyle aynı en kısa gösterim). Satırlar:
yalnızca ölçüm istekleri (ısınma sayılır ama yazılmaz); sıra = bölüm (train, validation, test) → veri setindeki deney
sırası → `seq`. Aynı girdi dosyaları ve politika → bayt bayt aynı CSV'ler ve aynı manifest `content_sha256`'sı;
`generated_at` CSV'leri ve özeti etkilemez.

Üretimden önce (herhangi biri başarısızsa hiçbir dosya yazılmaz; hata deney kimliği ve kural koduyla raporlanır):
veri seti manifestinin biçimi ve kendi `content_sha256`'sı (`dataset_manifest_tampered`); veri seti kayıtlı
parametrelerle yeniden üretilir — bu, kampanya kataloğunu ve tüm dosyaları doğrular (`file_hash_mismatch`,
`file_missing`, `campaign_manifest_invalid`, …) ve sonucun manifestle birebir aynı olmasını ister (`catalog_changed`,
`split_mismatch`, `dataset_not_reproducible`); her sonuç ve etiket dosyası bir kez okunur ve okunan baytların özeti
veri setindeki başvuruyla karşılaştırılır (`feature_source_mismatch`, `label_source_mismatch`); sonuç kayıtları etiket
kayıtlarıyla birebir eşleşmelidir (`label_join_mismatch`). Geçersiz deneyler veri seti politikasına göre zaten
dışarıdadır ve manifestte listelenir.

Örnek (yukarıdaki kampanya ve veri seti): `features.csv` ve `labels.csv` 210'ar satır (train 126, validation 42,
test 42; 10 ısınma isteği sayıldı, yazılmadı); iki ayrı üretim bayt bayt aynı.

## Baseline hazırlığı: değerlendirme kampanyası ve protokol

Bu bölüm dedektör veya model **içermez**; istatistiksel baseline yöntemlerinin ileride nasıl değerlendirileceğini ve
bunun için üretilen sentetik veriyi tanımlar. Veri gerçek HGS2 ölçümü değildir.

### Kampanya tasarımı (`configs/campaign.baseline.example.json`)

12 temel plan × 3 seed (101, 102, 103) = 36 deney; her plan kendi grubudur (seed tekrarları aynı bölümde kalır). Yalnızca
mevcut hata türleri ve `onset_after` kullanılır (hepsi `synthetic.parse_manifest` ile doğrulanır). Her anomali planı tek
rotada **önce normal bir bölümle** başlar ve bilinen bir istekte bozulur; böylece her çalıştırma bilinen bir değişim
noktası taşır. `onset_after` ısınma isteklerini de sayar (3 ısınma + `onset_after: 23` = ilk 20 ölçüm normal).

| Plan | Davranış | İlk anormal `seq` |
|---|---|---|
| `normal-steady`, `normal-paced` | Yalnızca normal (yanlış alarm referansı; ikincisinde 5 ms istek aralığı) | — |
| `fixed-small`, `fixed-large` | 20 normal ölçümden sonra sabit 5 / 40 ms gecikme | 24 |
| `random-narrow`, `random-wide` | 20 normal ölçümden sonra 2–10 / 10–80 ms rastgele gecikme | 24 |
| `http500-late`, `http503-mid` | 25 / 20 normal ölçümden sonra HTTP 500 / 503 | 29 / 24 |
| `drop-late`, `timeout-late` | 37 / 38 normal ölçümden sonra 3 bağlantı kopması / 2 zaman aşımı | 41 / 42 |
| `mixed-latency-error` | Rastgele 5–30 ms gecikme bölümü, ardından HTTP 502 bölümü | 14 |
| `mixed-delay-timeout` | Sabit 15 ms gecikme bölümü, ardından tek zaman aşımı | 14 |

Çalıştırma öncesi hesap: 1488 planlanan istek (108 ısınma + 1380 ölçüm), enjekte bekleme alt sınırı ~10 sn; güvenlik
sınırı tahmini (`guard_forecast`) hiçbir deneyde tetiklenme öngörmedi.

### Gerçek çalıştırma (bu makine, geçici dizin)

`campaign run` ~22 sn (deney başına 0,22–1,31 sn, medyan 0,44): 36/36 deney tamamlandı ve geçerli, 1488/1488 etiket
`confirmed`, `campaign verify` sorunsuz (180 dosya kaydının tamamı SHA-256 ile eşleşti). Sayımlar kaynaklar arası
tutarlı: katalog `planned` = `recorded` = sonuç satırı = etiket kaydı = 1488; ısınma 108; ölçüm 1380 = veri seti
`measured_requests` = `features.csv` = `labels.csv` satırı. Ölçüm etiket dağılımı: `none` 942, `fixed_delay` 150,
`random_delay` 150, `http_error` 120, `connection_drop` 9, `timeout` 9.

`dataset build --split-seed 20261024`:

| Bölüm | Gruplar | Deney | Ölçüm | Sınıflar |
|---|---|---|---|---|
| train | 7: normal-steady, random-wide, http500-late, http503-mid, drop-late, timeout-late, mixed-latency-error | 21 | 810 | none 585, random_delay 90, http_error 120, connection_drop 9, timeout 6 |
| validation | 3: fixed-small, fixed-large, mixed-delay-timeout | 9 | 330 | none 177, fixed_delay 150, timeout 3 |
| test | 2: normal-paced, random-narrow | 6 | 240 | none 180, random_delay 60 |

Oran (deney sayısına göre) 0,583 / 0,250 / 0,167 — sapma tolerans (0,1) içinde, çünkü 36 deney 3'erli 12 gruptan oluşur
ve gruplar bölünmez. Grup ve çalıştırma kesişimi yok; geçersiz deney yok; altı bütünlük denetimi geçti.

**Yeterlilik değerlendirmesi — yetersiz:** `missing_classes` uyarıları: train'de `fixed_delay` yok; validation'da
`connection_drop`, `http_error`, `random_delay` yok; test'te yalnızca `none` ve `random_delay` var. Her hata ailesi
yalnızca bir veya iki bölümde. Bu yapısaldır: 12 grup ve 0,6/0,2/0,2 ile test her bölme seed'inde 2 grup alır; grup başına
en çok 2 aile olduğundan test, denenen 1000 bölme seed'inin hiçbirinde 5 anomali ailesinin tamamını içermedi (birim testi
aynı sonucu 50 seed için sınar). Ayrıca `connection_drop` ve `timeout` toplam 9'ar ölçüm isteğidir. Bu kampanya mekanizmayı ve
protokolü doğrular; senaryo bazında güvenilir performans tahmini için **yetersizdir**. Gruplama politikası
değiştirilmedi. Öneri: aile başına en az 5 grup (ör. 3 train / 1 validation / 1 test) ya da açıkça tanımlanacak ayrı bir
"katmanlı grup ataması" politikası; nadir sınıflar için daha fazla tekrar.

### Alanların anlamı (koddan doğrulandı)

| Alan | Anlam | Kullanım |
|---|---|---|
| `duration_ms` | `http_transport.py` `send`: `session.request` çağrısından hemen önce → yanıt gövdesinin tamamı okunduktan hemen sonra. Yanıt yoksa boş | Birincil gecikme gözlemi |
| `elapsed_ms` | `runner.py` `_run_once`: `transport.send` çağrısı öncesi → dönüş/istisna. `duration_ms`'e ek olarak hedef denetimi (ad çözümleme dahil) ve istek hazırlığını içerir; taşıma hatasında da doludur (zaman aşımı ≈ 300 ms). Ölçülen fark (yanıtlı 1362 istek): 0,054–0,413 ms, medyan 0,108 ms, negatif yok | Taşıma hatalarında tek süre bilgisi; gecikme dedektörü için ikincil |
| `offset_ms` | İsteğin başlangıcı, çalıştırmanın monotonik başlangıcına göre | **Yalnızca sıralama/zaman ekseni** (aşağıdaki sızıntı bulgusu) |
| `status_code` | HTTP durum kodu; yanıt yoksa boş | Gözlem |
| `success` | `http_ok=true` ise `true`; HTTP hatası (5xx) veya taşıma hatasında `false` | Gözlem; HTTP/taşıma hataları istemcide doğrudan görülür |
| `error_type` | `timeout` / `connection_error` / `transport_error`; HTTP hatasında boş | Gözlem |
| `planned_fault` | Bu isteğe uygulanan planlı hata (onset öncesi `none`) | Etiket (sınıflandırma hedefi); özellik değil |
| `expected_outcome` | Plandan türetilen beklenen kategori (`success`/`http_error`/`transport_error`) | Tasarım metadata'sı; özellik değil |
| `hold_ms_actual` | Sunucuda gerçekleşen bekleme | Gecikme regresyonu hedefi; özellik değil |

Gecikmeli isteklerde istemci süresi gerçekleşen beklemeden büyüktür (fixed_delay: `duration_ms` medyan 17,96 ms,
`hold_ms_actual` medyan 15,49 ms; tüm satırlarda `duration_ms ≥ hold_ms_actual`). Train normal `duration_ms` medyan
1,146 ms, MAD 0,260 ms (betimleyici, kalibrasyon değil). Rastgele gecikmelerde seed etkisi belirgindir (random-wide anormal
bölüm medyanı seed'e göre 42,7 / 48,7 / 59,5 ms); sabit gecikmelerde küçüktür (fixed-large 43,2–43,3 ms).

### Veri sızıntısı kontrolleri

Uygulanan ve testle sınanan kurallar: etiket/tasarım sütunları (`hold_ms_actual`, `planned_fault`, `expected_outcome`,
`scenario`, …) yalnızca `labels.csv`'de; sonuç dosyalarında etiket anahtarı yok (`labels_absent_from_features`); sunucu
olay dosyaları özellik kaynağı değil; bir çalıştırma ve bir grup tek bölümde; aynı planın seed tekrarları aynı grupta.

**Yeni bulgu — konum sızıntısı:** değişim noktalı tasarımda anomaliler çalıştırmanın sonundadır; ölçüm kullanmayan
`seq >= 24` kuralı tek başına precision 0,57 / recall 0,86 verir (`seq >= 14`: recall 1,00). `seq`, `iteration` anahtar /
tanımlayıcıdır, ancak `offset_ms` F3-D'nin `observed-v1` politikasında "gözlenen özellik" olarak işaretlidir. Şema bu
aşamada değiştirilmedi; protokol konum alanlarını (`seq`, `iteration`, `offset_ms`) dedektör girdisi olarak **yasaklar**
ve yalnızca sıralama/gecikme hesabı için kullanır. Öneri: `offset_ms`'i "sıralama" rolüne alan yeni bir politika sürümü.

### Değerlendirme protokolü (F5'te yalnızca Robust Z-score uygulandı)

**Etiketler** plandan türetilebilir: istek düzeyinde anormal = `planned_fault ≠ none` (yalnızca `label_status =
confirmed`, ısınma hariç). **Gecikme anomalisi epizodu:** aynı çalıştırmada aynı senaryoya ait, `seq` sırasıyla ardışık
ve planda `fixed_delay`/`random_delay` taşıyan ölçüm istekleri. Başlangıcı ilk böyle istektir. Senaryonun gecikme
anomalisi dizisi bitince, yani senaryoda gecikme olmayan ilk istekte veya senaryo sonunda, epizot da biter. HTTP
hatası, bağlantı kopması ve timeout planlı istekler gecikme epizoduna girmez ve onu bitirir (bkz. F5). Bu tasarımda
her gecikme senaryosunda tam bir epizot vardır. Belirsiz olan tek nokta "anomalinin
büyüklüğü"dür: 5 ms'lik planlı gecikme de anormal sayılır; tespit edilebilirlik planlı büyüklüğe göre raporlanmalıdır.

**Görev ayrımı:** HTTP ve taşıma hataları istemcide doğrudan gözlenir (`success=false`, `error_type`); bunları "tespit
etmek" totolojidir ve dedektör başarısına katılmaz, ayrı sayılır. Baseline yöntemleri **gecikme anomalisi** görevinde
değerlendirilir: seri (skorlanan girdi) = bir çalıştırmanın `success=true` ölçüm istekleri, `seq` sırasıyla. Epizot
sınırları ise plana göre tüm ölçüm istekleri üzerinden belirlenir; başarısız gecikme planlı istekler epizotta kalır
ama skorlanmaz. Girdi yalnızca `log(duration_ms)`; pozitif sınıf `planned_fault ∈ {fixed_delay, random_delay}`.
Her çalıştırmada durum sıfırlanır.

**Dedektör girdi politikası (ilk dedektör; bağlayıcı):**

* **İzinli tek tahmin girdisi:** `duration_ms`; uygulanan ilk ve tek dönüşüm `log(duration_ms)`.
* **Tahmin girdisi olarak yasak:** `seq`, `iteration`, `offset_ms` (konum sızıntısı, yukarıda); `planned_fault`,
  `expected_outcome`, `hold_ms_actual`, `label_status` ve `labels.csv`'deki diğer tüm etiket/tasarım sütunları
  (`scenario`, `planned_status`, `planned_delay_ms`); tanımlayıcılar (`run_id`, `campaign_id`, `group_id`, `plan_id`,
  `seed`, `split`); sunucu olay dosyaları; F4 telemetrisi.
* `seq`, `iteration` ve `offset_ms` yalnızca **sıralama, hizalama ve değerlendirme** (seri sırası, epizot başlangıcı,
  tespit gecikmesi) için kullanılabilir. `planned_fault` yalnızca değerlendirme etiketidir ve kalibrasyonda normal
  satırların seçimi için kullanılır.
* `observed-v1` politikası bilinçli olarak değiştirilmedi; `feature-manifest.json` `offset_ms`'i hâlâ
  `observed_feature` olarak işaretler ve `not_for_features` listesine almaz. Bu protokol o role göre önceliklidir:
  dedektör kodu sütunu manifest rolünden değil yukarıdaki listeden seçmelidir. `elapsed_ms`, `status_code`, `success`,
  `error_type`, `response_bytes` gözlem olsa da ilk dedektörün girdisi değildir (`success` yalnızca seriyi
  `success=true` isteklere süzmek için kullanılır).

**Veri kullanımı:** kalibrasyon (referans dağılım) yalnızca train bölümündeki normal satırlardan (`planned_fault = none`);
parametre seçimi yalnızca validation'da, önceden ilan edilen ızgaralardan; test bir kez, en sonda. Test hiçbir aşamada
kalibrasyona girmez.

| Yöntem | Tanım | Sabitler / seçim |
|---|---|---|
| Robust Z-score | `z = 0.6745·(x − medyan)/MAD`, x = log(duration_ms); medyan ve MAD train normal satırlarından | Eşik `z > 3,5` (tek yönlü, önceden sabit); MAD = 0 ise `degenerate_baseline`: skor ve alarm üretilmez (sessiz geri dönüş yok; bkz. F5) |
| EWMA | `E_t = λ·x_t + (1−λ)·E_{t−1}`, `E_0` = train normal medyanı; `UCL = μ0 + L·σ·sqrt(λ/(2−λ))`, σ = 1,4826·MAD | λ ∈ {0,1; 0,2; 0,3}, L = 3; λ validation'da "yanlış alarm oranı ≤ %1 koşuluyla en yüksek recall" ile seçilir |
| CUSUM | `S_t = max(0, S_{t−1} + z_t − k)`, z_t standartlaştırılmış log-gecikme (train normal medyan/σ) | k = 0,5; h ∈ {4, 5, 8}, validation'da aynı ölçütle; ilk alarm epizot için sayılır |

**Ölçütler (her yöntem için):** istek düzeyinde precision, recall, false-positive rate (normal satırlarda alarm /
normal satır); epizot düzeyinde tespit oranı; **istek cinsinden tespit gecikmesi** = ilk alarmın `seq`'i − epizot
başlangıç `seq`'i. Wall-clock tespit gecikmesi için alarm üretim zamanı gerekir; bu zaman kaydedilmez, bu yüzden
hesaplanmaz (bkz. F5). Epizot dışındaki alarmlar yanlış alarmdır. Ayrıca yalnızca normal gruplarda
çalıştırma başına yanlış alarm sayısı; plan ve hata ailesi bazında ayrı tablolar; seed'ler arası değişkenlik (plan
başına 3 seed için aralık); belirsizlik için grup düzeyinde (bağımsız birim) bootstrap. Bir bölümde bulunmayan aileler
için sonuç "değerlendirilemedi" olarak raporlanır, sıfır olarak değil.

### F3-E kapanış kontrolü (2026-10-24)

**Karar: sınırlamalarla tamamlandı.** Yeni veri üretilmedi; mevcut kampanya, veri seti ve özellik dosyaları salt okunur
denetlendi (denetim öncesi ve sonrası 254 dosyanın SHA-256 özetleri aynı).

* **Bütünlük:** kampanya manifesti `configs/campaign.baseline.example.json` ile bayt bayt aynı; `campaign verify` 0 sorun,
  180 dosya kaydının özeti tutuyor; sayımlar planlanan = kaydedilen = sonuç satırı = etiket kaydı = `confirmed` = 1488
  (108 ısınma + 1380 ölçüm). Veri seti kayıtlı parametrelerle bellekte birebir yeniden üretildi; `features.csv` ve
  `labels.csv` bellekte yeniden üretilenle bayt bayt aynı (1380 satır, ısınma satırı yok); özetler F3-E raporundakilerle
  aynı (`campaign.json` `1c5f59c2…cda6a`, veri seti `41b2f0b9…4964f`, `features.csv` `4b923e5b…391f2`, `labels.csv`
  `04d77dd0…7c38`). 12 grup ve 36 çalıştırmanın her biri tek bölümde; seed tekrarları ve özdeş tasarımlar bölümler arasında
  paylaşılmıyor.
* **Sınıf kapsamı (açık kısıt):** test bölümünde yalnızca `none` 180 ve `random_delay` 60 ölçüm (tek grup:
  `random-narrow`) var. `fixed_delay` yalnızca validation'da, `http_error` ve `connection_drop` yalnızca train'de.
  Nadir aileler toplamda `connection_drop` 9 (train, tek grup) ve `timeout` 9 (train 6 + validation 3). Gecikme görevi
  için pozitif / normal ölçüm: train 90 / 585, validation 150 / 177, test 60 / 180. Test sonucu yalnızca `random_delay`
  (2–10 ms) için anlamlıdır; diğer aileler için "değerlendirilemedi" raporlanmalıdır.
* **Tekrarlanamayan entegrasyon hatası (açık kısıt):** F3-E sırasında entegrasyon paketinin bir çalıştırması
  `1 failed, 88 passed, 700 deselected` verdi. Çıktı yalnızca özet satırına kısaltıldığı için test adı, traceback ve hata
  türü **kaydedilmedi ve geri kazanılamaz**. Sonrasında 27 tam entegrasyon turu (89/89), şüpheli 8 zamanlama/eşzamanlılık
  testinin 40 turu ve 2026-10-24 kapanış turu (`pytest -m integration -rfE --tb=long`: 90/90, F4 testi dahil) başarılı.
  Hata çözülmüş sayılmaz; kararsız bir test olabilir. Bundan sonra entegrasyon çalıştırmaları `-rfE` ile ve tam çıktı
  saklanarak yapılmalıdır.

## Sistem telemetrisi (F4)

Amaç: ileride gecikme anomalilerini sistem kaynaklarıyla ilişkilendirebilmek için çalıştırma sırasında **zaman damgalı**
CPU, bellek, disk ve ağ (TCP) sayaçlarını toplamak. Bu aşamada telemetri **yalnızca toplanır**: `analyze`, `dataset`,
`dataset features` ve (henüz olmayan) anomali dedektörü onu okumaz; `observed-v1` politikası değişmedi. Yeni bağımlılık
yoktur (Windows sayaçları standart kütüphanedeki `ctypes` ile salt okunur; yönetici yetkisi gerekmez).

```
hgs2-lab synthetic run --manifest configs/synthetic.example.json --results-dir results --run-id syn-demo-2 --telemetry
hgs2-lab run --config configs/config.json --telemetry --telemetry-interval-ms 500
```

`--telemetry` verilmezse davranış ve tüm dosyalar öncekiyle aynıdır (telemetri dizini bile oluşmaz). Aralık 100–60 000
ms (varsayılan 250); geçersiz değer veya `--telemetry` olmadan `--telemetry-interval-ms` kullanım hatasıdır (çıkış 2).
`campaign run` telemetri toplamaz.

### Toplanan metrikler ve kapsam

`system` = makine geneli (deneyle ilgisiz tüm süreçler dahil); `process` = yalnızca bu Python süreci: istemci,
`synthetic run`'da **aynı süreçteki sentetik sunucu** ve örnekleyici iş parçacığı birlikte.

| Grup | Kapsam | Kaynak (Windows) | Alanlar | Not |
|---|---|---|---|---|
| `cpu_system` | system | `GetSystemTimes` | `idle_s`, `kernel_s`, `user_s` (sayaç, s) | Tüm mantıksal CPU'ların toplamı; `kernel_s` boşta süreyi **içerir** |
| `cpu_process` | process | `os.times` + `QueryProcessCycleTime` | `user_s`, `system_s` (s), `cycles` (sayaç) | `cycles` gerçek işlemci çevrimi; süreye çevrilmez |
| `memory_system` | system | `GlobalMemoryStatusEx` | `memory_load_percent`, `total_phys_bytes`, `avail_phys_bytes`, `commit_limit_bytes`, `commit_avail_bytes` (anlık) | |
| `memory_process` | process | `K32GetProcessMemoryInfo` | `working_set_bytes`, `peak_working_set_bytes`, `private_bytes` (anlık), `page_faults` (sayaç) | |
| `disk_system` | system | `IOCTL_DISK_PERFORMANCE` (`\\.\PhysicalDriveN`) | `drives`, `read/write_bytes`, `read/write_count`, `read/write/idle_time_s` (sayaç), `queue_depth` (anlık) | Başlangıçta bulunan fiziksel disklerin toplamı; bir disk okunamazsa grup null (kısmi toplam yok) |
| `io_process` | process | `GetProcessIoCounters` | `read/write/other_ops`, `read/write/other_bytes` (sayaç) | Dosya, aygıt **ve soket** G/Ç'si (loopback HTTP trafiği `other_*`'da görünür); disk G/Ç'si değildir |
| `net_tcp_system` | system | `GetTcpStatisticsEx2` (IPv4 + IPv6) | `active/passive_opens`, `attempt_fails`, `estab_resets`, `in/out_segs`, `retrans_segs`, `in_errs`, `out_rsts` (sayaç), `curr_estab`, `num_conns` (anlık) | **Loopback dahil**; segment sayısı, bayt değil |

Sayaçların mutlak değeri anlamsızdır; yalnızca aynı dosyadaki örnekler arası farklar anlamlıdır. Her örnekte önceki
örnekten türetilen `derived`: `interval_ms`, `system_cpu_busy_ratio` = (Δkernel + Δuser − Δidle) / (Δkernel + Δuser) ve
`process_cpu_ratio` = (Δuser + Δsystem) / (aralık × mantıksal CPU sayısı); gerekli değer yoksa `null`.

**Değerlendirilip alınmayan:** ağ arabirimi bayt sayaçları (`GetIfTable2`/`GetIfEntry2`). Bu makinede 52 MB'lık bir
loopback aktarımı loopback arabiriminin sayaçlarını hiç değiştirmedi (Windows loopback trafiği arabirim sayaçlarına
yansımaz) ve okuma örnek başına 0,7 ms (`GetIfEntry2`, 2 donanım arabirimi) ile 5,5 ms (`GetIfTable2`, 57 satır) sürdü.
Buna karşılık 20 loopback bağlantısı `GetTcpStatisticsEx2`'de `active_opens` +20 ve ~640 segment olarak göründü
(okuma ~4 µs). Bu yüzden ağ için TCP istatistikleri seçildi.

### Ölçüm sıklığı ve zaman damgaları

* `start()` (ilk istekten hemen önce) ve `stop()` (son istekten sonra) anlarında birer örnek; arada arka plan iş
  parçacığı `başlangıç + k × aralık` son tarihlerinde örnek alır (kayma birikmez). Geç kalınan aralıklar telafi
  edilmez, `missed_slots` olarak sayılır. `threading.Event.wait` erken dönerse son tarihe kadar yeniden beklenir: örnek
  planlanan andan önce alınmaz. En çok 20 000 örnek; fazlası `dropped_samples` (bitiş örneği korunur).
* Her örnek: `monotonic_ns` (`time.perf_counter_ns`, saat çapasıyla aynı saat; grupların okunmasından hemen önce),
  `offset_ms` (sonuç metadata'sındaki `clock.monotonic_ns`'e göre; ilk istekten önceki örnekte negatif; çapa yoksa veya
  başka bir saatse `null`), `wall_time_ns`/`wall_time_utc`, `collect_ns` (tüm grupların okunma süresi), `lag_ns`
  (planlanan son tarihe göre gecikme; yalnızca periyodik örneklerde), `values` ve `errors`.
* Böylece bir isteğin `offset_ms` değeri telemetri örnekleriyle aynı eksene yerleşir. Bu hizalama yalnızca aynı süreç
  için geçerlidir (bkz. "Saat çapası").
* **Hata politikası:** okunamayan grup için değer uydurulmaz; değer `null`, hata metni `errors`'ta, sayısı
  `summary.probe_errors`'ta. Platformda olmayan grup `metrics.<grup>.available = false` ve `reason` ile işaretlenir ve
  yeniden denenmez. Hiçbir telemetri hatası çalıştırmayı durdurmaz veya çıkış kodunu değiştirmez.

### Telemetri dosyası

* `<sonuç dizini>/telemetry/<run_id>.telemetry.json`; kısmi çalıştırmada `<run_id>.partial.telemetry.json`.
  Sonuçlardan **sonra** yazılır ve `result_files` ile sonuç dosyalarının adını ve SHA-256 özetini taşır.
* Üzerine yazılmaz: dosya varsa `--telemetry` ile çalıştırma ön kontrolde reddedilir (çıkış 3, istek yok). Dosya
  yazılamazsa sonuçlar korunur ve stderr'e uyarı yazılır.
* `format: "hgs2-lab-telemetry"`, `telemetry_schema_version: 1` (alan eklemek sürüm değiştirmez). Ayrıca `metrics`
  (grup başına kapsam, kaynak, alan birimi/türü, kullanılabilirlik), `sampling`, `clock`, `process_model`,
  `derived_fields`, `caveats` ve `summary` (örnek sayısı, toplama maliyeti min/medyan/en çok/toplam, gecikme, atlanan ve
  düşürülen örnekler, örnekleyici iş parçacığının CPU süresi, temiz kapanış).
* **Şema uyumluluğu:** sonuç dosyaları (şema v2) değişmez; metadata'ya yeni anahtar eklenmedi. Telemetrili ve
  telemetrisiz çalıştırmanın CSV/JSON dosyaları bayt bayt aynıdır (birim testi). `reader`/`analyze`, etiket dosyaları ve
  kampanya kataloğu telemetri dizinini okumaz.

### Ölçüm maliyeti (bu makine: Windows 11, Python 3.15.0, 64 bit)

| Ölçüm | Değer |
|---|---|
| Grup başına okuma | `GetSystemTimes` ~8–27 µs, `GlobalMemoryStatusEx` ~2 µs, `K32GetProcessMemoryInfo` ~3 µs, `GetProcessIoCounters` ~3 µs, disk başına `DeviceIoControl` ~10 µs, `GetTcpStatisticsEx2` ~4 µs/aile, `os.times` < 1 µs |
| Tam örnek (`collect_ns`), boşta | medyan ~0,4–0,6 ms |
| `synthetic run` (örnek manifest, 55 istek, ~2,2 sn) | 250 ms: 10 örnek, toplama medyan 0,58 / en çok 0,68 ms, gecikme medyanı 8,3 ms, dosya 31 KB; 100 ms: 24 örnek, 0,48 / 0,77 ms, 59 KB |
| Ana iş parçacığı CPU-yoğunken | GIL'i bırakan çağrılarla (`WinDLL`) toplama medyanı ~46 ms (her çağrı dönüşü GIL'i bekler); GIL bırakılmadan (`PyDLL`, 64 bit) ~0,33 ms. Gecikme (`lag`) yine ~20–25 ms |

Bu yüzden 64 bit'te sayaçlar GIL bırakılmadan okunur (çağrılar mikrosaniyelik ve bloklamaz). Bir örnek <1 ms boyunca
diğer iş parçacıklarını bekletir; `[monotonic_ns, monotonic_ns + collect_ns]` aralığına denk gelen istekler bu kadar
etkilenebilir. Telemetrinin istemci sürelerine etkisi sistematik olarak ölçülmedi.

### Platform kısıtlamaları ve bilinen sınırlamalar

* Yalnızca Windows'ta (64 bit, Python 3.15.0) çalıştırıldı ve sınandı. Diğer platformlarda yalnızca `cpu_process`
  (`os.times`) toplanır; diğer gruplar "desteklenmeyen platform" nedeniyle `available: false` olur (Linux `/proc`
  okuyucuları uygulanmadı). 32 bit Windows yolu (`WinDLL`) sınanmadı.
* Örnekleyici istemciyle (ve sentetik sunucuyla) aynı süreçte ve aynı GIL'dedir. `process` metrikleri istemci + sunucu +
  örnekleyicinin toplamıdır; sunucu servis süresi veya sunucunun kaynak kullanımı olarak **yorumlanmamalıdır**.
* CPU sayaçları saat adımıyla (~15,6 ms) güncellenir: kısa aralıklarda oranlar kabadır (oranlar için ≥ 250 ms önerilir).
  `cpu_process` süreleri de bu çözünürlüktedir; örnekleyici iş parçacığının CPU süresi çoğu zaman 0 görünür.
* `lag_ns`: `Event.wait` Windows'ta zamanlayıcı adımıyla uyanır; ölçülen medyan ~5–8 ms, CPU-yoğun bir iş parçacığı
  varken ~20–25 ms. Değer her örnekte kaydedilir.
* `net_tcp_system` makine genelidir (diğer süreçlerin bağlantıları dahil), IPv4 ve IPv6 toplanır, bayt değil segment
  sayar; `in_segs`/`out_segs` dışındaki sayaçlar 32 bittir ve taşabilir. Arabirim bayt sayaçları toplanmaz.
* `disk_system` yalnızca başlangıçta bulunan fiziksel diskleri (en çok 16) izler; disk performans sayaçları kapalıysa
  grup `available: false` olur.
* Sentetik deneyde `process` ve `net_tcp_system` değerleri enjekte edilen hatayı yansıtabilir (ör. `connection_drop`
  yeni TCP bağlantısı açtırır); bağımsız bir sinyal değildir. İleride özellik olarak kullanılmadan önce sızıntı
  açısından ayrıca değerlendirilmelidir.
* Örnekler bellekte tutulur ve çalıştırma sonunda yazılır; süreç zorla sonlandırılırsa telemetri kaybolur.

## Robust Z-score gecikme dedektörü (F5)

**Amaç:** ilk istatistiksel **gecikme anomalisi** dedektörü; yukarıdaki "Değerlendirme protokolü"nü uygular. EWMA ve
CUSUM uygulanmadı. Veri sentetiktir; sonuçlar ölçüm ve değerlendirme hattını sınar, HGS2 hakkında bilgi vermez.

```
hgs2-lab detect robust-z --features-dir work/camp-baseline-001.features --output work/robust-z.evaluation.json
```

Girdi `dataset features` çıktı dizinidir ve yalnızca okunur: manifestin kendi özeti, `features.csv`/`labels.csv`
SHA-256 özetleri, politika tanımı, başlıklar, satır anahtarları ve "bir çalıştırma tek bölümde" kuralı doğrulanır.
Çıktı tek JSON dosyasıdır ve üzerine yazılmaz. Çıkış kodları: 0 yazıldı (dejenere baseline'da da; stderr uyarısı),
1 tablo doğrulama/kalibrasyon hatası, 5 çıktı var veya yazılamadı. Komutun parametresi yoktur: eşik ve sabitler
değerlendirmeden önce sabittir, sonuçlara göre ayarlanamaz.

### Algoritma

| Adım | Tanım |
|---|---|
| Girdi | Yalnızca `duration_ms` (`robust_z.INPUT_FIELDS`, açık izin listesi) |
| Dönüşüm | `x = ln(duration_ms)`; `duration_ms` pozitif ve sonlu olmalı |
| Kalibrasyon | `median = median(x)`, `MAD = median(|x − median|)` |
| Skor | `z = 0,6745 · (x − median) / MAD` |
| Karar | `alarm = z > 3,5`; yalnızca üst kuyruk, düşük gecikme anomali değildir |
| Geçersiz değer | null, sayı olmayan, NaN, ±inf, ≤ 0. Kalibrasyon kümesinde varsa **hata** (sessizce dışlanmaz). Skorlamada `status = invalid_input`: normal sayılmaz, metriklere girmez, ayrıca sayılır |
| MAD = 0 | Sıfıra bölünmez, MAD uydurulmaz: `baseline.status = degenerate_baseline`, hiçbir satır skorlanmaz (`z = alarm = null`, `status = degenerate_baseline`), tüm oranlar null; uyarı yazılır |

Çıktıda ayrıca eşiğin süre karşılığı (`alarm_threshold_duration_ms` = `exp(median + 3,5·MAD/0,6745)`) bulunur.
Bu değer yalnızca yorum içindir; karar `z` ile verilir.

### Dedektör girdi politikası ve kalibrasyon verisi

* `robust_z.py` tablo, etiket veya sıra görmez; yalnızca sayı listesi alır. Satırdan girdiye geçiş tek noktadadır
  (`detection.detector_input`) ve yalnızca `duration_ms` döner. Manifestteki sütun rolleri (ör. `offset_ms` =
  `observed_feature`) girdi seçiminde **kullanılmaz**.
* **Kalibrasyon:** yalnızca `split = train`, `planned_fault = none`, `label_status = confirmed`, `success = true`
  satırları. Isınma satırları özellik tablosunda yoktur. Validation ve test hiçbir parametreye girmez.
* `seq`, `offset_ms`, `run_id`, `scenario`, `plan_id` ve etiketler yalnızca satır seçimi, epizot sınırları ve
  değerlendirme için kullanılır. Testler, `iteration`/`offset_ms`/tasarım alanları ve değerlendirme etiketleri
  değiştirildiğinde skorların birebir aynı kaldığını sınar.
* İki değerlendirme kapsamı birbirinden ayrıdır:
  1. **Gecikme anomalisi tespiti:** `label_status = confirmed`, `success = true`, geçerli `duration_ms` ve
     `planned_fault ∈ {none, fixed_delay, random_delay}` olan satırlar. Pozitif sınıf `fixed_delay` veya `random_delay`.
     Dedektörün başarısı yalnızca bu satırlarla ölçülür.
  2. **Operasyonel hata sayımı (`operational_failures`):** `success = false` olan tüm satırlar (HTTP hatası, bağlantı
     hatası, timeout). Planlanan hataya (`by_planned_fault`) ve gözlenen sonuca (`by_observed_outcome`: `error_type`
     veya `http_<durum>`) göre sayılır. Bu satırlar dedektöre verilmez, normal sınıfa eklenmez ve hiçbir gecikme
     metriğine girmez. Gecikme planlı olup başarısız olan istekler `latency_planned_rows_failed` ile ayrıca sayılır.
     Bu istekler epizot sınırlarında yer alır (plan) ama skorlanmaz (`unsuccessful_rows`).
* **Recall paydası** (TP + FN): yalnızca skorlanan, yani başarılı ve geçerli `duration_ms`'li gecikme planlı satırlar.
  Başarısız gecikme planlı satırlar bu paydaya girmez; `latency_planned_rows_failed` her raporda bu yüzden kontrol
  edilmelidir. Gecikme planlı isteklerin çoğu zaman aşımına uğrarsa recall olduğundan iyi görünebilir.

### Değerlendirme metrikleri (bölüm başına; tanımlar çıktıda `metric_definitions`)

| Metrik | Tanım ve payda |
|---|---|
| precision | TP / (TP + FP); alarm yoksa null (`no_alarms`) |
| recall | TP / (TP + FN); pozitif satır yoksa null (`no_positive_rows`) |
| FPR | FP / (FP + TN): skorlanan normal satırlarda alarm oranı; normal satır yoksa null |
| Normal yanlış alarm | FP sayısı ve oranı; ayrıca tüm satırları `none` olan çalıştırmalarda çalıştırma başına yanlış alarm |
| Epizot tespit oranı | Tespit edilen / değerlendirilebilir gecikme epizodu (tanım: protokol). Bir epizot en çok bir kez sayılır; esas alınan, epizot içindeki skorlanan satırlardaki **ilk** alarmdır. Tespit edilmeyen epizotlar paydada kalır. Hiç skorlanan satırı olmayan epizot (ör. tüm istekleri başarısız) gecikme dedektörüyle değerlendirilemez; paydaya girmez ve `episodes − evaluable` farkı olarak görünür. Epizot dışındaki alarmlar yanlış alarmdır |
| Request Detection Delay (`request_detection_delay`) | İlk alarmı üreten isteğin `seq`'i − epizot başlangıç isteğinin `seq`'i; istek sayısıdır. 0, alarmın epizodun ilk isteğine ait olduğunu gösterir; 0 ms demek **değildir** |
| Wall-clock Detection Delay (`wall_clock_detection_delay_ms`) | Epizot başlangıcından alarmın gerçekten üretildiği ana kadar geçen süre. **Hesaplanmaz:** `value = null`, `status = not_available` |
| `start_to_alarm_request_offset_ms` | Alarmı üreten istek ile epizot başlangıç isteğinin `offset_ms` farkı, yani iki isteğin **başlangıçları** arasındaki süre. Alarm gecikmesi değildir: alarmı üreten isteğin kendi süresini ve skorlama zamanını içermez |

**Neden wall-clock gecikmesi yok:** kayıtlı zamanlar istek başlangıcı (`offset_ms`, `started_at`), `elapsed_ms` ve
`duration_ms`'tir. Dedektör kayıtlı veriyi çalıştırma bittikten sonra, çevrimdışı skorlar; alarmın üretildiği an
hiçbir yerde kaydedilmez. İsteğin bitişi (`offset_ms + elapsed_ms`) yalnızca alarmın en erken üretilebileceği anı
verir; gerçek alarm zamanı değildir ve bu değer de metrik olarak hesaplanmaz. Wall-clock gecikmesi için ileride şu
gereklidir: çalıştırma sırasında skorlama yapılması ve alarm anının, epizot başlangıcıyla aynı monotonik zaman
tabanında (saat çapası) kaydedilmesi. Bu altyapı uygulanmadı.

Her oran `{value, numerator, denominator, status}` biçimindedir; sıfır paydada `value = null`. Ayrıca aile ve plan
bazında kırılımlar, temsil edilmeyen aileler (`coverage`) ve satır bazında tahminler (`predictions`: anahtar, `x`,
`z`, `alarm`, durum; etiket içermez) yazılır. Kaynak izlenebilirliği: özellik manifestinin `content_sha256`'sı,
CSV özetleri, `dataset_id`, kampanya ve bölme parametreleri. Aynı girdi → aynı `content_sha256`.

### F3-E veri setinde sonuç (2026-10-24; tek çalıştırma, salt okunur girdi)

Kalibrasyon: train'in 21 çalıştırmasından 585 normal satır; medyan 1,146 ms, MAD(ln) 0,2429, eşik karşılığı
≈ 4,04 ms. Bölümler F3-E'deki gibidir; yeniden üretilmedi.

| Bölüm | Skorlanan | TP / FP / TN / FN | Precision | Recall | FPR | Epizot | Request Detection Delay |
|---|---|---|---|---|---|---|---|
| train (örneklem içi) | 675 | 90 / 0 / 585 / 0 | 1,000 | 1,000 | 0,000 | 6/6 | hepsi 0 |
| validation | 327 | 150 / 0 / 177 / 0 | 1,000 | 1,000 | 0,000 | 9/9 | hepsi 0 |
| test | 240 | 59 / 0 / 180 / 1 | 1,000 | 0,983 | 0,000 | 3/3 | 0, 0, 1 istek |

* Wall-clock tespit gecikmesi her bölümde `not_available`. Testte 1 isteklik gecikmeli epizotta
  `start_to_alarm_request_offset_ms` 4,0 ms'dir; bu, iki isteğin başlangıçları arasındaki süredir, alarm gecikmesi
  değildir.
* Operasyonel hatalar (gecikme metriklerine dahil değil):
  * train 135: planlanan `http_error` 120, `connection_drop` 9, `timeout` 6. Gözlenen HTTP 500/502/503 sırasıyla
    45/15/60, `connection_error` 9, `timeout` 6.
  * validation 3 (`timeout`), test 0.
  * Gecikme planlı ama başarısız istek hiçbir bölümde yok (`latency_planned_rows_failed = 0`).
* Testte kaçırılan tek satır: planlanan 2,04 ms gecikme, `duration_ms` 3,85 ms (eşik 4,04 ms; z = 3,36). Normal
  çalıştırmalarda (train 3, test 3) yanlış alarm yok.
* **Yorum ve sınırlar:** bu değerler kolay bir sentetik görevi yansıtır. Aynı süreçteki loopback sunucuda normal
  yanıt ~1,1 ms, enjekte gecikmeler ise 2–80 ms'dir; eşik yaklaşık 4 ms'ye denk gelir. Test bölümünde yalnızca tek
  grup (`random-narrow`, 2–10 ms), 3 çalıştırma, 3 epizot ve 60 pozitif satır vardır. `fixed_delay` testte, train'de
  yoktur; `random_delay` validation'da yoktur. Bu ailelerin ilgili bölümdeki sonucu "değerlendirilemedi"dir. Güven
  aralığı ve seed'ler arası değişkenlik hesaplanmadı. Gerçek sistemlerdeki gecikme dağılımları, kuyruklar ve küçük
  gecikmeler için genellenemez.

### Bilinen sınırlamalar

* Tek sabit eşik ve tek baseline; eşik seçimi veya ROC analizi yoktur (protokol gereği).
* Gözlemler bağımsız varsayılır; seri bağımlılığı, kayma ve mevsimsellik ele alınmaz.
* Grup düzeyinde bootstrap ve seed değişkenliği protokolde tanımlıdır ama bu sürümde hesaplanmaz. Daha geniş bir test
  kümesi (her gecikme ailesi için test grubu) yoktur.
* Wall-clock tespit gecikmesi ölçülemez: dedektör çevrimdışıdır ve alarm zamanı kaydedilmez (yukarıda).
* Değerlendirme çıktısı şeması `evaluation_schema_version = 2`. Önceki sürüm (1) `delay_requests`/`delay_ms`
  alanlarını kullanıyordu ve `delay_ms` adıyla gerçek gecikme gibi görünüyordu. Sayısal sonuçlar iki sürümde aynıdır.
* Dedektör özellik tablosunun kendi manifestini ve özetlerini doğrular. Kampanya kataloğunu yeniden doğrulamaz; bu,
  tablo üretilirken `dataset features` tarafından yapılır.

## Test sonucu analizi: TestRecord, JUnit/Surefire ayrıştırıcısı ve kural sınıflandırıcı

**Amaç:** test çıktılarını ortak bir modele dönüştürmek ve her sonucu, kararının gerekçesini ve kanıtlarını göstererek
sınıflandırmak. Makine öğrenmesi yoktur; harici servis ve ağ erişimi yoktur. Kurallar yalnızca sentetik fikstürlerle
sınanmıştır. Gerçek HGS2'den bugün yalnızca bir başarılı JUnit testi vardır; hata örneği yoktur. Bu nedenle kuralların
gerçek HGS2 hatalarındaki doğruluğu **ölçülmemiştir**.

```
hgs2-lab junit classify --report target/surefire-reports/TEST-x.xml --dataset-kind real --output work/x.classification.json
```

Akış: rapor dosyası → `junit_report.parse_junit_report` → `TestRecord` (maskeleme kurulumda uygulanır) →
`classify.classify_record` → `build_junit_document` → JSON. Çıktının üzerine yazılmaz. Python içinden Lab'in kendi istek
sonuçları da sınıflandırılabilir: `records.record_from_raw_result(raw, dataset_kind=..., expected=ExpectedResult(...))`.

### TestRecord (`records.py`, `RECORD_SCHEMA_VERSION = 2`)

| Grup | Alanlar |
|---|---|
| Zorunlu | `record_id`, `source_type` (`junit_xml`, `lab_result`), `dataset_kind` (`real`, `synthetic`, `fixture`, `unknown`), `test_outcome` |
| Kimlik / kaynak | `run_id`, `source_file` (yalnızca dosya adı), `source_sha256`, `test_id`, `test_name`, `suite_name`, `scenario_id`, `timestamp` |
| Beklenen / gözlenen | `expected_result` (`status_codes`, `business_outcomes`, `description`, `expected_test_outcome`, `expected_transport`, `provenance`; `null` = bilinmiyor), `status_code`, `business_outcome`, `duration_ms`, `transport_error` |
| Hata | `exception_type`, `error_message`, `stack_trace` |
| Etiket ve kalite | `label` + `label_source` (`synthetic_plan`, `human_review`; ikisi birlikte; model tahmini buraya yazılmaz), `data_quality_status` (`valid`, `partial`, `contradictory`, `invalid`), `warnings` (kod listesi) |
| Analiz | `analysis`: `classification`, `rule_ids`, `reason`, `evidence[]` (`field`, `value`, `source`, `note`), `confidence`, `requires_review`, `warnings`, `limitations`, `classifier_version` |

* `test_outcome` **kaynağın** kararıdır: JUnit için `PASS`/`FAIL`/`ERROR`/`SKIPPED`/`UNKNOWN`; Lab sonucu için HTTP durum
  denetimi (`http_ok`). `analysis.classification` ise **analiz motorunun** kararıdır. Analiz kaynak sonucu değiştirmez.
* Kaynakta olmayan değer uydurulmaz; bilinmeyen değer `null` olur. Geçersiz değerler (negatif/sonsuz süre, bilinmeyen
  enum, yol içeren `source_file`, 100–599 dışı durum kodu) `RecordError` verir. Hata mesajları alan değerini içermez.
* Maskeleme sınırı modelin kendisidir. Serbest metin alanları, beklenen sonuç açıklaması, kanıt değerleri ve gerekçe
  kurulum sırasında maskelenir. Bu yüzden `to_dict`/`to_json` hiçbir zaman maskelenmemiş değer üretmez. `from_dict`
  ve `from_json` gidiş-dönüşü kaydı aynen geri kurar; bilinmeyen anahtar reddedilir.
* `business_outcome` alanını kaynak sağlar: JUnit raporunda yoktur; Lab sonuçlarında yanıt ayrıştırıcısı doldurur.
  `record_from_raw_result(..., parsed=...)` ayrıştırma kuralını ve uyarılarını `response_rule:<kural>` ve
  `response_<uyarı>` kodlarıyla kaydın `warnings` alanına ekler. Bozuk JSON, çözülemeyen metin veya geçersiz durum
  kodunda kalite `partial` olur. Özet sonuç kaydıyla uyuşmazsa `RecordError` verilir.

### JUnit/Surefire ayrıştırıcısı (`junit_report.py`)

| Rapordaki öğe | `test_outcome` |
|---|---|
| sonuç öğesi yok | `PASS` (`flakyFailure`/`flakyError` varsa `flaky_rerun_passed` uyarısı) |
| `<failure>` / `<error>` / `<skipped>` | `FAIL` / `ERROR` / `SKIPPED` |
| farklı türler birlikte (ör. `<failure>` + `<skipped>`) | `UNKNOWN`, `data_quality_status = contradictory` |

* `<testsuites>` ve `<testsuite>` kökleri, birden çok ve iç içe suite, boş suite ve XML ad alanları desteklenir.
  `failure`/`error` öğesinin `type` özniteliği `exception_type` olur; `type` yoksa iz metninin ilk satırı kullanılır ve
  `exception_type_from_trace` uyarısı eklenir. `message` özniteliği `error_message`, öğe metni `stack_trace` olur.
  Mesaj 4 000 karakterde, iz 200 satır / 32 000 karakterde kırpılır ve kırpma bir uyarıyla bildirilir.
* `time` saniyedir. Eksikse `duration_missing` uyarısı verilir; negatif, sonsuz, sayı olmayan veya virgüllü değer
  `invalid_duration` + `partial` olur. Virgüllü değer tahmin edilmez, çünkü binlik ayırıcı mı ondalık virgül mü olduğu
  bilinemez.
* Suite özeti, beyan edilen sayıları (`tests`/`failures`/`errors`/`skipped`) kayıtlardan sayılanlarla karşılaştırır ve
  uyuşmazlığı `declared_count_mismatch:<alan>` uyarısıyla bildirir.
* **Okunmayan bölümler:** `<properties>` (JVM/sistem özellikleri gizli değer içerebilir), `<system-out>` ve
  `<system-err>` (testin yakaladığı log çıktısı). İçerikleri kayda alınmaz; yalnızca sayıları
  `ignored_sections` alanında bildirilir. Tek istisna, testcase düzeyindeki `hgs2_lab.scenario_id` özelliğidir
  (bkz. "Toplu JUnit analizi"). JUnit raporu uygulamanın tüm loglarını içermez; ayrı log dosyaları bu
  ayrıştırıcının kapsamı dışındadır.
* **Güvenlik:** dosya en çok 32 MiB olabilir. DOCTYPE veya varlık (entity) bildirimi içeren XML ayrıştırılmadan
  reddedilir (`unsafe_xml`); böylece harici varlık (XXE) ve varlık genişletme engellenir. İçerik çalıştırılmaz.
  Dosya düzeyindeki hata kodları: `not_found`, `unreadable`, `empty`, `too_large`, `unsafe_xml`, `malformed_xml`,
  `unsupported_format`. Hata mesajı dosya içeriğinden alıntı veya yerel yol içermez. Birden çok rapor verildiğinde
  hatalı dosya listelenir ve diğerleri işlenmeye devam eder.

### Sınıflandırıcı (`classify.py`, `rules-v3`)

`rules-v2` (N11), `rules-v1`'e tek bir kural ekledi: yalnızca durum kodu (ya da yalnızca "yanıt alınır") beklentisi
**2xx** bir yanıtla karşılandığında gövdeden tanınan bir iş sonucu çıkarılamadıysa (ayrıştırma kuralı
`R-TEXT-UNRECOGNIZED`, `R-JSON-UNRECOGNIZED`, `R-MALFORMED-JSON`, `R-UNDECODABLE` veya `R-UNSUPPORTED-TYPE`) karar
`PASS` değil `INCONCLUSIVE`'dir (`H-STATUS-OK-UNKNOWN-BODY`, `business_outcome_unrecognized`, inceleme gerekir).

`rules-v3` (N12, denetim bulgusu F-1) aynı koşulda (2xx + iş sonucu beklentisi yok) gövde hakkında güvenilir kanıt
olmayan ya da gövdesi yalnızca bir ara durum bildiren yanıtları da `PASS` saymaz; hepsi `INCONCLUSIVE`, `confidence`
yok, inceleme gerekir ve `business_expectation_missing` uyarısı taşır:

| Kural | Koşul | Uyarı |
|---|---|---|
| `H-STATUS-OK-EMPTY-BODY` | Gövde boş (`R-EMPTY-BODY`) ve durum kodu gövdesiz yanıt tanımlamıyor (204/205 dışında) | `response_body_empty` |
| `H-STATUS-OK-BODY-NOT-PARSED` | Gövde ayrıştırılmadı: 4 KiB'tan büyük (`R-TOO-LARGE`) ya da taşıyıcı vermedi (`R-BODY-NOT-CAPTURED`) | `response_body_not_parsed` |
| `H-STATUS-OK-BODY-UNVERIFIED` | Lab kaydında ayrıştırma özeti yok (`response_parsing_unavailable` / `_missing` / `_invalid`; eski dosya ya da bozuk metadata). Sonuç dosyasında iş sonucu yazılı olsa bile gövdenin incelendiği kanıtlanamaz | `response_parsing_not_available` |
| `H-STATUS-OK-STATE-BODY` | Gövde bir ara durum: `WAITING`, `READY`, `NONE`, `SCAN_CARD`, `SCAN_FP`, `SCAN_SCHOOL_NO` (`STATE_BUSINESS_OUTCOMES`). Bunlar iş başarısı ya da kimlik doğrulama onayı değildir | `business_outcome_state_only` |

Değişmeyenler: 204/205 + boş gövde (ör. HGS2 `DELETE /api/sensor/session`) `PASS` (`H-STATUS-MATCH`, `medium`)
kalır; olumlu iş sonucu (`ONAYLANDI`, `OK`, `KAYDEDILDI`) + yalnızca durum kodu beklentisi `PASS` (`medium`,
`business_outcome_not_checked`) kalır; beklenen 3xx/4xx/5xx kararı durum koduna dayanır (gövde kuralları yalnızca
2xx'te); iş sonucu beklentisi tanımlı kayıtlar ve JUnit kayıtları etkilenmez. Ara durumlar açık bir iş sonucu
beklentisiyle (`"business_outcomes": ["WAITING", "READY"]`) `PASS` olabilir. Bilinen sınır: 200 ile gerçekten boş
gövde dönen bir uç için "boş gövde beklenir" diye bir beklenti alanı yoktur; böyle bir uç `INCONCLUSIVE` kalır (HGS2
sözleşmesinde böyle bir uç bulunmadı).

| Sınıf | Ne zaman | Örnek kural |
|---|---|---|
| `PASS` | JUnit testi geçti; ya da gözlenen yanıt açıkça tanımlı beklentiyi karşıladı | `J-PASS`, `H-EXPECTED-MATCH`, `H-STATUS-MATCH` |
| `APPLICATION_FAILURE` | Beklenti açıkken durum kodu veya iş sonucu uymadı; ya da JUnit assertion başarısız oldu | `H-STATUS-MISMATCH`, `H-BUSINESS-MISMATCH`, `J-ASSERTION` |
| `TRANSPORT_FAILURE` | Bağlantı veya taşıma hatası kaydedildi | `H-TRANSPORT`, `J-TRANSPORT` |
| `TIMEOUT` | Zaman aşımı kaydedildi | `H-TIMEOUT`, `J-TIMEOUT-TYPE`, `J-TIMEOUT-MESSAGE` |
| `TEST_INFRASTRUCTURE_FAILURE` | Test bağlamı veya ortamı başlatılamadı (`Failed to load ApplicationContext`, `BeanCreationException`, `NoClassDefFoundError`, havuz/JDBC bağlantısı …) | `J-INFRA` |
| `INVALID_TEST_DATA` | Kayıt geçersiz işaretlendi | `DQ-INVALID` |
| `INCONCLUSIVE` | Kanıt yetersiz veya çelişkili; daha fazla bilgiyle karar verilebilir | `H-NO-EXPECTATION`, `H-BUSINESS-MISSING`, `H-STATUS-OK-NEGATIVE-BODY`, `H-STATUS-OK-UNKNOWN-BODY`, `H-STATUS-OK-EMPTY-BODY`, `H-STATUS-OK-BODY-NOT-PARSED`, `H-STATUS-OK-BODY-UNVERIFIED`, `H-STATUS-OK-STATE-BODY`, `J-SKIPPED`, `DQ-CONTRADICTORY`, `H-CONFLICT-*` |
| `UNKNOWN` | Bu kayıt türü için kural yok (ör. tanınmayan istisnayla JUnit `error`) | `J-ERROR-UNRECOGNIZED`, `J-UNKNOWN-OUTCOME` |

Temel ilkeler (her biri testle sınanır):

* **HTTP 200 tek başına iş başarısı değildir.** HGS2'nin kimlik doğrulama ve terminal uçları sonucu düz metin gövdeyle
  bildirir (`ONAYLANDI`, `REDDEDILDI`, `OK`, `HATA`), durum kodu her zaman 200'dür (HGS2 kaynak kodundan statik
  olarak). Gövde değeri her zaman beklenen iş sonucuyla karşılaştırılır:
  * Beklenen sonuç `REDDEDILDI` olan bir negatif testte gövde `REDDEDILDI` ise karar `PASS` olur.
  * Beklenen sonuç `ONAYLANDI` iken gövde `REDDEDILDI` ise karar `APPLICATION_FAILURE` olur.
  * Beklenen sonuç bilinmiyorsa, durum kodu ve gövde ne olursa olsun karar `INCONCLUSIVE` olur.
  * İş sonucu bekleniyor ama gövdeden iş sonucu yoksa karar `INCONCLUSIVE` olur.
  * Yalnızca durum kodu bekleniyorsa ve durum kodu tutuyorsa karar ancak gövde ayrıştırılıp olumlu bir iş sonucu
    taşıyorsa (ya da yanıt 204/205 ise) `PASS` olur; güven düzeyi `medium` kalır ve `business_outcome_not_checked`
    uyarısı eklenir. 2xx gövdesi olumsuz (`H-STATUS-OK-NEGATIVE-BODY`), tanınmayan (`H-STATUS-OK-UNKNOWN-BODY`),
    boş (`H-STATUS-OK-EMPTY-BODY`), ayrıştırılmamış (`H-STATUS-OK-BODY-NOT-PARSED`), ara durum
    (`H-STATUS-OK-STATE-BODY`) ya da ayrıştırma özeti yoksa (`H-STATUS-OK-BODY-UNVERIFIED`) karar `INCONCLUSIVE`'dir
    (`rules-v3`). Beklenen durum kodu tek başına iş başarısını kanıtlamaz.
  * Sensör durumları (`WAITING`, `READY`, `NONE`, `SCAN_*`) olumsuz iş sonucu değildir ve kimlik doğrulama onayı da
    değildir: beklenen `ONAYLANDI` iken gözlenen `READY` veya `WAITING` bir uyuşmazlıktır (`H-BUSINESS-MISMATCH`);
    yalnızca durum kodu beklentisiyle de `PASS` olmaz (`H-STATUS-OK-STATE-BODY`).
* Kaynak `FAIL`/`ERROR` diyorsa analiz `PASS` vermez (`H-CONFLICT-SOURCE-OUTCOME` → `INCONCLUSIVE`). `SKIPPED` başarılı
  sayılmaz.
* JUnit `FAIL` → `APPLICATION_FAILURE`; güven düzeyi `medium` olur ve şu sınırlama eklenir: "testin kendisinin hatalı
  olması dışlanamaz".
* JUnit `ERROR` istisna zincirine göre değerlendirilir: üst istisna ve izdeki `Caused by:` türleri. Altyapı bağlamı
  zaman aşımına, zaman aşımı taşıma hatasına göre önceliklidir.
* Zaman aşımı ve taşıma hataları uygulama hatası sayılmaz ve kök neden uydurulmaz. "Veritabanı yavaş" gibi bir neden
  ancak ölçülmüşse söylenebilir.
* `502`/`503`/`504` uyuşmazlığı ağ geçidi kaynaklı olabileceği için incelemeye işaretlenir.
* **Güven düzeyi** (`confidence`) olasılık değildir. Kararın dayandığı kanıtın türünü gösterir:
  * `high`: doğrudan ve çelişkisiz kanıta dayanan deterministik kural.
  * `medium`: kısmi denetim veya yorum.
  * `low`: yalnızca mesajdaki metin kalıbı.
  * `null`: `INCONCLUSIVE` ve `UNKNOWN` kararları.
* **F5 ile ayrım:** sınıflandırıcı `duration_ms` değerini ve F5 çıktısını kullanmaz. Gecikme anomalisi ayrı bir
  eksendir: yavaş bir yanıt işlevsel olarak `PASS` olabilir; HTTP 200 ile dönen bir iş hatası gecikme anomalisi
  olmadan görülebilir.

Çıktı belgesi (`format: hgs2-lab-test-classification`, `document_schema_version: 1`): `sources` (dosya adı, SHA-256,
suite özetleri), `file_errors`, `summary` (sınıf ve kaynak sonuç sayıları, inceleme gerektirenler), `notes`, `records`.
`content_sha256`, `generated_at` dışındaki içeriğin özetidir; aynı girdiler aynı özeti verir.

**Sınırlamalar:**

* Gerçek HGS2 hatalarıyla doğrulanmadı.
* İstisna adı tabloları sınırlıdır; tanınmayan türler `UNKNOWN` olur.
* JUnit `<system-out>` logları ayrıştırılmaz.
* Spring Boot log dosyası ve JSONL ayrıştırıcısı yoktur.
* Makine öğrenmesi sınıflandırıcısı için gerçek HGS2'den bağımsız hata olaylarından oluşan, insan tarafından
  etiketlenmiş bir korpus gerekir: her sınıfta en az birkaç düzine olay ve olay bazlı gruplama. Bu korpus bugün yoktur.

### Yanıt ayrıştırma ve iş sonucu (`response_parser.py`, `result_analysis.py`)

**Amaç:** HGS2'nin bazı uçları sonucu durum kodunda değil gövdede bildirir. Kimlik doğrulama ve terminal uçları,
hem kabul hem ret için HTTP 200 + düz metin döndürür (HGS2 kaynak kodunda salt okunur olarak görüldü). Ayrıştırıcı
gövdeden **yalnızca açıkça yazan** iş sonucunu çıkarır. Anlamını (beklenen ret mi, hata mı) belirlemez; anlam,
sınıflandırıcıda beklenen sonuçla karşılaştırılarak verilir. Gerçek HGS2 uçlarına karşı hiçbir doğrulama yapılmadı;
tüm uçların desteklendiği iddia edilmez.

Akış:

```
run / synthetic run: istek → RequestsTransport (gövde + Content-Type) → süre ölçümü biter → parse_response
                     → RawResult.business_outcome (yalnızca tanınan değer) + metadata.response_parsing (özet)
results classify:    sonuç dosyaları + response_parsing + beklenti dosyası → TestRecord → classify (N4) → JSON
```

**Tanınan iş sonucu değerleri** (`response-parser-v2`, N11): `ONAYLANDI`, `REDDEDILDI`, `OK`, `HATA`, `NONE`,
`SCAN_CARD`, `SCAN_FP`, `SCAN_SCHOOL_NO` (düz metin) ve `WAITING`, `READY` (JSON `status` alanı). Kaynakları ve
anlamları için bkz. "Gerçek HGS2 API sözleşmesi". `KAYDEDILDI` HGS2'nin HTTP yanıtlarında yoktur (yalnızca
veritabanındaki `logs.sonuc` değeridir); `response-parser-v1` ile yazılmış kayıtlar ve beklentilerle uyum için
tanınmaya devam eder. Değerler yalnızca metin olarak tanınır; her uçta aynı anlama geldikleri varsayılmaz.
Karşılaştırmada büyük/küçük harf ve baştaki/sondaki boşluk yok sayılır. Alt dize araması yapılmaz:
`ISLEM REDDEDILDI` tanınmaz.

| Kural | Koşul | `business_outcome` |
|---|---|---|
| `R-TEXT-TOKEN` | `text/plain` (ya da içerik türü yok + `content_type_missing` uyarısı) ve gövdenin tamamı tanınan bir değer | değer |
| `R-JSON-STRING` | `application/json` / `+json` ve gövde tek bir JSON metni (`"REDDEDILDI"`) | değer |
| `R-JSON-FIELD` | JSON nesnesinin **üst düzey** `business_outcome` alanı tanınan bir değer. Bu, Lab'in kendi sözleşmesidir; HGS2'de böyle bir alan yoktur | değer |
| `R-JSON-STATUS` | `business_outcome` alanı yok; **üst düzey** `status` alanı metin ve `WAITING` ya da `READY` (HGS2 `GET /api/sensor/result`). `value` alanı okunmaz ve yazılmaz | değer |
| `R-TEXT-UNRECOGNIZED`, `R-JSON-UNRECOGNIZED` | Okunabildi ama tanınan değer yok. Eşanlamlı veya iç içe alan aranmaz; tanınmayan metin `status` değeri `status_field_unrecognized`, sayısal `status` (ör. Spring hata gövdesi) tanınmaz | boş |
| `R-EMPTY-BODY`, `R-BODY-NOT-CAPTURED`, `R-NO-RESPONSE` | Gövde boş / taşıyıcı vermedi / taşıma hatası | boş |
| `R-TOO-LARGE` | Gövde `MAX_PARSE_BYTES` = 4096 bayttan büyük; **ayrıştırılmaz** (`body_too_large_not_parsed`). Ölçüm gövdenin tamamını okumaya devam eder | boş |
| `R-UNSUPPORTED-TYPE` | Metin veya JSON dışı içerik türü (`text/html`, `application/octet-stream` …) | boş |
| `R-UNDECODABLE` | Bilinmeyen veya metin olmayan charset, ya da çözülemeyen bayt | boş |
| `R-MALFORMED-JSON` | JSON içerik türü ama geçersiz JSON (`malformed_json`). İstek başarısız sayılmaz | boş |

Geçersiz veya eksik durum kodu `invalid_status_code` / `status_code_missing` uyarısı verir; gövde yine ayrıştırılır.
Ayrıştırıcı hiçbir girdide istisna fırlatmaz. HTTP durum kodu, iş sonucu ve taşıma hatası ayrı alanlarda kalır.

**Gizlilik:** ayrıştırma özeti yalnızca medya türünü, bayt sayısını, kuralı, uyarıları ve izin listesindeki iş sonucu
değerini taşır. Gövdenin kendisi, bir kısmı veya hash'i hiçbir dosyaya, loga, gerekçeye ya da kanıta yazılmaz.
Hash de yazılmaz, çünkü düşük entropili kişisel değerler hash'ten geri bulunabilir.

**Beklenti dosyası** (`results classify --expectations`; bilinmeyen anahtar reddedilir). Önerilen biçim, sürüm 2
beklenti sözleşmesidir (bkz. "Beklenti sözleşmesi"). Aşağıdaki sürüm 1 biçimi geriye uyum için desteklenir; doğrulama
durumu ve kanıt taşımaz, bu yüzden kararlarda `expectation_verification_unspecified` uyarısı bulunur:

```json
{"expectations_version": 1,
 "scenarios": {"kart-pasif-cihaz": {"status_codes": [200], "business_outcomes": ["REDDEDILDI"],
                                    "description": "pasif cihazda kart reddedilmeli"}}}
```

Sürüm 1 dosyasında veya hiç dosya verilmediğinde beklenti şu sırayla aranır:

1. Beklenti dosyası.
2. Senaryonun açıkça yazılmış `expected_status` listesi (metadata'dan; boş liste beklenti sayılmaz).
3. Hiçbiri yoksa beklenti `null` olur ve karar `INCONCLUSIVE` verilir.

Sürüm 2 sözleşmesi verildiğinde yalnızca sözleşme kullanılır. Eşleşme yoksa başka bir kaynağa geri düşülmez.

Isınma istekleri sınıflandırılmaz. Çalıştırmada bulunmayan senaryolar için yazılmış beklentiler `unused_expectations`
altında listelenir. `response_parsing` içermeyen eski dosyalarda kayıtlar `response_parsing_unavailable` uyarısı
taşır. Özet sonuç kaydıyla tutarsızsa kayıt `invalid` işaretlenir (`INVALID_TEST_DATA`).

Davranış (sentetik testlerle doğrulandı; gerçek HGS2 davranışını tanımlamaz):

| HTTP | Gövde | Beklenen | Sınıf (kural) |
|---|---|---|---|
| 200 | `REDDEDILDI` | ret | `PASS` (`H-EXPECTED-MATCH`) |
| 200 | `REDDEDILDI` | kabul | `APPLICATION_FAILURE` (`H-BUSINESS-MISMATCH`) |
| 200 | `REDDEDILDI` | bilinmiyor | `INCONCLUSIVE` (`H-NO-EXPECTATION`) |
| 200 | boş / bozuk JSON / desteklenmeyen tür / çok büyük | iş sonucu bekleniyor | `INCONCLUSIVE` (`H-BUSINESS-MISSING`), ayrıştırma uyarısı kanıtta |
| 200 | boş | yalnızca durum kodu | `INCONCLUSIVE` (`H-STATUS-OK-EMPTY-BODY`; `rules-v3`) |
| 204 | boş | yalnızca durum kodu 204 | `PASS` (`H-STATUS-MATCH`, `medium`) |
| 200 | 4 KiB'tan büyük | yalnızca durum kodu | `INCONCLUSIVE` (`H-STATUS-OK-BODY-NOT-PARSED`; `rules-v3`) |
| 200 | herhangi; metadata'da ayrıştırma özeti eksik/bozuk | yalnızca durum kodu | `INCONCLUSIVE` (`H-STATUS-OK-BODY-UNVERIFIED`; `rules-v3`) |
| 200 | `ONAYLANDI` / `OK` | yalnızca durum kodu | `PASS` (`H-STATUS-MATCH`, `medium`, `business_outcome_not_checked`) |
| 200 | `WAITING` / `READY` / `NONE` / `SCAN_*` | yalnızca durum kodu | `INCONCLUSIVE` (`H-STATUS-OK-STATE-BODY`; `rules-v3`) |
| 200 | tanınmayan metin / tanınmayan JSON (ör. `{"sessionId": …}`) / bozuk JSON / desteklenmeyen tür | yalnızca durum kodu | `INCONCLUSIVE` (`H-STATUS-OK-UNKNOWN-BODY`; `rules-v2`) |
| 200 | `REDDEDILDI` / `HATA` | yalnızca durum kodu | `INCONCLUSIVE` (`H-STATUS-OK-NEGATIVE-BODY`) |
| 200 | `{"status":"WAITING"}` / `{"status":"READY",…}` | `WAITING` veya `READY` | `PASS` (`H-EXPECTED-MATCH`) |
| 200 | `{"status":"READY",…}` / `{"status":"WAITING"}` | kabul (`ONAYLANDI`) | `APPLICATION_FAILURE` (`H-BUSINESS-MISMATCH`) |
| 200 | `NONE` | `NONE` | `PASS` (`H-EXPECTED-MATCH`) |
| 400 | Spring biçimli hata JSON'u | yalnızca durum kodu 400 | `PASS` (`H-STATUS-MATCH`, `medium`); 2xx olmadığı için `H-STATUS-OK-UNKNOWN-BODY` uygulanmaz |
| 500 | `HATA` | 200 + kabul | `APPLICATION_FAILURE` (`H-STATUS-AND-BUSINESS-MISMATCH`) |
| — | zaman aşımı | herhangi | `TIMEOUT` (`H-TIMEOUT`) |
| — | bağlantı koptu | herhangi | `TRANSPORT_FAILURE` (`H-TRANSPORT`) |

Örnek çıktı kaydı (kısaltılmış; sentetik):

```json
{"scenario_id": "kart-gecerli", "test_outcome": "PASS", "status_code": 200, "business_outcome": "REDDEDILDI",
 "expected_result": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"], "description": "geçerli kart"},
 "warnings": ["response_rule:R-TEXT-TOKEN"],
 "analysis": {"classification": "APPLICATION_FAILURE", "rule_ids": ["H-BUSINESS-MISMATCH"],
              "reason": "Gözlenen yanıt açıkça tanımlı beklentiyi karşılamadı.", "confidence": "high",
              "requires_review": false, "warnings": ["source_outcome_differs"],
              "evidence": [{"field": "status_code", "value": 200, "source": "record", "note": null},
                           {"field": "business_outcome", "value": "REDDEDILDI", "source": "record", "note": null},
                           {"field": "response_parsing", "value": ["response_rule:R-TEXT-TOKEN"], "source": "record", "note": null},
                           {"field": "business_outcome", "value": "REDDEDILDI", "source": "rule", "note": "beklenen ['ONAYLANDI']"}]}}
```

`test_outcome` burada Lab'in HTTP durum denetimidir ve `PASS`'tir (200 beklenen durum). Analiz ise iş sonucuna
bakarak `APPLICATION_FAILURE` der. İki alan ayrı tutulur; `source_outcome_differs` uyarısı bunu işaretler.

**Sınırlamalar:**

* İzin listesi HGS2 kaynak kodundaki sabitlerden alındı. Uç bazında anlamı doğrulanmadı.
* Sentetik sunucunun gövdeleri (`synthetic ok`) iş sonucu değildir. Sentetik deney çıktılarında `business_outcome`
  boş kalır (doğrulandı).
* JSON'da yalnızca Lab'in `business_outcome` alanı, HGS2 sensör sonucunun `status` alanı (`WAITING`/`READY`) ve tek
  metin gövde desteklenir. HGS2'nin diğer JSON uçları (ör. kullanıcı listesi, `POST /api/sensor/start`'ın
  `sessionId` yanıtı, `{"error": …}`) iş sonucu taşımaz; yalnızca durum kodu beklentisiyle 2xx ise `INCONCLUSIVE` olur.
* Gövde 4 KiB'tan büyükse ayrıştırılmaz.
* Ayrıştırma, istekler arasına çok kısa bir işlem süresi ekler (`elapsed_ms`/`duration_ms` dışında).

### Beklenti sözleşmesi (`expectations.py`, `expectations_version: 2`)

**Amaç:** testin hangi davranışı beklediğini, bu beklentinin hangi kaynağa dayandığını ve ne ölçüde doğrulandığını
izlenebilir biçimde kaydetmek, ardından bunu kayıtlarla güvenli biçimde eşleştirip N4'e aktarmak. Bu bir altyapıdır;
gerçek HGS2 iş kurallarını içermez. Gerçek HGS2 için doğrulanmış bir beklenti tablosu **yoktur**.

```json
{"expectations_version": 2, "registry_id": "lab-sentetik",
 "evidence": [{"evidence_id": "ev-1", "source_type": "approved_business_rule", "source_ref": "IS-KURALI-12",
               "location": "madde 3", "supports": ["http_status", "business_outcome"],
               "review_status": "REVIEWED", "relation": "supports", "source_version": "v4", "description": "…"}],
 "expectations": [{"expectation_id": "exp-kart-pasif", "version": 1, "scenario_id": "kart-pasif-cihaz",
                   "endpoint_id": "POST /api/auth/kart-okut", "status": "VERIFIED", "scope": "real",
                   "expected_http_status": [200], "expected_business_outcome": ["REDDEDILDI"],
                   "expected_test_outcome": "PASS", "expected_transport": "response",
                   "evidence_ids": ["ev-1"], "description": "…"}]}
```

**Beklenti alanları.** Zorunlu alanlar: `expectation_id` (değişmez kimlik), `version`, `scenario_id`, `status` ve
`scope` (`synthetic` | `real`). Beklenen alanların hepsi isteğe bağlıdır; bilinmeyen alan `null` bırakılır. Varsayılan
olarak başarı üretilmez. En az bir beklenen alan olmalıdır: `expected_http_status`, `expected_business_outcome`,
`expected_transport` veya `expected_test_outcome`. Yalnızca `expected_test_outcome` içeren beklenti JUnit kayıtları
içindir; HTTP kayıtlarında karar üretmez.

- `expected_business_outcome` yalnızca yanıt ayrıştırıcısının tanıdığı değerleri alabilir.
- `expected_test_outcome` yalnızca kanıt olarak karşılaştırılır; kaynak sonucunu değiştirmez ve karar üretmez.
- Bir taşıma hatası beklenirken (`timeout` …) durum kodu, iş sonucu veya kaynak `PASS` beklenemez (çelişki).
- Yinelenen liste değerleri reddedilir.
- Bir HTTP durum kodunun hangi iş sonucuna karşılık geldiği varsayılmaz.

**Doğrulama durumu.**

| Durum | Anlamı |
|---|---|
| `DRAFT` | Taslak; kanıt gerekmez. |
| `REVIEWED` | İncelenmiş; doğrulama kapsamı sınırlı. En az bir kanıt referansı gerekir. |
| `VERIFIED` | Belirtilen kapsamda, kayıtlı kanıtla desteklenir. Gerçek dünyanın tamamında doğruluk iddiası değildir. |
| `DEPRECATED` | Eşleştirmede kullanılmaz. |

Yalnızca `VERIFIED` doğrulanmış sayılır.

**Kanıt referansları** (`EvidenceReference`).

- **Alanlar:**
  - `evidence_id`;
  - `source_type`: `existing_test`, `source_code_review`, `official_documentation`, `approved_business_rule`, `synthetic_fixture`, `manual_review`, `unknown`;
  - `source_ref`: kaynak tanımlayıcısı (belge kodu, test adı, depo içi göreli yol). Mutlak yerel yol reddedilir;
  - `location`;
  - `supports`: ilgili beklenti alanları;
  - `review_status`: `UNREVIEWED` | `REVIEWED`;
  - `relation`: `supports` | `contradicts`;
  - `source_version`;
  - `description`.
- **İçerik kopyalanmaz:** kaynağın içeriği değil, yalnızca güvenli bir başvurusu tutulur.
- **Referans inceleme demek değildir:** bir referansın bulunması içeriğin incelendiği anlamına gelmez; bunu `review_status` belirtir.
- **Maskeleme:** metin alanları N1 maskelemesinden geçer.

**Kanıt yeterliliği** (`assess_evidence`; deterministik). Bulgu kodları:

- `no_evidence`
- `evidence_unreviewed`
- `unknown_source:<id>`
- `non_verifying_source:<id>`
- `contradicting_evidence:<id>`
- `field_not_verified:<alan>`
- `field_contradicted:<alan>`

`VERIFIED` için beklenen her alan, en az bir **incelenmiş**, `supports` ilişkili ve kapsama uygun kaynak türündeki
kanıtla desteklenmelidir. O alanı çürüten incelenmiş bir kanıt da olmamalıdır.

| Kapsam | Doğrulayıcı kaynak türleri |
|---|---|
| `real` | `existing_test`, `official_documentation`, `approved_business_rule`, `manual_review` |
| `synthetic` | `synthetic_fixture`, `existing_test`, `official_documentation`, `manual_review` |

Kaynak kod incelemesinden çıkarılan bir varsayım onaylanmış iş kuralı sayılmaz. Sentetik fikstür de gerçek davranışı
doğrulamaz. Bu yüzden bu iki tür `real` kapsamında `VERIFIED` yapamaz.

**Registry davranışı.**

- **Kısmi kabul yok:** dosya yalnızca okunur. Tek bir şema, kimlik, kanıt veya durum hatası bile tüm dosyanın
  reddedilmesine yol açar ve bütün bulgular (`issues`) listelenir. Hata mesajları değer veya yerel yol içermez.
- **Kimlikler:** `expectation_id` ve `evidence_id` benzersiz olmalıdır; tanımsız kanıt kimliğine başvuru hatadır.
- **Gerekçelendirilemeyen VERIFIED:** dosya reddedilir; durum sessizce düşürülmez.
- **Çelişkiler:** aynı `scenario_id` için birden fazla etkin (DEPRECATED olmayan) beklenti dosyayı geçersiz kılmaz,
  ama `conflicts` altında raporlanır.
- **Determinizm:** sıralama `(scenario_id, expectation_id)` ile yapılır. `content_sha256`, girdi dosyasındaki
  sıradan bağımsızdır.
- **Bozuk dosyalar:** boş, bozuk, bulunamayan veya yanlış sürümlü dosyada varsayılan iş kuralına geçilmez;
  komut 1 ile çıkar.

**Eşleştirme.** Kaydın `scenario_id` değeriyle birebir ve büyük/küçük harfe duyarlı yapılır. `endpoint_id` yalnızca
açıklayıcıdır, eşleştirmede kullanılmaz (kayıtlarda güvenilir bir uç kimliği yoktur). Sonuçlar:

| Sonuç | Kayda eklenen uyarı |
|---|---|
| `matched` | — |
| `not_found` | `expectation_not_found` |
| `conflict` | `expectation_conflict` (hiçbiri seçilmez) |
| `deprecated_only` | `expectation_deprecated_only` |
| `no_scenario_id` | `expectation_no_scenario_id` |

Eşleşen beklenti kayda `expected_result.provenance` ile bağlanır: kaynak, kimlik, sürüm, doğrulama durumu, kapsam,
kanıt kimlikleri ve kanıt yeterliliği bulguları.

**N4 ile entegrasyon.** Mevcut kurallar aynen çalışır; beklenti sözleşmesi yalnızca kararın kesinliğini belirler.

| Durum | Karar |
|---|---|
| Beklenti yok / bulunamadı / yalnızca DEPRECATED | `INCONCLUSIVE` (`H-NO-EXPECTATION`) + eşleşme uyarısı |
| Aynı senaryo için birden fazla etkin beklenti | `INCONCLUSIVE` (`E-EXPECTATION-CONFLICT`) |
| `DRAFT` / `REVIEWED` beklenti, karar PASS veya APPLICATION_FAILURE olurdu | `INCONCLUSIVE` (`E-UNVERIFIED-EXPECTATION` + temel kural); olası sonuç `comparison` kanıtında (`would_be`) |
| `VERIFIED` ama kapsam kaydın veri türüyle eşleşmiyor (`real` ↔ `real`; `synthetic` ↔ `synthetic`/`fixture`) | `INCONCLUSIVE` (`E-SCOPE-MISMATCH`; veri türü `unknown` ise `E-SCOPE-UNCONFIRMED`) |
| `VERIFIED` ve kapsam uygun | Mevcut N4 kuralları (`H-EXPECTED-MATCH`, `H-BUSINESS-MISMATCH`, …) + "yalnızca bu kapsamda doğrulandı" sınırlaması |
| Taşıma hatası beklenirken HTTP yanıtı geldi | `APPLICATION_FAILURE` (`H-TRANSPORT-MISMATCH`; beklenti doğrulanmamışsa INCONCLUSIVE) |
| Zaman aşımı / bağlantı kopması | `TIMEOUT` / `TRANSPORT_FAILURE` (gözlemdir, beklentiden bağımsız) + `transport_matches_expectation` / `transport_differs_from_expectation` |
| Eski biçim (sürüm 1) veya senaryo `expected_status` | Önceki davranış + `expectation_verification_unspecified` |

Değişmeyen ilkeler:

- Kaynak `FAIL`/`ERROR` hiçbir zaman PASS'a çevrilmez.
- `SKIPPED` başarılı sayılmaz.
- HTTP 200 tek başına iş başarısı değildir.

Kararda beklenti `expectation` kanıtı olarak görünür. Güven düzeyinin anlamı değişmedi: doğrulama durumu, kanıtın
niteliği ve güven düzeyi ayrı kavramlardır; yeni bir puan eklenmedi.

**Kullanım:**

```
hgs2-lab expectations validate --file beklentiler.json
hgs2-lab expectations show     --file beklentiler.json --scenario kart-pasif-cihaz
hgs2-lab results classify --run-id RUN --results-dir DİZİN --expectations beklentiler.json \
                          --dataset-kind synthetic --output RUN.classification.json
```

**Fikstürler** (`tests/fixtures/expectations/`):

- `synthetic-registry.json`: sözleşmenin bütün durumlarını içeren sentetik registry.
- `hgs2-draft-example.json`: gerçek HGS2 için yalnızca **taslak** bir örnek. Tek kanıtı, HGS2 `AuthController`
  kaynak koduna yapılmış incelenmemiş bir referanstır; bu yüzden `VERIFIED` yapılamaz.

**Sınırlamalar:**

- Gerçek HGS2 için kaynakla desteklenmiş, doğrulanmış bir beklenti yoktur.
- Kanıt yeterliliği, kanıt metninin içeriğini değil, beyan edilen meta veriyi (tür, inceleme, kapsam, ilişki)
  denetler. İncelemenin gerçekten yapıldığı kullanıcının beyanıdır.
- JUnit kayıtları yalnızca testcase özelliği `hgs2_lab.scenario_id` ile eşleştirilir (bkz. "Toplu JUnit analizi").
- Uç (`endpoint_id`) veya test adına göre eşleştirme yoktur.

### Toplu JUnit analizi (`junit_analysis.py`, `junit classify --expectations`)

**Amaç:** birden fazla JUnit/Surefire raporunu tek seferde işlemek. Raporlar mevcut ayrıştırıcıyla okunur,
`TestRecord`'a dönüştürülür, isteğe bağlı olarak beklenti sözleşmesiyle eşleştirilir, mevcut N4 sınıflandırıcısıyla
yorumlanır ve sayaçlı tek bir JSON belgeye yazılır. Yeni bir XML ayrıştırıcısı, registry veya sınıflandırıcı yoktur.

```
hgs2-lab junit classify --report target/surefire-reports/TEST-a.xml --report target/surefire-reports/TEST-b.xml \
                        --expectations beklentiler.json --dataset-kind synthetic --output analiz.json
```

**Senaryo kimliği nasıl tanımlanır?** Testcase düzeyindeki `<properties>` öğesindeki tek bir açık özellikle. Özellik
adı Lab'in sözleşmesidir, JUnit standardı tanımlamaz. pytest 9.1.1 `record_property` bu yapıyı üretir (yerel olarak
doğrulandı). Maven Surefire/JUnit 5'in testcase düzeyinde özellik üretip üretmediği **doğrulanmadı** (bkz. "Gerçek
HGS2 entegrasyon hazırlığı"):

```xml
<testcase name="kartPasifCihaz" classname="com.example.lab.KartTests" time="0.010">
  <properties><property name="hgs2_lab.scenario_id" value="kart-pasif-cihaz"/></properties>
</testcase>
```

- **Değerin yeri:** `value` özniteliğinde ya da öğe metninde olabilir.
- **Biçim:** harf/rakamla başlar; yalnızca harf, rakam, `.`, `_`, `-` içerir (en çok 64 karakter).
- **Kimlik yoksa:** `scenario_id = null` olur.
- **Hatalı kimlik:** geçersiz değer `scenario_id_invalid`, aynı testte farklı değerler `scenario_id_conflict`
  uyarısı verir; hiçbiri seçilmez. Aynı değerin tekrarı `scenario_id_repeated` uyarısıyla kabul edilir.
- **Okunmayanlar:** suite düzeyindeki özellikler ve başka adlı özellikler okunmaz.
- **Türetme yok:** test metodu, sınıf, suite veya uç adından kimlik **türetilmez**.
- **Kayıt korunur:** kimlik sorunu kaydın kaynak sonucunu değiştirmez ve kaydı silmez.

**Eşleştirme.** Kaydın `scenario_id` değeriyle birebir yapılır. Beklenti dosyası sürüm 2 (registry) ya da sürüm 1
olabilir.
`--scenario-map` verilirse kimlik önce metadata ve eşleme dosyasından çözülür (bkz. "Senaryo eşleştirme ve uçtan uca
kabul (N10)").

| Durum | Davranış |
|---|---|
| Kimlik yok | `no_scenario_id` |
| Beklenti bulunamadı | `not_found` |
| Yalnızca DEPRECATED beklenti var | `deprecated_only` |
| Birden fazla etkin beklenti | `conflict`; hiçbiri seçilmez ve kayıt incelemeye düşer |

Bu durumların hepsinde kayıt aynen korunur; yalnızca `expectation_<durum>` uyarısı eklenir. Geçersiz, eksik veya
bozuk beklenti dosyası komutu 1 ile durdurur ve hiçbir şey yazılmaz. Geçerli kısımlarla kısmi analiz yapılmaz.
Beklenti dosyası verilmezse analiz açıkça "beklentisiz" olarak işaretlenir.

**JUnit kararı ve beklenti.** Karar her zaman kaynak test sonucundan gelir ve mevcut J-* kuralları kullanılır:

| Kaynak sonuç | Karar |
|---|---|
| PASS | `PASS` + "uygulamanın genel olarak hatasız olduğunu göstermez" sınırlaması |
| FAIL | `APPLICATION_FAILURE` (medium) + "testin kendisinin hatalı olması dışlanamaz" sınırlaması |
| ERROR | İstisna zincirine göre `TIMEOUT` / `TRANSPORT_FAILURE` / `TEST_INFRASTRUCTURE_FAILURE` / `UNKNOWN` / `INCONCLUSIVE` |
| SKIPPED | `INCONCLUSIVE` |

Beklenti bu kararı **değiştirmez**; yalnızca karara kanıt ve uyarı ekler:

- **`expectation` kanıtı:** kaynak, kimlik, sürüm, doğrulama durumu ve kapsam.
- **`expectation_comparison` kanıtı:** alan bazında `match` / `differs` / `not_observable` / `not_specified`. JUnit
  kaydında HTTP durumu, iş sonucu ve taşıma bilgisi olmadığı için bu alanların beklentileri karşılaştırılamaz:
  `not_observable` olur ve `expectation_not_observable_in_junit` uyarısı eklenir.
- **Kaynak sonuç karşılaştırması:** `test_outcome_matches_expectation` / `test_outcome_differs_from_expectation`.
- **DRAFT / REVIEWED beklenti:** `expectation_unverified`.
- **Kapsam uyuşmazlığı:** sentetik kapsamdaki beklenti `real` veya `unknown` kayıtta kullanıldığında
  `expectation_scope_mismatch`.

Böylece kaynak FAIL hiçbir zaman PASS'a çevrilmez, SKIPPED başarılı sayılmaz ve taslak beklenti bir teşhis gerekçesi
olmaz.

**Toplu girdi davranışı.**

- Her rapor ayrı okunur. Bozuk, boş, eksik, XXE içeren veya JUnit olmayan dosya diğerlerini durdurmaz;
  `file_errors` altında kod ve mesajla listelenir.
- Bayt bayt aynı içerikli bir rapor ikinci kez verilirse yeniden işlenmez ve `duplicate_reports` altında listelenir.
  Bu güvenilir bir tekilleştirmedir: aynı içerik aynı kayıt kimliklerini üretir.
- Farklı raporlarda aynı `test_id` görülürse kayıtlar **birleştirilmez**; `possible_duplicate_tests` altında
  raporlanır.

**JSON sayaçları** (`classification.summary`; tanımları belgede `counter_definitions` altında):

| Sayaç | Hangi küme üzerinden |
|---|---|
| `files_given` / `files_parsed` / `files_rejected` / `files_duplicate` | Verilen yollar. `files_given = files_parsed + files_rejected + files_duplicate`; reddedilen dosya analiz edilmiş sayılmaz |
| `suites` | Ayrıştırılan raporlardaki `<testsuite>` sayısı (bir rapor birden çok suite içerebilir; boş suite dahil) |
| `records` | Ayrıştırılan testcase kayıtları; her kayıt tam olarak bir sınıfa düşer |
| `by_test_outcome` | Kaynak raporun kendi sonucu; analiz sonucu değildir |
| `by_classification` | N4 sınıfı. `INCONCLUSIVE` ve `UNKNOWN` PASS/FAIL toplamlarına eklenmez |
| `requires_review` | İnceleme gerektiren kayıtlar; başarısızlık sayısı değildir |
| `expectation_matching` | `requested`, `records_with_scenario_id` / `records_without_scenario_id`, `by_match_status`, `matched_by_verification_status` (eşleşme doğrulama demek değildir) |
| `data_quality` | Kalite durumu dağılımı, uyarılı kayıt sayısı, suite uyarıları |
| `possible_duplicate_tests` | Birden fazla kayıtta görülen `test_id`'ler |

Kaynak PASS sayısı uygulamanın bütün olarak başarılı olduğunu göstermez; yalnızca rapordaki testlerin kendi
sonucudur.

**Fikstürler:**

- `tests/fixtures/junit-n8/`: 14 testcase, 3 suite (biri boş).
- `tests/fixtures/expectations/junit-registry.json`: sentetik kapsam.

**Gerçek HGS2 ile sınırlar:**

- Gerçek HGS2'nin tek mevcut raporu (`contextLoads`, PASS) senaryo kimliği içermez; bu yüzden beklentiyle
  eşleşmez.
- HGS2 testlerine `hgs2_lab.scenario_id` özelliği eklenmedikçe gerçek raporlar yalnızca beklentisiz analiz
  edilebilir.
- Gerçek HGS2 için doğrulanmış bir beklenti yoktur.

## Gerçek HGS2 API sözleşmesi (kaynak koddan statik; N11, 2026-10-29)

**Kaynak:** gerçek HGS2 deposu (`hgs2`, HEAD `ad255a4`, çalışma ağacı temiz), yol
`hgs2-main/HGS-main/HGS/src/main/java/com/HibritGirisSistemi/HGS/`. Yalnızca kaynak kodu okundu: HGS2 başlatılmadı,
testleri çalıştırılmadı, API'sine istek gönderilmedi, PostgreSQL'e bağlanılmadı. Projede DTO sınıfı yoktur; yanıtlar
`String` ve `Map.of(...)` ile üretilir. "Kaynak" sütunu: **K** = HGS2 kaynak kodunda doğrudan görülüyor; **S** = Spring
Boot'un varsayılan davranışı, HGS2 kodunda tanımlı değil, **doğrulanmadı**.

| Metot ve yol | Parametreler (gövde yok; query/form) | Yanıt (durum, içerik türü, gövde) | İş sonucu | Yan etki | Kaynak |
|---|---|---|---|---|---|
| `POST /api/auth/kart-okut` | `kartNo` (metin), `deviceId` (tam sayı) | 200, `text/plain;charset=UTF-8`, `ONAYLANDI` veya `REDDEDILDI` | başarı `ONAYLANDI`; ret `REDDEDILDI` (pasif/kayıtsız cihaz veya kullanıcı dahil) | **Her çağrıda `logs` tablosuna 1 satır.** Açık bir sensör oturumunu cihaza bakmadan doldurabilir (bellek) | K (`AuthController.kartOkut`, `islemYap`) |
| `POST /api/auth/numara-okut` | `ogrenciNo`, `deviceId` | aynı | aynı | aynı | K |
| `POST /api/auth/parmak-izi-okut` | `parmakIzi` (slot), `deviceId` | aynı | aynı | aynı | K |
| `POST /api/terminal/kart-kaydet` | `deviceId`, `ogrenciNo`, `kartNo` | 200, `text/plain;charset=UTF-8`, `OK` veya `HATA` | başarı `OK`; her iş hatası `HATA` (neden ayırt edilmez) | `users` UPDATE + `logs` INSERT (`@Transactional`) | K (`TerminalEnrollmentService`) |
| `POST /api/terminal/parmak-kaydet` | `deviceId`, `ogrenciNo`, `slot` | aynı | aynı | aynı | K |
| `POST /api/terminal/ogrenci-no-degistir` | `deviceId`, `eskiNo`, `yeniNo` | aynı | aynı | aynı | K |
| `POST /api/terminal/ogrenci-kaydet` | `deviceId`, `ogrenciNo` | aynı | `OK` (kayıt zaten varsa yazmadan `OK`) / `HATA` | `users` + `logs` INSERT | K |
| `POST /api/sensor/start` | `type` (`CARD`/`FINGERPRINT`/`SCHOOL_NO`), `deviceId` (isteğe bağlı, varsayılan 1) | 200 JSON `{"sessionId": "<12 karakter>"}`; geçersiz tipte 400 JSON `{"error": "Gecersiz tip: …"}` | iş sonucu yok (tanınmaz) | bellekte oturum; 180 sn'den eski oturumları yalnızca burada temizler | K |
| `GET /api/sensor/pending` | `deviceId` | 200, düz `String`: `NONE`, `SCAN_CARD`, `SCAN_FP` veya `SCAN_SCHOOL_NO` | `NONE` = bekleyen tarama yok; `SCAN_*` = tarama isteniyor | yok (okuma) | K (`SensorCaptureService.getPendingAction`); içerik türü `produces` ile tanımlı değil (**S**: istemcinin `Accept` başlığına göre `text/plain` beklenir, doğrulanmadı) |
| `GET /api/sensor/result` | `sessionId` | 200 JSON `{"status":"WAITING"}` veya `{"status":"READY","value":"<yakalanan değer>"}` | `WAITING` = henüz yok (hata değil); `READY` = sensör değeri hazır (**kimlik doğrulama onayı değil**). Bilinmeyen/silinmiş oturumda da `WAITING` (404 yok) | yok | K |
| `DELETE /api/sensor/session` | `sessionId` | 204, gövde yok | — | oturumu siler (yoksa da 204) | K |
| `GET/POST/PUT/DELETE /api/users[/{id}]`, `/api/devices[/{id}]`, `GET /api/logs` | JSON gövde (`User`/`Device`) | 200 JSON varlık/liste; kullanıcıda iş kuralı ihlali 400 `{"error": …}` | iş sonucu yok | CRUD; kullanıcı silme logları da siler | K |
| tümü: eksik/yanlış tipte parametre | — | 400 + Spring hata gövdesi | — | — | **S** |
| tümü: veritabanı hatası, `aciklama` (255) taşması vb. | — | 500 + Spring hata gövdesi; log yazılmayabilir | — | — | **S** (HGS2'de `@ControllerAdvice` yok) |

Önemli sonuçlar:

* **HTTP 200 iş başarısı değildir:** ret (`REDDEDILDI`) ve iş hatası (`HATA`) de 200 ile döner.
* **Kimlik doğrulama uçları salt okunur değildir:** her çağrı log yazar; test yalnızca yalıtılmış test veritabanına
  karşı yapılabilir. Hiçbir HGS2 ucu tekrar güvenli (idempotent) varsayılmamalıdır.
* **Kimlik doğrulama yoktur:** tüm uçlar `@CrossOrigin("*")` ve `server.address=0.0.0.0`.

**HGS2 tarafında test yalıtımı için öneri (UYGULANMADI; HGS2 kaynak kodu değiştirilmedi):** HGS2'nin tek testi
(`HgsApplicationTests.contextLoads`, `@SpringBootTest`) `application.properties` ile gerçek
`jdbc:postgresql://localhost:5432/hibrit_giris_db` veritabanına bağlanır ve `ddl-auto=update` ile şema değiştirir
(mevcut Surefire raporunda `create table`/`alter table` satırları görülür). Ayrı bir uygulama aşamasında önerilenler:

1. `src/test/resources/application-test.properties` (ya da Testcontainers): ayrı veritabanı URL'si, ayrı kullanıcı,
   `spring.jpa.hibernate.ddl-auto=create-drop`; test sınıflarında `@ActiveProfiles("test")`.
2. Ana `application.properties`'teki parolayı ortam değişkenine taşımak (`${HGS_DB_PASSWORD}`) ve
   `ddl-auto=validate` (ya da Flyway/Liquibase).
3. Test profilinde farklı `server.port` (ör. `18080`) ve yalnızca `127.0.0.1`'e bind; Lab'in hedef kimliğini
   doğrulayabilmesi için test profiline özgü salt okunur bir işaret ucu (ör. `GET /api/test-profile` → profil adı).
4. Bunlar uygulanıp gerçek veritabanına dokunulmadığı kanıtlanmadan hiçbir HGS2 testi çalıştırılmamalıdır.

## Gerçek HGS2 entegrasyon hazırlığı (`readiness.py`, `ingestion.py`)

**Bu bölüm bir hazırlık katmanını anlatır; gerçek HGS2 ile hiçbir doğrulama yapılmadı.** Lab gerçek HGS2'ye
bağlanmaz, HGS2 testlerini çalıştırmaz, veritabanına veya cihazlara erişmez. Aşağıdaki denetimler yalnızca verilen
dosyaları ve Lab'in kendi bileşenlerini çevrimdışı çalıştırır.

### Mevcut HGS2 raporlarında hangi alanlar var?

Gerçek HGS2'nin bugün erişilebilir tek test raporu Maven Surefire çıktısıdır (`TEST-…HgsApplicationTests.xml`, şema
`surefire-test-report.xsd` sürüm 3.0.2). Raporda tek bir test vardır (`contextLoads`, PASS). Rapor salt okunur
incelendi; `readiness check` envanteri:

| Alan | Durum |
|---|---|
| Test sınıfı, test adı, kaynak sonuç, süre | `available` |
| Hata türü, mesaj, stack trace | `not_applicable` (FAIL/ERROR kaydı yok) |
| Suite meta verisi (ad, süre, beyan edilen sayılar) | `available`; zaman damgası yok |
| `<properties>` (suite düzeyi, JVM/sistem özellikleri) | `withheld_for_security`: gizli değer içerebileceği için okunmaz |
| `system-out` / `system-err` | `present_not_parsed`: test logu ayrıştırılmaz |
| Senaryo kimliği (`hgs2_lab.scenario_id`) | `missing` |
| Beklenen sonuç, HTTP durumu, iş sonucu | `not_in_format`: JUnit/Surefire biçiminde böyle alanlar yok |

Envanter durumları:

| Durum | Anlamı |
|---|---|
| `available` | İlgili kayıtların hepsinde var |
| `partial` | Bazı kayıtlarda var |
| `missing` | Bu biçimde olabilirdi ama raporda yok |
| `not_applicable` | Alanın anlamlı olacağı kayıt yok |
| `present_not_parsed` | Raporda var ama okunmuyor |
| `withheld_for_security` | Bilinçli olarak okunmuyor |
| `not_in_format` | Biçimde böyle bir alan yok |

Envanter değer içermez; yalnızca durum ve sayıları gösterir.

### Senaryo kimliği sözleşmesi

- **Kaynak:** `hgs2_lab.scenario_id`, testcase düzeyindeki `<properties>` içinde açık bir özelliktir. Lab'in
  sözleşmesidir; JUnit standardı tanımlamaz.
- **Türetme yok:** test, sınıf, suite veya uç adından kimlik türetilmez. Adlar yeniden adlandırmayla değişebilir ve
  bir adın hangi senaryoyu sınadığını kanıtlamaz; türetilmiş bir eşleşme yanlış beklentiyi sessizce bağlayabilir.
- **Hatalı kimlik:**
  - Geçersiz kimlik düzeltilmez (`scenario_id_invalid`).
  - Çelişkili kimliklerden biri seçilmez (`scenario_id_conflict`).
  - Kimlik yoksa kayıt korunur ve eşleştirilmez.
- **Kimliği yazabilen araçlar:**

  | Araç | Durum |
  |---|---|
  | pytest 9.1.1 `record_property` | Bu yapıyı ürettiği yerel olarak **doğrulandı** |
  | Maven Surefire + JUnit 5 (HGS2'nin kullandığı Spring Boot test altyapısı) | Testcase düzeyinde özellik üretip üretmediği **doğrulanmadı** |
  | HGS2'deki özel test yardımcısı | Yok; tek test sınıfı var |

  HGS2 tarafında bir yol seçilip denenmeden gerçek raporların bu kimliği taşıyacağı varsayılmamalıdır.

### Gerçek beklentiler ne zaman doğrulanmış sayılır?

N7 kuralları aynen geçerlidir. `scope: real` olan bir beklentinin `VERIFIED` olabilmesi için beklenen her alanın en az
bir **incelenmiş** (`review_status: REVIEWED`) kanıtla desteklenmesi gerekir. Kanıtın kaynak türü şunlardan biri
olmalıdır: `existing_test`, `official_documentation`, `approved_business_rule` veya `manual_review`.

- Kaynak kod incelemesi ve sentetik fikstür gerçek kapsamda doğrulayıcı sayılmaz.
- Bir referansın bulunması içeriğin incelendiği anlamına gelmez.
- Bir testin PASS olması test kapsamı dışındaki davranışı doğrulamaz.

`readiness check`, her gerçek kapsam beklentisi için bir kontrol listesi üretir:

- kimlik, sürüm ve senaryo;
- tanımlı ve tanımsız (bilinmeyen) alanlar;
- kanıt sayısı ve kanıt yeterliliği bulguları;
- `VERIFIED` durumunu engelleyenler;
- çelişki.

### Önkoşul denetimi (`readiness check`)

```
hgs2-lab readiness check --report TEST-a.xml --expectations beklentiler.json --scope real --output hazirlik.json
```

| Grup | Denetimler (`fail` = engelleyici) |
|---|---|
| A. Rapor | A1 raporlar okunabiliyor (hiçbiri değilse fail), A2 kaynak sonuçlar belirlenebiliyor (kayıt yoksa fail), A3 senaryo kimliği kapsamı (hiç yoksa fail), A4 kimlik kalitesi, A5 ayrıştırma kalitesi |
| B. Beklenti | B1 sürüm 2 sözleşmesi verildi ve geçerli (yoksa, geçersizse veya sürüm 1 ise fail), B2 çelişkili etkin beklenti, B3 kapsamda VERIFIED beklenti (hiç yoksa fail), B4 rapordaki kimliklerin kapsamdaki beklentilerle örtüşmesi (hiç yoksa fail), B5 kanıt bulguları |
| C. Güvenlik | C1 N1 maskelemesi sentetik kanarya değerleri gizliyor, C2 XXE/DOCTYPE reddi, C3 suite/testcase özellikleri sızmıyor (yalnızca kimlik okunuyor), C4 çevrimdışı |
| D. Hat | D1 ayrıştırıcı → senaryo çözümlemesi → eşleştirme → sınıflandırıcı → JSON çalışıyor ve sayaçlar tutarlı |
| N10 (yalnızca `--scenario-map` ile) | A6 eşleme dosyası geçerli (geçersiz/eksik/bozuk/desteklenmeyen sürüm: fail; çelişkili eşleme: warn), C5 eşleme öz-testi (çelişki seçilmiyor, ad türetilmiyor, hassas tanımlayıcı sızmıyor). A3, A4 ve B4 çözümlenen kimliklerle hesaplanır |

Sonucun yorumu:

| Sonuç | Anlamı |
|---|---|
| `READY` | Bütün denetimler geçti |
| `READY_WITH_WARNINGS` | Engelleyici yok, uyarı var |
| `BLOCKED` | En az bir engelleyici var (`blocking` listesi) |

**READY, HGS2'nin doğru çalıştığını veya beklentilerin gerçek dünyada doğru olduğunu göstermez.** Yalnızca bu
önkoşulların karşılandığını gösterir. Dosyaların bulunması da iş kurallarının doğrulanması değildir.

Bugünkü durumda gerçek HGS2 raporu için sonuç **BLOCKED**'dır. Nedenleri:

- senaryo kimliği yok;
- gerçek kapsamda doğrulanmış beklenti yok.

### Veri alım sözleşmesi (`ingest analyze`, `ingestion_version: 1`)

Gerçek hata örnekleri ileride elde edildiğinde mevcut hatta bu biçimle aktarılır. Yeni bir kayıt modeli yoktur;
`record` alanı mevcut `TestRecord` sözlüğüdür (kayıt şeması 1 veya 2):

```json
{"ingestion_version": 1, "batch_id": "hgs2-hata-ornek", "dataset_kind": "real",
 "entries": [{"source_record_id": "surefire-TEST-x#t1",
              "source_reference": {"source_file": "TEST-x.xml", "source_sha256": "<64 hex>", "location": "t1"},
              "test_scope": "kart okutma ret akışı",
              "label_review": {"status": "REVIEWED", "evidence_ref": "INCELEME-12", "reviewer_role": "qa"},
              "record": {"record_id": "r-1", "source_type": "junit_xml", "dataset_kind": "real",
                         "test_outcome": "FAIL", "scenario_id": "kart-pasif-cihaz",
                         "label": "APPLICATION_FAILURE", "label_source": "human_review"}}]}
```

Kurallar:

- **Veri türü:** paketteki her kayıt aynı `dataset_kind` değerini taşır; gerçek ve sentetik kayıtlar karışamaz.
  Gerçek pakette `synthetic_plan` etiketi reddedilir.
- **Kaynak kimliği:** `source_record_id` zorunlu ve benzersizdir. Aynı kaynak kimliği veya aynı `record_id` ikinci
  bağımsız örnek sayılmaz (`duplicates`).
- **Etiket:** etiket ancak üç koşul birlikte sağlanırsa doğrulanmış (`human_review`) kabul edilir: `REVIEWED`
  inceleme, `evidence_ref` ve `source_reference`. Aksi halde etiket kayıttan çıkarılır ve `proposed_label` olarak
  raporlanır. Gerçek hata olduğu kanıtlanmamış bir kayıt gerçek hata diye etiketlenmez.
- **Eksik alanlar:** bilinmeyen alanlar `null` kalır; kaynak sonuç `UNKNOWN` olabilir. Kaynak referansı yoksa
  `source_reference_missing` uyarısı verilir.
- **Maskeleme:** metinler N1 maskelemesinden geçer; çıktı ham gövde, log veya rapor içermez.
- **Hatalı girdiler:** hatalı bir girdi diğerlerini durdurmaz (`ingestion_rejected`). Zarf geçersizse hiçbir şey
  yazılmaz.
- **Analiz:** kabul edilen kayıtlar isteğe bağlı beklentiyle eşleştirilir ve N4 ile sınıflandırılır. Kayıtta gömülü
  bir `expected_result` varsa registry onu değiştirmez (`embedded_expected_result_kept`).

## Senaryo eşleştirme ve uçtan uca kabul (N10; `scenario_mapping.py`)

**Bu katman yalnızca sentetik raporlarla doğrulandı. Gerçek HGS2'ye bağlanılmadı, testleri çalıştırılmadı ve gerçek
HGS2 için eşleme veya beklenti yazılmadı.**

### Seçilen strateji

İki açık kaynak birlikte kullanılır. Hiçbiri diğerine üstün sayılmaz.

| Kaynak | Görevi | Durum |
|---|---|---|
| Testcase metadata'sı (`hgs2_lab.scenario_id`, N3) | Testin kendisi kimliğini rapora yazar | pytest ile doğrulandı; **Maven Surefire + JUnit 5 ile doğrulanmadı** |
| Eşleme dosyası (`scenario_mapping_version: 1`) | Test kodu değiştirilmeden, rapordaki kararlı test tanımlayıcısını senaryoya bağlar | Sürümlü, denetlenebilir, Lab tarafında |

Neden ikisi birden?

- Gerçek HGS2 raporunda metadata yoktur ve Surefire'ın bu özelliği üretip üretmediği bilinmez. Yalnızca metadataya
  dayanmak bugün hiçbir gerçek kaydı eşleştiremez.
- Eşleme dosyası HGS2 kodunu değiştirmeden çalışır.
- Metadata zaten N3'te uygulanmıştı. Ek maliyet yalnızca eşleme dosyası ve iki kaynağı birleştiren kuraldır.

### Kararlı test tanımlayıcısı

Tanımlayıcı, rapordaki testcase `classname` ve `name` özniteliklerinin birebir yazımıdır: `<classname>#<name>`.
N3'ün `test_id` biçimiyle aynıdır.

- **Yalnızca ikisi birlikte varsa** tanımlayıcı vardır. Sınıfsız veya adsız kayıt eşlenmez (`identifier_missing`).
  Eksik sınıf adı suite adından **türetilmez**.
- Maskeleme tanımlayıcıyı değiştirdiyse rapordaki gerçek ad bilinemez (`identifier_unstable`).
- Benzerlik, önek, joker veya büyük/küçük harf duyarsız eşleştirme yapılmaz.
- `record_id` tanımlayıcı olarak kullanılmaz. Rapor içeriğinin SHA-256'sından ve kaydın konumundan türetildiği için
  her yeni çalıştırmada değişir.

**Sınırlamalar:**

- Test sınıfı veya metodu yeniden adlandırılırsa eşleme kaydı güncellenmelidir. Eski kayıt sessizce yeni teste
  uygulanmaz; test `not_mapped` olur.
- Parametreli testlerin adları (ör. `[1]`, `(String)`) çağrı sırasına veya araç sürümüne bağlı olabilir. Böyle adlar
  zayıf tanımlayıcıdır.
- Surefire'ın gerçek HGS2 raporlarında `name` özniteliğini nasıl yazdığı (ör. `contextLoads` / `contextLoads()`)
  araç sürümüne göre değişebilir. Eşleme dosyası her zaman gerçek rapordan okunarak hazırlanmalıdır.

### Eşleme dosyası şeması (`scenario_mapping_version: 1`)

```json
{"scenario_mapping_version": 1,
 "mapping_set_id": "lab-n10-ornek",
 "mappings": [
   {"mapping_id": "map-kart-pasif", "test_class": "com.example.lab.KartTests", "test_name": "kartPasifCihaz",
    "scenario_id": "kart-pasif-cihaz", "status": "ACTIVE", "evidence_ref": "N10-ESLEME-01",
    "description": "Sentetik örnek"}
 ]}
```

| Alan | Zorunlu | Kural |
|---|---|---|
| `scenario_mapping_version` | evet | Yalnızca `1`; başka sürüm reddedilir |
| `mapping_set_id` | hayır | Güvenli kimlik |
| `mappings[].mapping_id` | evet | Güvenli kimlik, dosyada benzersiz |
| `mappings[].test_class` / `test_name` | evet | Rapordaki yazımla birebir. Baş/son boşluk ve kontrol karakteri içermez. `test_class` `#` içermez. Maskelenecek bir kalıp (ör. `token=…`) içeren tanımlayıcı reddedilir |
| `mappings[].scenario_id` | evet | `hgs2_lab.scenario_id` ile aynı biçim |
| `mappings[].status` | evet | `ACTIVE` veya `DEPRECATED` (DEPRECATED kayıt eşleştirmede kullanılmaz) |
| `mappings[].evidence_ref` | hayır | Eşlemenin dayanağı; mutlak yerel yol olamaz, maskelenir |
| `mappings[].description` | hayır | Maskelenir |

Dosya doğrulaması N7 registry'si gibi bütünseldir. Tek bir hata bile dosyayı reddeder ve bütün bulgular
listelenir. Kısmen yüklenmiş eşlemeyle analiz yapılmaz. Şu durumlarda dosya reddedilir:

- dosya boş, bozuk JSON veya UTF-8 değil;
- sürüm desteklenmiyor;
- zorunlu alan eksik veya bilinmeyen alan var;
- geçersiz kimlik;
- yinelenen `mapping_id`;
- **yinelenen eşleme**: aynı test için aynı senaryoya giden ikinci bir ACTIVE kayıt.

Aynı test için **farklı** senaryolara giden ACTIVE kayıtlar dosyayı geçersiz kılmaz. `conflicts` altında raporlanır
ve o test için kimlik seçilmez.

```
hgs2-lab scenario-map validate --file esleme.json
```

### Çözümleme: çakışma ve belirsizlik

| `status` | `outcome` | Ne zaman | Kimlik |
|---|---|---|---|
| `metadata` | resolved | Yalnızca geçerli testcase özelliği | Özellik değeri |
| `mapping` | resolved | Yalnızca ACTIVE eşleme (tek senaryo) | Eşleme değeri |
| `metadata_and_mapping` | resolved | İkisi de var ve **aynı** | O kimlik |
| `no_source` | not_found | Metadata yok, eşleme dosyası verilmedi | yok |
| `not_mapped` | not_found | Metadata yok, eşleme dosyasında bu test yok | yok |
| `deprecated_only` | not_found | Metadata yok, yalnızca DEPRECATED eşleme var | yok |
| `identifier_missing` / `identifier_unstable` | ambiguous | Metadata yok; tanımlayıcı yok veya güvenilmez | yok |
| `metadata_invalid` | ambiguous | Testcase özelliği geçersiz (eşleme varsa da kullanılmaz) | yok |
| `metadata_conflict` | conflict | Aynı testte farklı özellik değerleri (N3) | yok |
| `metadata_mapping_conflict` | conflict | Metadata ve eşleme **farklı** | yok |
| `mapping_conflict` | conflict | Farklı senaryolara giden birden fazla ACTIVE eşleme | yok |

`ambiguous` ve `conflict` kayıtlar incelemeye düşer (`requires_review`). Adaylar `candidate_scenario_ids` altında
listelenir ama hiçbiri seçilmez. Öncelik kuralı yoktur: metadata eşlemeden, eşleme metadatadan üstün değildir.

Eşleme dosyası verildiğinde her kayda `scenario_resolution:<status>` uyarısı eklenir ve `scenario_id` çözülen
kimlik olur. Çözülemediyse `null` olur. Çelişkide mevcut N4 sözleşmesi gereği `scenario_id_conflict` de eklenir.
Böylece sınıflandırıcı, beklenti istendiğinde kaydı kural değişikliği olmadan incelemeye düşürür. Kaynak test sonucu
hiçbir durumda değişmez. Eşleme dosyası verilmezse kayıtlar N8'deki gibi aynen işlenir.

### N7 registry'si ve N4 ile birleşme

Akış:

```
JUnit/Surefire raporu → N3 ayrıştırıcı → TestRecord → senaryo çözümlemesi (metadata + eşleme dosyası)
  → N7 registry eşleştirmesi → N4 sınıflandırıcı → JSON belge → readiness
```

Yeni bir beklenti sistemi veya sınıflandırma kuralı yoktur. N7 registry'si ve N4 kuralları değiştirilmedi.

Belgedeki `scenario_trace` listesi her kayıt için şu katmanları **ayrı** alanlarda taşır:

| Alan | Katman |
|---|---|
| `source_file`, `source_sha256`, `test_id`, `test_name` | Kaynak referansı (dosya adı + özet; yol yok) |
| `source_test_outcome` | Kaynağın kendi sonucu; değişmez |
| `scenario` | Çözümleme (`status`, `outcome`, `sources`, `mapping_ids`, adaylar, `requires_review`) |
| `expectation` | Eşleşme durumu, beklenti kimliği ve sürümü, doğrulama durumu, kapsam, `scope_compatible` |
| `decision_basis` | Beklentinin kesin karşılaştırmaya uygunluğu (aşağıda) |
| `outcome_vs_expectation`, `expectation_assessment` | Kaynak sonucun beklenen sonuçla karşılaştırması |
| `classification` | N4 kararı, kurallar, güven, gerekçe, uyarılar |
| `requires_review`, `review_reasons` | Çözümleme veya N4 kaynaklı inceleme gereksinimi |

`decision_basis` değerleri:

| Değer | Anlamı |
|---|---|
| `no_scenario_id` | Kimlik çözülemedi; beklenti aranmadı |
| `no_expectations` | Beklenti dosyası verilmedi |
| `expectation_not_found` / `expectation_deprecated_only` / `expectation_conflict` | Kimlik var ama tek bir etkin beklenti yok |
| `expectation_unverified` | DRAFT veya REVIEWED; kesin teşhis gerekçesi olamaz |
| `expectation_verification_unspecified` | Sürüm 1 dosyası; doğrulama durumu yok |
| `expectation_scope_mismatch` / `expectation_scope_unconfirmed` | Beklentinin kapsamı kaydın veri türüyle uyuşmuyor veya veri türü bilinmiyor |
| `expectation_not_comparable` | Beklenti yalnızca HTTP durumu, iş sonucu veya taşıma tanımlıyor; JUnit kaydında gözlenemez |
| `verified_expectation_in_scope` | VERIFIED, kapsamda ve karşılaştırılabilir |

`expectation_assessment` değerleri:

| Değer | Ne zaman |
|---|---|
| `consistent` | Uygun beklenti var ve kaynak sonuç beklenene eşit |
| `inconsistent` | Uygun beklenti var ve kaynak sonuç farklı (ör. VERIFIED PASS beklentisi, kaynak FAIL) |
| `undetermined` | Diğer her durum. Uygun beklenti yoksa, ya da test çalıştırılmadıysa (SKIPPED) veya sonucu bilinmiyorsa (UNKNOWN) |

Bu değerlendirme N4 kararını **değiştirmez**:

- kaynak FAIL hiçbir zaman PASS olmaz;
- SKIPPED başarı sayılmaz;
- beklenti bulunmaması iş başarısızlığı sayılmaz;
- HTTP 200 veya iş sonucu JUnit kaydından uydurulmaz;
- F5 anomali puanı kullanılmaz.

### Kullanım (yalnızca sentetik veriyle)

```
hgs2-lab scenario-map validate --file tests/fixtures/scenario-mapping/n10-mapping.json
hgs2-lab junit classify --report tests/fixtures/scenario-mapping/n10-report.xml \
    --scenario-map tests/fixtures/scenario-mapping/n10-mapping.json \
    --expectations tests/fixtures/scenario-mapping/n10-registry.json --dataset-kind synthetic --output n10.json
hgs2-lab readiness check --report tests/fixtures/scenario-mapping/ready-unlabeled.xml \
    --scenario-map tests/fixtures/scenario-mapping/ready-mapping.json \
    --expectations tests/fixtures/readiness/ready-registry.json --scope synthetic
```

`junit classify` çıktısı, eşleme sayaçlarını ve beklenti uygunluğunu da yazdırır:

- senaryo çözümlemesi (`mapping=9, metadata=1, …; inceleme gerektiren 4`);
- beklenti uygunluğu;
- değerlendirme dağılımı.

Belgedeki ek alanlar:

| Alan | İçerik |
|---|---|
| `classification.summary.scenario_resolution` | `by_status`, `by_outcome`, `by_source`, `requires_review`, `by_decision_basis`, `by_expectation_assessment` |
| `classification.scenario_mapping` | Dosya adı, SHA-256 ve kanonik `content_sha256` |
| `classification.scenario_trace` | Kayıt başına iz |

**Determinizm.** Aynı girdiler aynı `content_sha256`'yı üretir. Eşleme dosyasındaki kayıt sırası çözümlemeyi ve
kanonik `content_sha256`'yı değiştirmez. Rapor sırası kayıt başına sonuçları ve sayaçları değiştirmez. Belgedeki
`records` ve `scenario_trace` listeleri ise N8 sözleşmesi gereği girdi sırasını izler; bu yüzden farklı rapor
sırası farklı belge özeti verebilir.

### Readiness'e etkisi

`readiness check --scenario-map` verildiğinde:

- A3 (kimlik kapsamı), A4 (kimlik kalitesi) ve B4 (beklenti örtüşmesi) çözülen kimliklerle hesaplanır;
- A4 metadata/eşleme çelişkisini, çoklu eşlemeyi ve tanımlayıcı eksikliğini ayrı sayar;
- A6 eşleme dosyasını denetler: geçersiz, eksik veya desteklenmeyen sürüm `fail`, çelişkili eşleme `warn` olur;
  rapordaki testlere karşılık gelmeyen ACTIVE kayıtlar listelenir;
- C5 eşleme öz-testini çalıştırır;
- D1 ayrıntılarına çözümleme sonucu, karar dayanağı ve değerlendirme dağılımı eklenir.

Eşleme dosyası verilmezse denetim kümesi N9 ile aynıdır.

### Sentetik ve gerçek kapsam

`ready-unlabeled.xml` + `ready-mapping.json` sentetik kapsamda READY verir. Aynı dosyalar gerçek kapsamda BLOCKED
kalır. Eşleme dosyası yalnızca "hangi test hangi senaryodur" sorusunu yanıtlar. Hiçbir beklentiyi doğrulamaz.
Sentetik kapsamdaki VERIFIED beklenti gerçek veya bilinmeyen veri türündeki kayıtta kesin karşılaştırmaya
kullanılmaz (`expectation_scope_mismatch` / `expectation_scope_unconfirmed`).

### Gerçek entegrasyon ne zaman BLOCKED kalır?

Aşağıdakilerden biri eksik olduğu sürece gerçek kapsamda sonuç BLOCKED'dır. Bugün hepsi eksiktir:

1. **Senaryo kimliği.** Gerçek HGS2 raporundaki testler için ya Surefire + JUnit 5'in `hgs2_lab.scenario_id`
   özelliğini ürettiği gerçek bir raporla doğrulanmalı, ya da gerçek rapordaki `classname`/`name` değerlerinden
   hazırlanmış, gerekçesi (`evidence_ref`) olan bir eşleme dosyası yazılmalıdır. Bugünkü tek gerçek test
   (`contextLoads`) bir bağlam yükleme testidir; hangi senaryoyu sınadığına ancak HGS2 tarafında karar verilebilir.
2. **Gerçek kapsamda VERIFIED beklenti.** N7 kurallarına göre incelenmiş, doğrulayıcı kaynaklı kanıtlar gerekir
   (resmî belge, onaylı iş kuralı, mevcut test veya el ile inceleme; kaynak kod incelemesi ve sentetik fikstür
   sayılmaz).
3. **Örtüşme.** Rapordaki çözülen kimliklerin gerçek kapsamdaki etkin beklentilerle örtüşmesi (B4).

Sentetik testler bu eksikleri dolduramaz.

## Testler

| Amaç | Komut |
|---|---|
| Birim testleri (varsayılan; entegrasyon testleri "deselected" olarak sayılır) | `pytest -p no:cacheprovider` |
| Yalnızca yerel HTTP entegrasyon testleri | `pytest -p no:cacheprovider -m integration` |
| Hepsi | `pytest -p no:cacheprovider -m "integration or not integration"` |

Windows'ta proje ortamıyla: `.\.venv\Scripts\python.exe -m pytest ...`. `--strict-markers` etkindir.

**Birim testleri** ağ ve soket kullanmaz; taşıyıcı, saat, `sleep` ve ad çözümleyici sahtedir. Hedef koruması,
yürütme ve CLI testlerinde her soket bağlantı girişimi testi başarısız kılar. Git metadata'sı sahte `subprocess.run`
ile sınanır; yalnızca bir duman testi yerel `git` komutunu salt okuma amaçlı çalıştırır.

Analiz katmanı testleri (birim):

* `tests/test_golden.py`: `tests/golden/` altındaki gerçek eski yazıcılarla üretilmiş v1/v2 dosyaları; bayt bayt
  değişmezlik (SHA-256), mevcut ve yeni okuyucularla okuma, v1'in reddi, yeni yazıcının v2 sözleşmesini koruması.
* `tests/test_reader.py`: sürüm politikası, dosya keşfi, bozuk/eksik/tutarsız girdiler, metadata doğrulaması.
* `tests/test_clock.py`: saat çapasının okuma sırası, belirsizlik penceresi, doğrulama, runner ve metadata entegrasyonu.
* `tests/test_analysis.py`: yüzdelik doğruluğu (elle hesaplanan değerler ve `statistics.quantiles` ile), sıfır/tek/küçük
  örneklem, ısınma ayrımı, HTTP/taşıma hatası ayrımı, throughput, bootstrap determinizmi, üzerine yazmayan çıktı.
* `tests/test_cli_analyze.py`: `analyze` komutu; her testte soket, ad çözümlemesi ve `requests` oturumu engellenir;
  analiz modüllerinin ağ kodunu içe aktarmadığı alt süreçte denetlenir.
* `tests/test_synthetic.py`: manifest doğrulaması (eksik/bilinmeyen alan, geçersiz hata türü, negatif/aşırı gecikme,
  sınırlar), seed ile plan tekrarlanabilirliği, etiketleme (beklenen/gözlenen ayrımı, uyumsuzluk, kısmi çalıştırma,
  sunucu tutarsızlıkları), alan rolleri, `dataset_kind` doğrulaması, `synthetic validate/plan` komutları; bekleme
  yöntemi (planlanandan kısa olmama, durdurmaya bir dilim içinde tepki, meşgul bekleme olmaması), istemci gitse bile
  gerçekleşen beklemenin kaydı, `server_hold_short` denetimi ve dört süre kavramının ayrı alanlarda tutulması.
* `tests/test_campaign.py`: kampanya manifesti doğrulaması, (plan × seed) deterministik açılım, seed'in yalnızca rastgele
  çekilişleri değiştirmesi, güvenli göreli yollar, deterministik grup ataması, oranlar, sahte yürütücüyle hata yalıtımı
  (hata/ret/geçersiz deney diğerlerini etkilemez), Ctrl+C'de `not_run` ve katalog yazımı, dolu çıktı dizininin reddi,
  modüllerin ağ kodunu içe aktarmaması.
* `tests/test_features.py`: CSV biçim kuralları (boş değer, bool, int, float, alıntılama, LF), sütun rolleri
  (`hold_ms_actual` ve diğer etiket/tasarım sütunlarının özellik dosyasında olmaması), veri seti manifestinin özet ve
  biçim denetimi, dolu çıktı dizininin hiçbir şey yazılmadan reddi, modülün ağ kodunu içe aktarmaması.
* `tests/test_robust_z.py`: Robust Z-score — log uzayında medyan/MAD, büyük gecikmenin işaretlenmesi ve katı üst
  kuyruk eşiği, düşük gecikmenin anomali sayılmaması, determinizm, MAD = 0 (`degenerate_baseline`), sıfır / negatif /
  NaN / ±inf / null / sayı olmayan girdiler, yalnızca `duration_ms` izin listesi, konum/tasarım/etiket alanlarının
  skorları değiştirmemesi, kalibrasyonun yalnızca train normal satırlarından yapılması, epizot tanımı, epizodun tek
  kez sayılması, tespit edilmeyen epizodun paydada kalması, istek cinsinden gecikme, wall-clock gecikmesinin
  uydurulmaması, başarısız isteklerin normal sınıfa ve recall paydasına girmeyip `operational_failures`'ta ayrı
  sayılması, sıfır paydalı metrikler, tablo bütünlüğü, deterministik ve üzerine yazmayan çıktı, CLI, ağ kodu içe aktarmama.
* `tests/test_telemetry.py`: telemetri örnek biçimi ve zaman damgaları, saat çapasına göre ofset, gerçek saatle periyodik
  örnekleme (planlanan andan önce örnek yok), örnek sınırı, okuma hatası / kullanılamayan grup / beklenmeyen istisna /
  eksik alanın değer uydurulmadan kaydı, türetilmiş CPU oranları, aralık doğrulaması, desteklenmeyen platform, Windows'ta
  gerçek sayaçların salt okunur okunması, ağ kodu içe aktarmama, belgede etiket/konum alanı olmaması; `execute_run` ile
  ayrı dosya ve **bayt bayt aynı** v2 sonuçları, kısmi/Ctrl+C çalıştırma, üzerine yazmama, telemetri hatasında sonuçların
  korunması, okuyucu/analizin etkilenmemesi, CLI seçenekleri.
* `tests/test_campaign_baseline.py`: baseline kampanya manifesti — 12 plan × 3 seed, benzersiz kimlikler, deterministik
  plan, seed tekrarlarının aynı grup ve tasarımda kalması, tüm hata türleri ve `onset_after`, her anomali planının
  normal bölümle başlaması, güvenlik sınırı tahmini, test bölümünün yapısal sınıf kapsamı sınırlılığı.

**Entegrasyon testleri** (`integration` işaretli):

* `tests/test_http_transport_local.py`: `RequestsTransport`'u gerçek soket üzerinden sınar (GET, JSON POST, HTTP 500,
  izlenmeyen yönlendirme, gecikmeli gövde, okuma zaman aşımları ve istisna zinciri, gzip boyutu, ortam proxy'si).
* `tests/test_run_local.py`: `hgs2-lab run`'ı uçtan uca sınar (sonuç dosyaları, metadata, `target_label`,
  maskeleme, zaman aşımıyla kontrollü durdurma, loopback dışı hedefin reddi, `localhost` adıyla doğrulanmış
  bağlantı, DNS rebinding'in bağlantı kurulmadan engellenmesi, gerçek saatlerle saat çapası ve ardından sunucuya istek
  göndermeden `analyze`).
* `tests/test_synthetic_server.py`: sentetik sunucunun başlatılması/kapatılması, yalnızca `127.0.0.1`'e bind, port
  çakışması, geçersiz yapılandırma, her hata türü, plan dışı istekler, olay kaydı sınırı, eşzamanlılık sınırı, kapanışta
  bekletilen isteklerin serbest bırakılması, gerçek soket üzerinden bekleme alanlarının sırası ve istemci süresinin
  beklemeyi kapsaması; her testte iş parçacığı kalmadığı denetlenir.
* `tests/test_synthetic_run.py`: `synthetic run` uçtan uca (gerçek `RequestsTransport`), sonuçların `analyze` ile
  okunması, etiket ve sunucu olaylarının doğrulanması, aynı seed ile aynı plan, kısmi (durdurulan) ve beklentiyle
  çelişen deneylerin geçersiz raporlanması, hedef korumasının atlatılamaması, üzerine yazmama, zaman aşımı
  beklemeleri sonraki isteklerle çakıştığında istek–sunucu olayı eşleştirmesinin korunması, planlanan/gerçekleşen
  bekleme ve istemci süresinin ayrı kaydedilmesi (sonuç dosyasına sızmaması), beklenmeyen hatada sunucunun kapatılması.
* `tests/test_robust_z_run.py`: gerçek yerel sunucuyla kampanya → veri seti → özellik tablosu → `detect robust-z`;
  kalibrasyonun bağımsız yeniden hesapla eşleşmesi, skorların yalnızca `duration_ms`'ten gelmesi, HTTP hatalarının
  dışarıda kalması, girdi dosyalarının değişmemesi.
* `tests/test_telemetry_run.py`: `synthetic run --telemetry` uçtan uca; telemetri dosyası, sonuç dosyası özetleri, aynı
  saat ekseninde isteklerin kapsanması, loopback bağlantılarının TCP sayaçlarında görünmesi, etiketlerin ve `analyze`'ın
  telemetriden bağımsız kalması.
* `tests/test_campaign_run.py`: gerçek yerel sunucuyla kampanya (geçerli ve güvenlik sınırıyla durdurulan deneyler),
  katalog özetlerinin dosyalarla eşleşmesi, bozuk/eksik dosya, güvensiz yol, özeti güncellenmiş ama tutarsız etiket ve
  değiştirilmiş kampanya manifestinin yakalanması, veri setinin determinizmi, grup/çalıştırma bütünlüğü, geçersiz deney
  politikası, eksik sınıf raporu, özdeş tasarım uyarısı, oran sapması, özellik dosyasına sızdırılmış etiket anahtarının
  yakalanması, loopback korumasının her deneyi istek göndermeden reddetmesi, hatalı deneyde sunucu temizliği, CLI akışı.
* `tests/test_features_run.py`: gerçek kampanyadan özellik tablosu; bayt bayt determinizm, manifest özetleri, sabit
  sütun/satır sırası, her satırın kaynak kayıt, run_id ve bölümle eşleşmesi, bölüm sayımlarının veri setiyle uyumu,
  etiketlerin özellik dosyasına sızmaması, geçersiz deneylerin politikaya uygunluğu, değiştirilmiş/eksik kaynak dosya,
  değiştirilmiş bölme kararı, sonradan değişen katalog ve geçersiz kampanyanın reddi, CLI ve üzerine yazmama.
* `tests/test_campaign_baseline_run.py`: baseline manifestinin her hata ailesini kapsayan alt kümesi gerçek sunucuda;
  tüm senaryoların desteklenip `confirmed` etiket üretmesi, sayımların katalog/sonuç/etiket/veri seti/CSV arasında
  tutarlılığı, değişim noktası etiketlerinin gözlemlerle uyumu ve özellik dosyasına sızmaması, grup/çalıştırma bütünlüğü.

Test sonucu analizi testleri (birim; ağ yok, sentetik fikstürler `tests/fixtures/junit/`):

* `tests/test_sanitize.py`: HGS2 kişisel parametreleri ve varyasyonları, benzer ama hassas olmayan alanlar, URL/form/JSON
  (iç içe, liste, bozuk), log, header ve stack trace satırları, bağlantı dizeleri, idempotentlik, desteklenmeyen türler.
* `tests/test_records.py`: `TestRecord` doğrulaması, JSON gidiş-dönüşü, eksik/geçersiz alanlar, maskeleme sınırı,
  kaynak sonucu ile analiz sonucunun ayrımı, `RawResult` dönüşümü.
* `tests/test_junit_report.py`: PASS/FAIL/ERROR/SKIPPED, birden çok suite, boş suite, eksik isteğe bağlı alanlar,
  çelişkili ve geçersiz değerler, okunmayan bölümler, boş/bozuk/bulunamayan dosya, XXE ve varlık genişletme, boyut
  sınırı, kırpma, 5 000 testlik rapor, UTF-16 ve ad alanı.
* `tests/test_classify.py`: her sınıf ve kural; beklenen ret ile beklenmeyen ret, bilinmeyen beklenti, gövdesiz
  HTTP 200, 4xx/5xx, zaman aşımı, taşıma ve altyapı hataları, çelişkiler, kanıtta hassas değer olmaması, süreden
  bağımsızlık.
* `tests/test_junit_pipeline.py`: fikstürlerden uçtan uca belge ve `junit classify` komutu, determinizm, üzerine
  yazmama, çıktıda hassas değer veya yerel yol olmaması, modüllerin ağ koduna ve F5'e bağımlı olmaması.
* `tests/test_response_parser.py`: tanınan değerler, alt dize eşleşmemesi, JSON metni/alanı, iç içe ve eşanlamlı
  alanların aranmaması, bozuk JSON, boş/yakalanmamış gövde, desteklenmeyen/eksik/geçersiz içerik türü, charset,
  boyut sınırı (sınırda ve bir bayt fazla), geçersiz durum kodu, rastgele baytlar, özette gövde içeriği olmaması,
  `from_dict` doğrulaması.
* `tests/test_business_outcome.py`: gerçek `ScenarioRunner` + sahte taşıyıcı → TestRecord → N4; davranış tablosunun
  tüm satırları, kaynak `FAIL`/`SKIPPED` sonucunun korunması, özet/sonuç tutarlılığı, `RawResult` şemasının
  değişmemesi, gövdedeki kişisel değerlerin hiçbir çıktıya ulaşmaması.
* `tests/test_result_analysis.py`: `execute_run` (sahte taşıyıcı) → sonuç dosyaları + `response_parsing` →
  `results classify`; beklenti dosyası doğrulaması, beklenti kaynakları, ısınma atlama, eski/tutarsız/bozuk
  metadata, veri türü çözümlemesi, determinizm, üzerine yazmama, girdilerin değişmemesi.
* `tests/test_business_outcome_local.py` (entegrasyon): gerçek `RequestsTransport` ile yerel sunucudaki HGS2 benzeri
  gövdeler → `run` → `results classify`; sentetik deneyin geçerliliğinin ve boş `business_outcome`'un korunması.
* `tests/test_expectations.py`: beklenti modeli (zorunlu alanlar, enum, durum kodu, çelişki, bilinmeyen iş sonucu,
  sürüm), doğrulama durumları ve kanıt yeterliliği (incelenmemiş, desteksiz alan, gerçek kapsamda kod
  incelemesi/fikstür, çürüten kanıt), kanıt referansları (mutlak yol, maskeleme), registry (boş/bozuk/eksik dosya,
  kısmi hata, yineleme, çelişki, determinizm, dosyanın değişmemesi), eşleştirme, CLI, değer sızdırmayan hata
  mesajları, ağ kodundan bağımsızlık.
* `tests/test_expectations_pipeline.py`: A–H senaryoları (doğrulanmış/taslak/incelenmiş/kaynaksız/çelişkili
  beklenti, kaynak FAIL/SKIPPED, HTTP 200 + gövdesiz), taşıma ve kapsam kuralları; sentetik yanıt → ayrıştırıcı →
  TestRecord → registry → N4 → JSON uçtan uca; geçersiz registry'nin reddi; sürüm 1 uyumu.
* `tests/test_junit_analysis.py`: testcase özelliğinden senaryo kimliği (değer/metin, eksik, geçersiz, çelişkili,
  tekrar, suite düzeyi ve test adının kullanılmaması), eşleştirme durumları ve kaydın korunması, A–J senaryoları
  (PASS/FAIL + VERIFIED, kimliksiz kayıt, DRAFT, çelişkili beklenti, bozuk rapor, çoklu rapor sayaçları, hassas
  veri, eski şema ve sürüm 1, geçersiz/eksik registry), sayaçların kayıtlarla tutarlılığı, tekrar eden rapor ve
  test, kapsam uyarısı, gözlenemeyen beklenti alanları, determinizm, CLI ve üzerine yazmama.
* `tests/test_readiness.py`: rapor envanteri (tüm durumlar, değer içermemesi), gerçek/sentetik kapsam beklenti
  hazırlığı, READY / READY_WITH_WARNINGS / BLOCKED yolları, eksik/geçersiz/sürüm 1 registry, yetersiz meta veri,
  okunamayan/boş rapor, güvenlik öz-testleri (maskeleme devre dışı bırakılınca yakalanması), hassas değer ve
  kanarya sızmaması, isimden kimlik türetilmemesi, CLI çıkış kodları, ağ kodundan bağımsızlık.
* `tests/test_ingestion.py`: alım paketinin kabul/ret/tekrar kuralları, incelenmiş ve incelenmemiş etiket,
  gerçek/sentetik ayrımı, eksik isteğe bağlı alanlar, bilinmeyen sonuç, geçersiz girdi ve zarf, şema 1 kaydı,
  maskeleme, mevcut hatta (registry → N4) aktarım, CLI.
* `tests/test_scenario_mapping.py` (N10): eşleme dosyası (geçerli, boş, bozuk JSON, desteklenmeyen sürüm, şema
  hataları, eksik tanımlayıcı, geçersiz senaryo kimliği, yinelenen kimlik/eşleme, DEPRECATED, çelişkili eşleme,
  hassas tanımlayıcının değeri yazılmadan reddi, maskeleme), kararlı tanımlayıcı (sınıfsız/adsız/maskeli kayıt,
  `#` içeren ad), metadata yolları (geçerli/eksik/geçersiz/çelişkili/tekrar), çakışma ve belirsizlik (aynı/farklı
  kimlik, çoklu eşleme, bulunamama, suite veya test adından türetilmeme), kayıtlara uygulama, sıra bağımsızlığı.
* `tests/test_scenario_mapping_pipeline.py` (N10): uçtan uca kabul (rapor → kayıt → çözümleme → registry → kapsam ve
  doğrulama → N4 → JSON → readiness), çelişkili ve belirsiz eşlemelerin uçtan uca davranışı, beklenti entegrasyonu
  (VERIFIED + PASS/FAIL, SKIPPED, DRAFT, REVIEWED, kapsam uyuşmazlığı, çoklu beklenti, gözlenemeyen alanlar,
  registry'de olmayan senaryo), determinizm (tekrar, dosya ve eşleme sırası), readiness (READY/BLOCKED yolları,
  çelişki ve belirsizlik uyarıları, geçersiz eşleme dosyası, yalnızca DRAFT/REVIEWED, öz-testin sessiz öncelik
  kuralını yakalaması), CLI, hassas veri ve yerel yol sızıntısı, ağ kodundan bağımsızlık.

N11 testleri (gerçek HGS2 ile canlı entegrasyon testi DEĞİLDİR; yanıt biçimleri HGS2 kaynak kodundan statik olarak
çıkarılmış sentetik gövdelerdir):

* `tests/test_hgs2_contract.py` (birim): sözleşmedeki her yanıt biçiminin ayrıştırılması (`NONE`, `SCAN_*`,
  `{"status":"WAITING"}`, `{"status":"READY","value":…}`, `sessionId`, Spring biçimli hata), eksik/bilinmeyen/sayısal
  `status`, bozuk JSON, boş/çözülemeyen/desteklenmeyen gövde; `ONAYLANDI`/`REDDEDILDI` ayrımı, `READY`/`WAITING`'in
  onay sayılmaması, 2xx + bilinmeyen gövdenin PASS olmaması (`H-STATUS-OK-UNKNOWN-BODY`), beklenen 4xx'in durum
  koduyla kararı, `READY` gövdesindeki değerin hiçbir çıktıya yazılmaması.
* `tests/test_isolation_guard.py` (birim): süreç içi yalıtım kararı (loopback + bu süreçte bind edilmiş port),
  korumanın gerçek `connect`'i çağırmadan reddetmesi ve oturum boyunca kurulu olması; ayrılmış portların (`8080`,
  `5432`) taşıyıcıda, bağlantı katmanında ve `execute_run`'da bağlantı kurulmadan reddi.
* `tests/test_hgs2_contract_local.py` (entegrasyon): yerel sunucudaki HGS2 biçimli uçlar → `run` → `results classify`
  uçtan uca; yalnızca süreç içi sunucuya bağlanıldığı; kapalı sunucuda tek girişim, yeniden deneme ve başka hedef
  olmaması; dış adrese yönlendirmenin izlenmemesi; oturum korumasının bu sürecin açmadığı porta bağlantıyı engellemesi.
* `tests/test_sanitize.py` (ekler): `eskiNo`, `yeniNo`, `slot`, `fpSlot` maskelenir; `timeslot`, `slots` gibi benzer
  adlar maskelenmez.

N12 testleri (F-1 ve F-3; gerçek HGS2 ile canlı entegrasyon testi DEĞİLDİR):

* `tests/test_classify.py`, `tests/test_hgs2_contract.py`, `tests/test_business_outcome.py`,
  `tests/test_expectations_pipeline.py`, `tests/test_result_analysis.py` (ekler, `rules-v3`): 2xx + yalnızca durum kodu
  beklentisinde boş, 4 KiB'tan büyük, yakalanmamış, tanınmayan, bozuk JSON gövde, eksik/boş/bozuk ayrıştırma özeti
  (uçtan uca `records_from_run` ile) ve `WAITING`/`READY`/`NONE`/`SCAN_*` → `INCONCLUSIVE`; 204 + boş gövde, olumlu
  iş sonucu, açık ara durum beklentisi, beklenen 3xx/4xx/5xx ve beklenmeyen 5xx kararlarının değişmemesi.
* `tests/test_target_identity.py` (birim; sahte dinleyici okuyucusu): dinleyici politikası (süreç içi, bildirilmiş
  dış süreç, bildirilmemiş, ad eşleşmezliği, okunamayan ad, JVM/PostgreSQL, karışık dinleyiciler), doğrulayıcının
  önbelleği ve okuma hatası, `verify_target`, bağlantı katmanı, `execute_run`'ın istek ve dosya olmadan reddi, sahte
  taşıyıcıların denetlenmemesi, `target_process` yapılandırması, oturum korumasının bırakılmış port kararı.
* `tests/test_target_identity_local.py` (entegrasyon, yalnızca Windows): gerçek dinleyici tablosu; süreç içi
  dinleyicinin PID'i, Python alt sürecinin dinleyicisinin bildirim gerektirmesi (alt sürece istek gönderilmez),
  bildirilmemiş dış hedefe `run`'ın istek ve dosya olmadan reddi, bırakılmış portu başka bir süreç dinleyince oturum
  korumasının engellemesi, dinleyicisiz bırakılmış porta izin, tamamlanan çalıştırmada
  `execution.target_verification` kaydı.

Ağ sınırları: test sunucusu (`tests/local_http_server.py`) yalnızca `127.0.0.1`'e ve geçici bir porta bind eder.
`tests/conftest.py` tüm test oturumunda `isolation_guard`'ı kurar: hedef loopback IP'si değilse ya da port bu test
sürecinde bind edilmemişse bağlantı kurulmadan engellenir ve test başarısız sayılır (gerçek HGS2 ayrı bir süreçtir).
Her entegrasyon testinde `socket.socket.connect`/`connect_ex` sarılır; hedef `127.0.0.1` değilse bağlantı kurulmadan
test hata verir. Testlerdeki dış adresler (`203.0.113.0/24`, `2001:db8::/32`) belge aralıklarıdır ve yalnızca
reddedilmesi beklenen değerler olarak kullanılır. Zamanlama testleri yalnızca alt sınır doğrular.

## N11 kapanış kaydı: güvenli entegrasyon hazırlığı (2026-10-29)

**Kapsam:** yanıt ayrıştırıcısı (`response-parser-v2`), sınıflandırıcı (`rules-v2`), maskeleme (`eskiNo`, `yeniNo`,
`slot`), ayrılmış portlar, test süreci yalıtımı, HGS2 biçimli sentetik testler ve bu belge. F1–F5 (sentetik sunucu,
kampanya, veri seti, F4 telemetri, F5 Robust Z-score) değiştirilmedi. Gerçek HGS2'ye istek gönderilmedi, HGS2
başlatılmadı ve testleri çalıştırılmadı, PostgreSQL'e bağlanılmadı, donanımla iletişim kurulmadı. `results/`
dizinine yazılmadı.

Çalıştırılan testler (Windows 11, Python 3.15.0, `.venv`, `-p no:cacheprovider -rfE --tb=long`):

| Komut | Sonuç |
|---|---|
| `pytest` (birim; entegrasyon hariç) | 1444 passed, 97 deselected |
| `pytest -m integration` (3 tam tur) | her turda 97 passed, 1444 deselected |
| `pytest -m integration tests/test_synthetic_server.py::test_hold_fields_over_real_socket_and_client_time_includes_hold` (30 ayrı süreç) | 30/30 passed |

* Kararsız test adayı: README'nin F3-E kaydına göre 2026-10-24'teki tek başarısız entegrasyon çalıştırmasının test adı
  **kaydedilmemişti**; bu testin o test olduğu kanıtlanamaz. N11'de başarısızlık gözlenmedi; kök neden bilinmiyor ve
  sorun çözülmüş sayılmaz.
* Platform gözlemi (N11): Windows'ta kapalı bir loopback portuna bağlanma, işletim sisteminin bağlantı yeniden
  denemeleri nedeniyle 1–2 sn'lik zaman aşımında `timeout` olarak sonuçlanabildi (beklenen `connection_error`
  yerine). İlgili test hata türünü taşıma hatası olarak kabul eder; tek girişim ve aynı hedef koşulunu korur.
* Bu testlerin hiçbiri gerçek HGS2 ile canlı entegrasyon testi değildir. Gerçek kapsamda `readiness` BLOCKED kalır.

## N12 kapanış kaydı: F-1 / F-3 düzeltmeleri ve saklanmış test kanıtları (2026-10-29)

**Kapsam:** N11 sonrası denetimin F-1 (yalnızca durum kodu beklentisiyle yanlış PASS), F-3 (gerçek HGS2'nin yalnızca
port listesiyle ayrılması), F-10 (doğrulanabilir test çıktısı yok) ve F-11 (geri dönüş noktası yok) bulguları.
Gerçek HGS2 dizinine dokunulmadı, HGS2 başlatılmadı, API'sine istek gönderilmedi; PostgreSQL'e bağlanılmadı (bu
makinede `127.0.0.1:5432`'de bir PostgreSQL hizmeti ÇALIŞIYOR; yalnızca dinleyici tablosu okundu, bağlantı
kurulmadı); donanımla iletişim yok. F1–F5'e özgü modüller ve testleri değiştirilmedi. Commit/push yapılmadı.

**Yedek (F-11):** `C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\backups\backup-20261029T182428-pre-f1-f3\`
— değişikliklerden ÖNCEKİ çalışma ağacı (HEAD `1fe78f4` + 14 değiştirilmiş + 62 izlenmeyen dosya, `.git` dahil;
`.venv`/`__pycache__`/egg-info hariç; 337 dosya). `MANIFEST-source.sha256` (144 kaynak dosya) kopya üzerinde yeniden
doğrulandı; `git-state/` altında durum, `diff --stat`, ikili yama ve dosya listeleri var. N11 raporunda bildirilen
yedek yolu bulunamadı.

**Değişiklikler:**

* F-1: `classify.py` `rules-v3` (bkz. "Sınıflandırıcı").
* F-3: `port_owner.py` (yeni; Windows dinleyici tablosu), `target_process.py` (yeni; ağ kodu içermez),
  `target_guard.check_listener`, `http_transport` (`verify_target`, bağlantı katmanında denetim), `execution`
  (ilk istekten önce doğrulama, `execution.target_verification`), `config` (`target_process`),
  `configs/config.example.json` (`"target_process": "python.exe"`), `tests/isolation_guard.py` (bırakılmış port).
* Bilinçli olarak değiştirilen eski test beklentileri (her biri yeni davranışı sınar): 2xx + boş gövde / ayrıştırma
  özeti yok + yalnızca durum kodu → artık `INCONCLUSIVE` (`test_classify`, `test_hgs2_contract`,
  `test_business_outcome`, `test_expectations_pipeline`, `test_result_analysis`); ayrılmış porta ve dinleyicisiz
  porta `run` artık istek göndermeden `PreflightError` (`test_isolation_guard`, `test_hgs2_contract_local`).

**Test kanıtları (F-10):** her çalıştırma ayrı bir dizinde; `command.txt`, `environment.json`, başlangıç/bitiş
(`summary.json`), `git-head.txt`, `git-status-short.txt`, `git-diff-stat.txt`, test edilen ağacın SHA-256 manifesti
(`tree-manifest.sha256`), `junit.xml`, tam konsol çıktısı (`console.txt`). Kök:
`C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\test-evidence\`; çalıştırıcı:
`hgs2-lab-artifacts\tools\run_pytest_evidence.py` (`.venv` Python 3.15.0, pytest 9.1.1, requests 2.34.2, urllib3
2.8.0, Windows 11; `-p no:cacheprovider -rfEs --tb=long --junitxml=...`).

| Dizin (`test-evidence\…`) | Kod sürümü | Komut özeti | Sonuç |
|---|---|---|---|
| `20261029T152546Z-baseline-pre-change-unit` | değişiklik ÖNCESİ (ağaç `67389db4…`, yedekle aynı) | `pytest` | 1444 passed |
| `20261029T152651Z-baseline-pre-change-integration` | değişiklik ÖNCESİ | `pytest -m integration` | 97 passed |
| `20261029T154402Z-step1-response-parser` | değişiklik SONRASI (ağaç `894c216f…`) | ayrıştırıcı + HGS2 sözleşmesi | 115 passed |
| `20261029T154405Z-step2-classification` | SONRASI | sınıflandırma | 248 passed |
| `20261029T154409Z-step3-target-security` | SONRASI | hedef güvenliği, maskeleme, yapılandırma | 364 passed |
| `20261029T154423Z-step4-synthetic-http-integration` | SONRASI | `-m integration` yerel HTTP | 34 passed |
| `20261029T154438Z-step5-f1-f5-regression` | SONRASI | F1–F5 ve ortak modüller (birim + entegrasyon) | 529 passed |
| `20261029T154522Z-step6-full-unit` | SONRASI | `pytest` | 1519 passed, 103 deselected |
| `20261029T154537Z…`, `…154620Z…`, `…154705Z-step6-full-integration-round1..3` | SONRASI | `pytest -m integration` (3 ayrı süreç) | her turda 103 passed |
| `20261029T154043Z-flaky-candidate-normal` | ara ağaç (`12780c8b…`; kod aynı, belge ve örnek yapılandırma farklı) | kararsız test adayı | 1 passed |
| `20261029T154053Z-flaky-candidate-race-repro` | ara ağaç + depo dışı gecikme eklentisi (`NOTE.txt`) | yarış yeniden üretimi | 1 failed (beklenen; `TypeError`) |

Değişiklik sonrası çalıştırmaların hepsi aynı ağaçtadır (`tree-manifest.sha256` özeti `894c216f…`, 148 dosya). Bu
kayıt (README.md) testlerden sonra yazıldı; test edilen ağaçla son ağaç arasındaki tek fark README.md'dir. Atlanan
(skipped) test yok. Gerçek kapsamda `readiness` BLOCKED kalır; bu testlerin hiçbiri gerçek HGS2 ile canlı entegrasyon
testi değildir.

## Henüz uygulanmamış özellikler ve bilinen sınırlamalar

* **Yanıt gövdesi belleğe sınırsız okunur.** `RequestsTransport.send`, ölçüm için gövdenin tamamını
  `response.content` ile belleğe alır; boyut sınırı yoktur (ayrıştırma 4 KiB ile sınırlıdır). Büyüyen HGS2 liste
  uçları (`/api/logs`, `/api/users`) ölçülürse bellek ve süre etkilenir. N11'de değiştirilmedi (taşıma katmanı yeniden
  yazımı kapsam dışı); bir üst sınır (ör. aşınca `transport_error`) ayrı bir tasarım kararıdır.
* **Hedefin yalıtılmış olduğu kanıtlanamaz.** Ayrılmış portlar (`8080`, `5432`) yalnızca alt korumadır. N12 dinleyici
  kimliği denetimi gerçek HGS2'yi (JVM) hangi portta çalışırsa çalışsın reddeder; ancak süreç adı bir kimlik kanıtı
  değildir (bildirilen bir dış süreç gerçek sisteme iletebilir), denetim yalnızca Windows'ta ve okunduğu anda geçerlidir.
  HGS2 tarafında test profili, ayrı test veritabanı ve doğrulanabilir kimlik işareti gerekir (bkz. "Gerçek HGS2 API
  sözleşmesi"); bunlar olmadan gerçek HGS2 testleri engellidir.
* **Kararsız test adayı (N12 statik analiz):** `synthetic_server._handle` yanıtı yazdıktan SONRA `completed_ns`'i
  kaydeder; `test_hold_fields_over_real_socket_and_client_time_includes_hold` istemci yanıtı alır almaz `snapshot()`
  okur ve `completed_ns` henüz `None` olabilir (`TypeError`). `_finish` yapay olarak geciktirildiğinde (depo dışı
  eklenti) test belirleyici biçimde başarısız oldu. Bu, gerçek bir yarış durumudur; 2026-10-24'teki kaydedilmemiş
  başarısızlığın bu olduğu kanıtlanmadı. F1 dosyaları değiştirilmedi; önerilen düzeltme testte olayın tamamlanmasını
  (`completed_ns`) beklemektir.
* **Donanım entegrasyonu doğrulanmadı.** ESP32/Arduino Mega ile hiçbir test yapılmadı; HGS2 deposundaki Mega
  firmware dosyası tamamen yorum satırıdır.

* **Senaryo eşleştirmesi (N10) yalnızca sentetik raporlarla doğrulandı.** Maven Surefire + JUnit 5'in testcase
  düzeyinde `hgs2_lab.scenario_id` özelliği üretip üretmediği ve gerçek HGS2 raporlarındaki `name` özniteliğinin
  biçimi (ör. parantezli/parametreli adlar) doğrulanmadı. Gerçek HGS2 için eşleme dosyası ve doğrulanmış beklenti
  yoktur; gerçek kapsamda `readiness check` BLOCKED kalır.
* **Gerçek HGS2'ye karşı hiç çalıştırılmadı.** Loopback dışı hedef (ör. ayrı bir test sunucusu) desteği bilinçli olarak
  yoktur; eklenmesi ayrı, açık bir tasarım kararı gerektirir.
* **Gerçek HGS2 performans verisi yoktur; makine öğrenmesi modeli yoktur.** Tek dedektör sentetik veri üzerinde
  değerlendirilen Robust Z-score'dur (bkz. F5). Test sonucu sınıflandırıcısı kural tabanlıdır ve gerçek HGS2 hata
  örnekleriyle doğrulanmamıştır; JUnit dışında test raporu biçimi (Spring Boot log dosyası, JSONL) desteklenmez. `analyze` yalnızca tek
  bir çalıştırmanın betimleyici istatistiklerini üretir; çalıştırmalar arası karşılaştırma ve rapor üretimi yoktur.
  Sistem telemetrisi (F4) yalnızca toplanır; analiz edilmez ve sonuçlarla birleştirilmez.
* Eşzamanlı istekler, yük profilleri (sabit hız, kademeli artış) ve süreye dayalı testler yok; istekler tek iş
  parçacığında sırayla gönderilir. Bu yüzden `analyze`'ın throughput'u bu çalıştırmada gözlenen istek hızıdır
  (senaryo gecikmeleri dahil), sunucu kapasitesi değildir.
* Bootstrap güven aralıkları gözlemlerin bağımsız olduğunu varsayar; ardışık istekler arasındaki bağımlılık (ısınma,
  önbellek, çöp toplama) aralıkları olduğundan dar gösterebilir.
* `duration_ms` istemci tarafında ölçülür ve yeni bağlantılarda bağlantı kurulumunu içerebilir; bağlantının yeniden
  kullanılıp kullanılmadığı kaydedilmez, bu yüzden analiz soğuk ve sıcak bağlantıları ayıramaz.
* Saat çapası süreçler veya makineler arası saat eşitliği sağlamaz (bkz. "Saat çapası").
* Analiz modülleri yalnızca Python 3.15.0 (tüm testler) ve 3.13.16 (analiz duman testi, aynı çıktı özeti) ile
  çalıştırıldı; `pyproject.toml`'daki en düşük sürüm olan 3.10 ile sınanmadı.
* Kimlik doğrulama (token alma/yenileme, ortam değişkeninden gizli değer) yok.
* `business_outcome` yalnızca izin listesindeki düz metin/JSON değerleri için doldurulur (bkz. "Yanıt ayrıştırma ve iş
  sonucu"); gerçek HGS2 uçlarına karşı doğrulanmadı. Bağlantının yeniden kullanılıp kullanılmadığı kaydedilmiyor.
* Sonuçlar çalıştırma sonunda yazılır (istek bazında ara yazım yok); süreç zorla sonlandırılırsa (ör. görev
  yöneticisinden) sonuçlar kaybolur. Ctrl+C desteklenir.
* requests `timeout` toplam süre sınırı değildir; tek bir istek `timeout_seconds`'tan uzun sürebilir.
* Bağlantı katmanındaki koruma urllib3'ün iç `_dns_host` özniteliğine dayanır (sürüm `constraints.txt` ile
  sabitlenmiştir; entegrasyon testleri doğrular). `localhost` birden çok adrese çözülürse sırayla denenir; Windows'ta
  kapalı bir `::1` portu bağlantıyı birkaç saniye geciktirebilir, bu yüzden örnekte `127.0.0.1` kullanılır.
* Senaryolar blok halinde (önce bir senaryonun tüm istekleri) çalışır; senaryolar arası karıştırma yok.
* Sentetik deneyler: sunucu istemciyle aynı süreçte çalışır (kaynak çekişmesi ölçümü etkiler); bağımsız
  (`serve`) sunucu komutu, aralıklı/olasılıklı hatalar, yavaş gövde ve kısmi yanıt gibi hatalar, eşzamanlı yük
  yoktur. Hata yalnızca "belirli istekten sonra başlar" biçiminde zamanlanabilir (`onset_after`); sona erme/iyileşme
  yoktur. Sunucu sıra numarasını rota başına geliş sırasından çıkarır; bu, motorun istekleri sırayla ve yeniden
  denemesiz göndermesine dayanır (aksi halde deney `server_*` gerekçeleriyle geçersiz sayılır).
* `connection_drop` istemcide `connection_error` olarak sınıflandırıldı (Windows, requests 2.34.2); başka platform ve
  sürümlerde farklı sınıflandırılırsa etiket `contradicted` olur.
* Kampanyalar: deneyler sırayla çalışır (eşzamanlılık yok); katalog yalnızca sonda (ve Ctrl+C'de) yazılır, süreç zorla
  sonlandırılırsa katalog oluşmaz (deney dosyaları kalır). Kesilen bir kampanya devam ettirilemez; yeni ve boş bir
  dizinle yeniden çalıştırılmalıdır. Seed'ler 0–999999 ile sınırlıdır. Veri seti manifesti dosyalara başvurur, özellik
  tablosu üretmez; bölme, temel plan düzeyinde sızıntıyı önler ama farklı `group` adıyla tanımlanmış benzer (özdeş
  olmayan) tasarımları otomatik tanımaz — yalnızca birebir özdeş tasarımlar `design_in_single_split` ile raporlanır.
* Özellik tablosu: yalnızca tek politika (`observed-v1`) var; pencere/toplama tabanlı türetilmiş özellik yok, satır
  başına ham gözlemler. Sıfır ölçüm satırlı deney manifestte `empty_experiments` olarak listelenir; mevcut manifest
  kuralları (her senaryoda en az 1 ölçüm tekrarı) ve geçersiz deney politikası nedeniyle bu durum pratikte oluşturulamadı,
  sınanmadı. Bütün CSV bellekte üretilir (kampanya üst sınırı 50 000 istek).
