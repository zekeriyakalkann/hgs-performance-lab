package com.HibritGirisSistemi.HGS.Controller;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.HibritGirisSistemi.HGS.Entity.User;
import com.HibritGirisSistemi.HGS.Service.UserService;

@RestController
@RequestMapping("/api/users")
@CrossOrigin(origins = "*")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping
    public ResponseEntity<List<User>> tumKullanicilariGetir() {
        List<User> kullanicilar = userService.tumKullanicilariGetir();
        return ResponseEntity.ok(kullanicilar);
    }

    @PostMapping
    public ResponseEntity<User> kullaniciEkle(@RequestBody User user) {
        User kaydedilenUser = userService.kullaniciKaydet(user);
        return ResponseEntity.ok(kaydedilenUser);
    }
    
    @PutMapping("/{id}")
    public ResponseEntity<User> kullaniciGuncelle(@PathVariable Integer id, @RequestBody User guncelUser) {
        guncelUser.setUserId(id); // Güncellenecek kişinin ID'sini veriye ekle
        User kaydedilen = userService.kullaniciKaydet(guncelUser); // Aynı kaydet metodunu kullanıyoruz (ID'si olduğu için update yapar)
        return ResponseEntity.ok(kaydedilen);
    }

    // YENİ EKLENEN SİLME METODU BURADA OLMALI
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> kullaniciSil(@PathVariable Integer id) {
        userService.kullaniciSil(id);
        return ResponseEntity.ok().build();
    }
}