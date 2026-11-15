package com.aisquad.owlmast.fixtures.security;

import com.aisquad.owlmast.testing.SyntheticKeycloak;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * What a browser does during sign-in, without a browser: it follows the redirects one at a time,
 * keeps the cookies of the backend and of Keycloak apart, and fills in Keycloak's login form. Every
 * answer the backend gave is kept, so a test can assert that none of them carried a token.
 *
 * <p>The backend redirects to its configured application origin, which is not the random port of a
 * test: the path and query of such a redirect are requested from the backend under test instead, as
 * the routing in front of a real installation would.
 */
public final class SyntheticBrowser {

  private static final Pattern FORM_ACTION = Pattern.compile("<form[^>]*\\baction=\"([^\"]+)\"");
  private static final Duration CALL = Duration.ofSeconds(30);

  private final HttpClient http =
      HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build();
  private final String backend;
  private final Map<String, String> backendCookies = new LinkedHashMap<>();
  private final Map<String, String> providerCookies = new LinkedHashMap<>();
  private final List<HttpResponse<String>> backendAnswers = new ArrayList<>();
  private final List<String> backendSetCookies = new ArrayList<>();

  public SyntheticBrowser(int backendPort) {
    this.backend = "http://localhost:" + backendPort;
  }

  /** A GET of the backend with this browser's cookies; extra headers as name, value pairs. */
  public HttpResponse<String> get(String pathAndQuery, String... headers) {
    return backend(HttpRequest.newBuilder(URI.create(backend + pathAndQuery)).GET(), headers);
  }

  public HttpResponse<String> post(String path, String body, String... headers) {
    return backend(
        HttpRequest.newBuilder(URI.create(backend + path))
            .POST(HttpRequest.BodyPublishers.ofString(body)),
        headers);
  }

  /**
   * Signs the user in through Keycloak's login form and returns the backend's answer to the
   * callback. When Keycloak still has a session for this browser it answers without a form.
   */
  public HttpResponse<String> signIn(SyntheticKeycloak keycloak, String username) {
    HttpResponse<String> start = get("/api/session/sign-in", "Accept", "text/html");
    if (start.statusCode() != 302) {
      return start;
    }
    HttpResponse<String> login = provider(HttpRequest.newBuilder(location(start)).GET());
    HttpResponse<String> granted = login;
    if (login.statusCode() == 200) {
      Matcher form = FORM_ACTION.matcher(login.body());
      if (!form.find()) {
        throw new IllegalStateException("Keycloak's answer has no login form");
      }
      String credentials =
          "username=" + encode(username) + "&password=" + encode(keycloak.userPassword());
      granted =
          provider(
              HttpRequest.newBuilder(URI.create(form.group(1).replace("&amp;", "&")))
                  .header("Content-Type", "application/x-www-form-urlencoded")
                  .POST(HttpRequest.BodyPublishers.ofString(credentials)));
    }
    if (granted.statusCode() != 302) {
      throw new IllegalStateException(
          "Keycloak did not grant the sign-in: " + granted.statusCode());
    }
    return returnToBackend(location(granted));
  }

  /** Requests the path and query of a redirect to the application origin from the backend. */
  public HttpResponse<String> returnToBackend(URI redirect) {
    String query = redirect.getRawQuery() == null ? "" : "?" + redirect.getRawQuery();
    return get(redirect.getRawPath() + query, "Accept", "text/html");
  }

  public static URI location(HttpResponse<String> answer) {
    return URI.create(answer.headers().firstValue("Location").orElseThrow());
  }

  /** The value of the backend's session cookie, or empty when the browser holds none. */
  public String sessionCookie() {
    return backendCookies.getOrDefault("OWLMAST_SESSION", "");
  }

  /** Every cookie the browser holds for the backend. */
  public Map<String, String> backendCookies() {
    return Map.copyOf(backendCookies);
  }

  /** Every {@code Set-Cookie} header the backend sent this browser. */
  public List<String> backendSetCookies() {
    return List.copyOf(backendSetCookies);
  }

  /** Everything the backend sent this browser: bodies and headers, for "no token" assertions. */
  public String everythingTheBackendSent() {
    return backendAnswers.stream()
        .map(answer -> answer.headers().map() + "\n" + answer.body())
        .collect(Collectors.joining("\n"));
  }

  private HttpResponse<String> backend(HttpRequest.Builder request, String... headers) {
    for (int i = 0; i + 1 < headers.length; i += 2) {
      request.header(headers[i], headers[i + 1]);
    }
    HttpResponse<String> answer = send(withCookies(request, backendCookies));
    backendAnswers.add(answer);
    backendSetCookies.addAll(answer.headers().allValues("Set-Cookie"));
    remember(answer, backendCookies);
    return answer;
  }

  private HttpResponse<String> provider(HttpRequest.Builder request) {
    HttpResponse<String> answer = send(withCookies(request, providerCookies));
    remember(answer, providerCookies);
    return answer;
  }

  private static HttpRequest.Builder withCookies(
      HttpRequest.Builder request, Map<String, String> cookies) {
    if (!cookies.isEmpty()) {
      request.header(
          "Cookie",
          cookies.entrySet().stream()
              .map(cookie -> cookie.getKey() + "=" + cookie.getValue())
              .collect(Collectors.joining("; ")));
    }
    return request;
  }

  private static void remember(HttpResponse<String> answer, Map<String, String> cookies) {
    for (String header : answer.headers().allValues("Set-Cookie")) {
      String pair = header.split(";", 2)[0];
      int equals = pair.indexOf('=');
      String name = pair.substring(0, equals).strip();
      String value = pair.substring(equals + 1).strip();
      boolean expired =
          value.isEmpty()
              || header.toLowerCase(java.util.Locale.ROOT).contains("max-age=0")
              || header.contains("01 Jan 1970");
      if (expired) {
        cookies.remove(name);
      } else {
        cookies.put(name, value);
      }
    }
  }

  private HttpResponse<String> send(HttpRequest.Builder request) {
    try {
      return http.send(request.timeout(CALL).build(), HttpResponse.BodyHandlers.ofString());
    } catch (IOException failed) {
      throw new IllegalStateException(failed);
    } catch (InterruptedException interrupted) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException(interrupted);
    }
  }

  private static String encode(String value) {
    return URLEncoder.encode(value, StandardCharsets.UTF_8);
  }
}
