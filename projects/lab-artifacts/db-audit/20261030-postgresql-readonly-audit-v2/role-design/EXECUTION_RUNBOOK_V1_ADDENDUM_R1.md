# EXECUTION_RUNBOOK_V1 — EK R1: Oturum kaybı, gizli bilgi temizliği ve tek süreçli yürütme

- Proje: HGS2 PostgreSQL Read-Only Audit V2
- Tarih: 2026-10-30 (+03:00)
- Dayanak: `role-design\EXECUTION_RUNBOOK_V1.md` (SHA-256 `de943cc52a9d79aa7138a22946d2eed0cd15820d987551ea2caa81e6a5ccc081`). **Bu dosya değiştirilmedi;** önceki sürüm olduğu gibi korunur.
- Bu ek, V1 kılavuzunun **ana içeriğini ve test kapsamını değiştirmez; hiçbir kapıyı gevşetmez.** İki tür içerik taşır:
  - **Netleştirmeler** (R1-1…R1-6): §0.7, §10.2, §10.4 ve §12.3'te açık bırakılmış noktalar (oturum kaybı, ikame tarama, eksik çalıştırma arşivi, temizlik, yeni RunId, tek süreçli yürütme).
  - **Uygulama kusuru düzeltmeleri** (R1-8, R1-9):
    - R1-8, §2.5 (2 yer), §10.1 (1 yer) ve §10.4 (1 yer) kapılarındaki süreç komut satırı karşılaştırmasını değiştirir. Ayrıca §12.2'deki elle inceleme listesine (kapı değildir) aynı düzeltme uygulanır. Değişiklik yalnızca yol ayırıcısını normalleştirir; kapıların anlamı aynıdır.
    - R1-9, çalıştırıcı betiğin kanıt klasörüne kopyalanma biçimini değiştirir; §10.2 kapısı değişmez.
- Tetikleyen olay: `iso18-20261030T223605` çalıştırması Aşama 2.4'ten sonra PowerShell oturumu kaybolduğu için yarım kaldı (kayıt: `role-design\iso-runs-incomplete\iso18-20261030T223605\`).

---

## R1-1. Oturum kaybında bellekteki gizli değerler geri getirilemez

- `$TestSecrets`, `$SuperPw`, `$Live0`, `$Hash0` ve tüm yardımcı fonksiyonlar yalnızca çalıştırmanın PowerShell sürecinde yaşar (§0.7). Süreç kapandığında **geri getirilemez.**
- Kaybolan parolaları yeniden üretmek veya tahmin etmek **yasaktır.** `New-TestSecret` her çağrıda yeni bir değer üretir. Eski değeri bulmak için hiçbir yöntem denenmez.
- Kaybolan oturumun RunId'si üzerinde **hiçbir test çalıştırılmaz.** Eski küme **başlatılmaz**. Yalnızca §12.3 gereği çalışıyorsa `pg_ctl -D <eski test data> -m fast -w stop` ile durdurulur.
- Çalıştırma sınıflandırması: **V1 TAMAMLANMADI**. Bu sınıflandırma, sonradan yapılan arşiv ve temizlikle değişmez.

## R1-2. §10.2 parola taraması oturum kaybından sonra artık aynı biçimde yapılamaz

- §10.2'deki tarama `$TestSecrets` bellek tablosuna dayanır. Bu tablo kaybolduğu için **özgün tarama artık NOT RUN olarak raporlanır.**
- İkame tarama (yalnızca kanıtı arşivlemeden önce):
  1. Test kökündeki `cfg\pgpass.conf` dosyası hâlâ duruyorsa, satırlarındaki parola alanı **yalnızca süreç belleğine** okunur. Hiçbir çıktıya, dosyaya veya günlüğe yazılmaz.
  2. Arşivlenecek her dosya bu değerle `Select-String -SimpleMatch` kullanılarak taranır. Raporda yalnızca **eşleşme sayısı** yer alır.
  3. Ek olarak `PRIVATE KEY` dizgisi ve pgpass satır biçimi (`^\*:\d+:\*:`) taranır.
  4. Değişkenler hemen `$null` yapılır.
- `pgpass.conf` içinde bulunmayan bir parola, örneğin pgpass satırı yazılmadan önce oturum kaybolduysa, **hiçbir yöntemle taranamaz.** Bu durumda tarama sınırlıdır; rapora "NOT RUN (kaynak yok)" yazılır.
- İkame tarama, özgün taramanın yerine geçmez. Raporda **"pgpass kaynaklı ikame tarama"** olarak ayrıca adlandırılır.

## R1-3. Eksik çalıştırmanın arşivlenmesi

- Arşiv hedefi, tamamlanmış çalıştırmalardan **ayrı** bir dizindir: `role-design\iso-runs-incomplete\<eski RunId>\`. Böylece `iso-runs\` altında yalnızca tamamlanmış çalıştırmalar bulunur.
- Kopyalananlar:
  - `evidence\`: kaynakla dosya sayısı ve SHA-256 kümesi karşılaştırılır.
  - `log\`: varsa.
  - `review\` altında:
    - `postgresql.conf` dosyasından yalnızca HGS2 ek bloğu (§2.4 kanıtı);
    - ad ve boyut envanteri (`root-inventory.txt`);
    - kapanış sonuçları (`closeout-results.txt`).
- **Kopyalanmayanlar:** `cfg\` (pgpass) ve `certs\` (özel anahtarlar). Bunların içeriği hiçbir arşive, rapora veya terminale yazılmaz.
- Arşivde `INCOMPLETE_STATUS.md` bulunur. Bu dosya, çalıştırmanın neden tamamlanmadığını, son kaydedilen aşamayı ve yapılan kapanış adımlarını açıklar.
- Arşivde `SHA256SUMS.txt` bulunur.

## R1-4. Gizli dosyaların temizlenmesi (eksik çalıştırma)

- Silme, §10.4'ün yedi kapısıyla aynı kapılardan geçer. Ek olarak şu kontroller yapılır:
  - `data\postmaster.pid` yok;
  - `pg_ctl status` çıkışı 3, yani sunucu çalışmıyor.
- RunId onayı: Oturum kaybından sonra Aşama 1 çıktısı ekranda bulunmayabilir. Bu durumda onay kaynağı, operatörün ya da görev tanımının **yazılı olarak verdiği RunId**'dir. Silme hedefinin yaprak adı bu değerle **birebir** (büyük/küçük harf duyarlı) eşleşmelidir.
- Sıra:
  1. `cfg\pgpass.conf` silinir.
  2. Test kökü `Remove-Item -Recurse` ile silinir.
  3. Kökün artık bulunmadığı doğrulanır.
- **Sınır:** NTFS/SSD üzerinde `Remove-Item` güvenli silme (üzerine yazma) **garanti etmez.** Riski azaltan etkenler şunlardır:
  - Silinen gizli değerler yalnızca silinen test kümesine aittir. Küme yok edildiği için parola hiçbir yerde geçerli değildir.
  - Sertifikalar 7 günlüktür ve yalnızca test CA'sına bağlıdır.
  - Canlı sistemle hiçbir ilişkileri yoktur.
- Kapılardan biri sağlanmazsa silme yapılmaz ve dosyalar yerinde bırakılır. Bu durum raporlanır.

## R1-5. Yeni RunId ile yeniden başlama

- Yeni çalıştırma **yeni RunId ile Aşama 0'dan** başlar (§12.3). Eski çalıştırmanın dosyaları, parolaları ve sertifikaları kullanılmaz.
- G3 kapısı (`test koku zaten var`) yeni kökün daha önce bulunmadığını doğrular. Eski kökün silinmiş olması bu kapı için gerekli değildir. Ancak port 55438'in boş olması gerekir.

## R1-6. Oturum kaybını önlemek için tek süreçli yürütme (öneri, kapsam genişletmez)

- §0.7 "aynı pencerede, sırayla" kuralı, otomasyonda şu şekilde uygulanabilir: runbook blokları **aynen ve aynı sırayla**, tek bir `powershell.exe` (5.1, ConsoleHost, yönetici olmayan) betiğinde çalıştırılır.
- Bu şekilde §10.2 taraması ve Aşama 11 karşılaştırması gibi oturuma bağlı kapılar korunur.
- Etkileşimsiz süreçte `Read-Host` (§10.4 RunId onayı) çalışmaz. Bu nedenle onay şöyle alınır:
  1. Çalıştırıcı `SILINECEK:` satırını yazar.
  2. Operatör RunId'yi Aşama 1 çıktısıyla karşılaştırır.
  3. Operatör RunId'yi önceden **bulunmayan** bir onay dosyasına yazar.
  4. Dosya önceden varsa çalıştırıcı başlamaz; bayat onay kabul edilmez.
  5. 30 dakika içinde onay gelmezse silme yapılmaz ve §10.4 erteleme kaydı yazılır.
- Runbook'ta olmayan satırlar yalnızca **eklemedir**:
  - Aşama 0 beklenen değerleri kapıya dönüştürülür;
  - her bloktan sonra canlı servis ve 5432 kontrol noktası alınır;
  - transcript ve konsol günlüğünde parola taraması yapılır;
  - hata durumunda yalnızca test kümesi durdurulur.
- Hiçbir kapı gevşetilmez.
- Bu yöntemin uygulaması (çalıştırıcının konumu ve kanıta kopyalanma durumu R1-9 ile birlikte okunur):

  | Çalıştırma | Çalıştırıcı sürümü (SHA-256) | Betiğin konumu | Kanıta kopyalandı mı |
  |---|---|---|---|
  | `iso18-20261030T231228` (geçerli) | R2 `92deca08dac31d9a3e9dc6724ff18894ffeb72e1718d4ea3b7ca14fd36a0f8a2` | `role-design\iso-runs\iso18-20261030T231228\runner\runner_v1_single_session.ps1`. Çalıştırma bittikten sonra eklendi; çalıştırmanın kendi `SHA256SUMS.txt` manifestinde yoktur | **Hayır.** Kanıtta yalnızca `evidence\00-inputs\runner_v1_single_session.sha256` ve `evidence\00-inputs\runner_provenance.txt` vardır |
  | `iso18-20261030T230745` (FAIL) | R1 `3d214f5645820e1375ed027b3d302b0a80465bab28f618ae88e173a626ec824a` | `role-design\iso-runs-incomplete\iso18-20261030T230745\evidence\00-inputs\runner_v1_single_session.ps1` | **Evet.** R1-9'daki yanlış pozitif bu kopyadan doğdu |

- `runner_provenance.txt`, blok başına runbook satır aralığını ve SHA-256 değerini içerir.

## R1-8. Düzeltme: süreç komut satırı ile test veri dizini karşılaştırması (kapılar: §2.5, §10.1, §10.4; elle inceleme listesi: §12.2)

- **Bulgu:** Bu bulgu `iso18-20261030T230745` çalıştırmasında, Aşama 2.5'te `GUARD: test postmaster bulunamadi` hatasıyla ortaya çıktı.
  - Çalıştırma bu aşamada durduruldu. Sınıflandırması: **FAIL / V1 TAMAMLANMADI**.
  - Arşiv: `role-design\iso-runs-incomplete\iso18-20261030T230745\`.
- **Kök neden:** `pg_ctl`, veri dizini yolunu `/` ayırıcısıyla kanonikleştirir.
  - Kanıt: `postmaster.opts` içeriği şöyledir: `C:/Program Files/PostgreSQL/18/bin/postgres.exe "-D" "C:/Users/Ceng Zeki/AppData/Local/hgs2-iso/<RunId>/data"`.
  - Runbook ise `$_.CommandLine -like "*$Data*"` ile `\` ayırıcılı yolu arar. Bu karşılaştırma **hiçbir zaman** eşleşmez.
- **Etkisi:**
  - §2.5'teki iki pozitif kapı ("test postmaster bulunamadi" ve "55438 dinleyicisi test postmaster degil") her zaman **başarısız** olur.
  - §10.1 ("test postmaster hala calisiyor") ve §10.4 ("test postmaster calisiyor - silme yapilmaz") negatif kapıları ise her zaman **anlamsız biçimde geçer**. Bu kapılar çalışan bir test kümesini yakalayamaz.
  - §12.2'deki `Format-Table` listesi bir kapı değildir; elle PID incelemesi içindir. Aynı kusur yüzünden çalışan test süreçleri varken bile **boş liste** gösterir.
  - Bu nedenle düzeltme yalnızca çalıştırmayı mümkün kılmakla kalmaz, güvenliği de artırır.
- **Düzeltme (anlam aynı; yalnızca ayırıcı normalizasyonu):**

  ```powershell
  function Test-CmdLineHasData([string]$CommandLine) {
      if ([string]::IsNullOrEmpty($CommandLine)) { return $false }
      return ($CommandLine.Replace([char]47, [char]92).IndexOf([IO.Path]::GetFullPath($Data), [StringComparison]::OrdinalIgnoreCase) -ge 0)
  }
  ```

  - `$_.CommandLine -like "*$Data*"` yerine `(Test-CmdLineHasData $_.CommandLine)` kullanılır.
  - `$cl -like "*$Data*"` yerine `(Test-CmdLineHasData $cl)` kullanılır.
  - Runbook'ta bu desen **beş yerde** geçer:

    | Yer | Runbook satırı | Tür | Geçerli çalıştırmada (`iso18-20261030T231228`) |
    |---|---|---|---|
    | §2.5 "test postmaster bulunamadi" | L418 | Kapı | Düzeltildi |
    | §2.5 "55438 dinleyicisi test postmaster degil" | L457 | Kapı | Düzeltildi |
    | §10.1 "test postmaster hala calisiyor" | L1297 | Kapı | Düzeltildi |
    | §10.4 "test postmaster calisiyor - silme yapilmaz" | L1371 | Kapı | Düzeltildi |
    | §12.2 süreç listesi | L1558 | Elle inceleme listesi (kapı değil) | Kullanılmadı: acil durum bloğu çalıştırılmadı. Kullanılacaksa aynı düzeltme uygulanır |

  - Dört kapının dördü de düzeltildi. §12.2 listesi çalıştırmaya girmedi.
  - Boş komut satırı, yani başka kullanıcının süreci olduğu için okunamayan bir komut satırı, **asla** eşleşmez. Canlı servis süreçleri bu yüzden hiçbir zaman "test postmaster" sayılmaz.
- **Birim sınaması:** Aşağıdaki girdilerle sınandı:

  | Girdi | Sonuç |
  |---|---|
  | `/` ayırıcılı test yolu | `True` |
  | `\` ayırıcılı test yolu | `True` |
  | Başka bir RunId'nin yolu | `False` |
  | Boş komut satırı | `False` |
  | Canlı veri dizini | `False` |

- **Eski çalıştırma kapanışındaki etki:** `iso18-20261030T223605` kapanış betiğinin (v1) süreç sayımı da aynı kusuru taşıyordu.
  - Silme kararı yine de güvenliydi. Ek kapılar bağımsız olarak doğrulandı:
    - `data\postmaster.pid` yok;
    - `pg_ctl status` çıkışı 3;
    - port 55438 dinlenmiyor.
  - Sonraki kapanış betiği (v2) düzeltilmiş karşılaştırmayı kullanır.

## R1-9. Düzeltme: §10.2 anahtar taramasının kendi deseniyle yanlış pozitif vermesi

- §10.2, kanıtta `PRIVATE KEY` dizgisini büyük/küçük harf duyarsız olarak arar. Runbook kodunun kendisi bu sabiti içerir.
- Bu nedenle runbook kodunu içeren bir çalıştırıcı betik `evidence\` altına kopyalanırsa §10.2 her zaman başarısız olur.
  - Bu durum `iso18-20261030T230745` kapanışında görüldü: 2 eşleşmenin ikisi de betikteki tarama satırlarıydı. Gerçek anahtar içeriği yoktu; `-----BEGIN` başlığı 0 eşleşme verdi.
- **Düzeltme:** Çalıştırıcı betik kanıta kopyalanmaz. Kanıta yalnızca betiğin SHA-256 değeri (`evidence\00-inputs\runner_v1_single_session.sha256`) yazılır.
  - Betiğin kendisi, çalıştırma bittikten sonra arşivin `runner\` klasörüne eklenir: `role-design\iso-runs\iso18-20261030T231228\runner\runner_v1_single_session.ps1`.
  - Bu kopya çalıştırmanın kendi manifestinde değildir; `asama4-v1-execution\FINAL_SHA256SUMS.txt` içindedir. SHA-256 değeri kanıta yazılan değerle (`92deca08…f8a2`) aynıdır.
  - Düzeltmeden önceki R1 çalıştırıcısı yalnızca `iso18-20261030T230745` çalıştırmasında kanıta kopyalandı (R1-6 tablosu).
  - §10.2 kapısı **değiştirilmedi.**

## R1-7. Kapsam

- Bu ek yeni test, yeni SQL denetim özelliği veya yeni güvenlik paketi **eklemez.**
- T2–T10 ve RC-02/04/05 hâlâ V1 dışıdır (§0.3).
