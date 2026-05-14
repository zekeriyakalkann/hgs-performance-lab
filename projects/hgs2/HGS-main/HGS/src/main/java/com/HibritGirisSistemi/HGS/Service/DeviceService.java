package com.HibritGirisSistemi.HGS.Service;

import java.util.List;

import org.springframework.stereotype.Service;

import com.HibritGirisSistemi.HGS.Entity.Device;
import com.HibritGirisSistemi.HGS.Repository.DeviceRepository;

@Service
public class DeviceService {

    private final DeviceRepository deviceRepository;

    public DeviceService(DeviceRepository deviceRepository) {
        this.deviceRepository = deviceRepository;
    }

    public List<Device> tumCihazlariGetir() {
        return deviceRepository.findAll();
    }

    public Device cihazKaydet(Device device) {
        if (device.getAktifMi() == null) {
            device.setAktifMi(true);
        }
        return deviceRepository.save(device);
    }

    public void cihazSil(Integer deviceId) {
        deviceRepository.deleteById(deviceId);
    }
}