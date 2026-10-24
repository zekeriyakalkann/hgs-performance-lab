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
| `sanitize.py` | Hassas sorgu değerlerini, URL parolalarını ve hata mesajlarındaki gizli değerleri maskeler |
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
| `cli.py` | `validate`, `list`, `run`, `analyze`, `synthetic validate/plan/run`, `campaign validate/run/verify`, `dataset build` |
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
python -m http.server 8080 --bind 127.0.0.1 --directory <boş-bir-dizin>

# 2. terminal: proje kökünde
copy configs\config.example.json configs\config.json        # base_url: http://127.0.0.1:8080
```

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
| 130 | `run` Ctrl+C ile durduruldu; kısmi sonuçlar `.partial` dosyalarında |

Beklenmeyen bir istisnada (programlama hatası) kısmi sonuçlar `execution.status = "failed"` ile kaydedilir ve istisna
hata ayıklama için yeniden fırlatılır (Python izi, çıkış kodu 1).

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
* `business_outcome`: ileride HGS2 yanıt gövdesinden doldurulacak; şimdilik boş.
* `error`: hata mesajı; hassas sorgu değerleri, URL parolaları ve isteğin hassas header değerleri maskelenir.

## HTTP taşıyıcısı ve ölçüm sınırları

`RequestsTransport` her `send` çağrısında:

1. **Hazırlık (ölçüm dışı):** metot, timeout ve hedef (metin + ad çözümlemesi) doğrulanır; `body` varsa JSON olarak
   serileştirilir (`Content-Type: application/json`, senaryo kendi değerini vermediyse).
2. **İstek:** `session.request(..., stream=True, allow_redirects=False, timeout=timeout_seconds)`.
3. **Gövde:** `response.content` ile yanıt gövdesinin tamamı okunur, ardından yanıt kapatılır.

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
* **Şema v3'e geçilmedi**: istek düzeyinde yeni alan gerekmedi. Saat çapası (`clock`), veri türü (`dataset_kind`) ve
  sentetik deney kimliği (`synthetic`) metadata anahtarı olarak eklendi. Sentetik etiketler bilinçli olarak sonuç
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

**Gizlilik:**

* Adı hassas görünen header/body alanları ve sorgu parametreleri (`token`, `access_token`, `api_key`, `apikey`,
  `password`, `passwd`, `secret`, `authorization`, `cookie`, `session` vb.; büyük/küçük harf duyarsız) `***REDACTED***`
  olarak yazılır. URL'nin path kısmı ve hassas olmayan parametreleri olduğu gibi korunur.
* Hata mesajlarında ve `execution.message` alanında da aynı maskeleme uygulanır.
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

Ağ sınırları: test sunucusu (`tests/local_http_server.py`) yalnızca `127.0.0.1`'e ve geçici bir porta bind eder.
Her entegrasyon testinde `socket.socket.connect`/`connect_ex` sarılır; hedef `127.0.0.1` değilse bağlantı kurulmadan
test hata verir. Testlerdeki dış adresler (`203.0.113.0/24`, `2001:db8::/32`) belge aralıklarıdır ve yalnızca
reddedilmesi beklenen değerler olarak kullanılır. Zamanlama testleri yalnızca alt sınır doğrular.

## Henüz uygulanmamış özellikler ve bilinen sınırlamalar

* **Gerçek HGS2'ye karşı hiç çalıştırılmadı.** Loopback dışı hedef (ör. ayrı bir test sunucusu) desteği bilinçli olarak
  yoktur; eklenmesi ayrı, açık bir tasarım kararı gerektirir.
* **Gerçek HGS2 performans verisi yoktur; makine öğrenmesi modeli yoktur.** Tek dedektör sentetik veri üzerinde
  değerlendirilen Robust Z-score'dur (bkz. F5). `analyze` yalnızca tek
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
* `business_outcome` doldurulmuyor; bağlantının yeniden kullanılıp kullanılmadığı kaydedilmiyor.
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
