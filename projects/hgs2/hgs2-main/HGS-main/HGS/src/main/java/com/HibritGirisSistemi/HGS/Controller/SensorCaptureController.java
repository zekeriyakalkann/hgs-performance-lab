package com.HibritGirisSistemi.HGS.Controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.HibritGirisSistemi.HGS.Service.SensorCaptureService;
import com.HibritGirisSistemi.HGS.Service.SensorCaptureService.CaptureType;

import java.util.Map;

/**
 * Web arayüzü için canlı sensör tarama endpoint'leri.
 *
 * POST   /api/sensor/start?type=CARD|FINGERPRINT|SCHOOL_NO  → {"sessionId":"abc123"}
 * GET    /api/sensor/result?sessionId=abc123                → {"status":"WAITING"} veya {"status":"READY","value":"..."}
 * DELETE /api/sensor/session?sessionId=abc123               → 204 No Content
 */
@RestController
@RequestMapping("/api/sensor")
@CrossOrigin(origins = "*")
public class SensorCaptureController {

    private final SensorCaptureService captureService;

    public SensorCaptureController(SensorCaptureService captureService) {
        this.captureService = captureService;
    }

    /** Yeni bir tarama oturumu başlatır. */
    @PostMapping("/start")
    public ResponseEntity<Map<String, String>> startSession(
            @RequestParam String type,
            @RequestParam(required = false, defaultValue = "1") Integer deviceId) {
        CaptureType captureType;
        try {
            captureType = CaptureType.valueOf(type.toUpperCase());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", "Gecersiz tip: " + type));
        }
        String sessionId = captureService.startSession(captureType, deviceId);
        return ResponseEntity.ok(Map.of("sessionId", sessionId));
    }

    /** ESP32'nin sorguladığı bekleyen işlem endpoint'i */
    @GetMapping("/pending")
    public String getPending(@RequestParam Integer deviceId) {
        return captureService.getPendingAction(deviceId);
    }

    /** Tarama sonucunu sorgular (polling). */
    @GetMapping("/result")
    public ResponseEntity<Map<String, String>> pollResult(@RequestParam String sessionId) {
        String value = captureService.pollResult(sessionId);
        if (value == null) {
            return ResponseEntity.ok(Map.of("status", "WAITING"));
        }
        return ResponseEntity.ok(Map.of("status", "READY", "value", value));
    }

    /** Oturumu kapatır / temizler. */
    @DeleteMapping("/session")
    public ResponseEntity<Void> removeSession(@RequestParam String sessionId) {
        captureService.removeSession(sessionId);
        return ResponseEntity.noContent().build();
    }
}
