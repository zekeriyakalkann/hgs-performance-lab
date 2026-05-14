package com.HibritGirisSistemi.HGS.Entity; // Kendi paket ismine göre düzeltmeyi unutma

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import com.fasterxml.jackson.annotation.JsonIgnore;

@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY) // PostgreSQL'de otomatik artan (SERIAL) ID
    private Integer userId;

    @Column(name = "ogrenci_no", unique = true, length = 20)
    private String ogrenciNo;

    @Column(length = 50)
    private String ad;

    @Column(length = 50)
    private String soyad;

    @Column(name = "kart_no", unique = true, length = 22)
    private String kartNo;

    @Lob // Biyometrik parmak izi verisini (BLOB) tutmak için
    @JsonIgnore
    @Column(name = "parmak_izi_sablonu")
    private byte[] parmakIziSablonu;

    /** R307 vb. sensördeki kayıt slotu (ESP32 FP: ile gönderilen sayı, örn. "1") */
    @Column(name = "parmak_izi_sensor_id", length = 10)
    private String parmakIziSensorId;

    @Column(length = 20)
    private String rol;

    @Column(name = "yetki_seviyesi", length = 20)
    private String yetkiSeviyesi;

    @Column(name = "aktif_mi")
    private Boolean aktifMi;

    @Column(name = "olusturma_tarihi", updatable = false)
    private LocalDateTime olusturmaTarihi;

    // Veritabanına ilk kez kaydedilirken tarihi otomatik atar
    @PrePersist
    protected void onCreate() {
        this.olusturmaTarihi = LocalDateTime.now();
    }
    //geter ve setter metotları

    public Integer getUserId() {
        return userId;
    }

    public String getOgrenciNo() {
        return ogrenciNo;
    }

    public String getAd() {
        return ad;
    }

    public String getSoyad() {
        return soyad;
    }

    public String getKartNo() {
        return kartNo;
    }

    public byte[] getParmakIziSablonu() {
        return parmakIziSablonu;
    }

    public String getParmakIziSensorId() {
        return parmakIziSensorId;
    }

    public String getRol() {
        return rol;
    }

    public String getYetkiSeviyesi() {
        return yetkiSeviyesi;
    }

    public Boolean getAktifMi() {
        return aktifMi;
    }

    public LocalDateTime getOlusturmaTarihi() {
        return olusturmaTarihi;
    }

    public void setUserId(Integer userId) {
        this.userId = userId;
    }

    public void setOgrenciNo(String ogrenciNo) {
        this.ogrenciNo = ogrenciNo;
    }

    public void setAd(String ad) {
        this.ad = ad;
    }

    public void setSoyad(String soyad) {
        this.soyad = soyad;
    }

    public void setKartNo(String kartNo) {
        this.kartNo = kartNo;
    }

    public void setParmakIziSablonu(byte[] parmakIziSablonu) {
        this.parmakIziSablonu = parmakIziSablonu;
    }

    public void setParmakIziSensorId(String parmakIziSensorId) {
        this.parmakIziSensorId = parmakIziSensorId;
    }

    public void setRol(String rol) {
        this.rol = rol;
    }

    public void setYetkiSeviyesi(String yetkiSeviyesi) {
        this.yetkiSeviyesi = yetkiSeviyesi;
    }

    public void setAktifMi(Boolean aktifMi) {
        this.aktifMi = aktifMi;
    }

    public void setOlusturmaTarihi(LocalDateTime olusturmaTarihi) {
        this.olusturmaTarihi = olusturmaTarihi;
    }
    
    
    // LÜTFEN DİKKAT: IDE'ni kullanarak (Sağ tık -> Generate -> Getters and Setters) 
    // tüm değişkenler için Getter ve Setter metotlarını buraya eklemelisin.
}