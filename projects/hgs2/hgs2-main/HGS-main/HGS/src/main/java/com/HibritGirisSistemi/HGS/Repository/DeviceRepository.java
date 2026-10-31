package com.HibritGirisSistemi.HGS.Repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.HibritGirisSistemi.HGS.Entity.Device;

@Repository
public interface DeviceRepository extends JpaRepository<Device, Integer> {
}