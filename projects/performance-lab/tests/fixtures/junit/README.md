# JUnit/Surefire test fikstürleri

`tests/test_junit_report.py`, `tests/test_classify.py` ve `tests/test_junit_pipeline.py` bu dosyaları girdi olarak kullanır. Dosyaların hepsi elle yazılmış **sentetik** dosyalardır. Gerçek HGS2 raporlarından kopyalanmadılar ve gerçek kişisel veri içermezler.

"Hassas" görünen bütün değerler (`KART-SENTETIK-...`, `OGR-SENTETIK-...`, `PARMAK-SENTETIK-...`, `FAKE-...`) sahtedir ve yalnızca maskeleme testleri için kullanılır. Testler, bu değerlerin hiçbirinin çıktıda yer almadığını denetler.

| Dosya | Amaç |
|---|---|
| `all-pass.xml` | Tek suite içinde iki başarılı test. `properties`, `system-out` ve `system-err` bölümleri de var; ayrıştırıcı bunların içeriğini okumamalı. |
| `failure.xml` | Assertion failure: iş sonucu uyuşmazlığı mesajı ve stack trace. |
| `error-context.xml` | Bağlam yükleme hatası: `Caused by` zinciri ve bağlantı dizesi içeren mesaj. |
| `skipped.xml` | Atlanan test. |
| `multi-suite.xml` | `<testsuites>` altında suite'ler: başarılı test, zaman aşımı, tanınmayan istisna, türsüz error ve boş bir suite. |
| `optional-missing.xml` | `time`, `classname`, `name`, `timestamp` gibi isteğe bağlı alanlar eksik. |
| `empty-suite.xml` | Hiç testcase içermeyen suite. |
| `sensitive.xml` | Hata mesajında, stack trace'te ve test adında hassas değerler. |
| `conflicting.xml` | Çelişkili sonuç öğeleri, geçersiz süreler ve beyan edilen ile gözlenen sayılar arasında uyuşmazlık. |
| `empty.xml` | Boş dosya. |
| `malformed.xml` | Bozuk XML. |
| `xxe.xml` | Harici varlık (XXE) girişimi; reddedilmesi gerekir. |
| `not-junit.xml` | JUnit olmayan bir kök öğe. |
