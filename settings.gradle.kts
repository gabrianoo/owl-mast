// Owl Mast build root. Backend lives in `backend`; the independently built web client (OM-01.04)
// will be added as a separate artifact, never bundled into the backend image (AD-14).
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

plugins {
    // Auto-provisions the pinned JDK toolchain (and the daemon JVM declared in
    // gradle/gradle-daemon-jvm.properties) from the Foojay Disco API when it is not installed.
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "owl-mast"

// The daemon JVM criteria (gradle/gradle-daemon-jvm.properties) only constrain major version and
// vendor, so an installed Temurin 27 of another patch would satisfy them. Enforce the qualified
// full version here; the backend build enforces the compiler and test launcher the same way.
run {
    val qualifiedRuntime = providers.gradleProperty("owlmast.qualified.jdk.runtime").get()
    val qualifiedVendor = providers.gradleProperty("owlmast.qualified.jdk.vendor").get()
    val actualRuntime = System.getProperty("java.runtime.version")
    val actualVendor = System.getProperty("java.vendor")
    if (actualRuntime != qualifiedRuntime || actualVendor != qualifiedVendor) {
        throw GradleException(
            "Gradle daemon JVM '$actualVendor $actualRuntime' is not the qualified JDK" +
                " '$qualifiedVendor $qualifiedRuntime' (docs/toolchain-qualification.md)." +
                " Install Eclipse Temurin $qualifiedRuntime, or run with" +
                " -Porg.gradle.java.installations.auto-detect=false so Gradle provisions the pinned" +
                " archive from gradle/gradle-daemon-jvm.properties instead of reusing another" +
                " installation."
        )
    }
}

include("backend")
