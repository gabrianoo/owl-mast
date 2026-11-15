package com.aisquad.owlmast.testing;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;

/**
 * The pinned Keycloak with a synthetic realm, for the sign-in tests and the local run (OM-02.01).
 * Everything in it is made up for the run: the realm, its users, their passwords and the client
 * secret are generated at start and exist only in this container and this JVM.
 *
 * <p>The realm mirrors what the installation chart imports: self-registration off, one confidential
 * client using the authorization code grant with PKCE, no direct grants on it. The other clients
 * and the second realm exist only to produce credentials the backend must refuse or, for {@link
 * #BEARER_CLIENT}, to prove the accepted case: the chart's realm has no client that issues a token
 * with the backend's audience.
 */
public final class SyntheticKeycloak implements AutoCloseable {

  public static final String REALM = "owl-mast";
  public static final String OTHER_REALM = "synthetic-other";
  public static final String CLIENT_ID = "owl-mast-web";

  /** Issues access tokens whose audience is the backend's client: the accepted bearer case. */
  public static final String BEARER_CLIENT = "synthetic-bearer";

  /** Issues access tokens of the same realm for another audience. */
  public static final String OTHER_AUDIENCE_CLIENT = "synthetic-other-audience";

  public static final String ADA = "ada.synthetic";
  public static final String GRACE = "grace.synthetic";

  /** Environment variable through which a caller may choose the synthetic users' password. */
  public static final String PASSWORD_VARIABLE = "OWLMAST_FIXTURE_USER_PASSWORD";

  private static final String CALLBACK_PATH = "/api/session/callback";
  private static final ParameterizedTypeReference<Map<String, Object>> OBJECT =
      new ParameterizedTypeReference<>() {};
  private static final ParameterizedTypeReference<List<Map<String, Object>>> LIST =
      new ParameterizedTypeReference<>() {};
  private static final Duration CALL = Duration.ofSeconds(30);

  private final GenericContainer<?> container;
  private final String adminPassword = UUID.randomUUID().toString();
  private final String clientSecret = UUID.randomUUID().toString();
  private final String userPassword;
  private final WebClient http = WebClient.create();

  private SyntheticKeycloak(String userPassword) {
    this.userPassword = userPassword;
    this.container =
        new GenericContainer<>(OwlMastImages.KEYCLOAK)
            .withCommand("start-dev")
            .withEnv("KC_BOOTSTRAP_ADMIN_USERNAME", "synthetic-admin")
            .withEnv("KC_BOOTSTRAP_ADMIN_PASSWORD", adminPassword)
            .withEnv("KC_HTTP_ENABLED", "true")
            // The issuer is whatever address the request used: the browser of a test and the
            // backend both reach this container on the same mapped loopback port.
            .withEnv("KC_HOSTNAME_STRICT", "false")
            .withExposedPorts(8080)
            // Lets Keycloak post its logout notice to a backend listening on the test host.
            .withAccessToHost(true)
            .waitingFor(
                Wait.forHttp("/realms/master")
                    .forPort(8080)
                    .withStartupTimeout(Duration.ofMinutes(4)));
  }

  /**
   * Starts Keycloak and creates the realms.
   *
   * @param applicationOrigin the origin the backend redirects the browser back to
   * @param accessTokenLifespan how long an access token lives; the backend renews a session's token
   *     within a minute of its expiry, so a value of a minute or less makes every request ask
   *     Keycloak whether the session still stands
   */
  public static SyntheticKeycloak start(String applicationOrigin, Duration accessTokenLifespan) {
    ContainerRuntime.requireAvailable();
    String chosen = System.getenv(PASSWORD_VARIABLE);
    SyntheticKeycloak keycloak =
        new SyntheticKeycloak(
            chosen == null || chosen.isBlank() ? UUID.randomUUID().toString() : chosen);
    keycloak.container.start();
    keycloak.createRealms(applicationOrigin, accessTokenLifespan);
    return keycloak;
  }

  public String baseUrl() {
    return "http://localhost:" + container.getMappedPort(8080);
  }

  public String issuerUri() {
    return baseUrl() + "/realms/" + REALM;
  }

  public String clientSecret() {
    return clientSecret;
  }

  /** The password of every synthetic user of this run. */
  public String userPassword() {
    return userPassword;
  }

  /** An access token for {@code username}, obtained with the direct grant of a test-only client. */
  public String accessToken(String realm, String client, String username) {
    Map<String, Object> answer =
        http.post()
            .uri(baseUrl() + "/realms/" + realm + "/protocol/openid-connect/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(
                BodyInserters.fromFormData("grant_type", "password")
                    .with("client_id", client)
                    .with("username", username)
                    .with("password", userPassword)
                    .with("scope", "openid"))
            .retrieve()
            .bodyToMono(OBJECT)
            .block(CALL);
    return (String) required(answer).get("access_token");
  }

  /** The subject Keycloak gave the user: what the backend binds, together with the issuer. */
  public String subjectOf(String username) {
    return (String) user(REALM, username).get("id");
  }

  /** Changes what the person is called; the subject stays the same. */
  public void rename(String username, String firstName, String lastName) {
    admin()
        .put()
        .uri("/admin/realms/{realm}/users/{id}", REALM, subjectOf(username))
        .bodyValue(Map.of("firstName", firstName, "lastName", lastName))
        .retrieve()
        .toBodilessEntity()
        .block(CALL);
  }

  /** How many Keycloak sessions the user has. */
  public int sessionsOf(String username) {
    List<Map<String, Object>> sessions =
        admin()
            .get()
            .uri("/admin/realms/{realm}/users/{id}/sessions", REALM, subjectOf(username))
            .retrieve()
            .bodyToMono(LIST)
            .block(CALL);
    return sessions == null ? 0 : sessions.size();
  }

  /**
   * An administrator ends every session of the user. Keycloak sends its logout notice to the client
   * when {@link #announceLogoutsTo} named an address, and otherwise tells nobody.
   */
  public void endSessionsOf(String username) {
    admin()
        .post()
        .uri("/admin/realms/{realm}/users/{id}/logout", REALM, subjectOf(username))
        .retrieve()
        .toBodilessEntity()
        .block(CALL);
  }

  /**
   * Sets (or, with empty, removes) the address Keycloak posts its logout notices to. A backend on
   * the test host is reached as {@code http://host.testcontainers.internal:<port>} once the port
   * was exposed with {@code Testcontainers.exposeHostPorts}.
   */
  public void announceLogoutsTo(Optional<String> backchannelLogoutUrl) {
    Map<String, Object> client =
        required(
                admin()
                    .get()
                    .uri("/admin/realms/{realm}/clients?clientId={id}", REALM, CLIENT_ID)
                    .retrieve()
                    .bodyToMono(LIST)
                    .block(CALL))
            .getFirst();
    admin()
        .put()
        .uri("/admin/realms/{realm}/clients/{id}", REALM, client.get("id"))
        .bodyValue(
            Map.of(
                "clientId",
                CLIENT_ID,
                "attributes",
                Map.of(
                    "backchannel.logout.url",
                    backchannelLogoutUrl.orElse(""),
                    "backchannel.logout.session.required",
                    "true",
                    "pkce.code.challenge.method",
                    "S256")))
        .retrieve()
        .toBodilessEntity()
        .block(CALL);
  }

  @Override
  public void close() {
    container.stop();
  }

  private void createRealms(String applicationOrigin, Duration accessTokenLifespan) {
    Map<String, Object> browserClient =
        Map.ofEntries(
            Map.entry("clientId", CLIENT_ID),
            Map.entry("protocol", "openid-connect"),
            Map.entry("publicClient", false),
            Map.entry("secret", clientSecret),
            Map.entry("standardFlowEnabled", true),
            Map.entry("implicitFlowEnabled", false),
            Map.entry("directAccessGrantsEnabled", false),
            Map.entry("serviceAccountsEnabled", false),
            Map.entry("fullScopeAllowed", false),
            Map.entry("redirectUris", List.of(applicationOrigin + CALLBACK_PATH)),
            Map.entry("webOrigins", List.of()),
            Map.entry(
                "attributes",
                Map.of(
                    "pkce.code.challenge.method", "S256",
                    "backchannel.logout.session.required", "true")));
    createRealm(
        Map.ofEntries(
            Map.entry("realm", REALM),
            Map.entry("enabled", true),
            Map.entry("registrationAllowed", false),
            Map.entry("resetPasswordAllowed", false),
            Map.entry("editUsernameAllowed", false),
            Map.entry("bruteForceProtected", true),
            Map.entry("sslRequired", "external"),
            Map.entry("accessTokenLifespan", (int) accessTokenLifespan.toSeconds()),
            Map.entry(
                "clients",
                List.of(
                    browserClient,
                    directGrantClient(BEARER_CLIENT, Optional.of(CLIENT_ID)),
                    directGrantClient(OTHER_AUDIENCE_CLIENT, Optional.empty()))),
            Map.entry(
                "users",
                List.of(person(ADA, "Ada", "Synthetic"), person(GRACE, "Grace", "Synthetic")))));
    createRealm(
        Map.of(
            "realm",
            OTHER_REALM,
            "enabled",
            true,
            "registrationAllowed",
            false,
            "clients",
            List.of(directGrantClient(BEARER_CLIENT, Optional.of(CLIENT_ID))),
            "users",
            List.of(person(ADA, "Ada", "Elsewhere"))));
  }

  private void createRealm(Map<String, Object> realm) {
    admin().post().uri("/admin/realms").bodyValue(realm).retrieve().toBodilessEntity().block(CALL);
  }

  private Map<String, Object> person(String username, String firstName, String lastName) {
    return Map.of(
        "username",
        username,
        "enabled",
        true,
        "emailVerified",
        true,
        "email",
        username + "@synthetic.invalid",
        "firstName",
        firstName,
        "lastName",
        lastName,
        "credentials",
        List.of(Map.of("type", "password", "value", userPassword, "temporary", false)));
  }

  private static Map<String, Object> directGrantClient(String clientId, Optional<String> audience) {
    return Map.of(
        "clientId",
        clientId,
        "protocol",
        "openid-connect",
        "publicClient",
        true,
        "standardFlowEnabled",
        false,
        "directAccessGrantsEnabled",
        true,
        "protocolMappers",
        audience
            .map(value ->
                List.of(
                    Map.of(
                        "name", "synthetic-audience",
                        "protocol", "openid-connect",
                        "protocolMapper", "oidc-audience-mapper",
                        "config",
                            Map.of(
                                "included.custom.audience", value,
                                "access.token.claim", "true",
                                "id.token.claim", "false"))))
            .orElseGet(List::of));
  }

  private Map<String, Object> user(String realm, String username) {
    return required(
            admin()
                .get()
                .uri("/admin/realms/{realm}/users?username={name}&exact=true", realm, username)
                .retrieve()
                .bodyToMono(LIST)
                .block(CALL))
        .getFirst();
  }

  /** A client carrying a fresh administrator token; the token is short-lived, so none is kept. */
  private WebClient admin() {
    Map<String, Object> answer =
        http.post()
            .uri(baseUrl() + "/realms/master/protocol/openid-connect/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(
                BodyInserters.fromFormData("grant_type", "password")
                    .with("client_id", "admin-cli")
                    .with("username", "synthetic-admin")
                    .with("password", adminPassword))
            .retrieve()
            .bodyToMono(OBJECT)
            .block(CALL);
    return WebClient.builder()
        .baseUrl(baseUrl())
        .defaultHeaders(
            headers -> headers.setBearerAuth((String) required(answer).get("access_token")))
        .build();
  }

  private static <T> T required(T value) {
    if (value == null) {
      throw new IllegalStateException("Keycloak answered without a body");
    }
    return value;
  }
}
