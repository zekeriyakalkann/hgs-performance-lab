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

import com.HibritGirisSistemi.HGS.Entity.Device;
import com.HibritGirisSistemi.HGS.Service.DeviceService;

@RestController
@RequestMapping("/api/devices")
@CrossOrigin(origins = "*")
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @GetMapping
    public ResponseEntity<List<Device>> tumCihazlariGetir() {
        return ResponseEntity.ok(deviceService.tumCihazlariGetir());
    }

    @PostMapping
    public ResponseEntity<Device> cihazEkle(@RequestBody Device device) {
        return ResponseEntity.ok(deviceService.cihazKaydet(device));
    }

    @PutMapping("/{id}")
    public ResponseEntity<Device> cihazGuncelle(@PathVariable Integer id, @RequestBody Device guncelDevice) {
        guncelDevice.setDeviceId(id);
        return ResponseEntity.ok(deviceService.cihazKaydet(guncelDevice));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> cihazSil(@PathVariable Integer id) {
        deviceService.cihazSil(id);
        return ResponseEntity.ok().build();
    }
}