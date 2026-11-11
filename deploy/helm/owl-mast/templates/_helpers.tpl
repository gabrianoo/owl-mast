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
check). Names that fit are unchanged. Usage: include "owl-mast.suffixedName" (list . "postgresql-data")
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
{{- define "owl-mast.postgresql.dataClaim" -}}{{ include "owl-mast.suffixedName" (list . "postgresql-data") }}{{- end -}}
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

{{/* Issuer the backend trusts: bundled Keycloak realm or the supplied external issuer. */}}
{{- define "owl-mast.identity.issuerUri" -}}
{{- if .Values.identity.bundled -}}
{{- printf "http://%s:%v/realms/%s" (include "owl-mast.keycloak.fullname" .) .Values.identity.keycloak.service.port .Values.identity.realm -}}
{{- else -}}
{{- .Values.identity.external.issuerUri -}}
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
{{- /* JVM memory and -XX tuning flags only: a system property, agent or argument file here would override the validated configuration */ -}}
{{- $jvm := $v.backend.javaToolOptions | default "" -}}
{{- if or (not (regexMatch "^\\s*(-(XX:[+-][A-Za-z0-9]+|XX:[A-Za-z0-9]+=[A-Za-z0-9.%]+|Xm[sxn][0-9]+[kKmMgG]?|Xss[0-9]+[kKmMgG]?)(\\s+|$))*$" $jvm)) (regexMatch "-XX:(VMOptionsFile|Flags|OnError|OnOutOfMemoryError)=" $jvm) -}}
{{- fail (printf "backend.javaToolOptions %q is refused: only JVM memory and tuning flags are accepted (-XX:+Flag, -XX:-Flag, -XX:Name=value, -Xms/-Xmx/-Xmn/-Xss). System properties (-D), agents (-javaagent, -agentlib, -agentpath), argument files (@file), -XX:VMOptionsFile, -XX:Flags and -XX:On* hooks would override the chart-validated issuer and database configuration" $jvm) -}}
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
{{- if $v.identity.bundled -}}
{{- if and $v.identity.keycloak.bootstrapAdmin.enabled (not $v.identity.keycloak.bootstrapExistingSecret) -}}
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
{{- if not $v.networkPolicy.enabled -}}
{{- fail (printf "identity.keycloak.proxyHeaders=%s needs networkPolicy.enabled=true: without the Keycloak NetworkPolicy any pod can reach :8080 and send forged X-Forwarded-*/Forwarded headers" $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- if not (dig "keycloak" "extraFrom" list $v.networkPolicy) -}}
{{- fail (printf "identity.keycloak.proxyHeaders=%s needs networkPolicy.keycloak.extraFrom to name the trusted proxy: with no entry the policy admits only the backend, whose direct requests are not proxied" $v.identity.keycloak.proxyHeaders) -}}
{{- end -}}
{{- end -}}
{{- else -}}
{{- $issuer := $v.identity.external.issuerUri -}}
{{- if not $issuer -}}
{{- fail "identity.bundled=false requires identity.external.issuerUri: disabling the bundled Keycloak never disables authentication" -}}
{{- end -}}
{{- /* authority: a DNS name of RFC 1123 labels (an IPv4 address included) with an optional port 1-65535 */ -}}
{{- $authority := "[A-Za-z0-9]([-A-Za-z0-9]*[A-Za-z0-9])?(\\.[A-Za-z0-9]([-A-Za-z0-9]*[A-Za-z0-9])?)*(:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?" -}}
{{- /* path: RFC 3986 pchar segments without '@' (what java.net.URI in the backend accepts), percent escapes complete */ -}}
{{- $path := "(/([-A-Za-z0-9._~!$&'()*+,;=:]|%[0-9A-Fa-f]{2})*)*" -}}
{{- if regexMatch (printf "^https://%s%s$" $authority $path) $issuer -}}
{{- else if regexMatch (printf "^http://%s%s$" $authority $path) $issuer -}}
{{- if not $v.identity.external.allowInsecureIssuer -}}
{{- fail (printf "identity.external.issuerUri %q uses plaintext http: discovery and signing keys could be substituted in transit. Use https://, or set identity.external.allowInsecureIssuer=true to accept plaintext explicitly (disposable local fixtures only)" $issuer) -}}
{{- end -}}
{{- else -}}
{{- fail (printf "identity.external.issuerUri %q must be an absolute https:// URL with a host, an optional port 1-65535, valid path characters and no query, fragment or user info" $issuer) -}}
{{- end -}}
{{- end -}}
{{- /* AC3: every principal has its own Secret */ -}}
{{- $secrets := list (list "database.existingSecret" $v.database.existingSecret) -}}
{{- if $v.database.bundled -}}{{- $secrets = append $secrets (list "postgresql.adminExistingSecret" $v.postgresql.adminExistingSecret) -}}{{- end -}}
{{- if $v.identity.bundled -}}
{{- $secrets = append $secrets (list "identity.keycloak.database.existingSecret" $v.identity.keycloak.database.existingSecret) -}}
{{- if $v.identity.keycloak.bootstrapAdmin.enabled -}}
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
{{- fail (printf "postgresql.provisionKeycloakDatabase=true is refused on install: the pre-upgrade hook needs the release's existing PostgreSQL. This install reuses the claim %q, whose initialised volume never reruns the first-initialisation script: if it was initialised with identity.bundled=false, install first, then provision Keycloak's database in the PostgreSQL pod (kubectl exec deploy/<release>-postgresql -- bash /owl-mast/provision-keycloak.sh; docs/installation.md), or install with the identity mode the volume was initialised with and enable the bundle with this value on helm upgrade" $v.postgresql.persistence.existingClaim) -}}
{{- end -}}
{{- fail "postgresql.provisionKeycloakDatabase=true is refused on install: a fresh install provisions Keycloak's database at first initialisation, and the pre-upgrade hook needs the release's existing PostgreSQL (use it on helm upgrade; helm template needs --is-upgrade)" -}}
{{- end -}}
{{- end -}}
{{- if $v.frontend.enabled -}}
{{- if and (not $v.frontend.image.tag) (not $v.frontend.image.digest) -}}
{{- fail "frontend.enabled=true requires frontend.image.tag or frontend.image.digest (artifact delivered by OM-01.04)" -}}
{{- end -}}
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
{{- if not (has $ext.sslMode (list "disable" "allow" "prefer" "require" "verify-ca" "verify-full")) -}}
{{- fail (printf "%s.sslMode must be one of disable, allow, prefer, require, verify-ca, verify-full" $path) -}}
{{- end -}}
{{- if has $ext.sslMode (list "verify-ca" "verify-full") -}}
{{- fail (printf "%s.sslMode=%s is refused: it needs a CA trust the chart does not mount yet (deferred, see docs/installation.md), so the backend and Keycloak would render and then fail every database connection. Use require, which encrypts the connection but does not authenticate the server" $path $ext.sslMode) -}}
{{- end -}}
{{- if and (has $ext.sslMode (list "disable" "allow" "prefer")) (not $ext.allowInsecureTransport) -}}
{{- fail (printf "%s.sslMode=%s can send database credentials in plaintext: use require, or set %s.allowInsecureTransport=true to accept plaintext explicitly" $path $ext.sslMode $path) -}}
{{- end -}}
{{- end -}}

{{/* Ingress host and TLS: the host is a lowercase DNS name (optional leading '*.'), and a TLS block must cover it. */}}
{{- define "owl-mast.validateIngress" -}}
{{- $in := .Values.routing.ingress -}}
{{- $hostPattern := "^(\\*\\.)?[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)*$" -}}
{{- if not $in.host -}}
{{- fail "routing.ingress.enabled=true requires routing.ingress.host" -}}
{{- end -}}
{{- if or (gt (len $in.host) 253) (not (regexMatch $hostPattern $in.host)) -}}
{{- fail (printf "routing.ingress.host %q is not a valid Ingress host: lowercase DNS name with labels of at most 63 characters, optional leading wildcard label '*.', no scheme, port or path" $in.host) -}}
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
{{- if and (not $gw.hostnames) (not $gw.allowAllListenerHostnames) -}}
{{- fail "routing.gateway.hostnames is empty: an HTTPRoute without hostnames attaches to every hostname of the referenced listener(s), including other tenants' on a shared Gateway. List the hostnames, or set routing.gateway.allowAllListenerHostnames=true to accept every listener hostname explicitly" -}}
{{- end -}}
{{- if gt (len $gw.hostnames) 16 -}}
{{- fail (printf "routing.gateway.hostnames has %d entries; HTTPRoute allows at most 16" (len $gw.hostnames)) -}}
{{- end -}}
{{- range $i, $host := $gw.hostnames -}}
{{- if or (eq $host "") (gt (len $host) 253) (not (regexMatch "^(\\*\\.)?[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" $host)) -}}
{{- fail (printf "routing.gateway.hostnames[%d] %q is not a valid HTTPRoute hostname: lowercase DNS name, optional leading wildcard label '*.', no scheme, port or path, at most 253 characters" $i $host) -}}
{{- end -}}
{{- if regexMatch "^[0-9]+(\\.[0-9]+){3}$" $host -}}
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
