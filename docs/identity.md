# Browser identity and session (OM-02.01)

This is the one published decision for browser sign-in: the session model, the origins, the realm and client, the account policy, the lifetimes and what is deliberately left to later stories. The owner decided the first section on 2026-11-15 ([#24](https://github.com/gabrianoo/owl-mast/issues/24)); the rest states how the code implements it and what was run. Chart values are in [installation.md](installation.md#public-origins-realm-and-client), the shell's states in [frontend.md](frontend.md#session-om-0201), the error envelope in [api-compatibility.md](api-compatibility.md#common-error-envelope).

## Decisions

| Topic | Decision |
| --- | --- |
| Session model | The backend holds the session. It is a confidential OpenID Connect client using the authorization code grant with PKCE. Tokens never reach the browser, which holds one `HttpOnly`, `Secure`, `SameSite=Lax` session cookie. Unsafe methods need a CSRF token. Sign-out and Keycloak's back-channel logout end the server session. |
| Origins and routing | The frontend (`/`) and the backend (`/api`) share the one application origin the chart routes, so there is no CORS. Keycloak is reached on its own public origin, set by an explicit value. The bundled Keycloak gets its own route (Gateway API first, Ingress optional); an external one is used as it is. |
| Accounts | Invitation only. Self-registration is off; an administrator creates the account in Keycloak and the person sets their password there. Recovery is Keycloak's "forgot password" when the operator configured mail for the realm, otherwise an administrator reset. Self-service tenant sign-up belongs to the multi-tenant rollout (OM-19.01). |
| Session store | The backend's memory. A backend restart or upgrade signs everyone out, and the chart refuses more than one backend replica. A durable store is deferred work. |

There is no setting that turns authentication off, in the backend or in the chart. The backend does not start without an issuer, a client id, a client secret and the application origin.

## Principal

A principal is the pair (issuer, subject) of a validated credential, exactly as the credential carries them. Display name, username and email are never identity: they are not compared and not stored.

- `access.principal` (migration `V006__access_principal.sql`) holds the pair, a generated id, the tenant, and when and how often the person signed in. It holds no name, no address and no credential. The principal id is `person:<uuid>`; the same issuer and subject always give the same id, whatever the person is called at the time.
- The tenant of every principal is the installation's configured tenant (`owlmast.sign-in.tenant`, `default`) until OM-02.02 supplies tenant membership.
- Every authenticated request runs with `ScopeContext(tenant, principal)` bound in the Reactor Context, after authorization. A request without an authenticated principal has no scope, so code that needs one fails with `MissingScopeException`.

## Endpoints

All of them are below `/api`, the only prefix routed to the backend.

| Endpoint | Who may call it | Behaviour |
| --- | --- | --- |
| `GET /api/session` | anyone | Always 200, `Cache-Control: no-store`: `{"state":"signed-out"}`, or `signed-in` with `person` (`principalId`, `displayName`) and `csrf` (`headerName`, `token`). Nothing else about the person is published. 503 when a session exists and the identity provider cannot be asked whether it still stands. The shell reads it once a minute while the page is visible, and not in a hidden tab. |
| `GET /api/session/sign-in` | anyone, as a browser navigation | 302 to the identity provider's authorization endpoint with `state`, `nonce` and a PKCE challenge. A browser that already has a session is sent back to the shell instead; to change the person, sign out first. |
| `GET /api/session/callback` | the browser, returning from the identity provider | Exchanges the code, validates the ID token, binds the principal, records the sign-in, then 302 to `<application origin>/`. |
| `POST /api/session/sign-out` | a signed-in session, with the CSRF header | Ends the session, asks the identity provider to end its own, answers `{"state":"signed-out","identityProvider":"ended"\|"unconfirmed"}`. It works during an identity provider outage too: the session ends here and the answer is `unconfirmed`. 409 for a bearer caller, which has no browser session. |
| `POST /api/session/backchannel-logout` | the identity provider | OpenID Connect Back-Channel Logout 1.0: a signed logout token ends the sessions it names. 200 for a valid notice, 400 for one the provider did not sign or that is not a logout token, 503 when the provider's keys cannot be fetched to verify it, so that the provider sends it again. |
| `GET /api/compatibility`, `GET /actuator/health/**` | anyone | Unchanged, no credential needed. |
| everything else | an authenticated principal | 401 without one, in the problem-details envelope with `WWW-Authenticate: Bearer`. An API call is never redirected to a login page. An unknown path is 401 for an anonymous caller and 404 for an authenticated one. An unsafe method (`POST`, `PUT`, `PATCH`, `DELETE`) without a live session answers 403, not 401: the CSRF check comes first and a session that ended has no token. The shell reads its session again after either. |

When a sign-in step fails, a browser navigation (a request that accepts `text/html`) is sent back to the shell with the outcome in the address: `/?sign-in=failed` when the sign-in was refused or its answer could not be accepted, `/?sign-in=unavailable` when the identity provider could not do its part. Any other caller gets 401 or 503 in the envelope. Neither form carries what the identity provider said. Every redirect is built from the configured application origin (`owlmast.sign-in.application-origin`, the chart's `routing.publicOrigin`), never from request or forwarding headers.

This adds endpoints, so the API contract is 1.1 ([api-compatibility.md](api-compatibility.md)); the shell needs at least 1.1.

## Credential checks

| Credential | Checked for | Where |
| --- | --- | --- |
| ID token at sign-in | RS256 signature against the issuer's keys, `iss` equal to the configured issuer, `aud` containing the client, `exp`, `iat`, `nonce`; the authorization response must match a request this browser session started (`state`) and the code is redeemed with the PKCE verifier and the client secret | Spring Security's OpenID Connect login |
| Session cookie | names a session in this process's memory; the tokens that session holds are renewed with the identity provider (below) | `SessionKeeper` |
| Bearer credential (`Authorization: Bearer`) | RS256 signature, then in this order `exp` (required: a token without one is refused) and `nbf` (one minute of clock difference allowed), `iss` equal to the configured issuer, `aud` containing `owlmast.sign-in.audience` (the client id unless set), the token kind, a subject | `CredentialValidation.bearer` |
| Logout token | RS256 signature, `exp` (required), `iss`, `aud` containing the client, the back-channel logout event, no `nonce`, a session id or a subject | `CredentialValidation.logoutToken` |

A credential that fails a check denies the request with 401 (400 for a logout token). The answer carries the challenge and no reason; the reason is one of a fixed set of codes in the audit record (`credential-expired`, `credential-issuer-mismatch`, `credential-audience-mismatch`, `credential-kind-mismatch`, `credential-subject-missing`, `credential-invalid`). A token whose signature does not verify is `credential-invalid` whatever its claims say, so a token of another realm is recorded that way. An identity provider that cannot be reached for its keys is an outage (503), not a refusal. Nothing cached or public is answered in place of a protected answer.

Signature algorithm: only RS256 is accepted, for ID tokens, bearer credentials and logout tokens alike. It is Keycloak's default; a realm or client switched to another algorithm (ES256, PS256) fails every sign-in as a rejected ID token until that is changed back, because the algorithm is not configurable here.

Keys that cannot be fetched say nothing about a token: a bearer call then answers 503, a sign-in ends as `sign-in=unavailable` and a logout notice answers 503. That holds however the fetch fails: the key endpoint refuses the connection, answers an error status or something that is not a key set, or does not answer in time. Every call to the identity provider (code exchange, renewal, key fetch) is given 10 seconds, each on its own; one that takes longer is an outage. The time bounds the provider's part only. At sign-in, binding the principal and recording the sign-in come after the code exchange and the ID token's keys and are not inside either bound, so a record that commits late still completes the sign-in it records.

**Key fetches.** A bearer credential and a logout notice can be presented by anybody, and the key a token names (`kid`) is the sender's choice. The two share one set of the issuer's keys (`IssuerSigningKeys`), which asks the identity provider at a bounded rate:

- A token whose key is held is verified with it, without a request. The held set is replaced only by a later fetch.
- A token whose key is not held causes a fetch, and for 30 seconds after that fetch no further one is made: a token naming a key the set still does not have is refused (401, or 400 for a logout notice) without asking again. So after a fetch that succeeded, the provider receives no further key request for 30 seconds, however many such tokens arrive.
- A fetch that fails is the outage above. It is answered to every token that needs a fetch for 5 seconds, then tried again: a key endpoint that keeps failing is asked once every 5 seconds while such tokens arrive, not once per 30. Tokens whose key is held are still verified meanwhile.

The price: a signing key the issuer starts using is accepted up to 30 seconds late, and only when a fetch happened in that window. Anybody can cause the fetch that starts those 30 seconds, by sending a token that names an unknown key. A logout notice signed with it in that window answers 400. The ID token of a sign-in comes from the token endpoint, not from the caller, and is verified with the framework's own key source, which fetches whenever a token names a key it does not hold.

Token kind: the issuer signs ID, refresh and logout tokens with the same key, and an ID token carries the client as its audience. A bearer credential that names its kind (Keycloak's `typ` claim) must say `Bearer`, and one with a `nonce` or a logout event is refused.

**What the bearer check is for.** The check exists and is proven, but the realm the chart imports has no client that issues a token with the backend's audience (no audience mapper, no direct grants), so in a chart installation no bearer credential passes it. Which clients may obtain such tokens is not decided here: native enrollment credentials, MCP OAuth and service identities belong to Epics 4 and 5, and the browser session's lifetime does not set theirs. A bearer call takes no cookie, has no browser session (`GET /api/session` reads `signed-out`) and needs no CSRF token, because it carries no ambient authority.

## Session lifetime

The session lives in the backend's memory; how long it lives is decided by the realm, not by an Owl Mast value.

- **Renewal.** On every request with a session, the backend looks at the access token it holds and, within a minute of its expiry, renews it with the refresh token. A renewal the identity provider refuses ends the session at that request: the provider's session reached its idle or maximum lifetime, the person signed out elsewhere, or an administrator ended it. The request continues without a session, so a protected operation answers 401 and a public one is still served. The renewed ID token is not used; who the person is was decided at sign-in.
- **Back-channel logout.** When Keycloak ends a session it posts a logout token to the backend, and the named sessions end at once. The chart's realm sets the address to the backend's cluster-local Service.
- **Outage.** When the identity provider cannot be asked (unreachable, no answer within 10 seconds, a 5xx at the token endpoint), the session is kept and the request is answered 503. Three exceptions: the compatibility descriptor and the health endpoints are served without the session, and sign-out is served, so a person can always end their session here. Only a refusal of the grant (`invalid_grant`) ends a session. A provider that refuses the backend itself (`invalid_client`, `unauthorized_client`: a wrong or rotated client secret) is treated as an outage and logged as an error: sessions are kept and answer 503 until the client configuration is corrected, instead of everybody being signed out as expired.
- **Discovery.** The issuer's endpoints are read from its discovery document, kept for 5 minutes and then read again. When that read fails, the last accepted document keeps being used and the read is retried every 5 seconds, so a provider that is briefly away does not turn requests of valid sessions into 503.
- **Readiness during an outage.** The backend's readiness includes a check of the issuer's discovery document ([installation.md](installation.md#combinations)). Once the provider has published the configured issuer to the running backend, a provider that gives no answer (the connection fails, nothing arrives within 3 seconds, or a 5xx status comes back) does not make the backend unready: the check reports UP with a detail saying the provider did not answer. The single backend therefore stays in the Service during an identity provider outage, a restart of the bundled Keycloak included, and the answers of the Outage bullet (503 in the envelope for a kept session, the public endpoints, sign-out) reach the caller instead of the routing layer's own failure. Two cases remain unready: a backend process that has not seen the matching issuer yet (one that starts or restarts during the outage), and a provider that answers with something that is not the configured issuer (another issuer, no issuer, an empty body, a document that cannot be read, or a status that is neither success nor 5xx, such as the 404 of a deleted realm), whenever that answer arrives. Such an answer also ends what was verified: a provider that goes silent after it leaves the backend unready until the configured issuer is published again.
- **Memory bound.** A signed-in session that is idle for 12 hours is dropped from memory whatever the realm allows. This bounds memory; it is longer than Keycloak's default maximum session, so with default realm settings the realm decides first. The state of a sign-in that was started and not finished is kept for 5 minutes.
- **Store size.** The in-memory store holds at most 10,000 sessions (Spring's default), unfinished sign-ins included. Nothing in the backend limits how fast sign-ins are started, so a flood of them can keep new people from signing in for up to those 5 minutes; sessions that exist are not affected. A sign-in started while the store is full answers like an outage (503, or `sign-in=unavailable` for a browser). Limiting request rates is the routing layer's job (deferred work).
- **Restart.** A backend restart or upgrade signs everyone out. People sign in again; when their Keycloak session is still alive they are not asked for the password.

The lifetimes that matter are the realm's (Keycloak 26.8.2 defaults for the imported realm, which the chart does not change):

| Realm setting | Default | Effect here |
| --- | --- | --- |
| Access token lifespan | 5 minutes | How often an active session is renewed, and the longest an ended Keycloak session can go unnoticed when no logout notice arrives (below) |
| SSO session idle | 30 minutes | A session that was not renewed for this long is refused at its next renewal. "Renewed" means a request reached the backend, and the shell sends one every minute while its page is visible: an open, visible tab therefore keeps the session active without the person doing anything, and the idle limit applies once the tab is closed, hidden or the device sleeps |
| SSO session max | 10 hours | The longest a session lasts whatever its activity, an open tab included |

**Revocation without a notice.** When a session is ended in Keycloak and the logout notice does not arrive (the back-channel address is not configured on an operator-managed client, Keycloak cannot reach the backend, the notice is lost), the backend learns it at the next renewal: at most one access token lifespan later, 5 minutes by default. Until then the session cookie is still accepted. With the notice the next operation is denied. An operator who needs the bound to be shorter lowers the realm's access token lifespan.

## Sign-out

`POST /api/session/sign-out` ends the Owl Mast session first and unconditionally, then asks the identity provider to end its own session by posting the refresh token, with the client's credentials, to Keycloak's logout endpoint next to the token endpoint (`…/protocol/openid-connect/logout`). No token goes through the browser, which is why the browser-redirect form of logout (it needs the ID token as a hint) is not used. The answer says `ended` when Keycloak confirmed and `unconfirmed` otherwise; the shell says so. An issuer whose token endpoint does not have Keycloak's layout always answers `unconfirmed`: "compatible" for an external issuer means Keycloak-compatible here.

## CSRF, CORS, cookies, proxies

- **CSRF.** Every `POST`, `PUT`, `PATCH` and `DELETE` needs the session's CSRF token in the header that `GET /api/session` names (`X-CSRF-TOKEN`); without it the answer is 403 and nothing happens. That includes an unsafe call whose session has ended: it answers 403, not 401. The token is kept in the session, not in a second cookie, and the value handed out is masked per request. Two exceptions carry no ambient authority: a call with a bearer credential, and the identity provider's logout notice, which is authenticated by its own signed token.
- **CORS.** None is configured. Shell and backend share one origin; a cross-origin script gets no CORS headers.
- **Cookie.** `OWLMAST_SESSION`, an opaque random id, `HttpOnly; Secure; SameSite=Lax; Path=/api`. It is replaced when the session is authenticated. Because it is always `Secure`, the application origin must be `https`; plain `http` is accepted only on a loopback host, where browsers still accept such a cookie.
- **Proxies.** The backend does not trust `Forwarded` or `X-Forwarded-*` headers and does not need them: redirects use the configured application origin. The bundled Keycloak is told its public origin (`KC_HOSTNAME`) and answers the backend on the cluster-local Service (`KC_HOSTNAME_BACKCHANNEL_DYNAMIC`); the backend is told both addresses (`owlmast.identity.issuer-uri` is the public issuer that tokens carry, `owlmast.identity.backchannel-uri` is where it fetches the discovery document). The document must still publish exactly the configured issuer, and a plaintext endpoint in it is refused unless plaintext was allowed for that address.
- **Plaintext inside the cluster.** The backend reaches the bundled Keycloak over plain `http` on the Service. The imported realm has `sslRequired: external`, which lets Keycloak answer plaintext only to private addresses (loopback, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16). On a cluster whose pod network is outside those ranges Keycloak refuses the backend's calls ("HTTPS required"), the backend never becomes ready and nobody can sign in: such a cluster needs an external issuer reached over `https`.
- **Content-Security-Policy.** The frontend image's policy is unchanged: sign-in is a top-level navigation and sign-out a same-origin request.

## Realm and client

The chart imports this realm into the bundled Keycloak ([installation.md](installation.md#realm-and-client) has the values); an operator who supplies Keycloak creates the same client there.

| Setting | Value |
| --- | --- |
| Self-registration | off |
| "Forgot password" | off until the operator configures mail for the realm and turns it on in Keycloak |
| Client | confidential; standard flow only (no implicit flow, no direct access grants, no service account) |
| Redirect URI | exactly `<application origin>/api/session/callback` |
| PKCE | `S256` |
| Web origins | none |
| Back-channel logout URL | `<address Keycloak reaches the backend on>/api/session/backchannel-logout`, session required |
| Scopes used | `openid profile email`; the user-info endpoint is not called |

Owl Mast stores no password and shows no form for accounts, passwords or recovery: those screens are Keycloak's. Keycloak imports the realm only when it does not exist yet, so an installation that already has the realm needs the client created by hand.

## Audit outcomes

Every session outcome is recorded through the audit owner (`AuditedMutations`, [durable-work-and-audit-contract.md](durable-work-and-audit-contract.md)), so it has the envelope's guarantees and nothing but identifiers and fixed codes can reach it: no credential, token, name or address. The correlation id of a session's records is the session's reference, a random value that is not the session id.

| What happened | Action | Outcome | Actor | Reason |
| --- | --- | --- | --- | --- |
| Sign-in completed | `session.sign-in` | `SUCCEEDED` | the principal (`HUMAN`) | |
| Sign-in refused (declined at the provider, unmatched or replayed response, rejected code or ID token) | `session.sign-in` | `DENIED` | Unknown (`HUMAN`) | `sign-in-declined`, `authorization-response-unmatched`, `authorization-code-rejected`, `id-token-rejected`, `sign-in-refused` |
| Sign-in could not be completed (identity provider or principal store failed) | `session.sign-in` | `FAILED` | Unknown (`HUMAN`) | exception class names |
| Signed out in the shell | `session.sign-out` | `SUCCEEDED` | the principal | |
| Session no longer renewed, or dropped from memory | `session.expire` | `SUCCEEDED` | the principal whose session ended | |
| Session ended by a logout notice | `session.revoke` | `SUCCEEDED` | the principal whose session ended | |
| A later sign-in completed in the same browser session (two tabs that both started one) | `session.replace` | `SUCCEEDED` | the principal of the earlier sign-in | |
| Bearer credential refused | `credential.verify` | `DENIED` | Unknown (`HUMAN`) | the credential codes above |

- A sign-in is recorded in the same transaction as the principal's sign-in count, before the session is authenticated: when the record cannot be written, the sign-in fails and no session exists.
- For an expiry or a revocation the actor is the person whose session ended. Who ended it at the identity provider is in the provider's own event log; the backend cannot tell an administrator's action from the person's.
- A renewal that is refused is recorded as `session.expire` whether the provider's session ran out or was ended there: the backend sees the same answer.
- A session dropped from memory is recorded with the next request the backend handles (at most once a minute), not by a timer, so on an idle backend the record is later than the drop.
- A callback that fails does not end a session somebody is signed in with, and one that matches no sign-in this browser started leaves the sign-ins it did start pending: anyone can send a browser to the callback address.
- The provider's own error code arrives in the callback address, which anyone can write. It is only looked up to one of the fixed reasons, never recorded.
- A refused bearer credential writes one audit row per request, and so does every request that needs no credential to fail a sign-in: a callback nobody started, and a sign-in start or callback while the identity provider is unavailable or the session store is full. Nothing limits how many such requests a caller can make (deferred work).

## What was qualified

All with synthetic realms and users; no live realm, user or mail server.

| What | How | Result on 2026-11-15 |
| --- | --- | --- |
| Sign-in, principal bound by issuer and subject, scope bound, outcome recorded, one `HttpOnly`/`Secure`/`SameSite=Lax` cookie, no token in anything the browser receives or in the log | `SignInIT` against the pinned Keycloak 26.8.2 container (`OwlMastImages.KEYCLOAK`, the chart's digest) with a generated realm | passed |
| Same person after a display-name change is the same principal | `SignInIT` | passed |
| Credential of another client (audience) or another realm: 401, no principal, `DENIED` recorded, no reason in the answer | `SignInIT` | passed |
| Expired credential | `CredentialValidationTest` (unit: a token Keycloak signed cannot be made old) | passed |
| Session that Keycloak no longer renews: next protected operation 401, public endpoint still served, `session.expire` recorded | `SignInIT` (access tokens of 30 s, so every request renews; an administrator ends the session and no notice is sent) | passed |
| Session revoked in Keycloak with the logout notice: denied at once, `session.revoke` recorded, another person's session untouched; a notice Keycloak did not sign changes nothing | `SignInIT` | passed |
| Sign-out ends the session here and in Keycloak; the old cookie is worth nothing | `SignInIT` | passed |
| Unsafe call without the CSRF token: 403, no effect | `SignInIT` | passed |
| Unauthenticated protected call: 401 in the envelope with the challenge, never a redirect | `SignInIT`, `CompatibilityEndpointIT` | passed |
| Identity provider unavailable: 503 or the shell's provider-error address, no session, `FAILED` recorded, public endpoints unaffected | `IdentityProviderUnavailableIT` | passed |
| Discovery accepted and the key endpoint refusing connections: a logout notice answers 503 and is logged as not verifiable, a bearer call answers 503 in the envelope and records no refusal | `IdentityKeysUnavailableIT` | passed on 2026-11-16 |
| Key fetches: held keys need no request; tokens naming unknown keys are refused with at most one request per 30 s; a failed fetch (error status, refused connection, no answer in 10 s, not a key set) is an outage repeated after 5 s while held keys still verify | `IssuerSigningKeysTest`, `CredentialValidationTest` (unit: a local issuer with keys generated for the test, a clock the test moves) | passed on 2026-11-16 |
| The 10 s given to the provider at sign-in bound the code exchange and the ID token's keys, each on its own; a sign-in record that commits later still completes the sign-in, recorded once | `SignInManagerTest` (unit: the same local issuer, stand-ins for the principal store and the audit owner, a clock the test moves) | passed on 2026-11-16 |
| Readiness stays UP, with the detail, when a provider whose issuer was verified gives no answer (refused connection, 503); DOWN before it was verified, for an answer that is not the matching issuer (another issuer, no issuer, no body, 404), and for no answer after such an answer | `IdentityDiscoveryHealthIndicatorTest` (unit) | passed on 2026-11-16 |
| A session whose provider cannot be asked (`server_error`, no answer, a refused client) is kept: protected call 503, public content served, sign-out served, nothing recorded; `invalid_grant` ends it | `SessionKeeperTest`, `SessionStandingFilterTest` (unit: the provider's answers are stubbed) | passed |
| An idle session dropped from memory is recorded once; a second sign-in on one browser session records `session.replace`; sign-out without the provider's confirmation ends the session and says `unconfirmed` | `SessionKeeperTest` (unit, with a clock the test moves) | passed |
| Every kind of callback failure: where the browser goes, what is recorded, what becomes of the pending session | `SignInOutcomeHandlersTest` (unit) | passed |
| Browser login and return across the separately packaged frontend and backend | `frontend/e2e/smoke/session.spec.ts` (Chromium, the built shell behind its preview server, the backend from `bootTestRun`, Keycloak's own login page) | passed |
| The chart's realm import in the pinned Keycloak: client, redirect URI, PKCE, registration off, public issuer with cluster-local token and key endpoints | `deploy/tests/test_keycloak_readonly.py` (Docker) | passed |

Not qualified:

- **No run on a cluster.** The chart's Keycloak route, the back-channel logout from the bundled Keycloak to the backend Service, the secret placeholder in a Kubernetes pod and a browser sign-in through a Gateway or Ingress have not run on the Kind target or anywhere else. The integration tests reach Keycloak and the backend on loopback, where the issuer and the back-channel address are the same; the split between a public issuer and a cluster-local address is covered by `IdentityDiscoveryTest` and by the Docker run of the rendered Keycloak, not by a sign-in.
- **An outage of a running Keycloak** (stopped or restarted under a backend that was ready) was not run, on a cluster or against the container: the outage cases above use a local stand-in whose endpoints refuse, fail or do not answer. That Kubernetes keeps the backend in the Service through such an outage follows from the readiness result and was not observed.
- **A slow database at sign-in** was not run: the late sign-in record is a delay in a stand-in for the principal store.
- **A realm lifetime running out by itself** (SSO idle or max) was not waited for; the refused renewal it produces is the one the tests cause by ending the session in Keycloak.
- **An external Keycloak** was not run; it differs from the tests only in who creates the client.

## Open for later stories

| Topic | Where |
| --- | --- |
| Tenant and project membership, roles and permissions | OM-02.02, OM-02.04 |
| External account bindings | OM-02.03 |
| Enrollment credentials, MCP OAuth, service identities, and which clients may obtain a bearer credential for the backend | Epics 4 and 5 |
| Self-service tenant sign-up | OM-19.01 |
| A durable session store, and with it more than one backend replica | deferred work |
| A limit on audit rows written for unauthenticated requests (refused bearer credentials, unmatched callbacks, sign-ins during an outage); a timer for recording dropped sessions; signature algorithms other than RS256 | deferred work |
