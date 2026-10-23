# hgs2-performance-lab

HGS2 Spring Boot API'si için akademik performans testi ve analiz aracı (bağımsız Python projesi).

**Durum:** Yapılandırmadan sonuç dosyalarına kadar çalıştırma akışı ve `run` komutu etkindir, ama **yalnızca loopback
hedeflere** (`127.0.0.1`, `::1`, `localhost`) istek gönderir. Araç bugüne kadar yalnızca testlerdeki yerel HTTP
sunucularına karşı çalıştırıldı. **Gerçek HGS2 API'sine karşı hiçbir test veya ölçüm yapılmadı**; loopback dışı bir
hedefe izin veren bir ayar da yoktur.

## Mimari

```
Config -> Scenarios -> ön kontrol -> Metadata -> Runner -> HTTP Transport -> Results -> Storage
```

| Modül | Sorumluluk |
|---|---|
| `config.py` | JSON yapılandırmasını ve güvenlik sınırlarını (`limits`) yükler, doğrular |
| `scenarios.py` | Senaryo tanımı, doğrulama, yükleme |
| `execution.py` | Uçtan uca çalıştırma: ön kontrol, güvenlik koruması, metadata, kayıt; çalıştırma durumu |
| `target_guard.py` | Hedef güvenliği: şema/ad izin listesi, ad çözümlemesi, loopback denetimi |
| `runner.py` | Senaryoları yürütür: ısınma + ölçüm istekleri, `seq`/`offset_ms`, süre ölçümü, güvenlik kancaları |
| `transport.py` | Taşıyıcı arayüzü (`Transport.send`) ve taşıma istisnaları |
| `http_transport.py` | `RequestsTransport`: requests tabanlı taşıyıcı, bağlantı katmanında loopback koruması, hata çevirisi |
| `models.py` | `RawResult`: girişim başına ham sonuç kaydı, `run_id` doğrulaması |
| `metadata.py` | JSON üst verisi: çalıştırma durumu, kod/bağımlılık/ortam bilgisi, girdi özetleri, maskelenmiş görüntüler |
| `sanitize.py` | Hassas sorgu değerlerini, URL parolalarını ve hata mesajlarındaki gizli değerleri maskeler |
| `storage.py` | CSV/JSON yazma ve okuma; üzerine yazmaz, atomik yayımlar, kısmi sonuçları ayrı adla yazar |
| `cli.py` | `validate`, `list`, `run` |
| `_validate.py` | Ortak doğrulama yardımcıları |

Analiz (pandas/numpy/matplotlib) sonraki aşamada eklenecek; ham sonuç CSV/JSON bu katmanın girdisidir.

## Kurulum

Bağımlılık tanımlarının kaynağı `pyproject.toml`'dur; geliştirme ortamının kesin sürümleri `constraints.txt`'dedir
(requests, urllib3, pytest ve geçişli bağımlılıkları). Yeni çalışma zamanı bağımlılığı yoktur.

```
pip install -r requirements.txt    # -c constraints.txt ile çekirdek + test ("dev" eki), sabit sürümlerle
pip install -e ".[analysis,dev]"   # analiz kütüphaneleri dahil; analysis eki henüz sabitlenmedi
```

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
```

* `validate`: yapılandırma ve senaryoları doğrular, çözülen yolları ve hedefin `run` için izinli olup olmadığını
  (yalnızca URL metnine bakarak) gösterir. İstek göndermez.
* `list`: senaryoları listeler. İstek göndermez.
* `run`: ön kontrolden sonra senaryoları sırayla çalıştırır, sonuçları ve metadata'yı kaydeder, bir özet yazdırır
  (istek sayıları, HTTP/taşıma hatası sayıları, ölçüm isteklerinin `duration_ms` medyan/en az/en çok değeri,
  sonuç dosyalarının yolu). `--target-label` metadata'ya `target_label` olarak yazılır.

`--config` varsayılanı `configs/config.json`'dır. Windows'ta kurulum yapılmadan: `.\.venv\Scripts\python.exe -m hgs2_lab.cli ...`.

### Çıkış kodları

| Kod | Anlam |
|---|---|
| 0 | Başarılı (`run`: planlanan tüm istekler yapıldı; HTTP 5xx ve taşıma hataları sonuçlarda kayıtlıdır) |
| 1 | Yapılandırma veya senaryo hatası (hiç istek yok) |
| 2 | Komut satırı kullanım hatası (argparse) |
| 3 | `run` ön kontrolde reddedildi: hedef, bütçe, `target_label` veya dosya çakışması (hiç istek yok) |
| 4 | `run` güvenlik sınırıyla durduruldu; kısmi sonuçlar `.partial` dosyalarında |
| 5 | `run` sonuçları kaydedilemedi |
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

* **CSV:** yalnızca sonuç satırları (`RawResult` alanları). Boş hücre = null, bool = `true`/`false`.
* **JSON:** `schema_version`, `run_id`, aşağıdaki metadata alanları ve `results`.

| Alan | İçerik |
|---|---|
| `tool_version` | `hgs2_lab.__version__` |
| `target_label` | `--target-label` değeri; verilmezse `null` |
| `started_at`, `finished_at` | Çalıştırmanın UTC duvar saati başlangıç/bitişi |
| `monotonic_duration_ms` | İlk isteğin başlangıcından son isteğin bitişine (kesintide kesildiği ana) kadar monotonik süre |
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

**Entegrasyon testleri** (`integration` işaretli):

* `tests/test_http_transport_local.py`: `RequestsTransport`'u gerçek soket üzerinden sınar (GET, JSON POST, HTTP 500,
  izlenmeyen yönlendirme, gecikmeli gövde, okuma zaman aşımları ve istisna zinciri, gzip boyutu, ortam proxy'si).
* `tests/test_run_local.py`: `hgs2-lab run`'ı uçtan uca sınar (sonuç dosyaları, metadata, `target_label`,
  maskeleme, zaman aşımıyla kontrollü durdurma, loopback dışı hedefin reddi, `localhost` adıyla doğrulanmış
  bağlantı, DNS rebinding'in bağlantı kurulmadan engellenmesi).

Ağ sınırları: test sunucusu (`tests/local_http_server.py`) yalnızca `127.0.0.1`'e ve geçici bir porta bind eder.
Her entegrasyon testinde `socket.socket.connect`/`connect_ex` sarılır; hedef `127.0.0.1` değilse bağlantı kurulmadan
test hata verir. Testlerdeki dış adresler (`203.0.113.0/24`, `2001:db8::/32`) belge aralıklarıdır ve yalnızca
reddedilmesi beklenen değerler olarak kullanılır. Zamanlama testleri yalnızca alt sınır doğrular.

## Henüz uygulanmamış özellikler ve bilinen sınırlamalar

* **Gerçek HGS2'ye karşı hiç çalıştırılmadı.** Loopback dışı hedef (ör. ayrı bir test sunucusu) desteği bilinçli olarak
  yoktur; eklenmesi ayrı, açık bir tasarım kararı gerektirir.
* Eşzamanlı istekler, yük profilleri (sabit hız, kademeli artış) ve süreye dayalı testler yok; istekler tek iş
  parçacığında sırayla gönderilir. Throughput ve yüzdelik analizi yok (analiz katmanı sonraki aşama).
* Kimlik doğrulama (token alma/yenileme, ortam değişkeninden gizli değer) yok.
* `business_outcome` doldurulmuyor; bağlantının yeniden kullanılıp kullanılmadığı kaydedilmiyor.
* Sonuçlar çalıştırma sonunda yazılır (istek bazında ara yazım yok); süreç zorla sonlandırılırsa (ör. görev
  yöneticisinden) sonuçlar kaybolur. Ctrl+C desteklenir.
* requests `timeout` toplam süre sınırı değildir; tek bir istek `timeout_seconds`'tan uzun sürebilir.
* Bağlantı katmanındaki koruma urllib3'ün iç `_dns_host` özniteliğine dayanır (sürüm `constraints.txt` ile
  sabitlenmiştir; entegrasyon testleri doğrular). `localhost` birden çok adrese çözülürse sırayla denenir; Windows'ta
  kapalı bir `::1` portu bağlantıyı birkaç saniye geciktirebilir, bu yüzden örnekte `127.0.0.1` kullanılır.
* Senaryolar blok halinde (önce bir senaryonun tüm istekleri) çalışır; senaryolar arası karıştırma yok.
