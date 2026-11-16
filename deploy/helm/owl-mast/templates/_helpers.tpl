{{/* Names */}}
{{- define "owl-mast.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "owl-mast.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "owl-mast.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/name: {{ include "owl-mast.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: owl-mast
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "owl-mast.selectorLabels" -}}
app.kubernetes.io/name: {{ include "owl-mast.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Immutable image reference: repository:tag@digest when a digest is pinned. */}}
{{- define "owl-mast.image" -}}
{{- $img := . -}}
{{- if $img.digest -}}
{{- if $img.tag -}}{{ printf "%s:%s@%s" $img.repository $img.tag $img.digest }}{{- else -}}{{ printf "%s@%s" $img.repository $img.digest }}{{- end -}}
{{- else -}}
{{ printf "%s:%s" $img.repository $img.tag }}
{{- end -}}
{{- end -}}

{{/*
Suffixed resource name, at most 63 characters: the fullname is shortened BEFORE the suffix is appended, so a
long release name or fullnameOverride never renders a name the API server rejects. A shortened base carries a
6-character hash of the release name and the whole fullname, so two releases whose fullnames share the kept
prefix never render the same name (a hook's before-hook-creation policy deletes by name, without an ownership
check). Names that fit are unchanged. Usage: include "owl-mast.suffixedName" (list . "postgresql-init")
The hash keeps two releases apart by accident, not by intent: an operator who deliberately names a release
after another release's shortened name plus its hash renders the same names. Helm's ownership check then
refuses the shared objects; only the hook Job and its ConfigMap are replaced by name (docs/installation.md).
*/}}
{{- define "owl-mast.suffixedName" -}}
{{- $root := index . 0 -}}
{{- $suffix := index . 1 -}}
{{- $full := include "owl-mast.fullname" $root -}}
{{- $budget := int (sub 62 (len $suffix)) -}}
{{- if le (len $full) $budget -}}
{{- printf "%s-%s" $full $suffix -}}
{{- else -}}
{{- $hash := printf "%s/%s" $root.Release.Name $full | sha256sum | trunc 6 -}}
{{- printf "%s-%s-%s" ($full | trunc (int (sub $budget 7)) | trimSuffix "-") $hash $suffix -}}
{{- end -}}
{{- end -}}

{{- define "owl-mast.postgresql.fullname" -}}{{ include "owl-mast.suffixedName" (list . "postgresql") }}{{- end -}}
{{- define "owl-mast.keycloak.fullname" -}}{{ include "owl-mast.suffixedName" (list . "keycloak") }}{{- end -}}
{{- define "owl-mast.backend.fullname" -}}{{ include "owl-mast.suffixedName" (list . "backend") }}{{- end -}}
{{- define "owl-mast.frontend.fullname" -}}{{ include "owl-mast.suffixedName" (list . "frontend") }}{{- end -}}
{{/*
The data claim keeps the chart 0.1.0 spelling, <postgresql fullname>-data, and is never shortened on its own:
a PersistentVolumeClaim name may have 253 characters, and a different name on upgrade would attach a new,
empty volume while the old one stays behind, detached. Every fullname chart 0.1.0 could install (at most 52
characters, the limit of its PostgreSQL Service name) therefore renders the claim it already has.
*/}}
{{- define "owl-mast.postgresql.dataClaim" -}}{{ printf "%s-data" (include "owl-mast.postgresql.fullname" .) }}{{- end -}}
{{- define "owl-mast.postgresql.initConfigMap" -}}{{ include "owl-mast.suffixedName" (list . "postgresql-init") }}{{- end -}}
{{- define "owl-mast.postgresql.provisionScripts" -}}{{ include "owl-mast.suffixedName" (list . "postgresql-provision-scripts") }}{{- end -}}
{{- define "owl-mast.postgresql.provisionJob" -}}{{ include "owl-mast.suffixedName" (list . "postgresql-provision-keycloak") }}{{- end -}}
{{- define "owl-mast.keycloak.realmConfigMap" -}}{{ include "owl-mast.suffixedName" (list . "keycloak-realm") }}{{- end -}}

{{/* Application database endpoint (bundled service or external host). */}}
{{- define "owl-mast.database.host" -}}
{{- if .Values.database.bundled -}}{{ include "owl-mast.postgresql.fullname" . }}{{- else -}}{{ .Values.database.external.host }}{{- end -}}
{{- end -}}
{{- define "owl-mast.database.port" -}}
{{- if .Values.database.bundled -}}{{ .Values.postgresql.service.port }}{{- else -}}{{ .Values.database.external.port }}{{- end -}}
{{- end -}}
{{- define "owl-mast.database.sslMode" -}}
{{- if .Values.database.bundled -}}disable{{- else -}}{{ .Values.database.external.sslMode }}{{- end -}}
{{- end -}}

{{/* Keycloak database endpoint: shared bundled instance or its own external host. */}}
{{- define "owl-mast.keycloak.database.host" -}}
{{- if .Values.database.bundled -}}{{ include "owl-mast.postgresql.fullname" . }}{{- else -}}{{ .Values.identity.keycloak.database.external.host }}{{- end -}}
{{- end -}}
{{- define "owl-mast.keycloak.database.port" -}}
{{- if .Values.database.bundled -}}{{ .Values.postgresql.service.port }}{{- else -}}{{ .Values.identity.keycloak.database.external.port }}{{- end -}}
{{- end -}}
{{- define "owl-mast.keycloak.database.sslMode" -}}
{{- if .Values.database.bundled -}}disable{{- else -}}{{ .Values.identity.keycloak.database.external.sslMode }}{{- end -}}
{{- end -}}

{{/*
Base URL of the bundled Keycloak, the one value behind both KC_HOSTNAME and the issuer the backend trusts.
Keycloak leaves the scheme's default port out of the issuer it publishes (HostnameV2Provider sanitises the
port), and the backend compares issuers exactly, so port 80 is left out here too. The bundle is http only,
so 443 is an ordinary port and stays.
*/}}
{{- define "owl-mast.keycloak.baseUrl" -}}
{{- $port := int .Values.identity.keycloak.service.port -}}
{{- if eq $port 80 -}}
{{- printf "http://%s" (include "owl-mast.keycloak.fullname" .) -}}
{{- else -}}
{{- printf "http://%s:%d" (include "owl-mast.keycloak.fullname" .) $port -}}
{{- end -}}
{{- end -}}

{{/*
Values added in chart 0.3.0, read through dig so that a release upgraded with --reuse-values (values without
these keys) reaches the validation below, which names the missing value, instead of a nil-pointer error.
*/}}
{{- define "owl-mast.routing.publicOrigin" -}}{{ dig "publicOrigin" "" .Values.routing | toString }}{{- end -}}
{{- define "owl-mast.keycloak.publicOrigin" -}}{{ dig "publicOrigin" "" .Values.identity.keycloak | toString }}{{- end -}}
{{- define "owl-mast.keycloak.adminOrigin" -}}{{ dig "adminOrigin" "" .Values.identity.keycloak | toString }}{{- end -}}
{{- define "owl-mast.identity.clientId" -}}{{ dig "client" "id" "owl-mast-web" .Values.identity | toString }}{{- end -}}
{{- define "owl-mast.identity.clientSecret" -}}{{ dig "client" "existingSecret" "owl-mast-oidc-client" .Values.identity | toString }}{{- end -}}
{{- define "owl-mast.keycloak.route.gateway.enabled" -}}{{ dig "route" "gateway" "enabled" false .Values.identity.keycloak | toString }}{{- end -}}
{{- define "owl-mast.keycloak.route.ingress.enabled" -}}{{ dig "route" "ingress" "enabled" false .Values.identity.keycloak | toString }}{{- end -}}

{{/* Host of an origin (scheme://host[:port]) that owl-mast.validateOrigin accepted. */}}
{{- define "owl-mast.originHost" -}}
{{- regexReplaceAll ":[0-9]+$" (regexReplaceAll "^https?://" . "") "" -}}
{{- end -}}

{{/*
Where an origin that owl-mast.validateOrigin accepted listens: its host and the port it names, or its scheme's
default port (443 for https, 80 for http). The scheme is left out, because one port carries one listener
whatever the scheme. localhost and 127.0.0.1 are one machine, so both are written "(loopback)", which no host
can be. Two origins with the same result cannot be two services. Nothing else is folded: a name under
.localhost can be told apart by a local proxy that routes by host, and another 127.x.x.x address can be bound
apart, so they stay hosts of their own.
*/}}
{{- define "owl-mast.originSocket" -}}
{{- $host := include "owl-mast.originHost" . -}}
{{- if regexMatch "^(localhost|127\\.0\\.0\\.1)$" $host -}}{{- $host = "(loopback)" -}}{{- end -}}
{{- $port := regexFind "[0-9]+$" (regexFind ":[0-9]+$" .) | default (ternary "443" "80" (hasPrefix "https://" .)) -}}
{{- printf "%s:%s" $host $port -}}
{{- end -}}

{{/*
Issuer the backend trusts, which is the issuer tokens carry: for the bundled Keycloak its PUBLIC origin
(identity.keycloak.publicOrigin, also KC_HOSTNAME) followed by the realm, for an external issuer the supplied
value as it is. The browser reaches Keycloak on that origin; the backend reaches the bundled Keycloak through
the cluster-local Service (owl-mast.identity.backchannelUri).
*/}}
{{- define "owl-mast.identity.issuerUri" -}}
{{- if .Values.identity.bundled -}}
{{- printf "%s/realms/%s" (include "owl-mast.keycloak.publicOrigin" .) .Values.identity.realm -}}
{{- else -}}
{{- .Values.identity.external.issuerUri -}}
{{- end -}}
{{- end -}}

{{/*
Where the backend fetches the bundled Keycloak's discovery document and calls its token and key endpoints: the
cluster-local Service. Keycloak runs with KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true, so a request that arrives on
this address is answered with the public issuer and with back-channel endpoints on this address.
*/}}
{{- define "owl-mast.identity.backchannelUri" -}}
{{- printf "%s/realms/%s" (include "owl-mast.keycloak.baseUrl" .) .Values.identity.realm -}}
{{- end -}}

{{/*
A public origin: scheme://host[:port] and nothing else. https, or plain http for a loopback host only (the
session cookie is always Secure, and browsers accept a Secure cookie over http on loopback alone). The host is
lowercase, as browsers send it: a DNS name whose last label starts with a letter, a single label, or an IPv4
address. The scheme's default port is refused, because Keycloak and browsers leave it out and origins and
issuers are compared as exact strings. validateOrigin (list "<values path>" <origin> "<what it is>")
*/}}
{{- define "owl-mast.validateOrigin" -}}
{{- $path := index . 0 -}}
{{- $origin := index . 1 -}}
{{- $what := index . 2 -}}
{{- $octet := "(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])" -}}
{{- $label := "[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?" -}}
{{- $top := "[a-z]([-a-z0-9]{0,61}[a-z0-9])?" -}}
{{- $host := printf "((%s\\.){3}%s|%s|(%s\\.)+%s)" $octet $octet $label $label $top -}}
{{- $port := "(:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?" -}}
{{- if not (regexMatch (printf "^https?://%s%s$" $host $port) $origin) -}}
{{- fail (printf "%s %q is not an origin: %s must be scheme://host[:port] with nothing after it (no path, trailing slash, query, fragment or user info), a lowercase host (a DNS name whose last label starts with a letter, a single label, or an IPv4 address) and a port 1-65535" $path $origin $what) -}}
{{- end -}}
{{- if gt (len (include "owl-mast.originHost" $origin)) 253 -}}
{{- fail (printf "%s %q is not an origin: its host exceeds 253 characters" $path $origin) -}}
{{- end -}}
{{- if and (hasPrefix "http://" $origin) (not (regexMatch "^http://(localhost|127\\.0\\.0\\.1)(:[0-9]+)?$" $origin)) -}}
{{- fail (printf "%s %q uses plaintext http: %s must be https. Plain http is accepted only for a loopback host (http://localhost or http://127.0.0.1, with an optional port), because the session cookie is always Secure and credentials would cross the network unencrypted" $path $origin $what) -}}
{{- end -}}
{{- if or (regexMatch "^https://[^:]+:443$" $origin) (regexMatch "^http://[^:]+:80$" $origin) -}}
{{- fail (printf "%s %q names the scheme's default port: write it without the port. Browsers and Keycloak leave the default port out, and origins and issuers are compared as exact strings" $path $origin) -}}
{{- end -}}
{{- end -}}

{{/*
PostgreSQL system databases are never an application database. Arguments: value path, name, whether the
bundled PostgreSQL serves it. template0 and template1 are refused everywhere; postgres only on the bundled
server, where the init scripts would refuse it after initdb (it is owned by the superuser). The comparison
ignores case: the schema admits lowercase only, and this also holds with --skip-schema-validation.
*/}}
{{- define "owl-mast.validateDatabaseName" -}}
{{- $path := index . 0 -}}
{{- $name := lower (toString (index . 1)) -}}
{{- if has $name (list "template0" "template1") -}}
{{- fail (printf "%s=%q is refused: template0 and template1 are PostgreSQL's template databases, never an application database" $path (index . 1)) -}}
{{- end -}}
{{- if and (index . 2) (eq $name "postgres") -}}
{{- fail (printf "%s=%q is refused with database.bundled=true: postgres is the maintenance database of the bundled PostgreSQL, owned by the superuser, so the initialisation scripts would refuse it only after initdb and leave the volume without the role and database" $path (index . 1)) -}}
{{- end -}}
{{- end -}}

{{/*
Fail-closed validation of optional-dependency values and existing-secret references (AC2).
Rendering stops with the offending value named; nothing is installed partially.
*/}}
{{- define "owl-mast.validate" -}}
{{- $v := .Values -}}
{{- if and (not $v.backend.image.tag) (not $v.backend.image.digest) -}}
{{- fail "backend.image.tag or backend.image.digest is required: without either the image reference renders as \"<repository>:\" and the pod fails at pull time" -}}
{{- end -}}
{{- include "owl-mast.validateImageTag" (list "backend.image.tag" $v.backend.image.tag) -}}
{{- /* A named allow-list of JVM memory and tuning options: a system property, agent, argument file, or an -XX option that */ -}}
{{- /* loads a file or opens the attach mechanism would override or bypass the validated configuration */ -}}
{{- $jvm := $v.backend.javaToolOptions | default "" -}}
{{- if not (regexMatch (include "owl-mast.javaToolOptionsPattern" .) $jvm) -}}
{{- fail (printf "backend.javaToolOptions %q is refused: only the listed JVM memory and tuning options are accepted, each with the value form the JVM takes (-Xms/-Xmx/-Xmn/-Xss and the -XX size options with a whole number and an optional k, m or g; the -XX percentage options with a number and no suffix; the -XX count options with a whole number; the -XX flags named in values.yaml, such as -XX:+UseZGC). System properties (-D), agents (-javaagent, -agentlib, -agentpath), argument files (@file) and every other -XX option (file-loading, hook and attach options included) are refused: they would override the chart-validated issuer and database configuration" $jvm) -}}
{{- end -}}
{{- /* the frontend image listens on 8080 only; repeated from the schema so --skip-schema-validation does not reopen it */ -}}
{{- if ne (toString $v.frontend.containerPort) "8080" -}}
{{- fail (printf "frontend.containerPort %v is refused: the frontend image listens on 8080 only, so the probes and the Service would point at a port nothing listens on; set frontend.service.port to change the Service port" $v.frontend.containerPort) -}}
{{- end -}}
{{- /* the schema's extraEnv rules, repeated here so that --skip-schema-validation does not reopen them: a later */ -}}
{{- /* duplicate of a variable the chart renders wins in Kubernetes */ -}}
{{- range $i, $e := $v.backend.extraEnv -}}
{{- $name := toString (get $e "name") -}}
{{- if not (regexMatch "^[A-Za-z_][A-Za-z0-9_]*$" $name) -}}
{{- fail (printf "backend.extraEnv[%d].name %q is not a valid environment variable name" $i $name) -}}
{{- end -}}
{{- if or (regexMatch "(?i)^(OWLMAST_|SPRING_|MANAGEMENT_|SERVER_|LOADER_|LD_)" $name) (regexMatch "(?i)^(JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS|_JAVA_OPTIONS|JAVA_OPTS|JAVA_HOME|PATH|CLASSPATH)$" $name) -}}
{{- fail (printf "backend.extraEnv[%d].name %q is refused: it would override the chart-validated configuration (OWLMAST_*, SPRING_*, MANAGEMENT_*, SERVER_*, LOADER_*), the JVM options or the dynamic loader (every LD_* variable: LD_PRELOAD, LD_AUDIT, LD_LIBRARY_PATH and the rest)" $i $name) -}}
{{- end -}}
{{- if regexMatch "(?i)(password|secret|token|credential)" $name -}}
{{- fail (printf "backend.extraEnv[%d].name %q looks like a credential: credentials are existing Secret references, never plain values" $i $name) -}}
{{- end -}}
{{- end -}}
{{- /* the readiness indicator keeps a result for 5 s (IdentityDiscoveryHealthIndicator.CACHE_TTL), counted from the */ -}}
{{- /* START of its discovery request, however long the answer took: with a longer period, two consecutive probes */ -}}
{{- /* never read the result of the same request. A shorter or equal period would let them */ -}}
{{- if le (int $v.backend.probes.readiness.periodSeconds) 5 -}}
{{- fail (printf "backend.probes.readiness.periodSeconds=%v is refused: it must be greater than 5, the interval (counted from the start of the discovery request) for which the backend keeps its identity readiness result, so two consecutive probes never read the result of the same request" $v.backend.probes.readiness.periodSeconds) -}}
{{- end -}}
{{- if not $v.database.existingSecret -}}
{{- fail "database.existingSecret is required: an existing Secret with keys username and password for the application principal" -}}
{{- end -}}
{{- if $v.database.bundled -}}
{{- if not $v.postgresql.adminExistingSecret -}}
{{- fail "postgresql.adminExistingSecret is required when database.bundled=true" -}}
{{- end -}}
{{- else -}}
{{- if not $v.database.external.host -}}
{{- fail "database.bundled=false requires database.external.host (compatible PostgreSQL 18 with VectorChord installed)" -}}
{{- end -}}
{{- include "owl-mast.validateSslMode" (list "database.external" $v.database.external) -}}
{{- end -}}
{{- include "owl-mast.validateDatabaseName" (list "database.name" $v.database.name $v.database.bundled) -}}
{{- if $v.identity.bundled -}}
{{- include "owl-mast.validateDatabaseName" (list "identity.keycloak.database.name" $v.identity.keycloak.database.name $v.database.bundled) -}}
{{- if and (eq (include "owl-mast.keycloak.bootstrapAdminEnabled" .) "true") (not $v.identity.keycloak.bootstrapExistingSecret) -}}
{{- fail "identity.keycloak.bootstrapExistingSecret is required when identity.bundled=true and identity.keycloak.bootstrapAdmin.enabled=true" -}}
{{- end -}}
{{- if not $v.identity.keycloak.database.existingSecret -}}
{{- fail "identity.keycloak.database.existingSecret is required when identity.bundled=true" -}}
{{- end -}}
{{- if not $v.database.bundled -}}
{{- if not $v.identity.keycloak.database.external.host -}}
{{- fail "identity.bundled=true with database.bundled=false requires identity.keycloak.database.external.host" -}}
{{- end -}}
{{- include "owl-mast.validateSslMode" (list "identity.keycloak.database.external" $v.identity.keycloak.database.external) -}}
{{- end -}}
{{- if or (kindIs "invalid" $v.identity.realm) (and (kindIs "string" $v.identity.realm) (not $v.identity.realm)) -}}
{{- fail "identity.realm is required" -}}
{{- end -}}
{{- /* the schema's pattern, repeated so that --skip-schema-validation cannot open it: the realm is written into the */ -}}
{{- /* issuer, the back-channel address and the routed path /realms/<realm>/, where "master/" or "a/../master" would */ -}}
{{- /* name the master realm past the refusal below */ -}}
{{- /* only text is a realm name: every consumer formats the value as it is, so a number would be written as */ -}}
{{- /* %!s(int64=7) into the issuer and the routed path while its string form passed the checks below */ -}}
{{- if not (kindIs "string" $v.identity.realm) -}}
{{- fail (printf "identity.realm %v is not text (its kind is %s): a realm name is a string. Quote the value in the values file, or pass it with --set-string. The realm is written as it is into the issuer and into the routed path /realms/<identity.realm>/" $v.identity.realm (kindOf $v.identity.realm)) -}}
{{- end -}}
{{- $realm := $v.identity.realm -}}
{{- if not (regexMatch "^[a-zA-Z0-9][a-zA-Z0-9_-]*$" $realm) -}}
{{- fail (printf "identity.realm %q is not a realm name: letters, digits, '_' and '-', starting with a letter or digit. The realm is written as it is into the issuer and into the routed path /realms/<identity.realm>/" $realm) -}}
{{- end -}}
{{- /* Keycloak realm names are case-sensitive, so only "master" is that realm; any case is refused, which costs nothing */ -}}
{{- if eq (lower $realm) "master" -}}
{{- fail (printf "identity.realm=%q is refused: master is the bundled Keycloak's administration realm, where administrators sign in and obtain tokens. People sign in to Owl Mast in a realm of their own, and the Keycloak route publishes /realms/<identity.realm>/, which would publish the administrators' realm" $realm) -}}
{{- end -}}
{{- /* AC3: Keycloak keeps its own database on a shared server (the bundled instance, or the same external host and port) */ -}}
{{- /* textual comparison (case and a trailing dot ignored); aliases such as an IP address and a DNS name are not detected */ -}}
{{- $shared := or $v.database.bundled (and (eq (lower $v.database.external.host | trimSuffix ".") (lower $v.identity.keycloak.database.external.host | trimSuffix ".")) (eq (int $v.database.external.port) (int $v.identity.keycloak.database.external.port))) -}}
{{- if and $shared (eq $v.database.name $v.identity.keycloak.database.name) -}}
{{- fail (printf "identity.keycloak.database.name and database.name are both %q on the same PostgreSQL server: Keycloak and the application need separate databases (AC3)" $v.database.name) -}}
{{- end -}}
{{- /* D5: without the synthetic import the issuer realm exists only if an operator creates it */ -}}
{{- if and (not $v.identity.keycloak.importRealm) (not $v.identity.keycloak.realmManagedByOperator) -}}
{{- fail (printf "identity.keycloak.importRealm=false leaves the bundled Keycloak without the realm %q, so the backend never becomes ready; create the realm yourself and acknowledge it with identity.keycloak.realmManagedByOperator=true" $v.identity.realm) -}}
{{- end -}}
{{- /* trusted forwarding headers only where a named proxy is the sole admitted path besides the backend */ -}}
{{- if $v.identity.keycloak.proxyHeaders -}}
{{- $policy := $v.networkPolicy | default dict -}}
{{- if not (dig "enabled" true $policy) -}}
{{- fail (printf "identity.keycloak.proxyHeaders=%s needs networkPolicy.enabled=true: without the Keycloak NetworkPolicy any pod can reach :8080 and send forged X-Forwarded-*/Forwarded headers" $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- $peers := dig "keycloak" "extraFrom" list $policy -}}
{{- if not $peers -}}
{{- fail (printf "identity.keycloak.proxyHeaders=%s needs networkPolicy.keycloak.extraFrom to name the trusted proxy: with no entry the policy admits only the backend, whose direct requests are not proxied" $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- include "owl-mast.validateKeycloakPeers" (list $peers (printf "identity.keycloak.proxyHeaders=%s" $v.identity.keycloak.proxyHeaders) "send forged X-Forwarded-*/Forwarded headers") -}}
{{- end -}}
{{- else -}}
{{- $issuer := $v.identity.external.issuerUri -}}
{{- if not $issuer -}}
{{- fail "identity.bundled=false requires identity.external.issuerUri: disabling the bundled Keycloak never disables authentication" -}}
{{- end -}}
{{- /* host: what java.net.URI in the backend parses as a server host (IdentityProperties refuses a null host): a */ -}}
{{- /* dotted IPv4 address with octets 0-255, a single label, or labels whose LAST one starts with a letter; an */ -}}
{{- /* optional trailing dot. idp.123 or 1.2.3.999 parse with no host there and are refused here. An IPv6 literal */ -}}
{{- /* is not accepted by the chart. Then an optional port 1-65535. */ -}}
{{- $octet := "(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])" -}}
{{- $label := "[A-Za-z0-9]([-A-Za-z0-9]*[A-Za-z0-9])?" -}}
{{- $top := "[A-Za-z]([-A-Za-z0-9]*[A-Za-z0-9])?" -}}
{{- $host := printf "((%s\\.){3}%s|%s\\.?|(%s\\.)+%s\\.?)" $octet $octet $label $label $top -}}
{{- $authority := printf "%s(:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?" $host -}}
{{- /* path: RFC 3986 pchar segments without '@' (what java.net.URI in the backend accepts), percent escapes complete */ -}}
{{- $path := "(/([-A-Za-z0-9._~!$&'()*+,;=:]|%[0-9A-Fa-f]{2})*)*" -}}
{{- if regexMatch (printf "^https://%s%s$" $authority $path) $issuer -}}
{{- else if regexMatch (printf "^http://%s%s$" $authority $path) $issuer -}}
{{- if not $v.identity.external.allowInsecureIssuer -}}
{{- fail (printf "identity.external.issuerUri %q uses plaintext http: discovery and signing keys could be substituted in transit. Use https://, or set identity.external.allowInsecureIssuer=true to accept plaintext explicitly (disposable local fixtures only)" $issuer) -}}
{{- end -}}
{{- else -}}
{{- fail (printf "identity.external.issuerUri %q must be an absolute https:// URL with a host the backend can parse (a DNS name whose last label starts with a letter, a single label, or an IPv4 address with octets 0-255; no IPv6 literal), an optional port 1-65535, valid path characters and no query, fragment or user info" $issuer) -}}
{{- end -}}
{{- end -}}
{{- /* OM-02.01: sessions live in the backend's memory, so a second replica would not know them */ -}}
{{- if gt (int $v.backend.replicas) 1 -}}
{{- fail (printf "backend.replicas=%v is refused: it must be 0 or 1. Browser sessions are held in the backend's memory, so a second replica would answer a signed-in person as signed out, and two backends would run against one database (a durable session store is deferred work)" $v.backend.replicas) -}}
{{- end -}}
{{- /* OM-02.01: the one application origin (frontend at / and backend at /api): redirect URI, cookie */ -}}
{{- $appOrigin := include "owl-mast.routing.publicOrigin" . -}}
{{- if not $appOrigin -}}
{{- fail "routing.publicOrigin is required: the public origin people open Owl Mast on (for example https://owl-mast.example.com), which serves the frontend at / and the backend at /api. The sign-in redirect URI and the session cookie are bound to it" -}}
{{- end -}}
{{- include "owl-mast.validateOrigin" (list "routing.publicOrigin" $appOrigin "the application origin") -}}
{{- /* OM-02.01: the backend is a confidential OpenID Connect client; its secret is an existing Secret reference */ -}}
{{- if not (include "owl-mast.identity.clientSecret" .) -}}
{{- fail "identity.client.existingSecret is required: an existing Secret with the key client-secret, the secret of the backend's OpenID Connect client (the bundled Keycloak imports the client with it; an external issuer must hold the same value)" -}}
{{- end -}}
{{- if not (regexMatch "^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$" (include "owl-mast.identity.clientSecret" .)) -}}
{{- fail (printf "identity.client.existingSecret %q is not a valid Secret name" (include "owl-mast.identity.clientSecret" .)) -}}
{{- end -}}
{{- if not (regexMatch "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$" (include "owl-mast.identity.clientId" .)) -}}
{{- fail (printf "identity.client.id %q is refused: a client id of letters, digits, '.', '_' and '-', starting with a letter or digit, at most 128 characters" (include "owl-mast.identity.clientId" .)) -}}
{{- end -}}
{{- if $v.identity.bundled -}}
{{- /* OM-02.01: the browser reaches the bundled Keycloak on its own public origin, never on the cluster-local Service */ -}}
{{- $idOrigin := include "owl-mast.keycloak.publicOrigin" . -}}
{{- if not $idOrigin -}}
{{- fail "identity.keycloak.publicOrigin is required when identity.bundled=true: the public origin browsers reach the bundled Keycloak on (for example https://id.owl-mast.example.com). It is Keycloak's hostname and the issuer of every token; the cluster-local Service address is not reachable from a browser" -}}
{{- end -}}
{{- include "owl-mast.validateOrigin" (list "identity.keycloak.publicOrigin" $idOrigin "the bundled Keycloak's public origin") -}}
{{- if eq $idOrigin $appOrigin -}}
{{- fail (printf "identity.keycloak.publicOrigin and routing.publicOrigin are both %q: Keycloak is reached on its own origin, separate from the application's (the chart routes only / and /api on the application origin)" $appOrigin) -}}
{{- end -}}
{{- /* another port is not another host: Gateway and Ingress match the host without the port, and cookies are scoped */ -}}
{{- /* by host. The one exception is a loopback host that the chart renders no Keycloak route for (port-forwards). */ -}}
{{- $sameHost := eq (include "owl-mast.originHost" $idOrigin) (include "owl-mast.originHost" $appOrigin) -}}
{{- $idLoopback := regexMatch "^(localhost|127\\.0\\.0\\.1)$" (include "owl-mast.originHost" $idOrigin) -}}
{{- $idRouted := or (eq (include "owl-mast.keycloak.route.gateway.enabled" .) "true") (eq (include "owl-mast.keycloak.route.ingress.enabled" .) "true") -}}
{{- if and $sameHost (or $idRouted (not $idLoopback)) -}}
{{- fail (printf "identity.keycloak.publicOrigin %q and routing.publicOrigin %q name the same host %q: Keycloak needs a host of its own, not another port on the application's. Gateway and Ingress routes match the host without the port, so one hostname cannot keep Keycloak's paths apart from the application's, and cookies are scoped by host, so the session cookie and Keycloak's cookies would be sent to both. Only a loopback host (localhost, 127.0.0.1) may carry both on different ports, and only while the chart renders no Keycloak route" $idOrigin $appOrigin (include "owl-mast.originHost" $idOrigin)) -}}
{{- end -}}
{{- /* a loopback host is the machine the browser runs on. Beside an application that other machines open, every */ -}}
{{- /* browser would be sent to sign in on itself, and a loopback http origin would switch on the plaintext issuer */ -}}
{{- /* (OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER) for a public installation. No route is needed for that, so this runs */ -}}
{{- /* with or without one, and before the route refusal, whose advice to disable the route would lead here. */ -}}
{{- if and $idLoopback (not (regexMatch "^(localhost|127\\.0\\.0\\.1)$" (include "owl-mast.originHost" $appOrigin))) -}}
{{- fail (printf "identity.keycloak.publicOrigin %q is a loopback origin, but routing.publicOrigin %q is not: every browser that opens the application would be sent to sign in on its own machine, so people could sign in only from the machine that forwards the Keycloak port. A loopback Keycloak is only for an application that is port-forwarded too (routing.publicOrigin on localhost or 127.0.0.1). Set identity.keycloak.publicOrigin to the public origin browsers reach Keycloak on" $idOrigin $appOrigin) -}}
{{- end -}}
{{- /* with a loopback application as well, a route for the loopback host still reaches Keycloak from nowhere else */ -}}
{{- if and $idRouted $idLoopback -}}
{{- fail (printf "identity.keycloak.route.*.enabled=true cannot route the loopback identity.keycloak.publicOrigin %q: a loopback host is reached by port-forward, never through a proxy, so people could sign in only from the machine that forwards the port. Set identity.keycloak.publicOrigin to the public origin the route serves, or disable the Keycloak route" $idOrigin) -}}
{{- end -}}
{{- /* what is left on the application's host and port is an unrouted loopback pair that differs in the scheme alone, */ -}}
{{- /* or in the spelling of the loopback host: one local port forwards to one Service, whatever the scheme */ -}}
{{- if eq (include "owl-mast.originSocket" $idOrigin) (include "owl-mast.originSocket" $appOrigin) -}}
{{- fail (printf "identity.keycloak.publicOrigin %q and routing.publicOrigin %q name the same port %s of the loopback host: another scheme is not another address, and localhost and 127.0.0.1 are the same machine, so one port-forward would have to carry both Keycloak and the application. Give Keycloak a port of its own" $idOrigin $appOrigin (regexFind "[0-9]+$" (include "owl-mast.originSocket" $idOrigin))) -}}
{{- end -}}
{{- with (include "owl-mast.keycloak.adminOrigin" .) -}}
{{- include "owl-mast.validateOrigin" (list "identity.keycloak.adminOrigin" . "the address administrators open the Keycloak admin console on") -}}
{{- /* the admin console signs administrators in with the master realm's cookies, and cookies are scoped by host: it */ -}}
{{- /* is kept off the application's origin and host as the public origin is. These run without a rendered route, so */ -}}
{{- /* operator-owned routing is covered. A loopback host may carry both on different ports (port-forwards), with or */ -}}
{{- /* without a Keycloak route: that route serves the public origin's host and never /admin. */ -}}
{{- if eq . $appOrigin -}}
{{- fail (printf "identity.keycloak.adminOrigin and routing.publicOrigin are both %q: the admin console is reached on an address of its own, never on the application's origin" .) -}}
{{- end -}}
{{- $adminHost := include "owl-mast.originHost" . -}}
{{- if and (eq $adminHost (include "owl-mast.originHost" $appOrigin)) (not (regexMatch "^(localhost|127\\.0\\.0\\.1)$" $adminHost)) -}}
{{- fail (printf "identity.keycloak.adminOrigin %q and routing.publicOrigin %q name the same host %q: the admin console needs a host that is not the application's, not another port on it. Cookies are scoped by host, so the administrators' Keycloak cookies and the application's session cookie would be sent to both. Only a loopback host (localhost, 127.0.0.1) may carry both on different ports" . $appOrigin $adminHost) -}}
{{- end -}}
{{- /* as for the public origin: a loopback pair on one port is one listener, whatever the scheme or the spelling */ -}}
{{- if eq (include "owl-mast.originSocket" .) (include "owl-mast.originSocket" $appOrigin) -}}
{{- fail (printf "identity.keycloak.adminOrigin %q and routing.publicOrigin %q name the same port %s of the loopback host: another scheme is not another address, and localhost and 127.0.0.1 are the same machine, so one port-forward would have to carry both the admin console and the application. Give the admin console a port of its own" . $appOrigin (regexFind "[0-9]+$" (include "owl-mast.originSocket" .))) -}}
{{- end -}}
{{- /* on Keycloak's own port the console is Keycloak, so sharing the port is fine (the equal value, or the other */ -}}
{{- /* spelling of loopback, is the same port-forward). Another scheme there is not: one port takes one scheme, so */ -}}
{{- /* one of the two addresses would name a listener that cannot answer it. */ -}}
{{- if and (eq (include "owl-mast.originSocket" .) (include "owl-mast.originSocket" $idOrigin)) (ne (hasPrefix "https://" .) (hasPrefix "https://" $idOrigin)) -}}
{{- fail (printf "identity.keycloak.adminOrigin %q and identity.keycloak.publicOrigin %q name the same port %s of the loopback host under different schemes: one port takes one scheme, and localhost and 127.0.0.1 are the same machine, so one of the two addresses would name a listener that cannot answer it. Give identity.keycloak.adminOrigin the scheme of identity.keycloak.publicOrigin, or a port of its own" . $idOrigin (regexFind "[0-9]+$" (include "owl-mast.originSocket" .))) -}}
{{- end -}}
{{- end -}}
{{- $kcGateway := eq (include "owl-mast.keycloak.route.gateway.enabled" .) "true" -}}
{{- $kcIngress := eq (include "owl-mast.keycloak.route.ingress.enabled" .) "true" -}}
{{- if and $kcGateway $kcIngress -}}
{{- fail "identity.keycloak.route.gateway.enabled and identity.keycloak.route.ingress.enabled are both true: choose one routing mechanism for Keycloak (ambiguous exposure is refused)" -}}
{{- end -}}
{{- $idHost := include "owl-mast.originHost" $idOrigin -}}
{{- if $kcGateway -}}
{{- include "owl-mast.validateParentRefs" (list . "identity.keycloak.route.gateway" (dig "route" "gateway" "parentRefs" list $v.identity.keycloak)) -}}
{{- if regexMatch (include "owl-mast.ipv4Pattern" .) $idHost -}}
{{- fail (printf "identity.keycloak.route.gateway.enabled=true cannot route identity.keycloak.publicOrigin %q: its host is an IP address, and the Gateway API Hostname type forbids IP addresses" $idOrigin) -}}
{{- end -}}
{{- if not (.Capabilities.APIVersions.Has "gateway.networking.k8s.io/v1/HTTPRoute") -}}
{{- fail "identity.keycloak.route.gateway.enabled=true requires the Gateway API CRDs: the target does not serve the capability gateway.networking.k8s.io/v1/HTTPRoute (install the standard-channel CRDs first; for helm template pass --api-versions gateway.networking.k8s.io/v1/HTTPRoute)" -}}
{{- end -}}
{{- end -}}
{{- if $kcIngress -}}
{{- include "owl-mast.validateIngress" (list . "identity.keycloak.route.ingress" "the host of identity.keycloak.publicOrigin" $idHost (dig "route" "ingress" "tls" list $v.identity.keycloak)) -}}
{{- end -}}
{{- /* a rendered route is useless, or the policy is, unless the Keycloak NetworkPolicy admits exactly the proxy */ -}}
{{- $policy := $v.networkPolicy | default dict -}}
{{- if and (or $kcGateway $kcIngress) (dig "enabled" true $policy) (not $v.identity.keycloak.proxyHeaders) -}}
{{- $routeValue := ternary "identity.keycloak.route.gateway.enabled=true" "identity.keycloak.route.ingress.enabled=true" $kcGateway -}}
{{- $peers := dig "keycloak" "extraFrom" list $policy -}}
{{- if not $peers -}}
{{- fail (printf "%s needs networkPolicy.keycloak.extraFrom to name the proxy (the Gateway or Ingress data plane): with no entry the Keycloak NetworkPolicy admits only the backend, so the route would reach nothing. Name the proxy, or set networkPolicy.enabled=false" $routeValue) -}}
{{- end -}}
{{- include "owl-mast.validateKeycloakPeers" (list $peers $routeValue "reach Keycloak directly, past the proxy") -}}
{{- end -}}
{{- end -}}
{{- /* AC3: every principal has its own Secret */ -}}
{{- $secrets := list (list "database.existingSecret" $v.database.existingSecret) -}}
{{- $secrets = append $secrets (list "identity.client.existingSecret" (include "owl-mast.identity.clientSecret" .)) -}}
{{- if $v.database.bundled -}}{{- $secrets = append $secrets (list "postgresql.adminExistingSecret" $v.postgresql.adminExistingSecret) -}}{{- end -}}
{{- if $v.identity.bundled -}}
{{- $secrets = append $secrets (list "identity.keycloak.database.existingSecret" $v.identity.keycloak.database.existingSecret) -}}
{{- if eq (include "owl-mast.keycloak.bootstrapAdminEnabled" .) "true" -}}
{{- $secrets = append $secrets (list "identity.keycloak.bootstrapExistingSecret" $v.identity.keycloak.bootstrapExistingSecret) -}}
{{- end -}}
{{- end -}}
{{- range $i, $a := $secrets -}}
{{- range $j, $b := $secrets -}}
{{- if and (lt $i $j) (eq (index $a 1) (index $b 1)) -}}
{{- fail (printf "%s and %s both reference Secret %q: each principal needs its own Secret (AC3 separate principals)" (index $a 0) (index $b 0) (index $a 1)) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if $v.postgresql.provisionKeycloakDatabase -}}
{{- if not (and $v.database.bundled $v.identity.bundled) -}}
{{- fail "postgresql.provisionKeycloakDatabase=true applies only to a bundled PostgreSQL with a bundled Keycloak (database.bundled=true and identity.bundled=true)" -}}
{{- end -}}
{{- if .Release.IsInstall -}}
{{- if $v.postgresql.persistence.existingClaim -}}
{{- fail (printf "postgresql.provisionKeycloakDatabase=true is refused on install: the pre-upgrade hook needs the release's existing PostgreSQL. This install reuses the claim %q, whose initialised volume never reruns the first-initialisation script: if it was initialised with identity.bundled=false, install first, then provision Keycloak's database in the PostgreSQL pod (kubectl exec deploy/%s -- bash /owl-mast/provision-keycloak.sh; docs/installation.md), or install with the identity mode the volume was initialised with and enable the bundle with this value on helm upgrade" $v.postgresql.persistence.existingClaim (include "owl-mast.postgresql.fullname" .)) -}}
{{- end -}}
{{- fail "postgresql.provisionKeycloakDatabase=true is refused on install: a fresh install provisions Keycloak's database at first initialisation, and the pre-upgrade hook needs the release's existing PostgreSQL (use it on helm upgrade; helm template needs --is-upgrade)" -}}
{{- end -}}
{{- end -}}
{{- if $v.frontend.enabled -}}
{{- if and (not $v.frontend.image.tag) (not $v.frontend.image.digest) -}}
{{- fail "frontend.enabled=true requires frontend.image.tag or frontend.image.digest (artifact delivered by OM-01.04)" -}}
{{- end -}}
{{- include "owl-mast.validateImageTag" (list "frontend.image.tag" $v.frontend.image.tag) -}}
{{- end -}}
{{- if $v.routing.ingress.enabled -}}
{{- include "owl-mast.validateIngress" (list . "routing.ingress" "routing.ingress.host" $v.routing.ingress.host $v.routing.ingress.tls) -}}
{{- end -}}
{{- if and $v.routing.ingress.enabled $v.routing.gateway.enabled -}}
{{- fail "routing.ingress.enabled and routing.gateway.enabled are both true: choose one routing mechanism (ambiguous exposure is refused)" -}}
{{- end -}}
{{- if $v.routing.gateway.enabled -}}
{{- include "owl-mast.validateGateway" . -}}
{{- if not (.Capabilities.APIVersions.Has "gateway.networking.k8s.io/v1/HTTPRoute") -}}
{{- fail "routing.gateway.enabled=true requires the Gateway API CRDs: the target does not serve the capability gateway.networking.k8s.io/v1/HTTPRoute (install the standard-channel CRDs first; for helm template pass --api-versions gateway.networking.k8s.io/v1/HTTPRoute)" -}}
{{- end -}}
{{- end -}}
{{- range (list $v.routing.apiPathPrefix $v.routing.actuatorPathPrefix $v.routing.frontendPathPrefix) -}}
{{- include "owl-mast.validatePathPrefix" . -}}
{{- end -}}
{{- /* D2: the prefixes are pinned to what the artifacts serve (no rewrite is rendered), which also makes them disjoint */ -}}
{{- /* exactly /api: the same value is handed to the frontend shell, which calls <prefix>/compatibility, and the backend serves only /api/... */ -}}
{{- if ne $v.routing.apiPathPrefix "/api" -}}
{{- fail (printf "routing.apiPathPrefix %q is not served by the backend: it must be exactly /api (the chart renders no rewrite, and the frontend shell calls the backend below this prefix)" $v.routing.apiPathPrefix) -}}
{{- end -}}
{{- if not (regexMatch "^/actuator(/.*)?$" $v.routing.actuatorPathPrefix) -}}
{{- fail (printf "routing.actuatorPathPrefix %q is not served by the backend: it must be /actuator or a path below /actuator/ (the chart renders no rewrite)" $v.routing.actuatorPathPrefix) -}}
{{- end -}}
{{- if ne $v.routing.frontendPathPrefix "/" -}}
{{- fail (printf "routing.frontendPathPrefix %q is not served by the frontend shell: it must be / (the chart renders no rewrite)" $v.routing.frontendPathPrefix) -}}
{{- end -}}
{{- /* OM-02.01: the sign-in redirect URI and the session cookie are bound to routing.publicOrigin, so it must be a host this chart routes */ -}}
{{- $appHost := include "owl-mast.originHost" $appOrigin -}}
{{- if $v.routing.ingress.enabled -}}
{{- $routed := $v.routing.ingress.host | toString -}}
{{- if ne (include "owl-mast.routeCoversHost" (list $routed $appHost false)) "true" -}}
{{- fail (printf "routing.publicOrigin %q names the host %q, which routing.ingress.host %q does not route: the sign-in redirect URI and the session cookie would be bound to an origin that never reaches Owl Mast. Set routing.publicOrigin to the origin of the routed host, or route its host" $appOrigin $appHost $routed) -}}
{{- end -}}
{{- end -}}
{{- if and $v.routing.gateway.enabled $v.routing.gateway.hostnames -}}
{{- $covered := false -}}
{{- range $v.routing.gateway.hostnames -}}
{{- if eq (include "owl-mast.routeCoversHost" (list . $appHost true)) "true" -}}{{- $covered = true -}}{{- end -}}
{{- end -}}
{{- if not $covered -}}
{{- fail (printf "routing.publicOrigin %q names the host %q, which is not among routing.gateway.hostnames (%s): the sign-in redirect URI and the session cookie would be bound to an origin that never reaches Owl Mast. Set routing.publicOrigin to the origin of a routed hostname, or add its host to routing.gateway.hostnames" $appOrigin $appHost (join ", " $v.routing.gateway.hostnames)) -}}
{{- end -}}
{{- end -}}
{{- /* OM-02.01: the application's route must not answer on a host of the bundled Keycloak: the public origin's, or the */ -}}
{{- /* admin console's. It would serve the application on that origin for every path Keycloak's route does not take, */ -}}
{{- /* same-origin with Keycloak's session cookies. A loopback host is reached by port-forward and never routed */ -}}
{{- /* (refused above for the public origin), so no route receives it. A wildcard is read as covering every depth */ -}}
{{- /* below it for both mechanisms: the Ingress API says one label, but the chart cannot tell that the controller */ -}}
{{- /* holds to it (an nginx server_name wildcard, for one, matches deeper names), and this refusal fails closed. */ -}}
{{- if $v.identity.bundled -}}
{{- $consequence := "would answer on Keycloak's host as well: the application would be served on Keycloak's origin for every path outside Keycloak's own, where its pages run same-origin with Keycloak's session cookies. Route the application on hosts that leave Keycloak's out, or give Keycloak a host outside them" -}}
{{- range (list (list "identity.keycloak.publicOrigin" (include "owl-mast.keycloak.publicOrigin" .)) (list "identity.keycloak.adminOrigin" (include "owl-mast.keycloak.adminOrigin" .))) -}}
{{- $idPath := index . 0 -}}
{{- $idOrigin := index . 1 -}}
{{- $idHost := include "owl-mast.originHost" $idOrigin -}}
{{- if and $idOrigin (not (regexMatch "^(localhost|127\\.0\\.0\\.1)$" $idHost)) -}}
{{- if and $v.routing.ingress.enabled (eq (include "owl-mast.routeCoversHost" (list $v.routing.ingress.host $idHost true)) "true") -}}
{{- fail (printf "routing.ingress.host %q covers the host %q of %s %q: the application's Ingress %s" ($v.routing.ingress.host | toString) $idHost $idPath $idOrigin $consequence) -}}
{{- end -}}
{{- if $v.routing.gateway.enabled -}}
{{- range $i, $routed := $v.routing.gateway.hostnames -}}
{{- if eq (include "owl-mast.routeCoversHost" (list $routed $idHost true)) "true" -}}
{{- fail (printf "routing.gateway.hostnames[%d] %q covers the host %q of %s %q: the application's HTTPRoute %s" $i ($routed | toString) $idHost $idPath $idOrigin $consequence) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- /* without hostnames the application's HTTPRoute takes every hostname of its listener; beside a Keycloak HTTPRoute */ -}}
{{- /* that includes Keycloak's whenever both attach to one listener, which parentRefs alone cannot rule out. Where the */ -}}
{{- /* chart renders no Keycloak HTTPRoute it cannot tell what else the listener serves: that stays the operator's. */ -}}
{{- if and $v.routing.gateway.enabled (not $v.routing.gateway.hostnames) (eq (include "owl-mast.keycloak.route.gateway.enabled" .) "true") -}}
{{- fail (printf "routing.gateway.allowAllListenerHostnames=true is refused while identity.keycloak.route.gateway.enabled=true: an HTTPRoute without hostnames attaches to every hostname of its listener, so on a listener the two routes share the application would answer on Keycloak's host %q as well, same-origin with Keycloak's session cookies. List the application's hostnames in routing.gateway.hostnames" (include "owl-mast.originHost" (include "owl-mast.keycloak.publicOrigin" .))) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Whether a routed host (an Ingress host or an HTTPRoute hostname) answers for a host: the same name, or a
wildcard over it. By the APIs an Ingress wildcard covers exactly one label and an HTTPRoute wildcard one or
more; a caller that refuses on coverage passes true for both, because it cannot rely on the controller's reading.
routeCoversHost (list "<routed host>" "<host>" <true when the wildcard covers more than one label>) renders
"true" or nothing.
*/}}
{{- define "owl-mast.routeCoversHost" -}}
{{- $routed := index . 0 | toString -}}
{{- $host := index . 1 | toString -}}
{{- $suffix := trimPrefix "*" $routed -}}
{{- if eq $routed $host -}}
true
{{- else if and (hasPrefix "*." $routed) (hasSuffix $suffix $host) -}}
{{- $label := trimSuffix $suffix $host -}}
{{- if and (ne $label "") (or (index . 2) (not (contains "." $label))) -}}true{{- end -}}
{{- end -}}
{{- end -}}

{{/*
networkPolicy.keycloak.extraFrom must NAME the proxy in front of the bundled Keycloak whenever something relies
on it: trusted forwarding headers (identity.keycloak.proxyHeaders) or a rendered route. validateKeycloakPeers
(list <peers> "<the value that needs them>" "<what an unnamed peer could do>")
*/}}
{{- define "owl-mast.validateKeycloakPeers" -}}
{{- $peers := index . 0 -}}
{{- $reason := index . 1 -}}
{{- $risk := index . 2 -}}
{{- /* a peer must NAME the proxy: an empty peer or an empty selector admits every pod, and so does a selector made */ -}}
{{- /* only of Exists, NotIn or DoesNotExist terms (key Exists on a label every namespace carries is {} spelled */ -}}
{{- /* differently). An ipBlock must be a narrow range: /0 is every address, and two /1 blocks are too. */ -}}
{{- range $i, $peer := $peers -}}
{{- if not $peer -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d] is empty: with %s every entry must name the trusted proxy (podSelector, namespaceSelector or ipBlock), because an empty peer admits every pod" $i $reason) -}}
{{- end -}}
{{- range $key := list "podSelector" "namespaceSelector" -}}
{{- if hasKey $peer $key -}}
{{- $selector := get $peer $key | default dict -}}
{{- if and (not (get $selector "matchLabels")) (not (get $selector "matchExpressions")) -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].%s is empty: with %s it must select the trusted proxy by matchLabels or matchExpressions, because an empty selector admits every %s. Every one of them could %s" $i $key $reason (ternary "pod of the release namespace" "pod of every namespace" (eq $key "podSelector")) $risk) -}}
{{- end -}}
{{- $names := not (empty (get $selector "matchLabels")) -}}
{{- range $expr := (get $selector "matchExpressions" | default list) -}}
{{- if kindIs "map" $expr -}}
{{- if and (eq (toString (get $expr "operator")) "In") (get $expr "values") -}}{{- $names = true -}}{{- end -}}
{{- end -}}
{{- end -}}
{{- if not $names -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].%s names nothing: with %s it must select the trusted proxy by a matchLabels entry or a matchExpressions term with operator In. Exists, NotIn and DoesNotExist terms alone can match every %s (key Exists on a label all of them carry is an empty selector spelled differently). Every one of them could %s" $i $key $reason (ternary "pod of the release namespace" "namespace" (eq $key "podSelector")) $risk) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if hasKey $peer "ipBlock" -}}
{{- $cidr := toString (get (get $peer "ipBlock" | default dict) "cidr") -}}
{{- $minPrefix := ternary 32 8 (contains ":" $cidr) -}}
{{- if not (regexMatch "^[0-9A-Fa-f:.]+/[0-9]{1,3}$" $cidr) -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with %s it must be the proxy's own address range in CIDR form (address/prefix)" $i $cidr $reason) -}}
{{- end -}}
{{- if lt (int (regexFind "[0-9]+$" $cidr)) $minPrefix -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with %s it must be the proxy's own address range, with a prefix of at least /%d (/8 for IPv4, /32 for IPv6). A wider block, alone (/0) or combined with another (0.0.0.0/1 and 128.0.0.0/1), admits every address" $i $cidr $reason $minPrefix) -}}
{{- end -}}
{{- /* An IPv6 range is read group by group. One that embeds an IPv4 address is refused whatever its prefix: Go's */ -}}
{{- /* net.ParseCIDR reads ::ffff:0.0.0.0/96 as 0.0.0.0/0, so the IPv6 floor would admit every IPv4 address. */ -}}
{{- if contains ":" $cidr -}}
{{- $address := lower (regexReplaceAll "/[0-9]+$" $cidr "") -}}
{{- if contains "." $address -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with %s an IPv6 range must not embed a dotted IPv4 address. An IPv4-mapped range such as ::ffff:0.0.0.0/96 is read as the IPv4 range 0.0.0.0/0, which admits every address; write the proxy's IPv4 range itself (for example 10.1.2.0/24)" $i $cidr $reason) -}}
{{- end -}}
{{- $halves := splitList "::" $address -}}
{{- $groups := compact (splitList ":" (index $halves 0)) -}}
{{- $wellFormed := and (le (len $halves) 2) (not (regexMatch "(^:[^:]|[^:]:$|:::)" $address)) -}}
{{- if eq (len $halves) 2 -}}
{{- $tail := compact (splitList ":" (index $halves 1)) -}}
{{- if gt (add (len $groups) (len $tail)) 7 -}}{{- $wellFormed = false -}}{{- end -}}
{{- range until (int (max 0 (sub 8 (add (len $groups) (len $tail))))) -}}{{- $groups = append $groups "0" -}}{{- end -}}
{{- $groups = concat $groups $tail -}}
{{- end -}}
{{- if ne (len $groups) 8 -}}{{- $wellFormed = false -}}{{- end -}}
{{- $normal := list -}}
{{- range $group := $groups -}}
{{- if not (regexMatch "^[0-9a-f]{1,4}$" $group) -}}{{- $wellFormed = false -}}{{- end -}}
{{- $normal = append $normal (regexReplaceAll "^0+([0-9a-f])" $group "${1}") -}}
{{- end -}}
{{- if not $wellFormed -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with %s it must be the proxy's own address range in CIDR form (address/prefix), and this is not an IPv6 address of eight hexadecimal groups (one \"::\" may stand for the zero groups)" $i $cidr $reason) -}}
{{- end -}}
{{- if regexMatch "^0:0:0:0:0:(ffff|0):" (join ":" $normal) -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with %s an IPv6 range must not be an IPv4-mapped (::ffff:0:0/96) or IPv4-compatible (::/96) one. An IPv4-mapped range is read as an IPv4 range (::ffff:0:0/96 is 0.0.0.0/0), which admits every address; write the proxy's IPv4 range itself (for example 10.1.2.0/24)" $i $cidr $reason) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* D1: external PostgreSQL transport. validateSslMode (list "<values path>" <external values>) */}}
{{- define "owl-mast.validateSslMode" -}}
{{- $path := index . 0 -}}
{{- $ext := index . 1 -}}
{{- if has $ext.sslMode (list "verify-ca" "verify-full") -}}
{{- fail (printf "%s.sslMode=%s is refused: it needs a CA trust the chart does not mount yet (deferred, see docs/installation.md), so the backend and Keycloak would render and then fail every database connection. Use require, which encrypts the connection but does not authenticate the server" $path $ext.sslMode) -}}
{{- end -}}
{{- if not (has $ext.sslMode (list "disable" "allow" "prefer" "require")) -}}
{{- fail (printf "%s.sslMode must be one of disable, allow, prefer, require" $path) -}}
{{- end -}}
{{- if and (has $ext.sslMode (list "disable" "allow" "prefer")) (not $ext.allowInsecureTransport) -}}
{{- fail (printf "%s.sslMode=%s can send database credentials in plaintext: use require, or set %s.allowInsecureTransport=true to accept plaintext explicitly" $path $ext.sslMode $path) -}}
{{- end -}}
{{- end -}}

{{/*
Ingress host and TLS: the host is a lowercase DNS name (optional leading '*.'), and a TLS block must cover it.
validateIngress (list <root> "<values path of the ingress>" "<values path of the host>" <host> <tls entries>)
*/}}
{{- define "owl-mast.validateIngress" -}}
{{- $root := index . 0 -}}
{{- $path := index . 1 -}}
{{- $hostPath := index . 2 -}}
{{- $in := dict "host" (index . 3) "tls" (index . 4) -}}
{{- $hostPattern := "^(\\*\\.)?[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)*$" -}}
{{- $ipPattern := include "owl-mast.ipv4Pattern" $root -}}
{{- if not $in.host -}}
{{- fail (printf "%s.enabled=true requires %s" $path $hostPath) -}}
{{- end -}}
{{- if or (gt (len $in.host) 253) (not (regexMatch $hostPattern $in.host)) -}}
{{- fail (printf "%s %q is not a valid Ingress host: lowercase DNS name with labels of at most 63 characters, optional leading wildcard label '*.', no scheme, port or path" $hostPath $in.host) -}}
{{- end -}}
{{- if regexMatch $ipPattern $in.host -}}
{{- fail (printf "%s %q is an IP address: the Kubernetes API server rejects an IP address as an Ingress host (it must be a DNS name)" $hostPath $in.host) -}}
{{- end -}}
{{- if $in.tls -}}
{{- $covered := false -}}
{{- range $i, $t := $in.tls -}}
{{- if not $t.hosts -}}
{{- fail (printf "%s.tls[%d].hosts must list the host it secures" $path $i) -}}
{{- end -}}
{{- if not $t.secretName -}}
{{- fail (printf "%s.tls[%d].secretName is required: a TLS entry without a Secret makes the controller serve its default certificate" $path $i) -}}
{{- end -}}
{{- range $t.hosts -}}
{{- if or (gt (len .) 253) (not (regexMatch $hostPattern .)) -}}
{{- fail (printf "%s.tls[%d].hosts entry %q is not a valid DNS name" $path $i .) -}}
{{- end -}}
{{- if regexMatch $ipPattern . -}}
{{- fail (printf "%s.tls[%d].hosts entry %q is an IP address: the Kubernetes API server rejects an IP address as an Ingress TLS host" $path $i .) -}}
{{- end -}}
{{- if eq . $in.host -}}{{- $covered = true -}}{{- end -}}
{{- if and (hasPrefix "*." .) (not (hasPrefix "*." $in.host)) (contains "." $in.host) -}}
{{- if eq (trimPrefix "*" .) (printf ".%s" (regexReplaceAll "^[^.]+\\." $in.host "")) -}}{{- $covered = true -}}{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if not $covered -}}
{{- fail (printf "%s.tls does not cover %s %q: the controller would serve its default certificate" $path $hostPath $in.host) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Gateway API input validation against the stable HTTPRoute v1 contract (Gateway API v1.4.0 standard CRD):
ordinary schema constraints (patterns, lengths, cardinalities) and the CEL rules that apply to the inputs this
chart exposes. Rendering is refused with the offending value named; nothing is coerced. This is manifest
validation, not controller acceptance: listener permission, hostname intersection and route status are decided
by the operator's Gateway.
*/}}
{{- define "owl-mast.validateGateway" -}}
{{- $gw := .Values.routing.gateway -}}
{{- include "owl-mast.validateParentRefs" (list . "routing.gateway" $gw.parentRefs) -}}
{{- if and (not $gw.hostnames) (not (dig "allowAllListenerHostnames" false $gw)) -}}
{{- fail "routing.gateway.hostnames is empty: an HTTPRoute without hostnames attaches to every hostname of the referenced listener(s), including other tenants' on a shared Gateway. List the hostnames, or set routing.gateway.allowAllListenerHostnames=true to accept every listener hostname explicitly" -}}
{{- end -}}
{{- if gt (len $gw.hostnames) 16 -}}
{{- fail (printf "routing.gateway.hostnames has %d entries; HTTPRoute allows at most 16" (len $gw.hostnames)) -}}
{{- end -}}
{{- range $i, $host := $gw.hostnames -}}
{{- if or (eq $host "") (gt (len $host) 253) (not (regexMatch "^(\\*\\.)?[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" $host)) -}}
{{- fail (printf "routing.gateway.hostnames[%d] %q is not a valid HTTPRoute hostname: lowercase DNS name, optional leading wildcard label '*.', no scheme, port or path, at most 253 characters" $i $host) -}}
{{- end -}}
{{- if regexMatch (include "owl-mast.ipv4Pattern" $) $host -}}
{{- fail (printf "routing.gateway.hostnames[%d] %q is an IP address: the Gateway API Hostname type forbids IP addresses, and no conformant controller matches one" $i $host) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* HTTPRoute parentRefs of one route. validateParentRefs (list <root> "<values path of the gateway block>" <parentRefs>) */}}
{{- define "owl-mast.validateParentRefs" -}}
{{- $root := index . 0 -}}
{{- $path := index . 1 -}}
{{- $refs := index . 2 -}}
{{- if not $refs -}}
{{- fail (printf "%s.enabled=true requires at least one %s.parentRefs entry naming the operator-supplied Gateway" $path $path) -}}
{{- end -}}
{{- if gt (len $refs) 32 -}}
{{- fail (printf "%s.parentRefs has %d entries; HTTPRoute allows at most 32" $path (len $refs)) -}}
{{- end -}}
{{- $seen := dict -}}
{{- range $i, $ref := $refs -}}
{{- if not $ref.name -}}
{{- fail (printf "%s.parentRefs[%d] needs a name" $path $i) -}}
{{- end -}}
{{- if gt (len $ref.name) 253 -}}
{{- fail (printf "%s.parentRefs[%d].name exceeds 253 characters" $path $i) -}}
{{- end -}}
{{- if $ref.namespace -}}
{{- if or (gt (len $ref.namespace) 63) (not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$" $ref.namespace)) -}}
{{- fail (printf "%s.parentRefs[%d].namespace %q is not a valid namespace name (lowercase RFC 1123 label, at most 63 characters)" $path $i $ref.namespace) -}}
{{- end -}}
{{- end -}}
{{- if $ref.sectionName -}}
{{- if or (gt (len $ref.sectionName) 253) (not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" $ref.sectionName)) -}}
{{- fail (printf "%s.parentRefs[%d].sectionName %q is not a valid listener section name (lowercase RFC 1123 subdomain, at most 253 characters)" $path $i $ref.sectionName) -}}
{{- end -}}
{{- end -}}
{{- if hasKey $ref "port" -}}
{{- if or (lt (int $ref.port) 1) (gt (int $ref.port) 65535) -}}
{{- fail (printf "%s.parentRefs[%d].port %v is outside 1-65535" $path $i $ref.port) -}}
{{- end -}}
{{- end -}}
{{- /* CEL: references to the same parent must all carry a sectionName, and those must be unique */ -}}
{{- /* an omitted namespace is the route's own (the release namespace): both spellings name the same Gateway */ -}}
{{- $parent := printf "%s/%s" (default $root.Release.Namespace $ref.namespace) $ref.name -}}
{{- $section := default "" $ref.sectionName -}}
{{- if hasKey $seen $parent -}}
{{- $prev := index $seen $parent -}}
{{- if or (eq $section "") (eq $prev "") -}}
{{- fail (printf "%s.parentRefs: Gateway %q is referenced more than once; every reference to the same parent must set a distinct sectionName" $path $parent) -}}
{{- end -}}
{{- if has $section (splitList "," $prev) -}}
{{- fail (printf "%s.parentRefs: Gateway %q is referenced twice with sectionName %q; sectionName must be unique per parent" $path $parent $section) -}}
{{- end -}}
{{- $_ := set $seen $parent (printf "%s,%s" $prev $section) -}}
{{- else -}}
{{- $_ := set $seen $parent $section -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* HTTPRoute path match value (type PathPrefix): absolute, no '//', '/./', '/../', '%2f', '%2F' or '#', at most 1024 characters. */}}
{{- define "owl-mast.validatePathPrefix" -}}
{{- $path := . -}}
{{- if or (not (hasPrefix "/" $path)) (gt (len $path) 1024) (contains "//" $path) (contains "/./" $path) (contains "/../" $path) (contains "%2f" $path) (contains "%2F" $path) (contains "#" $path) (hasSuffix "/." $path) (hasSuffix "/.." $path) (not (regexMatch "^(?:[-A-Za-z0-9/._~!$&'()*+,;=:@]|[%][0-9a-fA-F]{2})+$" $path)) -}}
{{- fail (printf "routing path prefix %q is not a valid HTTPRoute PathPrefix value: it must start with '/', be at most 1024 characters, use only valid path characters or %%XX escapes, and contain none of '//', '/./', '/../', '%%2f', '%%2F' or '#'" $path) -}}
{{- end -}}
{{- end -}}

{{/* An image tag as registries accept it; a blank or whitespace-only tag would render "<repository>: ". validateImageTag (list "<values path>" <tag>) */}}
{{- define "owl-mast.validateImageTag" -}}
{{- $tag := index . 1 | default "" | toString -}}
{{- if and $tag (not (regexMatch "^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$" $tag)) -}}
{{- fail (printf "%s %q is not a valid image tag: letters, digits, '_', '.' and '-', not starting with '.' or '-', at most 128 characters (no whitespace)" (index . 0) $tag) -}}
{{- end -}}
{{- end -}}

{{/*
backend.javaToolOptions: whitespace-separated options, each one of the heap and stack sizes or a NAMED -XX
option with the value form the JVM takes: size options a whole number with an optional k/m/g, percentage options
a number without a suffix, count options a whole number (the JVM exits with "Improperly specified VM option" on
-XX:MaxRAMPercentage=75m or -XX:ParallelGCThreads=1.5g). The same expression is the schema's pattern
(deploy/tests pins that they are identical).
*/}}
{{- define "owl-mast.javaToolOptionsPattern" -}}
^\s*(-(Xm[sxn][0-9]+[kKmMgG]?|Xss[0-9]+[kKmMgG]?|XX:(MaxRAM|MaxMetaspaceSize|MetaspaceSize|MaxDirectMemorySize|ReservedCodeCacheSize|G1HeapRegionSize|SoftMaxHeapSize|MaxNewSize|NewSize)=[0-9]+[kKmMgG]?|XX:(MaxRAMPercentage|InitialRAMPercentage|MinRAMPercentage)=[0-9]+(\.[0-9]+)?|XX:(ActiveProcessorCount|MaxHeapFreeRatio|MinHeapFreeRatio|MaxGCPauseMillis|ParallelGCThreads|ConcGCThreads|InitiatingHeapOccupancyPercent|NewRatio|SurvivorRatio|TieredStopAtLevel)=[0-9]+|XX:[+-](UseG1GC|UseZGC|UseSerialGC|UseParallelGC|UseShenandoahGC|UseContainerSupport|UseStringDeduplication|AlwaysPreTouch|ExitOnOutOfMemoryError|UseCompressedOops|UseCompressedClassPointers|TieredCompilation|DisableExplicitGC|UseNUMA))(\s+|$))*$
{{- end -}}

{{/*
0.2.0 value read with its default, so a release upgraded with --reuse-values (0.1.0 values, no new keys) renders.
Only true and false are accepted: with --skip-schema-validation a string such as "False" would match neither
branch of the callers, and Keycloak would start without the bootstrap admin and without any warning.
*/}}
{{- define "owl-mast.keycloak.bootstrapAdminEnabled" -}}
{{- $enabled := dig "bootstrapAdmin" "enabled" true .Values.identity.keycloak | toString -}}
{{- if not (has $enabled (list "true" "false")) -}}
{{- fail (printf "identity.keycloak.bootstrapAdmin.enabled %q must be a boolean: true or false" $enabled) -}}
{{- end -}}
{{- $enabled -}}
{{- end -}}

{{/*
A dotted IPv4 address as the Kubernetes API server reads one (octets 0-255, leading zeros allowed): the hosts it
rejects as "an IP address, not a DNS name". 999.1.1.1 or 256.0.0.1 are DNS names made of numeric labels and are
not matched. The same expression is the schema's (deploy/tests pins that they are identical).
*/}}
{{- define "owl-mast.ipv4Pattern" -}}
^(0*(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}0*(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$
{{- end -}}
