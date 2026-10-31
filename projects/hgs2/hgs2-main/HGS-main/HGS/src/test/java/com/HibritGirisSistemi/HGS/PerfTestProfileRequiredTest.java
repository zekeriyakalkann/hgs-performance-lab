package com.HibritGirisSistemi.HGS;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.ContextCustomizerFactory;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.util.TestContextSpringFactoriesUtils;

/**
 * PerfTestProfileRequired'ın çalışma anı doğrulaması.
 *
 * Spring Boot bağlamı, PerfTestSafetyGuard veya veritabanı kullanmaz: örnek sınıflar yalnızca boş bir @Configuration
 * ile düz Spring TestContext bağlamı ister. Bu sınıfın kendisinde Spring anotasyonu yoktur; bağlam testlerin içinde
 * TestContextManager ile istenir.
 */
class PerfTestProfileRequiredTest {

    // Bağlam yenilendiğinde (refresh -> invokeBeanFactoryPostProcessors) artar.
    static final AtomicInteger REFRESH_COUNT = new AtomicInteger();

    @Test
    void factorySpringFactoriesUzerindenKesfedilir() {
        // Spring Test'in varsayılan factory'leri yüklediği yol. Yüklenemeyen kayıt yalnızca debug günlüğüyle atlandığı
        // için factory'nin listede olduğu açıkça doğrulanır.
        List<ContextCustomizerFactory> factories =
                TestContextSpringFactoriesUtils.loadFactoryImplementations(ContextCustomizerFactory.class);
        assertTrue(factories.stream().anyMatch(PerfTestProfileRequired.class::isInstance),
                "PerfTestProfileRequired META-INF/spring.factories üzerinden yüklenmedi");
    }

    @Test
    void profilsizBaglamYenilenmedenDurur() {
        assertStoppedBeforeRefresh(ProfilsizOrnek.class);
    }

    @Test
    void yanlisProfilliBaglamYenilenmedenDurur() {
        assertStoppedBeforeRefresh(YanlisProfilOrnek.class);
    }

    @Test
    void perftestProfiliyleBaglamVeriKaynagiOlmadanYuklenir() {
        ApplicationContext context = new TestContextManager(PerftestOrnek.class).getTestContext().getApplicationContext();
        assertArrayEquals(new String[] { "perftest" }, context.getEnvironment().getActiveProfiles());
        assertEquals(0, context.getBeanNamesForType(DataSource.class).length);
    }

    private static void assertStoppedBeforeRefresh(Class<?> exampleClass) {
        int before = REFRESH_COUNT.get();
        TestContextManager manager = new TestContextManager(exampleClass);
        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> manager.getTestContext().getApplicationContext());
        assertTrue(causedByProfileCheck(failure), "Hata PerfTestProfileRequired denetiminden gelmedi: " + failure);
        assertEquals(before, REFRESH_COUNT.get(), "Bağlam, profil denetiminden önce yenilendi");
    }

    private static boolean causedByProfileCheck(Throwable failure) {
        for (Throwable t = failure; t != null; t = t.getCause()) {
            if (t instanceof IllegalStateException && t.getMessage() != null
                    && t.getMessage().startsWith("Test bağlamı durduruldu")) {
                return true;
            }
        }
        return false;
    }

    @Configuration(proxyBeanMethods = false)
    static class BosYapilandirma {

        @Bean
        static BeanFactoryPostProcessor yenilemeIsareti() {
            return beanFactory -> REFRESH_COUNT.incrementAndGet();
        }
    }

    @ContextConfiguration(classes = BosYapilandirma.class)
    static class ProfilsizOrnek {
    }

    @ActiveProfiles("perfest")
    @ContextConfiguration(classes = BosYapilandirma.class)
    static class YanlisProfilOrnek {
    }

    @ActiveProfiles("perftest")
    @ContextConfiguration(classes = BosYapilandirma.class)
    static class PerftestOrnek {
    }
}
