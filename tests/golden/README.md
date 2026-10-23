# Altın örnek sonuç dosyaları

Geriye dönük uyumluluk testlerinin (`tests/test_golden.py`, `tests/test_reader.py`, `tests/test_cli_analyze.py`)
girdileridir. Her dizindeki dosyalar, adındaki commit'in **kendi yazıcısıyla** (o commit'in `src/` ağacı
`git archive` ile ayrı bir dizine çıkarılarak) üretildi; sonradan elle düzenlenmedi.

| Dizin | Üreten commit | Şema | İçerik |
|---|---|---|---|
| `v1-a2f5d9f/` | a2f5d9f | 1 | Reddedilmesi beklenen eski sürüm örneği |
| `v2-76d15bb/` | 76d15bb | 2 | `execution` ve `clock` metadata'sı **yok** |
| `v2-a1331fd/` | a1331fd | 2 | `execution` var, `clock` yok; tamamlanmış ve kısmi (`.partial`) çalıştırma |

Üretim koşulları:

* Ağ yok: sahte taşıyıcı, sahte monotonik saat, sabit `now`, loopback dönen sahte çözümleyici.
* Hedef `http://127.0.0.1:8080` (yalnızca metin; hiçbir bağlantı açılmadı).
* `environment` alanları nötrleştirildi (`golden-fixture`); `dependencies` sabit değerler; `code` alanına
  üreten commit'in kimliği yazıldı.
* Gizli değerler sahtedir (`FAKE-GOLDEN-TOKEN-0001`) ve v2 dosyalarında yalnızca maskeli haliyle (`***REDACTED***`)
  yer alır. v1 yazıcısı maskeleme yapmadığı için v1 örneğinde gizli değer kullanılmadı.
* Senaryolar: `login` (1 ısınma + 3 ölçüm: 200, HTTP 500, zaman aşımı) ve `items` (4 ölçüm, 200).

Dosyalar bayt bayt korunur: `.gitattributes` içinde `tests/golden/** -text` (satır sonu dönüşümü yok) ve SHA-256
özetleri `tests/test_golden.py` içinde sabitlenmiştir. Bir altın dosyayı değiştirmek bilinçli bir şema kararıdır.
