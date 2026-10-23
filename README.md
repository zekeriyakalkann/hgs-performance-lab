# hgs2-performance-lab

HGS2 Spring Boot API'si için akademik performans testi ve analiz aracı (bağımsız Python projesi).

**Durum:** requests tabanlı HTTP taşıyıcısı (`RequestsTransport`) sahte oturumlarla ve `127.0.0.1` üzerindeki yerel
test sunucusuyla doğrulandı. Runner, metadata ve sonuç deposu yalnızca testlerde birlikte çalıştırılıyor; hiçbir komuta
bağlı değiller. `run` komutu devre dışıdır ve gerçek bir hedefe (HGS2) karşı henüz hiçbir istek gönderilmemiştir.

## Mimari

| Modül | Sorumluluk |
|---|---|
| `config.py` | JSON yapılandırmasını yükler ve doğrular |
| `scenarios.py` | Senaryo tanımı, doğrulama, yükleme |
| `transport.py` | Taşıyıcı arayüzü (`Transport.send`) ve taşıma istisnaları |
| `http_transport.py` | `RequestsTransport`: requests tabanlı gerçek taşıyıcı, hata çevirisi, süre/boyut ölçümü |
| `runner.py` | Bir çalıştırmayı yürütür: ısınma + ölçüm istekleri, `seq`/`offset_ms`, süre ölçümü, taşıma hatası sınıflandırması |
| `models.py` | `RawResult`: girişim başına ham sonuç kaydı, `run_id` doğrulaması |
| `metadata.py` | JSON üst verisi: kod/bağımlılık/ortam bilgisi, girdi dosyası özetleri, maskelenmiş yapılandırma/senaryo görüntüsü |
| `sanitize.py` | Hassas sorgu değerlerini, URL parolalarını ve hata mesajlarındaki gizli değerleri maskeler |
| `storage.py` | CSV/JSON yazma ve okuma; üzerine yazmaz, atomik yayımlar |
| `cli.py` | `validate`, `list`, `run` (devre dışı) |
| `_validate.py` | Ortak doğrulama yardımcıları |

Analiz (pandas/numpy/matplotlib) sonraki aşamada `analysis/` altına eklenecek; ham sonuç CSV/JSON bu katmanın girdisidir.

## Kurulum

Bağımlılık tanımlarının kaynağı `pyproject.toml`'dur; geliştirme ortamının kesin sürümleri `constraints.txt`'dedir.

```
pip install -r requirements.txt    # -c constraints.txt ile çekirdek + test ("dev" eki), sabit sürümlerle
pip install -e ".[analysis,dev]"   # analiz kütüphaneleri dahil; analysis eki henüz sabitlenmedi
```

Araç sürümünün kaynağı `src/hgs2_lab/__init__.py` içindeki `__version__`'dır; `pyproject.toml`'daki
`version` ile eşitliği bir birim testiyle denetlenir.

## Yapılandırma

`configs/config.example.json` dosyasını `configs/config.json` olarak kopyalayın.

| Anahtar | Zorunlu | Açıklama |
|---|---|---|
| `base_url` | evet | `http://` veya `https://`; kimlik bilgisi, sorgu ve parça içeremez |
| `timeout_seconds` | hayır (10) | Sonlu, pozitif sayı |
| `output_dir` | hayır (`results`) | Sonuç dizini |
| `scenarios_file` | hayır (`scenarios.json`) | Senaryo dosyası |

**Göreli yollar yapılandırma dosyasının bulunduğu dizine göre çözülür**, çalışma dizinine göre değil.
Örneğin `configs/config.json` içindeki `"output_dir": "../results"` her zaman proje kökündeki `results/`
dizinini verir. Mutlak yollar olduğu gibi kullanılır. `--config` yolunun kendisi ise çalışma dizinine görelidir.

Bilinmeyen anahtarlar reddedilir (yazım hatalarını yakalamak için).

## Senaryolar

`scenarios` listesi boş olamaz; adlar benzersizdir. Alanlar: `name`, `method`, `path` (zorunlu);
`repetitions` (pozitif tam sayı, varsayılan 1), `warmup_repetitions` (negatif olmayan tam sayı, varsayılan 0),
`delay_seconds` (>= 0), `headers`, `body` (nesne), `expected_status` (durum kodu listesi).
`expected_status` boşsa 2xx başarılı sayılır.

**Isınma:** her senaryoda önce `warmup_repetitions` ısınma isteği, sonra `repetitions` ölçüm isteği gönderilir.
Isınma istekleri ölçümlerle aynı yoldan geçer ve aynı kurallarla kaydedilir, ama `warmup=true` olarak işaretlenir;
analizde ayrılmalıdır. `delay_seconds` ısınma dahil ardışık istekler arasında uygulanır.

`path` sorgu parametresi içerebilir (`/items?page=2`). Hassas adlı parametrelerin değerleri sonuçlara ve metadata'ya
maskelenerek yazılır (bkz. "Sonuç dosyaları"); istek ise değiştirilmeden gönderilir.

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
* Taşıyıcı yalnızca `TransportTimeout`, `TransportConnectionError` (veya genel `TransportError`) fırlatmalıdır.
  Diğer istisnalar yakalanmaz ve hata ayıklama için yayılır.

## HTTP taşıyıcısı ve ölçüm sınırları

`RequestsTransport` (bkz. `http_transport.py`) her `send` çağrısında şunu yapar:

1. **Hazırlık (ölçüm dışı):** metot ve timeout doğrulanır; `body` varsa JSON olarak serileştirilir
   (`Content-Type: application/json`, senaryo kendi `Content-Type` değerini vermediyse).
2. **İstek:** `session.request(..., stream=True, allow_redirects=False, timeout=timeout_seconds)`.
3. **Gövde:** `response.content` ile yanıt gövdesinin tamamı okunur, ardından yanıt kapatılır.

**Süre sınırları**

| Alan | Başlangıç | Bitiş |
|---|---|---|
| `duration_ms` | `session.request` çağrısından hemen önce | Yanıt gövdesinin **tamamı** okunduktan hemen sonra |
| `elapsed_ms` (runner) | `Transport.send` çağrısından önce | `send` dönünce/hata verince; hazırlık (JSON serileştirme) dahil |

İkisi de `time.perf_counter_ns()` ile ölçülür. Hata durumunda yalnızca `elapsed_ms` kaydedilir.

**Yanıt boyutu** (`response_bytes`): içerik kodlaması (gzip/deflate) çözüldükten sonraki gövdenin bayt sayısıdır;
HTTP başlıkları ve ağdaki sıkıştırılmış boyut dahil değildir.

**Hata sınıflandırması**

| requests hatası | Sonuç |
|---|---|
| HTTP yanıtı (500 dahil) | Hata değil; `status_code` dolu, `error_type` boş |
| `ConnectTimeout`, `ReadTimeout`, gövde okurken okuma zaman aşımı | `timeout` |
| `ConnectionError` (`SSLError`, `ProxyError` dahil), `ChunkedEncodingError` | `connection_error` |
| Diğer `RequestException` (ör. `ContentDecodingError`) | `transport_error` |
| Girdi hataları (`InvalidURL`, `MissingSchema`, `InvalidHeader`, serileştirilemeyen body), desteklenmeyen metot, diğer tüm istisnalar | **Yakalanmaz**, olduğu gibi yayılır |

**Davranış notları ve sınırlamalar**

* requests `timeout` değeri toplam süre sınırı değildir: bağlanma ve her okuma adımı için ayrı uygulanır.
  Yavaş ama kesintisiz akan bir yanıt `timeout_seconds` değerinden uzun sürebilir.
* Oturum bağlantıyı yeniden kullanır (keep-alive). Bağlantı kurma ve TLS maliyeti genelde yalnızca ilk istekte ölçülür.
* Yönlendirmeler izlenmez; 3xx olduğu gibi raporlanır (varsayılan beklenti 2xx olduğundan `http_ok=false` olur).
* Yeniden deneme yoktur. Kendi oluşturduğu oturumda `trust_env=False` kullanılır
  (ortam proxy'leri, `.netrc` ve CA ayarları okunmaz).
* Gövde tamamen belleğe okunur; çok büyük yanıtlar için uygun değildir.

## Sonuç dosyaları

`results/<run_id>.csv` ve `results/<run_id>.json`. `run_id` harf/rakamla başlar; yalnızca harf, rakam, `.`, `_`, `-` içerir (en çok 64 karakter).
Var olan bir `run_id` ile dosyaların üzerine yazılmaz.

**Şema sürümü:** `2`. Yetkili kaynak JSON'daki üst düzey `schema_version`'dır; CSV'de sürüm sütunu yoktur.
Yalnızca şema 2 okunur. Şema 1 JSON dosyaları ve şema 1 başlıklı CSV dosyaları `UnsupportedSchemaError` ile, açık bir
mesajla reddedilir; v1 → v2 dönüştürme yoktur (şema 1 ile hiç gerçek sonuç üretilmedi).

* **CSV:** `RawResult` alanları, aynı sırayla. Boş hücre = null, bool = `true`/`false`. `ResultStore.load_csv` tipleri
  (`seq` int, `offset_ms` float, `warmup` bool dahil) kayıpsız geri kazanır.
* **JSON:** `schema_version`, `run_id`, metadata alanları ve `results`.

**Metadata alanları** (`build_run_metadata`):

| Alan | İçerik |
|---|---|
| `tool_version` | `hgs2_lab.__version__` |
| `target_label` | İsteğe bağlı, kullanıcının verdiği ortam etiketi; verilmezse `null` |
| `started_at`, `finished_at` | Çalıştırmanın UTC duvar saati başlangıç/bitişi |
| `monotonic_duration_ms` | Çalıştırmanın monotonik toplam süresi (`ScenarioRunner.monotonic_duration_ms`) |
| `code.git_commit` | Kodun bulunduğu Git deposunun HEAD commit kimliği; alınamazsa `null` |
| `code.git_dirty` | Çalışma ağacı temiz değilse `true`, temizse `false`; alınamazsa `null`. Dosya adları yazılmaz. |
| `dependencies` | `requests` ve `urllib3` kurulu sürümleri |
| `environment` | Python sürümü/uygulaması, platform, işlemci, CPU sayısı |
| `inputs` | `config_file`/`scenarios_file` (yalnızca dosya adı), `config_sha256`/`scenarios_sha256` (orijinal baytların SHA-256 özeti), `hash_errors` |
| `config` | `base_url`, `timeout_seconds`; `output_dir` ve `scenarios_file` yalnızca ad olarak |
| `scenarios` | Senaryoların maskelenmiş görüntüsü |

* Git bilgisi sabit argümanlı `git rev-parse --verify HEAD` ve `git status --porcelain` ile, kabuk kullanılmadan ve 5 sn
  zaman sınırıyla alınır. Git yoksa, kod bir depoda değilse veya komut zaman aşımına uğrarsa değerler `null` olur; bu
  bir hata sayılmaz.
* Girdi dosyası okunamazsa özet `null` olur ve `hash_errors` içine yalnızca hata türü (ör. `FileNotFoundError`) yazılır.
  Dosya içerikleri metadata'ya kopyalanmaz.

**Gizlilik:**

* Adı hassas görünen header/body alanları ve sorgu parametreleri (`token`, `access_token`, `api_key`, `apikey`,
  `password`, `passwd`, `secret`, `authorization`, `cookie`, `session` vb.; büyük/küçük harf duyarsız) `***REDACTED***`
  olarak yazılır. URL'nin path kısmı ve hassas olmayan parametreleri olduğu gibi korunur.
* Hata mesajlarında da aynı maskeleme, URL'deki kullanıcı bilgisi parolası ve isteğin hassas header değerleri için
  uygulanır.
* Metadata mutlak yerel yol içermez; dosya ve dizinler yalnızca adlarıyla anılır.
* Maskeleme anahtar adına dayanır: masum adlı bir alana yazılmış gizli değer maskelenmez. Senaryo dosyalarına gerçek
  parola veya token yazmayın.

## Çıkış kodları

| Kod | Anlam |
|---|---|
| 0 | Başarılı |
| 1 | Yapılandırma veya senaryo hatası |
| 2 | Komut satırı kullanım hatası (argparse) |
| 3 | `run` komutu bu sürümde devre dışı |

## Kullanım

```
hgs2-lab validate --config configs/config.json
hgs2-lab list --config configs/config.json
```

## Testler

| Amaç | Komut |
|---|---|
| Birim testleri (varsayılan; entegrasyon testleri "deselected" olarak sayılır) | `pytest -p no:cacheprovider` |
| Yalnızca yerel HTTP entegrasyon testleri | `pytest -p no:cacheprovider -m integration` |
| Hepsi | `pytest -p no:cacheprovider -m "integration or not integration"` |

Windows'ta proje ortamıyla: `.\.venv\Scripts\python.exe -m pytest ...`.
`--strict-markers` etkin olduğundan tanımsız işaret adları hata verir.

**Birim testleri** ağ ve soket kullanmaz; taşıyıcı, saat ve `sleep` sahtedir. Git metadata'sı sahte `subprocess.run`
ile sınanır; yalnızca bir duman testi yerel `git` komutunu salt okuma amaçlı çalıştırır ve sonucun türünü denetler.
`tests/test_pipeline.py` config dosyasından sonuç dosyalarına kadar akışı ağsız olarak uçtan uca sınar.

**Entegrasyon testleri** (`tests/test_http_transport_local.py`, `integration` işaretli) `RequestsTransport`'u
gerçek soket üzerinden sınar: GET, JSON POST, HTTP 500, izlenmeyen yönlendirme, gecikmeli gövde,
başlık öncesi ve gövde ortası okuma zaman aşımı (requests/urllib3 istisna zinciri dahil), gzip boyutu,
`HTTP_PROXY` ayarlıyken `trust_env=False` davranışı. Toplam birkaç saniye sürer.

Ağ sınırları:

* Sunucu (`tests/local_http_server.py`) yalnızca `127.0.0.1` adresine, işletim sisteminin atadığı geçici bir
  porta bind eder. Ters DNS sorgusu yapmaz, giden bağlantı açmaz.
* İstemci yalnızca bu sunucuya istek gönderir. `localhost` kullanılmaz (Windows'ta `::1` çözümlemesi gecikmesi).
* Her entegrasyon testinde `socket.socket.connect` / `connect_ex` sarılır. Hedef `127.0.0.1` değilse bağlantı
  kurulmadan test hata verir. Sunucu tarafı (`bind`/`listen`/`accept`) etkilenmez.
* Proxy testleri ortam değişkenine `203.0.113.1` (RFC 5737 belge adresi) yazar. Bu adrese yönelen her bağlantı
  girişimi yukarıdaki koruma tarafından engellenir. Kontrol testi `NETRC`'yi var olmayan bir dosyaya yönlendirir,
  kullanıcının `.netrc` dosyası okunmaz.

Zamanlama: testler yalnızca alt sınır doğrular (ör. 0,3 sn gecikmeli gövde için `duration_ms >= 240`).
Zaman aşımı testlerinde istemci 1 sn sonra vazgeçer, sunucu en fazla 15 sn bekler. Yavaş bir makine testleri
yavaşlatır ama başarısız yapmaz.
