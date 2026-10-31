package com.HibritGirisSistemi.HGS.Controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.HibritGirisSistemi.HGS.Service.TerminalEnrollmentService;

@RestController
@RequestMapping("/api/terminal")
@CrossOrigin(origins = "*")
public class TerminalEnrollmentController {

    private final TerminalEnrollmentService terminalEnrollmentService;

    public TerminalEnrollmentController(TerminalEnrollmentService terminalEnrollmentService) {
        this.terminalEnrollmentService = terminalEnrollmentService;
    }

    @PostMapping(value = "/kart-kaydet", produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> kartKaydet(
            @RequestParam Integer deviceId,
            @RequestParam String ogrenciNo,
            @RequestParam String kartNo) {
        String sonuc = terminalEnrollmentService.kartKaydet(deviceId, ogrenciNo, kartNo);
        return ResponseEntity.ok(sonuc);
    }

    @PostMapping(value = "/parmak-kaydet", produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> parmakKaydet(
            @RequestParam Integer deviceId,
            @RequestParam String ogrenciNo,
            @RequestParam String slot) {
        String sonuc = terminalEnrollmentService.parmakKaydet(deviceId, ogrenciNo, slot);
        return ResponseEntity.ok(sonuc);
    }

    @PostMapping(value = "/ogrenci-no-degistir", produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> ogrenciNoDegistir(
            @RequestParam Integer deviceId,
            @RequestParam String eskiNo,
            @RequestParam String yeniNo) {
        String sonuc = terminalEnrollmentService.ogrenciNoDegistir(deviceId, eskiNo, yeniNo);
        return ResponseEntity.ok(sonuc);
    }

    @PostMapping(value = "/ogrenci-kaydet", produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> ogrenciKaydet(
            @RequestParam Integer deviceId,
            @RequestParam String ogrenciNo) {
        String sonuc = terminalEnrollmentService.ogrenciKaydet(deviceId, ogrenciNo);
        return ResponseEntity.ok(sonuc);
    }
}
