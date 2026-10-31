package com.HibritGirisSistemi.HGS.Repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.HibritGirisSistemi.HGS.Entity.User;

@Repository
public interface UserRepository extends JpaRepository<User, Integer> {
    // Spring Boot isimden yola çıkarak SQL sorgusunu kendi üretir:
    // SELECT * FROM users WHERE kart_no = ?
    Optional<User> findByKartNo(String kartNo);
    
    // SELECT * FROM users WHERE ogrenci_no = ?
    Optional<User> findByOgrenciNo(String ogrenciNo);

    Optional<User> findByKartNoIgnoreCase(String kartNo);

    Optional<User> findByOgrenciNoIgnoreCase(String ogrenciNo);

    Optional<User> findByParmakIziSensorId(String parmakIziSensorId);
}
