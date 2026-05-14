package com.HibritGirisSistemi.HGS.Service;

import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Service;

/**
 * Web arayüzünden tetiklenen "canlı sensör tarama" oturumlarını yönetir.
 * <p>
 * Akış:
 * 1. Web, POST /api/sensor/start    → sessionId döner, oturum açılır
 * 2. Arduino kart/FP okur → AuthController /api/auth/kart-okut'u çağırır
 *    → AuthController buraya notifyCapture() ile veriyi bırakır
 * 3. Web, GET  /api/sensor/result?sessionId=X  ile polling yapar
 *    → veri geldiyse döner, gelmemişse "WAITING" döner
 * 4. Web formu doldurduktan sonra DELETE /api/sensor/session?sessionId=X ile temizler
 */
@Service
public class SensorCaptureService {

    public enum CaptureType { CARD, FINGERPRINT, SCHOOL_NO }

    public static class CaptureSession {
        public final String     sessionId;
        public final CaptureType type;
        public final Integer    deviceId; // Hangi cihazdan tarama beklendiği
        public final Instant    createdAt;
        public final AtomicReference<String> capturedValue = new AtomicReference<>(null);

        public CaptureSession(String sessionId, CaptureType type, Integer deviceId) {
            this.sessionId = sessionId;
            this.type      = type;
            this.deviceId  = deviceId;
            this.createdAt = Instant.now();
        }
    }

    private final ConcurrentHashMap<String, CaptureSession> sessions = new ConcurrentHashMap<>();

    public String startSession(CaptureType type, Integer deviceId) {
        String id = java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        sessions.put(id, new CaptureSession(id, type, deviceId));
        purgeExpired();
        return id;
    }

    /** ESP32 için bekleyen tarama isteği var mı? */
    public String getPendingAction(Integer deviceId) {
        return sessions.values().stream()
            .filter(s -> s.deviceId.equals(deviceId) && s.capturedValue.get() == null)
            .findFirst()
            .map(s -> {
                if (s.type == CaptureType.FINGERPRINT) return "SCAN_FP";
                return "SCAN_" + s.type.name();
            })
            .orElse("NONE");
    }

    public void notifyCapture(CaptureType type, String rawValue) {
        sessions.values().stream()
            .filter(s -> s.type == type && s.capturedValue.get() == null)
            .findFirst()
            .ifPresent(s -> s.capturedValue.set(rawValue));
    }

    /** Sonucu sorgular. Null ise henüz gelmemiştir. */
    public String pollResult(String sessionId) {
        CaptureSession s = sessions.get(sessionId);
        if (s == null) return null;
        return s.capturedValue.get();
    }

    /** Oturumu temizler. */
    public void removeSession(String sessionId) {
        sessions.remove(sessionId);
    }

    private void purgeExpired() {
        Instant cutoff = Instant.now().minusSeconds(180);
        sessions.entrySet().removeIf(e -> e.getValue().createdAt.isBefore(cutoff));
    }
}
