package com.HibritGirisSistemi.HGS.Service;

import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.HibritGirisSistemi.HGS.Entity.Log;
import com.HibritGirisSistemi.HGS.Repository.LogRepository;


@Service
public class LogService {

    private final LogRepository logRepository;

    public LogService(LogRepository logRepository) {
        this.logRepository = logRepository;
    }

    @Transactional(readOnly = true)
    public List<Log> tumLoglariGetir() {
        return logRepository.findAll(Sort.by(Sort.Direction.DESC, "logId"));
    }
}
