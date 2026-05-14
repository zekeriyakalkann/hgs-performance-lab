package com.HibritGirisSistemi.HGS.Service;

import java.util.List;

import org.springframework.stereotype.Service;

import com.HibritGirisSistemi.HGS.Entity.User;  
import com.HibritGirisSistemi.HGS.Repository.UserRepository;  

@Service
public class UserService {

    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    // HTML tarafındaki tabloyu doldurmak için tüm kullanıcıları getir
    public List<User> tumKullanicilariGetir() {
        return userRepository.findAll();
    }

    // HTML formundan gelen veriyi veritabanına kaydet
    public User kullaniciKaydet(User user) {
        // Yeni bir kayıt geliyorsa varsayılan olarak aktif yap
        if (user.getAktifMi() == null) {
            user.setAktifMi(true);
        }
        return userRepository.save(user);
    }

    // Kullanıcı silme metodu
    public void kullaniciSil(Integer userId) {
        userRepository.deleteById(userId);
    }
    // İlerleyen aşamalarda kullanıcı silme veya güncelleme metotları buraya eklenecek
}