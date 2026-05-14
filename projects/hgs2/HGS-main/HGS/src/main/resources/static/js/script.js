// ==========================================
// 1. GLOBAL DEĞİŞKENLER VE ARAYÜZ ELEMENTLERİ
// ==========================================
// Tum istekler tarayicinin adresine gider (localhost, LAN IP veya domain)
const API_BASE = window.location.origin;

function escapeHtml(s) {
    if (s == null || s === '') return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

let kullanicilar = [];
let cihazlar = [];
let loglar = []; 

const modal = document.getElementById('kullaniciModal');
const modalBaslik = document.getElementById('modalBaslik');
const cihazModal = document.getElementById('cihazModal');
const modalCihazBaslik = document.getElementById('modalCihazBaslik');

// ==========================================
// 2. GİRİŞ YAP / ÇIKIŞ YAP (YETKİLENDİRME)
// ==========================================
function adminGiris(event) {
    event.preventDefault();
    
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;
    const hata = document.getElementById('hataMesaji');

    if (user === "admin" && pass === "1234") {
        localStorage.setItem("hgs_oturum", "acik");
        window.location.href = "/index.html";
    } else {
        hata.style.display = "block";
        hata.innerText = "Hatalı kullanıcı adı veya şifre!";
    }
}

function cikisYap() {
    localStorage.removeItem("hgs_oturum");
    window.location.href = "/login.html";
}

// ==========================================
// 3. SAYFA YÜKLENDİĞİNDE ÇALIŞACAKLAR (KORUMA DAHİL)
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const currentPath = window.location.pathname;

    if (currentPath.endsWith("index.html") || currentPath === "/") {
        if (localStorage.getItem("hgs_oturum") !== "acik") {
            window.location.href = "/login.html";
            return;
        }

        veritabanindanKullanicilariGetir();
        veritabanindanCihazlariGetir();
        veritabanindanLoglariGetir();

        const apiEl = document.getElementById('apiKokGoster');
        if (apiEl) apiEl.textContent = API_BASE;
    }
});

// ==========================================
// 4. GENEL ARAYÜZ (NAVİGASYON & DASHBOARD)
// ==========================================
function menuyuGoster(bolumId) {
    const tumBolumler = document.querySelectorAll('.sayfa-bolumu');
    tumBolumler.forEach(bolum => bolum.style.display = 'none');

    const gosterilecekBolum = document.getElementById(bolumId);
    if (gosterilecekBolum) {
        gosterilecekBolum.style.display = 'block';
    }
}

function dashboardGuncelle() {
    const toplamKullanici = kullanicilar.length;
    const toplamLog = loglar.length;
    const onaylananGirisler = loglar.filter(l => l.sonuc && l.sonuc.includes("ONAYLANDI")).length;
    
    const ozetMetni = `Sisteme hoş geldiniz.<br><br>
        &bull; Toplam Kayıtlı Kullanıcı: <b>${toplamKullanici}</b><br>
        &bull; Toplam Giriş Denemesi: <b>${toplamLog}</b><br>
        &bull; Başarılı Geçiş (Onaylanan): <b style='color:green'>${onaylananGirisler}</b>`;
    
    const dashboardElemani = document.getElementById('dashboardOzet');
    if(dashboardElemani) dashboardElemani.innerHTML = ozetMetni;
}

// ==========================================
// 5. KULLANICI YÖNETİMİ MODÜLÜ
// ==========================================
function veritabanindanKullanicilariGetir() {
    fetch(`${API_BASE}/api/users`)
        .then(response => response.json())
        .then(data => {
            kullanicilar = data;
            tabloyuGuncelle();
            dashboardGuncelle();
        })
        .catch(error => console.error("Kullanıcılar çekilirken hata:", error));
}

function tabloyuGuncelle() {
    const tbody = document.querySelector("#kullanicilar tbody");
    if (!tbody) return;
    tbody.innerHTML = ""; 

    kullanicilar.forEach(k => {
        const tamIsim = (k.ad || "") + " " + (k.soyad || "");
        const durumMetni = k.aktifMi ? "Aktif" : "Pasif";

        // Giriş yöntemi ikonları
        const kartIkon  = k.kartNo            ? `<span class="yontem-ikon yontem-kart"  title="Kart: ${escapeHtml(k.kartNo)}">&#128266; Kart</span>` : '';
        const noIkon    = k.ogrenciNo         ? `<span class="yontem-ikon yontem-no"    title="Okul No: ${escapeHtml(k.ogrenciNo)}">&#128290; No</span>` : '';
        const fpIkon    = k.parmakIziSensorId ? `<span class="yontem-ikon yontem-fp"    title="FP Slot: ${escapeHtml(k.parmakIziSensorId)}">&#128406; FP:${escapeHtml(k.parmakIziSensorId)}</span>` : '';
        const yontemler = (kartIkon + noIkon + fpIkon) || '<span class="yontem-yok">&#10060; Yok</span>';

        const row = `<tr>
            <td>${k.userId}</td>
            <td>${escapeHtml(tamIsim.trim())}</td>
            <td>${escapeHtml(k.ogrenciNo || '-')}</td>
            <td class="yontem-hucre">${yontemler}</td>
            <td>${escapeHtml(k.rol || '-')}</td>
            <td><span class="status-${durumMetni.toLowerCase()}">${durumMetni}</span></td>
            <td>
                <button class="edit-btn" onclick="kullaniciDuzenle(${k.userId})">Düzenle</button>
                <button class="delete-btn" onclick="kullaniciSil(${k.userId})">Sil</button>
            </td>
        </tr>`;
        tbody.innerHTML += row;
    });
}

function modaliKapat() {
    modal.style.display = 'none';
}

function yeniKullaniciEkle() {
    document.getElementById('kullaniciFormu').reset(); 
    document.getElementById('formKullaniciId').value = ''; 
    modalBaslik.innerText = 'Yeni Kullanıcı Ekle';
    const uyari = document.getElementById('formUyari');
    if (uyari) uyari.style.display = 'none';
    modal.style.display = 'block'; 
}

function kullaniciDuzenle(id) {
    const kullanici = kullanicilar.find(k => k.userId === id);
    if (kullanici) {
        document.getElementById('formKullaniciId').value = kullanici.userId;
        document.getElementById('formAdSoyad').value = (kullanici.ad || "") + " " + (kullanici.soyad || "");
        document.getElementById('formNo').value = kullanici.ogrenciNo || "";
        document.getElementById('formKartNo').value = kullanici.kartNo || "";
        document.getElementById('formParmakIziSlot').value = kullanici.parmakIziSensorId || "";
        document.getElementById('formRol').value = kullanici.rol || "";
        document.getElementById('formDurum').value = kullanici.aktifMi ? "Aktif" : "Pasif";

        const uyari = document.getElementById('formUyari');
        if (uyari) uyari.style.display = 'none';

        modalBaslik.innerText = 'Kullanıcı Düzenle';
        modal.style.display = 'block';
    }
}

function kullaniciKaydet(event) {
    event.preventDefault();

    const formAdSoyad = document.getElementById('formAdSoyad').value.trim();
    const isimParcalari = formAdSoyad.split(' ');
    const soyad = isimParcalari.length > 1 ? isimParcalari.pop() : "";
    const ad = isimParcalari.join(' ');
    const idDegeri = document.getElementById('formKullaniciId').value;

    const kartNo = document.getElementById('formKartNo').value.trim();
    const fpSlot = document.getElementById('formParmakIziSlot').value.trim();

    // Uyarı: en az bir giriş yöntemi önerilir
    const uyariDiv = document.getElementById('formUyari');
    if (!kartNo && !fpSlot) {
        if (uyariDiv) {
            uyariDiv.style.display = 'block';
            uyariDiv.innerHTML = '&#9888;&#65039; <strong>Uyarı:</strong> Kart numarası ve parmak izi slot girilmedi. Bu kullanıcı sadece <strong>okul numarasıyla</strong> giriş yapabilir.';
        }
    } else {
        if (uyariDiv) uyariDiv.style.display = 'none';
    }

    const gonderilecekKullanici = {
        ...(idDegeri && { userId: idDegeri }),
        ad: ad,
        soyad: soyad,
        ogrenciNo: document.getElementById('formNo').value,
        kartNo: kartNo || null,
        parmakIziSensorId: fpSlot || null,
        rol: document.getElementById('formRol').value,
        aktifMi: document.getElementById('formDurum').value === 'Aktif'
    };

    const url = idDegeri ? `${API_BASE}/api/users/${idDegeri}` : `${API_BASE}/api/users`;
    const method = idDegeri ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(gonderilecekKullanici)
    })
    .then(response => {
        if (!response.ok) throw new Error("Sunucu reddetti.");
        return response.json();
    })
    .then(() => {
        alert(idDegeri ? "Kullanıcı güncellendi!" : "Yeni kullanıcı eklendi!");
        modaliKapat();
        veritabanindanKullanicilariGetir(); 
    })
    .catch(error => {
        console.error("HATA:", error);
        alert("İşlem başarısız! Bilgileri kontrol edip tekrar deneyin.");
    });
}

function kullaniciSil(id) {
    if (confirm("Bu kullanıcıyı kalıcı olarak silmek istediğinize emin misiniz?")) {
        fetch(`${API_BASE}/api/users/${id}`, { method: 'DELETE' })
        .then(response => {
            if (!response.ok) throw new Error("Silme işlemi başarısız.");
            alert("Kullanıcı silindi.");
            veritabanindanKullanicilariGetir();
        })
        .catch(error => alert("Kullanıcı silinirken hata oluştu!"));
    }
}

// ==========================================
// 6. CİHAZ (TERMINAL) YÖNETİMİ MODÜLÜ
// ==========================================
function veritabanindanCihazlariGetir() {
    fetch(`${API_BASE}/api/devices`)
        .then(response => response.json())
        .then(data => {
            cihazlar = data;
            cihazTablosunuGuncelle();
            dashboardGuncelle();
        })
        .catch(error => console.error("Cihazlar çekilirken hata:", error));
}

function cihazTablosunuGuncelle() {
    const tbody = document.getElementById("cihazTablosuGovdesi");
    if(!tbody) return;
    tbody.innerHTML = ""; 

    cihazlar.forEach(c => {
        const durumMetni = c.aktifMi ? "Aktif" : "Pasif";
        const row = `<tr>
            <td>${c.deviceId}</td>
            <td>${escapeHtml(c.cihazAdi || '-')}</td>
            <td>${escapeHtml(c.konum || '-')}</td>
            <td>${escapeHtml(c.ipAdresi || '-')}</td>
            <td><span class="status-${durumMetni.toLowerCase()}">${durumMetni}</span></td>
            <td>
                <button class="edit-btn" onclick="cihazDuzenle(${c.deviceId})">Düzenle</button>
                <button class="delete-btn" onclick="cihazSil(${c.deviceId})">Sil</button>
            </td>
        </tr>`;
        tbody.innerHTML += row;
    });
}

function cihazModaliKapat() {
    cihazModal.style.display = 'none';
}

function yeniCihazEkle() {
    document.getElementById('cihazFormu').reset(); 
    document.getElementById('formCihazId').value = ''; 
    modalCihazBaslik.innerText = 'Yeni Terminal Tanımla';
    cihazModal.style.display = 'block';
}

function cihazDuzenle(id) {
    const cihaz = cihazlar.find(c => c.deviceId === id);
    if (cihaz) {
        document.getElementById('formCihazId').value = cihaz.deviceId;
        document.getElementById('formCihazAd').value = cihaz.cihazAdi || "";
        document.getElementById('formCihazKonum').value = cihaz.konum || "";
        document.getElementById('formCihazIp').value = cihaz.ipAdresi || "";
        document.getElementById('formCihazDurum').value = cihaz.aktifMi ? "Aktif" : "Pasif";

        modalCihazBaslik.innerText = 'Cihaz Bilgilerini Güncelle';
        cihazModal.style.display = 'block';
    }
}

function cihazKaydet(event) {
    event.preventDefault();

    const idDegeri = document.getElementById('formCihazId').value;
    const gonderilecekCihaz = {
        ...(idDegeri && { deviceId: idDegeri }),
        cihazAdi: document.getElementById('formCihazAd').value,
        konum: document.getElementById('formCihazKonum').value,
        ipAdresi: document.getElementById('formCihazIp').value,
        cihazTipi: "Turnike/Kapi", 
        aktifMi: document.getElementById('formCihazDurum').value === 'Aktif'
    };

    const url = idDegeri ? `${API_BASE}/api/devices/${idDegeri}` : `${API_BASE}/api/devices`;
    const method = idDegeri ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(gonderilecekCihaz)
    })
    .then(response => {
        if (!response.ok) throw new Error("Cihaz kaydedilemedi.");
        return response.json();
    })
    .then(() => {
        alert(idDegeri ? "Cihaz güncellendi!" : "Yeni cihaz eklendi!");
        cihazModaliKapat();
        veritabanindanCihazlariGetir();
    })
    .catch(error => console.error("HATA:", error));
}

function cihazSil(id) {
    if (confirm("Bu cihazı kalıcı olarak silmek istediğinize emin misiniz?")) {
        fetch(`${API_BASE}/api/devices/${id}`, { method: 'DELETE' })
        .then(response => {
            if (!response.ok) throw new Error("Silme başarısız.");
            alert("Cihaz başarıyla silindi.");
            veritabanindanCihazlariGetir();
        })
        .catch(error => console.error("Hata:", error));
    }
}

// ==========================================
// 7. LOG (GEÇİŞ KAYITLARI) MODÜLÜ
// ==========================================
function veritabanindanLoglariGetir() {
    fetch(`${API_BASE}/api/logs`)
        .then(response => {
            if (!response.ok) throw new Error("Ağ hatası: " + response.status);
            return response.json();
        })
        .then(data => {
            loglar = data;
            loglariGuncelle();
            dashboardGuncelle();
        })
        .catch(error => console.error("Loglar çekilirken hata:", error));
}

function loglariGuncelle(gosterilecekLoglar = loglar) {
    const tbody = document.querySelector("#loglar tbody");
    if(!tbody) return;
    tbody.innerHTML = "";

    if (!gosterilecekLoglar || gosterilecekLoglar.length === 0) {
        tbody.innerHTML = "<tr><td colspan='6' style='text-align:center;'>Kayıt bulunamadı.</td></tr>";
        return;
    }

    const siraliLoglar = [...gosterilecekLoglar];

    siraliLoglar.forEach(l => {
        const tarih = l.girisZamani ? new Date(l.girisZamani).toLocaleString('tr-TR') : '-';
        const cihazId = l.device ? l.device.deviceId : '-';
        const kullaniciId = l.user ? l.user.userId : 'Kayıtsız Kart';

        const row = `<tr>
            <td>${tarih}</td>
            <td>${cihazId}</td>
            <td>${kullaniciId}</td>
            <td>${escapeHtml(l.girisYontemi || '-')}</td>
            <td style="color: ${l.sonuc && l.sonuc.includes('ONAYLANDI') ? 'green' : (l.sonuc && l.sonuc.includes('KAYDEDILDI') ? '#0d47a1' : 'red')}; font-weight: bold;">
                ${escapeHtml(l.sonuc || '-')}
            </td>
            <td class="log-aciklama">${escapeHtml(l.aciklama || '-')}</td>
        </tr>`;
        tbody.innerHTML += row;
    });
}

function logFiltrele() {
    const arananKullaniciId = document.getElementById('filtreKullanici').value;
    const arananSonuc = document.getElementById('filtreSonuc').value;

    const filtrelenmisLoglar = loglar.filter(l => {
        let eslesiyorMu = true;
        if (arananKullaniciId && l.user && l.user.userId.toString() !== arananKullaniciId) eslesiyorMu = false;
        if (arananSonuc && l.sonuc && !l.sonuc.includes(arananSonuc)) eslesiyorMu = false;
        return eslesiyorMu;
    });
    loglariGuncelle(filtrelenmisLoglar);
}

function filtreyiTemizle() {
    document.getElementById('filtreKullanici').value = '';
    document.getElementById('filtreSonuc').value = '';
    loglariGuncelle(loglar); 
}

// ==========================================
// 8. GEÇİŞ SİMÜLASYONU (TEST) — 3 YÖNTEM
// ==========================================

// Sekme geçişi
function simTabSec(tip) {
    // Tüm panel ve sekmeleri pasif yap
    ['kart','no','fp'].forEach(t => {
        const panel = document.getElementById('simPanel' + t.charAt(0).toUpperCase() + t.slice(1));
        const tab   = document.getElementById('tab' + t.charAt(0).toUpperCase() + t.slice(1));
        if (panel) panel.style.display = 'none';
        if (tab)   tab.classList.remove('active');
    });
    // Seçilen sekmeyi aktif yap
    const aktifPanel = document.getElementById('simPanel' + tip.charAt(0).toUpperCase() + tip.slice(1));
    const aktifTab   = document.getElementById('tab'      + tip.charAt(0).toUpperCase() + tip.slice(1));
    if (aktifPanel) aktifPanel.style.display = 'block';
    if (aktifTab)   aktifTab.classList.add('active');

    // Sonuç alanını temizle
    const sonucDiv = document.getElementById('simSonuc');
    if (sonucDiv) { sonucDiv.style.display = 'none'; sonucDiv.innerText = ''; }
}

function simulasyonCalistir(tip) {
    const sonucDiv = document.getElementById('simSonuc');
    let url = '';

    if (tip === 'kart') {
        const kartNo  = (document.getElementById('simKartNo') || {}).value.trim();
        const cihazId = parseInt((document.getElementById('simCihazIdKart') || {}).value || '0', 10);
        if (!kartNo || !cihazId || cihazId < 1) {
            alert("Geçerli kart numarası ve cihaz ID girin.");
            return;
        }
        url = `${API_BASE}/api/auth/kart-okut?kartNo=${encodeURIComponent(kartNo)}&deviceId=${cihazId}`;

    } else if (tip === 'no') {
        const okulNo  = (document.getElementById('simOkulNo') || {}).value.trim();
        const cihazId = parseInt((document.getElementById('simCihazIdNo') || {}).value || '0', 10);
        if (!okulNo || !cihazId || cihazId < 1) {
            alert("Geçerli okul numarası ve cihaz ID girin.");
            return;
        }
        url = `${API_BASE}/api/auth/numara-okut?ogrenciNo=${encodeURIComponent(okulNo)}&deviceId=${cihazId}`;

    } else if (tip === 'fp') {
        const fpSlot  = (document.getElementById('simFPSlot') || {}).value.trim();
        const cihazId = parseInt((document.getElementById('simCihazIdFP') || {}).value || '0', 10);
        if (!fpSlot || !cihazId || cihazId < 1) {
            alert("Geçerli parmak izi slot numarası ve cihaz ID girin.");
            return;
        }
        url = `${API_BASE}/api/auth/parmak-izi-okut?parmakIzi=${encodeURIComponent(fpSlot)}&deviceId=${cihazId}`;

    } else {
        alert("Bilinmeyen test tipi.");
        return;
    }

    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => {
        if (!response.ok) throw new Error("Sunucuya ulaşılamadı!");
        return response.text(); 
    })
    .then(yanit => {
        sonucDiv.style.display = "block";
        sonucDiv.innerText = yanit; 
        
        if (yanit === "ONAYLANDI") {
            sonucDiv.className = "sim-result result-approved";
        } else {
            sonucDiv.className = "sim-result result-denied";
        }
        
        veritabanindanLoglariGetir(); 
    })
    .catch(error => {
        console.error("HATA:", error);
        sonucDiv.style.display = "block";
        sonucDiv.innerText = "SİSTEM HATASI!";
        sonucDiv.className = "sim-result result-denied";
    });
}

// ==========================================
// 9. CANLI SENSÖR YAKALAMA (POLLING)
// ==========================================

<<<<<<< HEAD
let _sensorTimerId    = null;   // setTimeout handle (zaman aşımı)
let _sensorTargetField = null;  // Doldurulacak input ID'si
let _sensorBtnId      = null;   // Aktif buton ID'si
let _sensorRemaining  = 3;      // Geri sayım (sn) - Mock için kısa tutuyoruz
let _sensorTickId     = null;   // Geri sayım interval

const SENSOR_TIMEOUT_MS = 3000; // 3 saniye mock animasyonu

/**
 * Butona tıklandığında çağrılır (MOCK VERSIYON)
=======
let _sensorSessionId  = null;   // Aktif oturum kimliği
let _sensorPollingId  = null;   // setInterval handle
let _sensorTimerId    = null;   // setTimeout handle (zaman aşımı)
let _sensorTargetField = null;  // Doldurulacak input ID'si
let _sensorBtnId      = null;   // Aktif buton ID'si
let _sensorRemaining  = 30;     // Geri sayım (sn)
let _sensorTickId     = null;   // Geri sayım interval

const SENSOR_TIMEOUT_MS = 30000; // 30 saniye
const SENSOR_POLL_MS    = 1500;  // 1.5 saniyede bir sorgula

/**
 * Butona tıklandığında çağrılır.
>>>>>>> e06b7e102bf27bffc7f4a4add8d940d63fea4190
 * @param {string} type         'CARD' | 'FINGERPRINT' | 'SCHOOL_NO'
 * @param {string} targetField  Doldurulacak input'un id'si
 * @param {string} btnId        Aktif buton id'si (görsel geri bildirim için)
 */
function sensorOturumBaslat(type, targetField, btnId) {
    // Varsa önceki oturumu kapat
    sensorTemizle();

    _sensorTargetField = targetField;
    _sensorBtnId       = btnId;

    // Overlay metinlerini ayarla
    const isKart = type === 'CARD';
    const isFP   = type === 'FINGERPRINT';
    document.getElementById('sensorIconBig').textContent       = isKart ? '📡' : (isFP ? '🖐' : '🔢');
<<<<<<< HEAD
    document.getElementById('sensorModalBaslik').textContent   = isKart ? 'Sensör Aktif...' : (isFP ? 'Sensör Aktif...' : 'Sistem Aktif...');
    document.getElementById('sensorModalAciklama').textContent = 'Okunuyor, lütfen bekleyin... (Otomatik ID Atanıyor)';
=======
    document.getElementById('sensorModalBaslik').textContent   = isKart ? 'Kart Bekleniyor...' : (isFP ? 'Parmak İzi Bekleniyor...' : 'Numara Bekleniyor...');
    document.getElementById('sensorModalAciklama').textContent = isKart
        ? 'Arduino\'daki kart okuyucuya kartınızı yaklaştırın.'
        : (isFP ? 'Parmak izini sensöre okutun.' : 'Tuş takımından numarayı girip # ile onaylayın.');
>>>>>>> e06b7e102bf27bffc7f4a4add8d940d63fea4190

    // Geri sayımı başlat
    _sensorRemaining = SENSOR_TIMEOUT_MS / 1000;
    _guncelleCountdown();

    // Butonu aktif göster
    const btn = document.getElementById(btnId);
    if (btn) btn.classList.add('sensor-aktif');

    // Overlay'i göster
    document.getElementById('sensorModal').style.display = 'block';

<<<<<<< HEAD
    // Timer dolgu animasyonu (CSS geçiş ile)
    const fill = document.getElementById('sensorTimerFill');
    if (fill) {
        fill.style.transition = 'none';
        fill.style.width = '100%';
        // Bir frame bekle, sonra geçişi başlat
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                fill.style.transition = `width ${SENSOR_TIMEOUT_MS}ms linear`;
                fill.style.width = '0%';
            });
        });
    }

    // Geri sayım tick
    _sensorTickId = setInterval(() => {
        _sensorRemaining--;
        _guncelleCountdown();
    }, 1000);

    // MOCK: Süre bitince otomatik değer ata
    _sensorTimerId = setTimeout(() => {
        let mockValue = "";
        if (type === 'CARD') {
            // Rastgele 8 haneli HEX üret
            mockValue = Math.floor(Math.random() * 0xFFFFFFFF).toString(16).padStart(8, '0');
        } else if (type === 'FINGERPRINT') {
            // Rastgele 1 ile 127 arası slot üret
            mockValue = Math.floor(Math.random() * 127) + 1;
        } else {
            // Numara için rastgele 4 haneli sayı
            mockValue = Math.floor(1000 + Math.random() * 9000);
        }

        // Forma yaz
        const inp = document.getElementById(_sensorTargetField);
        if (inp) {
            inp.value = mockValue;
            inp.style.background = '#dcfce7'; // Kısa süre yeşil yanma
            setTimeout(() => { inp.style.background = ''; }, 1500);
        }

        sensorTemizle();
        // Overlay'i kapat
        document.getElementById('sensorModal').style.display = 'none';

    }, SENSOR_TIMEOUT_MS);
=======
    // Backend'de oturum aç
    fetch(`${API_BASE}/api/sensor/start?type=${type}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            _sensorSessionId = data.sessionId;

            // Polling başlat
            _sensorPollingId = setInterval(_sensorPoll, SENSOR_POLL_MS);

            // Zaman aşımı
            _sensorTimerId = setTimeout(() => {
                sensorIptal();
                alert('Sensörden cevap alınamadı (30 sn doldu). Tekrar deneyin.');
            }, SENSOR_TIMEOUT_MS);

            // Timer dolgu animasyonu (CSS geçiş ile)
            const fill = document.getElementById('sensorTimerFill');
            if (fill) {
                fill.style.transition = 'none';
                fill.style.width = '100%';
                // Bir frame bekle, sonra geçişi başlat
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        fill.style.transition = `width ${SENSOR_TIMEOUT_MS}ms linear`;
                        fill.style.width = '0%';
                    });
                });
            }

            // Geri sayım tick
            _sensorTickId = setInterval(() => {
                _sensorRemaining--;
                _guncelleCountdown();
            }, 1000);
        })
        .catch(() => {
            sensorIptal();
            alert('Sensör oturumu başlatılamadı! Sunucu bağlantısını kontrol edin.');
        });
>>>>>>> e06b7e102bf27bffc7f4a4add8d940d63fea4190
}

function _guncelleCountdown() {
    const el = document.getElementById('sensorCountdown');
    if (el) el.textContent = `${_sensorRemaining} sn kaldı`;
}

<<<<<<< HEAD
/** Kullanıcı İptal butonuna bastı. */
function sensorIptal() {
=======
function _sensorPoll() {
    if (!_sensorSessionId) return;

    fetch(`${API_BASE}/api/sensor/result?sessionId=${_sensorSessionId}`)
        .then(r => r.json())
        .then(data => {
            if (data.status === 'READY' && data.value) {
                // Forma yaz
                const inp = document.getElementById(_sensorTargetField);
                if (inp) {
                    inp.value = data.value;
                    inp.style.background = '#dcfce7'; // Kısa süre yeşil yanma
                    setTimeout(() => { inp.style.background = ''; }, 1500);
                }
                // Oturumu sunucuda temizle
                fetch(`${API_BASE}/api/sensor/session?sessionId=${_sensorSessionId}`, { method: 'DELETE' }).catch(() => {});
                sensorTemizle();
                // Overlay'i kapat
                document.getElementById('sensorModal').style.display = 'none';
            }
            // WAITING ise bir sonraki poll'u bekle
        })
        .catch(() => { /* ağ hatası — devam et */ });
}

/** Kullanıcı İptal butonuna bastı. */
function sensorIptal() {
    if (_sensorSessionId) {
        fetch(`${API_BASE}/api/sensor/session?sessionId=${_sensorSessionId}`, { method: 'DELETE' }).catch(() => {});
    }
>>>>>>> e06b7e102bf27bffc7f4a4add8d940d63fea4190
    sensorTemizle();
    document.getElementById('sensorModal').style.display = 'none';
}

/** Tüm zamanlayıcıları ve durumu temizler. */
function sensorTemizle() {
<<<<<<< HEAD
    clearTimeout(_sensorTimerId);
    clearInterval(_sensorTickId);
    _sensorTimerId   = null;
    _sensorTickId    = null;
=======
    clearInterval(_sensorPollingId);
    clearTimeout(_sensorTimerId);
    clearInterval(_sensorTickId);
    _sensorPollingId = null;
    _sensorTimerId   = null;
    _sensorTickId    = null;
    _sensorSessionId = null;
>>>>>>> e06b7e102bf27bffc7f4a4add8d940d63fea4190

    // Buton aktif sınıfını kaldır
    if (_sensorBtnId) {
        const btn = document.getElementById(_sensorBtnId);
        if (btn) btn.classList.remove('sensor-aktif');
    }
    _sensorBtnId       = null;
    _sensorTargetField = null;

    // Timer dolgu sıfırla
    const fill = document.getElementById('sensorTimerFill');
    if (fill) { fill.style.transition = 'none'; fill.style.width = '100%'; }
}