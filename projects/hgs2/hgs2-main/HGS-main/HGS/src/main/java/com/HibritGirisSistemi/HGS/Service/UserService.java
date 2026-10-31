package com.HibritGirisSistemi.HGS.Service;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.HibritGirisSistemi.HGS.Entity.User;  
import com.HibritGirisSistemi.HGS.Repository.LogRepository;
import com.HibritGirisSistemi.HGS.Repository.UserRepository;  

@Service
public class UserService {

    private final UserRepository userRepository;
    private final LogRepository logRepository;

    public UserService(UserRepository userRepository, LogRepository logRepository) {
        this.userRepository = userRepository;
        this.logRepository = logRepository;
    }

    // HTML tarafındaki tabloyu doldurmak için tüm kullanıcıları getir
    public List<User> tumKullanicilariGetir() {
        return userRepository.findAll();
    }

    // HTML formundan gelen veriyi veritabanına kaydet
    public User kullaniciKaydet(User user) {
        if (user.getKartNo() != null && !user.getKartNo().trim().isEmpty()) {
            java.util.Optional<User> existing = userRepository.findByKartNoIgnoreCase(user.getKartNo().trim());
            if (existing.isPresent() && !existing.get().getUserId().equals(user.getUserId())) {
                throw new IllegalArgumentException("Bu kart numarası başka bir kullanıcıya aittir.");
            }
        }
        if (user.getOgrenciNo() != null && !user.getOgrenciNo().trim().isEmpty()) {
            java.util.Optional<User> existing = userRepository.findByOgrenciNoIgnoreCase(user.getOgrenciNo().trim());
            if (existing.isPresent() && !existing.get().getUserId().equals(user.getUserId())) {
                throw new IllegalArgumentException("Bu öğrenci numarası başka bir kullanıcıya aittir.");
            }
        }
        if (user.getParmakIziSensorId() != null && !user.getParmakIziSensorId().trim().isEmpty()) {
            java.util.Optional<User> existing = userRepository.findByParmakIziSensorId(user.getParmakIziSensorId().trim());
            if (existing.isPresent() && !existing.get().getUserId().equals(user.getUserId())) {
                throw new IllegalArgumentException("Bu parmak izi başka bir kullanıcıya aittir.");
            }
        }

        // Yeni bir kayıt geliyorsa varsayılan olarak aktif yap
        if (user.getAktifMi() == null) {
            user.setAktifMi(true);
        }
        return userRepository.save(user);
    }

    // Kullanıcı silme metodu — önce ilgili logları temizle (FK kısıtlaması)
    @Transactional
    public void kullaniciSil(Integer userId) {
        logRepository.deleteByUser_UserId(userId);
        userRepository.deleteById(userId);
    }
    // İlerleyen aşamalarda kullanıcı silme veya güncelleme metotları buraya eklenecek
}