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

{{/* Issuer the backend trusts: bundled Keycloak realm or the supplied external issuer. */}}
{{- define "owl-mast.identity.issuerUri" -}}
{{- if .Values.identity.bundled -}}
{{- printf "%s/realms/%s" (include "owl-mast.keycloak.baseUrl" .) .Values.identity.realm -}}
{{- else -}}
{{- .Values.identity.external.issuerUri -}}
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
{{- if not $v.identity.realm -}}
{{- fail "identity.realm is required" -}}
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
{{- /* a peer must NAME the proxy: an empty peer or an empty selector admits every pod, and so does a selector made */ -}}
{{- /* only of Exists, NotIn or DoesNotExist terms (key Exists on a label every namespace carries is {} spelled */ -}}
{{- /* differently). An ipBlock must be a narrow range: /0 is every address, and two /1 blocks are too. */ -}}
{{- range $i, $peer := $peers -}}
{{- if not $peer -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d] is empty: with identity.keycloak.proxyHeaders=%s every entry must name the trusted proxy (podSelector, namespaceSelector or ipBlock), because an empty peer admits every pod" $i $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- range $key := list "podSelector" "namespaceSelector" -}}
{{- if hasKey $peer $key -}}
{{- $selector := get $peer $key | default dict -}}
{{- if and (not (get $selector "matchLabels")) (not (get $selector "matchExpressions")) -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].%s is empty: with identity.keycloak.proxyHeaders=%s it must select the trusted proxy by matchLabels or matchExpressions, because an empty selector admits every %s, each able to send forged X-Forwarded-*/Forwarded headers" $i $key $v.identity.keycloak.proxyHeaders (ternary "pod of the release namespace" "pod of every namespace" (eq $key "podSelector"))) -}}
{{- end -}}
{{- $names := not (empty (get $selector "matchLabels")) -}}
{{- range $expr := (get $selector "matchExpressions" | default list) -}}
{{- if kindIs "map" $expr -}}
{{- if and (eq (toString (get $expr "operator")) "In") (get $expr "values") -}}{{- $names = true -}}{{- end -}}
{{- end -}}
{{- end -}}
{{- if not $names -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].%s names nothing: with identity.keycloak.proxyHeaders=%s it must select the trusted proxy by a matchLabels entry or a matchExpressions term with operator In. Exists, NotIn and DoesNotExist terms alone can match every %s (key Exists on a label all of them carry is an empty selector spelled differently), each able to send forged X-Forwarded-*/Forwarded headers" $i $key $v.identity.keycloak.proxyHeaders (ternary "pod of the release namespace" "namespace" (eq $key "podSelector"))) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if hasKey $peer "ipBlock" -}}
{{- $cidr := toString (get (get $peer "ipBlock" | default dict) "cidr") -}}
{{- $minPrefix := ternary 32 8 (contains ":" $cidr) -}}
{{- if not (regexMatch "^[0-9A-Fa-f:.]+/[0-9]{1,3}$" $cidr) -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with identity.keycloak.proxyHeaders=%s it must be the proxy's own address range in CIDR form (address/prefix)" $i $cidr $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- if lt (int (regexFind "[0-9]+$" $cidr)) $minPrefix -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with identity.keycloak.proxyHeaders=%s it must be the proxy's own address range, with a prefix of at least /%d (/8 for IPv4, /32 for IPv6). A wider block, alone (/0) or combined with another (0.0.0.0/1 and 128.0.0.0/1), admits every address" $i $cidr $v.identity.keycloak.proxyHeaders $minPrefix) -}}
{{- end -}}
{{- /* An IPv6 range is read group by group. One that embeds an IPv4 address is refused whatever its prefix: Go's */ -}}
{{- /* net.ParseCIDR reads ::ffff:0.0.0.0/96 as 0.0.0.0/0, so the IPv6 floor would admit every IPv4 address. */ -}}
{{- if contains ":" $cidr -}}
{{- $address := lower (regexReplaceAll "/[0-9]+$" $cidr "") -}}
{{- if contains "." $address -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with identity.keycloak.proxyHeaders=%s an IPv6 range must not embed a dotted IPv4 address. An IPv4-mapped range such as ::ffff:0.0.0.0/96 is read as the IPv4 range 0.0.0.0/0, which admits every address; write the proxy's IPv4 range itself (for example 10.1.2.0/24)" $i $cidr $v.identity.keycloak.proxyHeaders) -}}
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
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with identity.keycloak.proxyHeaders=%s it must be the proxy's own address range in CIDR form (address/prefix), and this is not an IPv6 address of eight hexadecimal groups (one \"::\" may stand for the zero groups)" $i $cidr $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- if regexMatch "^0:0:0:0:0:(ffff|0):" (join ":" $normal) -}}
{{- fail (printf "networkPolicy.keycloak.extraFrom[%d].ipBlock.cidr %q is refused: with identity.keycloak.proxyHeaders=%s an IPv6 range must not be an IPv4-mapped (::ffff:0:0/96) or IPv4-compatible (::/96) one. An IPv4-mapped range is read as an IPv4 range (::ffff:0:0/96 is 0.0.0.0/0), which admits every address; write the proxy's IPv4 range itself (for example 10.1.2.0/24)" $i $cidr $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
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
{{- /* AC3: every principal has its own Secret */ -}}
{{- $secrets := list (list "database.existingSecret" $v.database.existingSecret) -}}
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
{{- include "owl-mast.validateIngress" . -}}
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

{{/* Ingress host and TLS: the host is a lowercase DNS name (optional leading '*.'), and a TLS block must cover it. */}}
{{- define "owl-mast.validateIngress" -}}
{{- $in := .Values.routing.ingress -}}
{{- $hostPattern := "^(\\*\\.)?[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)*$" -}}
{{- $ipPattern := include "owl-mast.ipv4Pattern" . -}}
{{- if not $in.host -}}
{{- fail "routing.ingress.enabled=true requires routing.ingress.host" -}}
{{- end -}}
{{- if or (gt (len $in.host) 253) (not (regexMatch $hostPattern $in.host)) -}}
{{- fail (printf "routing.ingress.host %q is not a valid Ingress host: lowercase DNS name with labels of at most 63 characters, optional leading wildcard label '*.', no scheme, port or path" $in.host) -}}
{{- end -}}
{{- if regexMatch $ipPattern $in.host -}}
{{- fail (printf "routing.ingress.host %q is an IP address: the Kubernetes API server rejects an IP address as an Ingress host (it must be a DNS name)" $in.host) -}}
{{- end -}}
{{- if $in.tls -}}
{{- $covered := false -}}
{{- range $i, $t := $in.tls -}}
{{- if not $t.hosts -}}
{{- fail (printf "routing.ingress.tls[%d].hosts must list the host it secures" $i) -}}
{{- end -}}
{{- if not $t.secretName -}}
{{- fail (printf "routing.ingress.tls[%d].secretName is required: a TLS entry without a Secret makes the controller serve its default certificate" $i) -}}
{{- end -}}
{{- range $t.hosts -}}
{{- if or (gt (len .) 253) (not (regexMatch $hostPattern .)) -}}
{{- fail (printf "routing.ingress.tls[%d].hosts entry %q is not a valid DNS name" $i .) -}}
{{- end -}}
{{- if regexMatch $ipPattern . -}}
{{- fail (printf "routing.ingress.tls[%d].hosts entry %q is an IP address: the Kubernetes API server rejects an IP address as an Ingress TLS host" $i .) -}}
{{- end -}}
{{- if eq . $in.host -}}{{- $covered = true -}}{{- end -}}
{{- if and (hasPrefix "*." .) (not (hasPrefix "*." $in.host)) (contains "." $in.host) -}}
{{- if eq (trimPrefix "*" .) (printf ".%s" (regexReplaceAll "^[^.]+\\." $in.host "")) -}}{{- $covered = true -}}{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if not $covered -}}
{{- fail (printf "routing.ingress.tls does not cover routing.ingress.host %q: the controller would serve its default certificate" $in.host) -}}
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
{{- if not $gw.parentRefs -}}
{{- fail "routing.gateway.enabled=true requires at least one routing.gateway.parentRefs entry naming the operator-supplied Gateway" -}}
{{- end -}}
{{- if gt (len $gw.parentRefs) 32 -}}
{{- fail (printf "routing.gateway.parentRefs has %d entries; HTTPRoute allows at most 32" (len $gw.parentRefs)) -}}
{{- end -}}
{{- $seen := dict -}}
{{- range $i, $ref := $gw.parentRefs -}}
{{- if not $ref.name -}}
{{- fail (printf "routing.gateway.parentRefs[%d] needs a name" $i) -}}
{{- end -}}
{{- if gt (len $ref.name) 253 -}}
{{- fail (printf "routing.gateway.parentRefs[%d].name exceeds 253 characters" $i) -}}
{{- end -}}
{{- if $ref.namespace -}}
{{- if or (gt (len $ref.namespace) 63) (not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$" $ref.namespace)) -}}
{{- fail (printf "routing.gateway.parentRefs[%d].namespace %q is not a valid namespace name (lowercase RFC 1123 label, at most 63 characters)" $i $ref.namespace) -}}
{{- end -}}
{{- end -}}
{{- if $ref.sectionName -}}
{{- if or (gt (len $ref.sectionName) 253) (not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" $ref.sectionName)) -}}
{{- fail (printf "routing.gateway.parentRefs[%d].sectionName %q is not a valid listener section name (lowercase RFC 1123 subdomain, at most 253 characters)" $i $ref.sectionName) -}}
{{- end -}}
{{- end -}}
{{- if hasKey $ref "port" -}}
{{- if or (lt (int $ref.port) 1) (gt (int $ref.port) 65535) -}}
{{- fail (printf "routing.gateway.parentRefs[%d].port %v is outside 1-65535" $i $ref.port) -}}
{{- end -}}
{{- end -}}
{{- /* CEL: references to the same parent must all carry a sectionName, and those must be unique */ -}}
{{- /* an omitted namespace is the route's own (the release namespace): both spellings name the same Gateway */ -}}
{{- $parent := printf "%s/%s" (default $.Release.Namespace $ref.namespace) $ref.name -}}
{{- $section := default "" $ref.sectionName -}}
{{- if hasKey $seen $parent -}}
{{- $prev := index $seen $parent -}}
{{- if or (eq $section "") (eq $prev "") -}}
{{- fail (printf "routing.gateway.parentRefs: Gateway %q is referenced more than once; every reference to the same parent must set a distinct sectionName" $parent) -}}
{{- end -}}
{{- if has $section (splitList "," $prev) -}}
{{- fail (printf "routing.gateway.parentRefs: Gateway %q is referenced twice with sectionName %q; sectionName must be unique per parent" $parent $section) -}}
{{- end -}}
{{- $_ := set $seen $parent (printf "%s,%s" $prev $section) -}}
{{- else -}}
{{- $_ := set $seen $parent $section -}}
{{- end -}}
{{- end -}}
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
