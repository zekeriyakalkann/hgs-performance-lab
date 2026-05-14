package com.HibritGirisSistemi.HGS.Entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "logs")
public class Log {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer logId;

    // Cihaz tablosu ile ilişki (Bir cihazın birden çok logu olabilir)
    @ManyToOne
    @JoinColumn(name = "device_id", referencedColumnName = "deviceId")
    private Device device;

    // Kullanıcı tablosu ile ilişki (Bir kullanıcının birden çok logu olabilir)
    @ManyToOne
    @JoinColumn(name = "user_id", referencedColumnName = "userId")
    private User user;

    @Column(name = "giris_yontemi", length = 20)
    private String girisYontemi;

    @Column(name = "giris_zamani", updatable = false)
    private LocalDateTime girisZamani;

    @Column(length = 20)
    private String sonuc;

    @Column(name = "yetkili_mi")
    private Boolean yetkiliMi;

    @Column(length = 255)
    private String aciklama;

    @PrePersist
    protected void onCreate() {
        this.girisZamani = LocalDateTime.now();
    }

    public Integer getLogId() {
        return logId;
    }

    public void setLogId(Integer logId) {
        this.logId = logId;
    }

    public Device getDevice() {
        return device;
    }

    public void setDevice(Device device) {
        this.device = device;
    }

    public User getUser() {
        return user;
    }

    public void setUser(User user) {
        this.user = user;
    }

    public String getGirisYontemi() {
        return girisYontemi;
    }

    public void setGirisYontemi(String girisYontemi) {
        this.girisYontemi = girisYontemi;
    }

    public LocalDateTime getGirisZamani() {
        return girisZamani;
    }

    public void setGirisZamani(LocalDateTime girisZamani) {
        this.girisZamani = girisZamani;
    }

    public String getSonuc() {
        return sonuc;
    }

    public void setSonuc(String sonuc) {
        this.sonuc = sonuc;
    }

    public Boolean getYetkiliMi() {
        return yetkiliMi;
    }

    public void setYetkiliMi(Boolean yetkiliMi) {
        this.yetkiliMi = yetkiliMi;
    }

    public String getAciklama() {
        return aciklama;
    }

    public void setAciklama(String aciklama) {
        this.aciklama = aciklama;
    }

    // getters ve setters metotları
    
}