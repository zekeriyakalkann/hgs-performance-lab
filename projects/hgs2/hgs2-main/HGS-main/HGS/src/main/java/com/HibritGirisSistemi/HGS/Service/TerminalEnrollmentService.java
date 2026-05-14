package com.HibritGirisSistemi.HGS.Service;

import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.HibritGirisSistemi.HGS.Entity.Device;
import com.HibritGirisSistemi.HGS.Entity.Log;
import com.HibritGirisSistemi.HGS.Entity.User;
import com.HibritGirisSistemi.HGS.Repository.DeviceRepository;
import com.HibritGirisSistemi.HGS.Repository.LogRepository;
import com.HibritGirisSistemi.HGS.Repository.UserRepository;

@Service
public class TerminalEnrollmentService {

    private final UserRepository userRepository;
    private final DeviceRepository deviceRepository;
    private final LogRepository logRepository;

    public TerminalEnrollmentService(UserRepository userRepository, DeviceRepository deviceRepository, LogRepository logRepository) {
        this.userRepository = userRepository;
        this.deviceRepository = deviceRepository;
        this.logRepository = logRepository;
    }

    private Optional<Device> aktifCihaz(Integer deviceId) {
        Optional<Device> opt = deviceRepository.findById(deviceId);
        if (opt.isEmpty() || !Boolean.TRUE.equals(opt.get().getAktifMi())) {
            return Optional.empty();
        }
        return opt;
    }

    private static String normalizeKart(String kartNo) {
        if (kartNo == null) return "";
        return kartNo.replaceAll("\\s+", "").trim().toLowerCase();
    }

    @Transactional
    public String kartKaydet(Integer deviceId, String ogrenciNo, String kartNo) {
        Optional<Device> deviceOpt = aktifCihaz(deviceId);
        if (deviceOpt.isEmpty()) {
            return "HATA";
        }
        String ogr = ogrenciNo == null ? "" : ogrenciNo.trim();
        if (ogr.isEmpty()) {
            return "HATA";
        }
        String kn = normalizeKart(kartNo);
        if (kn.isEmpty()) {
            return "HATA";
        }

        Optional<User> userOpt = userRepository.findByOgrenciNoIgnoreCase(ogr);
        if (userOpt.isEmpty()) {
            return "HATA";
        }
        User user = userOpt.get();

        Optional<User> kartSahibi = userRepository.findByKartNoIgnoreCase(kn);
        if (kartSahibi.isPresent() && !kartSahibi.get().getUserId().equals(user.getUserId())) {
            return "HATA";
        }

        user.setKartNo(kn);
        userRepository.save(user);

        Log log = new Log();
        log.setDevice(deviceOpt.get());
        log.setUser(user);
        log.setGirisYontemi("KAYIT_KART");
        log.setSonuc("KAYDEDILDI");
        log.setYetkiliMi(true);
        log.setAciklama("Terminal kart atamasi: " + kn);
        logRepository.save(log);

        return "OK";
    }

    @Transactional
    public String parmakKaydet(Integer deviceId, String ogrenciNo, String slot) {
        Optional<Device> deviceOpt = aktifCihaz(deviceId);
        if (deviceOpt.isEmpty()) {
            return "HATA";
        }
        String ogr = ogrenciNo == null ? "" : ogrenciNo.trim();
        String sl = slot == null ? "" : slot.trim();
        if (ogr.isEmpty() || sl.isEmpty()) {
            return "HATA";
        }

        Optional<User> userOpt = userRepository.findByOgrenciNoIgnoreCase(ogr);
        if (userOpt.isEmpty()) {
            return "HATA";
        }
        User user = userOpt.get();

        Optional<User> slotSahibi = userRepository.findByParmakIziSensorId(sl);
        if (slotSahibi.isPresent() && !slotSahibi.get().getUserId().equals(user.getUserId())) {
            return "HATA";
        }

        user.setParmakIziSensorId(sl);
        userRepository.save(user);

        Log log = new Log();
        log.setDevice(deviceOpt.get());
        log.setUser(user);
        log.setGirisYontemi("KAYIT_FP");
        log.setSonuc("KAYDEDILDI");
        log.setYetkiliMi(true);
        log.setAciklama("Terminal parmak slot: " + sl);
        logRepository.save(log);

        return "OK";
    }

    @Transactional
    public String ogrenciNoDegistir(Integer deviceId, String eskiNo, String yeniNo) {
        Optional<Device> deviceOpt = aktifCihaz(deviceId);
        if (deviceOpt.isEmpty()) {
            return "HATA";
        }
        String eski = eskiNo == null ? "" : eskiNo.trim();
        String yeni = yeniNo == null ? "" : yeniNo.trim();
        if (eski.isEmpty() || yeni.isEmpty() || eski.equalsIgnoreCase(yeni)) {
            return "HATA";
        }

        Optional<User> userOpt = userRepository.findByOgrenciNoIgnoreCase(eski);
        if (userOpt.isEmpty()) {
            return "HATA";
        }
        User user = userOpt.get();

        Optional<User> baska = userRepository.findByOgrenciNoIgnoreCase(yeni);
        if (baska.isPresent() && !baska.get().getUserId().equals(user.getUserId())) {
            return "HATA";
        }

        user.setOgrenciNo(yeni);
        userRepository.save(user);

        Log log = new Log();
        log.setDevice(deviceOpt.get());
        log.setUser(user);
        log.setGirisYontemi("KAYIT_NO");
        log.setSonuc("KAYDEDILDI");
        log.setYetkiliMi(true);
        log.setAciklama("Okul numarasi guncellendi: " + eski + " -> " + yeni);
        logRepository.save(log);

        return "OK";
    }

    /**
     * Cihaz üzerinden yeni öğrenci (kullanıcı) kaydı oluşturur.
     * Aynı okul numarası zaten varsa günceller (idempotent).
     * Ad / soyad girilmemişse "Kullanici" olarak atanır.
     */
    @Transactional
    public String ogrenciKaydet(Integer deviceId, String ogrenciNo) {
        Optional<Device> deviceOpt = aktifCihaz(deviceId);
        if (deviceOpt.isEmpty()) {
            return "HATA";
        }
        String ogr = ogrenciNo == null ? "" : ogrenciNo.trim();
        if (ogr.isEmpty()) {
            return "HATA";
        }

        // Zaten varsa güncelleme yapma, OK döndür
        Optional<User> mevcut = userRepository.findByOgrenciNoIgnoreCase(ogr);
        if (mevcut.isPresent()) {
            return "OK";
        }

        // Yeni kullanıcı oluştur
        User yeniUser = new User();
        yeniUser.setOgrenciNo(ogr);
        yeniUser.setAd("Kullanici");
        yeniUser.setSoyad(ogr);
        yeniUser.setRol("OGRENCI");
        yeniUser.setYetkiSeviyesi("STANDART");
        yeniUser.setAktifMi(true);
        userRepository.save(yeniUser);

        Log log = new Log();
        log.setDevice(deviceOpt.get());
        log.setUser(yeniUser);
        log.setGirisYontemi("KAYIT_OGR");
        log.setSonuc("KAYDEDILDI");
        log.setYetkiliMi(true);
        log.setAciklama("Terminal ogrenci kaydi: " + ogr);
        logRepository.save(log);

        return "OK";
    }
}
