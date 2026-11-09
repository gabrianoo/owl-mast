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
long release name or fullnameOverride never renders a name the API server rejects. Usage:
include "owl-mast.suffixedName" (list . "postgresql-data")
*/}}
{{- define "owl-mast.suffixedName" -}}
{{- $root := index . 0 -}}
{{- $suffix := index . 1 -}}
{{- $base := include "owl-mast.fullname" $root | trunc (int (sub 62 (len $suffix))) | trimSuffix "-" -}}
{{- printf "%s-%s" $base $suffix -}}
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
{{- if not $v.identity.keycloak.bootstrapExistingSecret -}}
{{- fail "identity.keycloak.bootstrapExistingSecret is required when identity.bundled=true" -}}
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
{{- else -}}
{{- $issuer := $v.identity.external.issuerUri -}}
{{- if not $issuer -}}
{{- fail "identity.bundled=false requires identity.external.issuerUri: disabling the bundled Keycloak never disables authentication" -}}
{{- end -}}
{{- /* authority: a DNS name of RFC 1123 labels (an IPv4 address included) with an optional numeric port */ -}}
{{- $authority := "[A-Za-z0-9]([-A-Za-z0-9]*[A-Za-z0-9])?(\\.[A-Za-z0-9]([-A-Za-z0-9]*[A-Za-z0-9])?)*(:[0-9]{1,5})?" -}}
{{- if regexMatch (printf "^https://%s(/[^?#@\\s]*)?$" $authority) $issuer -}}
{{- else if regexMatch (printf "^http://%s(/[^?#@\\s]*)?$" $authority) $issuer -}}
{{- if not $v.identity.external.allowInsecureIssuer -}}
{{- fail (printf "identity.external.issuerUri %q uses plaintext http: discovery and signing keys could be substituted in transit. Use https://, or set identity.external.allowInsecureIssuer=true to accept plaintext explicitly (disposable local fixtures only)" $issuer) -}}
{{- end -}}
{{- else -}}
{{- fail (printf "identity.external.issuerUri %q must be an absolute https:// URL with a host and no query, fragment or user info" $issuer) -}}
{{- end -}}
{{- end -}}
{{- /* AC3: every principal has its own Secret */ -}}
{{- $secrets := list (list "database.existingSecret" $v.database.existingSecret) -}}
{{- if $v.database.bundled -}}{{- $secrets = append $secrets (list "postgresql.adminExistingSecret" $v.postgresql.adminExistingSecret) -}}{{- end -}}
{{- if $v.identity.bundled -}}
{{- $secrets = append $secrets (list "identity.keycloak.database.existingSecret" $v.identity.keycloak.database.existingSecret) -}}
{{- $secrets = append $secrets (list "identity.keycloak.bootstrapExistingSecret" $v.identity.keycloak.bootstrapExistingSecret) -}}
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
{{- if not (regexMatch "^/api(/.*)?$" $v.routing.apiPathPrefix) -}}
{{- fail (printf "routing.apiPathPrefix %q is not served by the backend: it must be /api or a path below /api/ (the chart renders no rewrite)" $v.routing.apiPathPrefix) -}}
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
{{- if and (has $ext.sslMode (list "disable" "allow" "prefer")) (not $ext.allowInsecureTransport) -}}
{{- fail (printf "%s.sslMode=%s can send database credentials in plaintext: use require (or verify-ca/verify-full), or set %s.allowInsecureTransport=true to accept plaintext explicitly" $path $ext.sslMode $path) -}}
{{- end -}}
{{- end -}}

{{/* Ingress host and TLS: the host is a lowercase DNS name (optional leading '*.'), and a TLS block must cover it. */}}
{{- define "owl-mast.validateIngress" -}}
{{- $in := .Values.routing.ingress -}}
{{- $hostPattern := "^(\\*\\.)?[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" -}}
{{- if not $in.host -}}
{{- fail "routing.ingress.enabled=true requires routing.ingress.host" -}}
{{- end -}}
{{- if or (gt (len $in.host) 253) (not (regexMatch $hostPattern $in.host)) -}}
{{- fail (printf "routing.ingress.host %q is not a valid Ingress host: lowercase DNS name, optional leading wildcard label '*.', no scheme, port or path" $in.host) -}}
{{- end -}}
{{- if $in.tls -}}
{{- $covered := false -}}
{{- range $i, $t := $in.tls -}}
{{- if not $t.hosts -}}
{{- fail (printf "routing.ingress.tls[%d].hosts must list the host it secures" $i) -}}
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
{{- if $ref.port -}}
{{- if or (lt (int $ref.port) 1) (gt (int $ref.port) 65535) -}}
{{- fail (printf "routing.gateway.parentRefs[%d].port %v is outside 1-65535" $i $ref.port) -}}
{{- end -}}
{{- end -}}
{{- /* CEL: references to the same parent must all carry a sectionName, and those must be unique */ -}}
{{- $parent := printf "%s/%s" (default "" $ref.namespace) $ref.name -}}
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
{{- if gt (len $gw.hostnames) 16 -}}
{{- fail (printf "routing.gateway.hostnames has %d entries; HTTPRoute allows at most 16" (len $gw.hostnames)) -}}
{{- end -}}
{{- range $i, $host := $gw.hostnames -}}
{{- if or (eq $host "") (gt (len $host) 253) (not (regexMatch "^(\\*\\.)?[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" $host)) -}}
{{- fail (printf "routing.gateway.hostnames[%d] %q is not a valid HTTPRoute hostname: lowercase DNS name, optional leading wildcard label '*.', no scheme, port or path, at most 253 characters" $i $host) -}}
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
