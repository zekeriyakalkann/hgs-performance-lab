package com.HibritGirisSistemi.HGS.Repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.HibritGirisSistemi.HGS.Entity.Log;

@Repository
public interface LogRepository extends JpaRepository<Log, Integer> {
    void deleteByUser_UserId(Integer userId);
}
