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

include("backend")
