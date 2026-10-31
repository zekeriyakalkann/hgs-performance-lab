package com.HibritGirisSistemi.HGS.Config;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.EnvironmentAware;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.PriorityOrdered;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * "perftest" profili için başlangıç güvenlik denetimi (HGS Performance Lab ile izole performans testi).
 *
 * BeanFactoryPostProcessor olarak çalışır: DataSource ve EntityManagerFactory oluşturulmadan, dolayısıyla
 * veritabanı bağlantısı açılmadan, ddl-auto uygulanmadan ve HTTP portu açılmadan önce. Etkin (çözümlenmiş)
 * ayarları denetler; herhangi bir koşul sağlanmazsa istisna fırlatır ve uygulama başlamaz.
 *
 * Denetim, ayarların hangi dosyadan geldiğine dair bir varsayıma dayanmaz: perftest dosyası yüklenmemiş ya da
 * bir değeri geçersiz kılınmamışsa application.properties değerleri (8080, 0.0.0.0, gerçek veritabanı, update)
 * etkin kalır ve denetim başarısız olur.
 *
 * Hibernate'in Spring dışındaki ayar kaynakları da denetlenir: Hibernate 7.2 JPA önyüklemesi (MergedSettings) ayarlara
 * org.hibernate.cfg.Environment.getProperties() ile, yani classpath'teki /hibernate.properties ve JVM sistem
 * özellikleriyle başlar; Spring Boot ise ddl-auto=none için hibernate.hbm2ddl.auto anahtarını kaldırır. Bu yüzden
 * hibernate.*, jakarta.persistence.* ve javax.persistence.* sistem özellikleri ile classpath'teki hibernate.properties
 * ve hibernate.cfg.xml reddedilir. Denetim bu sınıfın çalıştığı anı görür; Hibernate'in kendi kopyasını aldığı anı değil.
 *
 * Son adımda test kullanıcısıyla gerçek veritabanına bağlanma denenir; bağlantı PostgreSQL tarafından yetki
 * hatasıyla (SQLState 42501, CONNECT yetkisi yok) reddedilmezse uygulama başlamaz.
 *
 * Profil etkin değilse bu sınıf hiç oluşturulmaz; gerçek sistemin davranışı değişmez.
 */
@Component
@Profile(PerfTestSafetyGuard.PROFILE)
public class PerfTestSafetyGuard implements BeanFactoryPostProcessor, EnvironmentAware, PriorityOrdered {

    public static final String PROFILE = "perftest";
    static final String TEST_DB_NAME = "hgs2_perftest_db";
    static final String PROD_DB_NAME = "hibrit_giris_db";
    static final String REQUIRED_ADDRESS = "127.0.0.1";
    static final String REQUIRED_PORT = "18080";
    static final String ENV_USERNAME = "HGS_PERFTEST_DB_USERNAME";
    static final String ENV_PASSWORD = "HGS_PERFTEST_DB_PASSWORD";

    private static final Logger log = LoggerFactory.getLogger(PerfTestSafetyGuard.class);

    // Yalnızca loopback ana makine, isteğe bağlı port ve yalnızca test veritabanı adı; sorgu parametresi ve çoklu ana makine yok.
    private static final Pattern TEST_DB_URL = Pattern.compile(
            "^jdbc:postgresql://(127\\.0\\.0\\.1|localhost|\\[::1\\])(:\\d{1,5})?/" + TEST_DB_NAME + "$");
    private static final Set<String> ALLOWED_DDL_AUTO = Set.of("none", "validate");
    private static final Set<String> ALLOWED_JPA_PROPERTIES = Set.of("hibernate.dialect");
    // Hibernate'in sistem özelliklerinden okuduğu ayar ad alanları (şema yönetimi, bağlantı, cfg.xml dahil).
    private static final List<String> HIBERNATE_SYSTEM_PROPERTY_PREFIXES =
            List.of("hibernate.", "jakarta.persistence.", "javax.persistence.");
    private static final List<String> HIBERNATE_CONFIG_RESOURCES = List.of("hibernate.properties", "hibernate.cfg.xml");
    private static final String SQLSTATE_INSUFFICIENT_PRIVILEGE = "42501";
    private static final String PROBE_TIMEOUT_SECONDS = "5";

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void postProcessBeanFactory(ConfigurableListableBeanFactory beanFactory) {
        requireOnlyPerftestProfile();
        requireLoopbackServer();
        requireSchemaUntouched();
        requireNoHibernateGlobalSettings();
        requireNoConnectionOverrides();
        Matcher url = requireTestDatabaseUrl();
        String username = requireCredentialsFromEnvironment();
        requireNoProductionAccess(url.group(1), url.group(2), username, System.getenv(ENV_PASSWORD));
        log.info("perftest güvenlik denetimi geçti: {}:{}, veritabanı {}, ddl-auto {}",
                REQUIRED_ADDRESS, REQUIRED_PORT, TEST_DB_NAME, property("spring.jpa.hibernate.ddl-auto"));
    }

    private void requireOnlyPerftestProfile() {
        String[] active = environment.getActiveProfiles();
        if (!Arrays.equals(active, new String[] { PROFILE })) {
            throw fail("etkin profil yalnızca '" + PROFILE + "' olmalı (etkin: " + Arrays.toString(active) + ")");
        }
    }

    private void requireLoopbackServer() {
        String address = property("server.address");
        if (!REQUIRED_ADDRESS.equals(address)) {
            throw fail("server.address " + REQUIRED_ADDRESS + " olmalı (etkin: " + address + ")");
        }
        String port = property("server.port");
        if (!REQUIRED_PORT.equals(port)) {
            throw fail("server.port " + REQUIRED_PORT + " olmalı; 8080'e veya başka porta düşülmez (etkin: " + port + ")");
        }
        if (property("management.server.port") != null || property("management.server.address") != null) {
            throw fail("management.server.* ayarlanamaz; actuator aynı " + REQUIRED_ADDRESS + ":" + REQUIRED_PORT
                    + " sunucusunda kalmalı");
        }
    }

    private void requireSchemaUntouched() {
        String ddlAuto = property("spring.jpa.hibernate.ddl-auto");
        if (ddlAuto == null || !ALLOWED_DDL_AUTO.contains(ddlAuto.trim().toLowerCase(Locale.ROOT))) {
            throw fail("spring.jpa.hibernate.ddl-auto yalnızca " + ALLOWED_DDL_AUTO + " olabilir (etkin: " + ddlAuto + ")");
        }
        if ("true".equalsIgnoreCase(property("spring.jpa.generate-ddl"))) {
            throw fail("spring.jpa.generate-ddl=true kullanılamaz");
        }
        if (!"never".equalsIgnoreCase(property("spring.sql.init.mode"))) {
            throw fail("spring.sql.init.mode never olmalı");
        }
        // Spring üzerinden Hibernate'e geçen hibernate.hbm2ddl.auto, jakarta.persistence.schema-generation.* veya
        // hibernate.connection.* gibi ayarlar burada reddedilir. Spring dışı kaynaklar: requireNoHibernateGlobalSettings.
        for (String key : bindMap("spring.jpa.properties").keySet()) {
            if (!ALLOWED_JPA_PROPERTIES.contains(key)) {
                throw fail("spring.jpa.properties." + key + " izinli değil");
            }
        }
    }

    /**
     * Hibernate'in Spring'i atlayarak okuduğu ayar kaynaklarını reddeder (bkz. sınıf açıklaması). Hata mesajında
     * yalnızca anahtar veya dosya adı yer alır; değer yazdırılmaz.
     */
    private void requireNoHibernateGlobalSettings() {
        for (Object key : new ArrayList<>(System.getProperties().keySet())) {
            String name = String.valueOf(key);
            String lower = name.toLowerCase(Locale.ROOT);
            for (String prefix : HIBERNATE_SYSTEM_PROPERTY_PREFIXES) {
                if (lower.startsWith(prefix)) {
                    throw fail("JVM sistem özelliği " + name + " kullanılamaz; Hibernate/JPA ayarları Spring denetimini "
                            + "atlayabilir");
                }
            }
        }
        // Hibernate /hibernate.properties dosyasını önce iş parçacığı bağlam sınıf yükleyicisinden, sonra kendi sınıf
        // yükleyicisinden okur; ikisi de denetlenir (uygulama sınıflarıyla aynı yükleyici olduğu varsayılır).
        for (ClassLoader loader : Arrays.asList(Thread.currentThread().getContextClassLoader(),
                PerfTestSafetyGuard.class.getClassLoader())) {
            if (loader == null) {
                continue;
            }
            for (String resource : HIBERNATE_CONFIG_RESOURCES) {
                if (loader.getResource(resource) != null) {
                    throw fail("classpath'te " + resource + " bulundu; perftest profilinde Hibernate ayarları yalnızca "
                            + "Spring yapılandırmasından gelmeli");
                }
            }
        }
    }

    private void requireNoConnectionOverrides() {
        for (String prefix : List.of("spring.datasource.hikari", "spring.datasource.xa")) {
            if (!bindMap(prefix).isEmpty()) {
                throw fail(prefix + ".* ayarlanamaz (bağlantı adresini veya kullanıcıyı değiştirebilir)");
            }
        }
        for (String key : List.of("spring.datasource.jndi-name", "spring.datasource.type")) {
            if (property(key) != null) {
                throw fail(key + " ayarlanamaz");
            }
        }
        String driver = property("spring.datasource.driver-class-name");
        if (driver != null && !"org.postgresql.Driver".equals(driver)) {
            throw fail("spring.datasource.driver-class-name yalnızca org.postgresql.Driver olabilir");
        }
    }

    private Matcher requireTestDatabaseUrl() {
        String url = property("spring.datasource.url");
        Matcher matcher = url == null ? null : TEST_DB_URL.matcher(url);
        if (matcher == null || !matcher.matches()) {
            // Adres yazdırılmaz: hatalı bir değer kimlik bilgisi içerebilir.
            throw fail("spring.datasource.url yalnızca jdbc:postgresql://<127.0.0.1|localhost|[::1]>[:port]/"
                    + TEST_DB_NAME + " olabilir");
        }
        return matcher;
    }

    private String requireCredentialsFromEnvironment() {
        String username = System.getenv(ENV_USERNAME);
        String password = System.getenv(ENV_PASSWORD);
        if (isBlank(username) || isBlank(password)) {
            throw fail(ENV_USERNAME + " ve " + ENV_PASSWORD + " ortam değişkenleri tanımlı ve boş olmamalı");
        }
        if (!username.equals(property("spring.datasource.username"))
                || !password.equals(property("spring.datasource.password"))) {
            throw fail("spring.datasource.username/password yalnızca " + ENV_USERNAME + " / " + ENV_PASSWORD
                    + " ortam değişkenlerinden gelmeli");
        }
        if ("postgres".equalsIgnoreCase(username)) {
            throw fail("varsayılan süper kullanıcı 'postgres' kullanılamaz; ayrı test kullanıcısı gerekli");
        }
        return username;
    }

    /**
     * Test kullanıcısıyla gerçek veritabanına bağlanmayı dener. Yalnızca PostgreSQL'in CONNECT yetkisi
     * olmadığı için reddetmesi (SQLState 42501) kabul edilir; bağlantı kurulursa hemen kapatılır, hiçbir sorgu
     * çalıştırılmaz ve uygulama başlamaz. Başka her hata (sunucu yok, kimlik doğrulama, zaman aşımı) da başlatmayı durdurur.
     */
    private void requireNoProductionAccess(String host, String port, String username, String password) {
        String probeUrl = "jdbc:postgresql://" + host + (port == null ? "" : port) + "/" + PROD_DB_NAME;
        Properties props = new Properties();
        props.setProperty("user", username);
        props.setProperty("password", password);
        props.setProperty("connectTimeout", PROBE_TIMEOUT_SECONDS);
        props.setProperty("loginTimeout", PROBE_TIMEOUT_SECONDS);
        props.setProperty("socketTimeout", PROBE_TIMEOUT_SECONDS);
        props.setProperty("ApplicationName", "hgs2-perftest-isolation-probe");
        try (Connection ignored = DriverManager.getConnection(probeUrl, props)) {
            // Bağlantı kuruldu: izolasyon yok. Aşağıda başlatma durdurulur.
        } catch (SQLException e) {
            if (SQLSTATE_INSUFFICIENT_PRIVILEGE.equals(e.getSQLState())) {
                return;
            }
            throw fail("gerçek veritabanına erişimin olmadığı doğrulanamadı (SQLState " + e.getSQLState()
                    + "); beklenen: " + SQLSTATE_INSUFFICIENT_PRIVILEGE + " (CONNECT yetkisi yok)");
        }
        throw fail("test kullanıcısı " + PROD_DB_NAME + " veritabanına bağlanabildi; CONNECT yetkisi veritabanı "
                + "düzeyinde kaldırılmalı");
    }

    private Map<String, String> bindMap(String prefix) {
        return Binder.get(environment).bind(prefix, Bindable.mapOf(String.class, String.class)).orElse(Map.of());
    }

    private String property(String key) {
        try {
            return environment.getProperty(key);
        } catch (IllegalArgumentException e) {
            // Çözümlenemeyen ${...} yer tutucusu
            throw fail(key + " çözümlenemedi");
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static IllegalStateException fail(String reason) {
        return new IllegalStateException("perftest güvenlik denetimi başarısız, uygulama başlatılmadı: " + reason);
    }
}
