package com.HibritGirisSistemi.HGS.Entity;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "devices")
public class Device {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer deviceId;

    @Column(name = "cihaz_adi", length = 100)
    private String cihazAdi;

    @Column(length = 150)
    private String konum;

    @Column(name = "cihaz_tipi", length = 50)
    private String cihazTipi;

    @Column(name = "ip_adresi", length = 45)
    private String ipAdresi;

    @Column(name = "aktif_mi")
    private Boolean aktifMi;

    @Column(name = "kurulum_tarihi", updatable = false)
    private LocalDateTime kurulumTarihi;

    @PrePersist
    protected void onCreate() {
        this.kurulumTarihi = LocalDateTime.now();
    }

    public Integer getDeviceId() {
        return deviceId;
    }

    public void setDeviceId(Integer deviceId) {
        this.deviceId = deviceId;
    }

    public String getCihazAdi() {
        return cihazAdi;
    }

    public void setCihazAdi(String cihazAdi) {
        this.cihazAdi = cihazAdi;
    }

    public String getKonum() {
        return konum;
    }

    public void setKonum(String konum) {
        this.konum = konum;
    }

    public String getCihazTipi() {
        return cihazTipi;
    }

    public void setCihazTipi(String cihazTipi) {
        this.cihazTipi = cihazTipi;
    }

    public String getIpAdresi() {
        return ipAdresi;
    }

    public void setIpAdresi(String ipAdresi) {
        this.ipAdresi = ipAdresi;
    }

    public Boolean getAktifMi() {
        return aktifMi;
    }

    public void setAktifMi(Boolean aktifMi) {
        this.aktifMi = aktifMi;
    }

    public LocalDateTime getKurulumTarihi() {
        return kurulumTarihi;
    }

    public void setKurulumTarihi(LocalDateTime kurulumTarihi) {
        this.kurulumTarihi = kurulumTarihi;
    }

    // geter ve setter metotları
    
}