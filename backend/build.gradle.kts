import net.ltgt.gradle.errorprone.errorprone

plugins {
    java
    `java-test-fixtures`
    `jvm-test-suite`
    alias(libs.plugins.spring.boot)
    alias(libs.plugins.spotless)
    alias(libs.plugins.errorprone)
}

group = "com.aisquad.owlmast"
version = "0.1.0-SNAPSHOT"
description = "Owl Mast backend: one modular reactive Spring Boot deployable (AD-2, AD-5)"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(libs.versions.java.get())
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

dependencyLocking {
    lockAllConfigurations()
}

dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-r2dbc")
    implementation("org.springframework.boot:spring-boot-starter-flyway")
    implementation("org.flywaydb:flyway-database-postgresql")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
    runtimeOnly("org.postgresql:postgresql")

    compileOnly("org.projectlombok:lombok")
    annotationProcessor(platform(libs.spring.boot.bom))
    annotationProcessor("org.projectlombok:lombok")
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")

    errorprone(libs.errorprone.core)

    testFixturesImplementation(platform(libs.spring.boot.bom))
    testFixturesImplementation("org.springframework.boot:spring-boot-testcontainers")
    testFixturesImplementation("org.springframework.boot:spring-boot-starter-test")
    testFixturesImplementation("org.testcontainers:testcontainers-postgresql")
    testFixturesRuntimeOnly("org.testcontainers:testcontainers-r2dbc")
}

testing {
    suites {
        getByName<JvmTestSuite>("test") {
            useJUnitJupiter()
            dependencies {
                implementation(platform(libs.spring.boot.bom))
                implementation("org.springframework.boot:spring-boot-starter-test")
                implementation("io.projectreactor:reactor-test")
                implementation(libs.archunit.junit5)
                implementation(testFixtures(project()))
            }
        }
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter()
            dependencies {
                implementation(project())
                implementation(testFixtures(project()))
                implementation(platform(libs.spring.boot.bom))
                implementation("org.springframework.boot:spring-boot-starter-test")
                implementation("org.springframework.boot:spring-boot-starter-webflux-test")
                implementation("org.springframework.boot:spring-boot-starter-web-server-test")
                implementation("org.springframework.boot:spring-boot-starter-r2dbc-test")
                implementation("org.springframework.boot:spring-boot-starter-flyway-test")
                implementation("org.springframework.boot:spring-boot-testcontainers")
                implementation("org.testcontainers:testcontainers-postgresql")
                runtimeOnly("org.testcontainers:testcontainers-r2dbc")
                implementation("io.projectreactor:reactor-test")
            }
            targets.all {
                testTask.configure { shouldRunAfter(tasks.named("test")) }
            }
        }
    }
}

tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.compilerArgs.addAll(
        listOf(
            "-Xlint:all",
            "-Xlint:-processing",
            "-Xlint:-serial",
            "-Werror",
            "-parameters",
        )
    )
    options.errorprone {
        disableWarningsInGeneratedCode = true
        // Treat every enabled Error Prone finding as a build failure (warnings included via -Werror).
        allErrorsAsWarnings = false
        excludedPaths = ".*/build/generated/.*"
    }
}

tasks.withType<Test>().configureEach {
    // Netty loads native libraries; JDK 24+ warns (and will block) without explicit native access.
    jvmArgs("--enable-native-access=ALL-UNNAMED")
    if (providers.gradleProperty("reactorDebug").isPresent) {
        systemProperty("reactor.trace.operatorStacktrace", "true")
    }
    testLogging {
        events("failed", "skipped")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        showStandardStreams = false
    }
}

spotless {
    java {
        target("src/**/*.java")
        googleJavaFormat(libs.versions.google.java.format.get())
        formatAnnotations()
    }
    format("misc") {
        target("*.gradle.kts", "*.config", "src/**/*.sql", "src/**/*.yaml", "src/**/*.properties")
        trimTrailingWhitespace()
        endWithNewline()
    }
}

springBoot {
    buildInfo()
}
