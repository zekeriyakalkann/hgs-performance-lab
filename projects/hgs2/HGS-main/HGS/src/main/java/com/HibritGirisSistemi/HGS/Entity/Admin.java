package com.HibritGirisSistemi.HGS.Entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "admins")
public class Admin {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer adminId;

    @Column(name = "kullanici_adi", unique = true, length = 50)
    private String kullaniciAdi;

    @Column(name = "sifre_hash", length = 255)
    private String sifreHash;

    @Column(name = "ad_soyad", length = 100)
    private String adSoyad;

    @Column(length = 100)
    private String email;

    @Column(name = "yetki_seviyesi", length = 20)
    private String yetkiSeviyesi;

    @Column(name = "son_giris")
    private LocalDateTime sonGiris;

    @Column(name = "olusturma_tarihi", updatable = false)
    private LocalDateTime olusturmaTarihi;

    @PrePersist
    protected void onCreate() {
        this.olusturmaTarihi = LocalDateTime.now();
    }

    public Integer getAdminId() {
        return adminId;
    }

    public void setAdminId(Integer adminId) {
        this.adminId = adminId;
    }

    public String getKullaniciAdi() {
        return kullaniciAdi;
    }

    public void setKullaniciAdi(String kullaniciAdi) {
        this.kullaniciAdi = kullaniciAdi;
    }

    public String getSifreHash() {
        return sifreHash;
    }

    public void setSifreHash(String sifreHash) {
        this.sifreHash = sifreHash;
    }

    public String getAdSoyad() {
        return adSoyad;
    }

    public void setAdSoyad(String adSoyad) {
        this.adSoyad = adSoyad;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getYetkiSeviyesi() {
        return yetkiSeviyesi;
    }

    public void setYetkiSeviyesi(String yetkiSeviyesi) {
        this.yetkiSeviyesi = yetkiSeviyesi;
    }

    public LocalDateTime getSonGiris() {
        return sonGiris;
    }

    public void setSonGiris(LocalDateTime sonGiris) {
        this.sonGiris = sonGiris;
    }

    public LocalDateTime getOlusturmaTarihi() {
        return olusturmaTarihi;
    }

    public void setOlusturmaTarihi(LocalDateTime olusturmaTarihi) {
        this.olusturmaTarihi = olusturmaTarihi;
    }

    // getters ve setters metotları
    
}