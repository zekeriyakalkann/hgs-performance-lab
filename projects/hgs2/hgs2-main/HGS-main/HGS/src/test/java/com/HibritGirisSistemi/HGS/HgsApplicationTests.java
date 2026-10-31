package com.HibritGirisSistemi.HGS;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

// Varsayılan yapılandırma gerçek veritabanına (hibrit_giris_db, ddl-auto=update) bağlanır. perftest profili
// PerfTestSafetyGuard ile yalnızca izole test veritabanına izin verir; ortam değişkenleri yoksa test başlamadan başarısız olur.
@SpringBootTest
@ActiveProfiles("perftest")
class HgsApplicationTests {

	@Test
	void contextLoads() {
	}

}
