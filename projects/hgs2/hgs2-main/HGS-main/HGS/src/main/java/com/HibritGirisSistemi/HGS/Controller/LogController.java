package com.HibritGirisSistemi.HGS.Controller;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.HibritGirisSistemi.HGS.Entity.Log;
import com.HibritGirisSistemi.HGS.Service.LogService;

@RestController
@RequestMapping("/api/logs")
@CrossOrigin(origins = "*")
public class LogController {

    private final LogService logService;

    public LogController(LogService logService) {
        this.logService = logService;
    }

    // GET İsteği: http://localhost:8080/api/logs
    @GetMapping
    public ResponseEntity<List<Log>> tumLoglariGetir() { 
        return ResponseEntity.ok(logService.tumLoglariGetir());
    }
}