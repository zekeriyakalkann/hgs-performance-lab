package com.HibritGirisSistemi.HGS.Controller;

import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.HibritGirisSistemi.HGS.Entity.Device;
import com.HibritGirisSistemi.HGS.Entity.Log;
import com.HibritGirisSistemi.HGS.Entity.User;
import com.HibritGirisSistemi.HGS.Repository.DeviceRepository;
import com.HibritGirisSistemi.HGS.Repository.LogRepository;
import com.HibritGirisSistemi.HGS.Repository.UserRepository;
import com.HibritGirisSistemi.HGS.Service.SensorCaptureService;
import com.HibritGirisSistemi.HGS.Service.SensorCaptureService.CaptureType;

@RestController
@RequestMapping("/api/auth")
@CrossOrigin(origins = "*")
public class AuthController {

    private final UserRepository userRepository;
    private final DeviceRepository deviceRepository;
    private final LogRepository logRepository;
    private final SensorCaptureService captureService;

    public AuthController(UserRepository userRepository, DeviceRepository deviceRepository,
                          LogRepository logRepository, SensorCaptureService captureService) {
        this.userRepository = userRepository;
        this.deviceRepository = deviceRepository;
        this.logRepository = logRepository;
        this.captureService = captureService;
    }

    // produces: Spring'in yanıtı JSON tırnaklarına sarmasını engeller — ESP32 düz metin okur.
    @PostMapping(value = "/kart-okut", produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> kartOkut(@RequestParam String kartNo, @RequestParam Integer deviceId) {
        // Aktif web kayit oturumu varsa kart degerini yakala
        captureService.notifyCapture(CaptureType.CARD, kartNo.trim().replaceAll("\\s+", ""));
        return islemYap(kartNo, null, null, deviceId, "KART");
    }

    @PostMapping(value = "/numara-okut", produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> numaraOkut(@RequestParam String ogrenciNo, @RequestParam Integer deviceId) {
        // Aktif web kayit oturumu varsa okul no degerini yakala
        captureService.notifyCapture(CaptureType.SCHOOL_NO, ogrenciNo.trim());
        return islemYap(null, ogrenciNo, null, deviceId, "NUMARA");
    }

    @PostMapping(value = "/parmak-izi-okut", produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> parmakIziOkut(@RequestParam String parmakIzi, @RequestParam Integer deviceId) {
        // Aktif web kayit oturumu varsa FP slot degerini yakala
        captureService.notifyCapture(CaptureType.FINGERPRINT, parmakIzi.trim());
        return islemYap(null, null, parmakIzi, deviceId, "PARMAK_IZI");
    }

    private ResponseEntity<String> islemYap(String kartNo, String ogrenciNo, String parmakIzi, Integer deviceId, String yontem) {
        Log gecisLogu = new Log();
        gecisLogu.setGirisZamani(LocalDateTime.now());
        gecisLogu.setGirisYontemi(yontem);

        Optional<Device> deviceOpt = deviceRepository.findById(deviceId);
        Device device = deviceOpt.orElse(null);
        if (device == null || !Boolean.TRUE.equals(device.getAktifMi())) {
            gecisLogu.setSonuc("REDDEDILDI");
            gecisLogu.setAciklama("Cihaz bulunamadı veya pasif");
            gecisLogu.setYetkiliMi(false);
            logRepository.save(gecisLogu);
            return ResponseEntity.ok("REDDEDILDI");
        }

        gecisLogu.setDevice(device);

        Optional<User> userOpt = Optional.empty();
        if (kartNo != null) {
            userOpt = userRepository.findByKartNoIgnoreCase(kartNo.trim());
        } else if (ogrenciNo != null) {
            userOpt = userRepository.findByOgrenciNoIgnoreCase(ogrenciNo.trim());
        } else if (parmakIzi != null) {
            userOpt = userRepository.findByParmakIziSensorId(parmakIzi.trim());
        }

        if (userOpt.isPresent() && Boolean.TRUE.equals(userOpt.get().getAktifMi())) {
            User user = userOpt.get();
            gecisLogu.setUser(user);
            gecisLogu.setSonuc("ONAYLANDI");
            gecisLogu.setAciklama("Basarili giris");
            gecisLogu.setYetkiliMi(true);
            logRepository.save(gecisLogu);
            return ResponseEntity.ok("ONAYLANDI");
        } else {
            gecisLogu.setSonuc("REDDEDILDI");
            String aciklama;
            if (kartNo != null) {
                aciklama = "Kart reddedildi veya pasif: " + kartNo.trim();
            } else if (ogrenciNo != null) {
                aciklama = "Numara bulunamadi veya pasif: " + ogrenciNo.trim();
            } else if (parmakIzi != null) {
                aciklama = "Parmak izi slotu eslesmedi veya pasif: " + parmakIzi.trim();
            } else {
                aciklama = "Kullanici bulunamadi veya pasif";
            }
            gecisLogu.setAciklama(aciklama);
            gecisLogu.setYetkiliMi(false);
            logRepository.save(gecisLogu);
            return ResponseEntity.ok("REDDEDILDI");
        }
    }
}
