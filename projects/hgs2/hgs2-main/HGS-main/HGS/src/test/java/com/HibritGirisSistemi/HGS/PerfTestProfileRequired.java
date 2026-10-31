package com.HibritGirisSistemi.HGS;

import java.util.Arrays;
import java.util.List;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ContextConfigurationAttributes;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.ContextCustomizerFactory;
import org.springframework.test.context.MergedContextConfiguration;

import com.HibritGirisSistemi.HGS.Config.PerfTestSafetyGuard;

/**
 * Spring TestContext ile yüklenen her test bağlamında etkin profilin tam olarak "perftest" olmasını zorunlu kılar.
 *
 * Varsayılan yapılandırma gerçek veritabanına (hibrit_giris_db, ddl-auto=update) bağlanır ve PerfTestSafetyGuard
 * yalnızca perftest profili etkinken yüklenir. Bu sınıf profilden ve test sınıfının anotasyonlarından bağımsız
 * çalışır: @ActiveProfiles("perftest") unutulmuş bir test, bağlam yenilenmeden (DataSource oluşturulmadan) durur.
 *
 * Kayıt: src/test/resources/META-INF/spring.factories (yalnızca test classpath'i; uygulama başlangıcını etkilemez).
 */
public class PerfTestProfileRequired implements ContextCustomizerFactory {

    @Override
    public ContextCustomizer createContextCustomizer(Class<?> testClass,
            List<ContextConfigurationAttributes> configAttributes) {
        return new ProfileCheck();
    }

    /**
     * Durumsuz denetim. ContextCustomizer, bağlam önbelleğinin anahtarına (MergedContextConfiguration) girdiği için
     * equals/hashCode uygulamalıdır; tüm örnekler eşittir, bu yüzden önbelleklemeyi bölmez.
     */
    static final class ProfileCheck implements ContextCustomizer {

        @Override
        public void customizeContext(ConfigurableApplicationContext context, MergedContextConfiguration mergedConfig) {
            String[] active = context.getEnvironment().getActiveProfiles();
            if (!Arrays.equals(active, new String[] { PerfTestSafetyGuard.PROFILE })) {
                throw new IllegalStateException("Test bağlamı durduruldu: etkin profil yalnızca '"
                        + PerfTestSafetyGuard.PROFILE + "' olmalı (etkin: " + Arrays.toString(active) + ", test: "
                        + mergedConfig.getTestClass().getName() + "). Profilsiz testler gerçek veritabanına "
                        + "bağlanabilir; test sınıfına @ActiveProfiles(\"" + PerfTestSafetyGuard.PROFILE + "\") ekleyin.");
            }
        }

        @Override
        public boolean equals(Object other) {
            return other != null && other.getClass() == getClass();
        }

        @Override
        public int hashCode() {
            return getClass().hashCode();
        }
    }
}
