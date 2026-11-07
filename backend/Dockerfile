# Owl Mast backend runtime image (OM-01.02-T2). Build after `./gradlew :backend:bootJar`:
#   docker build -t owl-mast/backend:0.1.0 -f backend/Dockerfile backend   (JAR_FILE build-arg selects another jar)
# Base and JDK are pinned to the qualified toolchain (docs/toolchain-qualification.md):
# Eclipse Temurin 27.0.1+1 Linux x64, sha256 30cb129f…, on the ubuntu:26.04 digest below.
FROM ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c AS jdk
ARG TEMURIN_URL=https://github.com/adoptium/temurin27-binaries/releases/download/jdk-27.0.1.0.2%2B1/OpenJDK27U-jdk_x64_linux_hotspot_27.0.1.0.2_1.tar.gz
ARG TEMURIN_SHA256=30cb129f6cf299c852cec0feca9ea2a596d2ee9f26d8605d3a253951f6c8b20f
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL -o /tmp/temurin.tar.gz "$TEMURIN_URL" \
    && echo "$TEMURIN_SHA256  /tmp/temurin.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/java && tar -xzf /tmp/temurin.tar.gz -C /opt/java --strip-components=1 \
    && /opt/java/bin/java -version

FROM ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c
ENV JAVA_HOME=/opt/java PATH=/opt/java/bin:$PATH LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 owlmast && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin owlmast
COPY --from=jdk /opt/java /opt/java
ARG JAR_FILE=build/libs/backend-0.1.0-SNAPSHOT.jar
COPY ${JAR_FILE} /app/owl-mast.jar
USER 10001:10001
WORKDIR /app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/owl-mast.jar"]
