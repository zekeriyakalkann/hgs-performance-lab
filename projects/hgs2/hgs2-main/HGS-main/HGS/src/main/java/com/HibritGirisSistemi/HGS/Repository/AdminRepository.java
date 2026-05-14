package com.HibritGirisSistemi.HGS.Repository;

import com.HibritGirisSistemi.HGS.Entity.Admin;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface AdminRepository extends JpaRepository<Admin, Integer> {
    Optional<Admin> findByKullaniciAdi(String kullaniciAdi);
}