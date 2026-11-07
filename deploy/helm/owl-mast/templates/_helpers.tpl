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

{{- define "owl-mast.postgresql.fullname" -}}{{ include "owl-mast.fullname" . }}-postgresql{{- end -}}
{{- define "owl-mast.keycloak.fullname" -}}{{ include "owl-mast.fullname" . }}-keycloak{{- end -}}
{{- define "owl-mast.backend.fullname" -}}{{ include "owl-mast.fullname" . }}-backend{{- end -}}
{{- define "owl-mast.frontend.fullname" -}}{{ include "owl-mast.fullname" . }}-frontend{{- end -}}

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
{{- if not .Values.database.existingSecret -}}
{{- fail "database.existingSecret is required: an existing Secret with keys username and password for the application principal" -}}
{{- end -}}
{{- if .Values.database.bundled -}}
{{- if not .Values.postgresql.adminExistingSecret -}}
{{- fail "postgresql.adminExistingSecret is required when database.bundled=true" -}}
{{- end -}}
{{- else -}}
{{- if not .Values.database.external.host -}}
{{- fail "database.bundled=false requires database.external.host (compatible PostgreSQL 18 with VectorChord installed)" -}}
{{- end -}}
{{- if not (has .Values.database.external.sslMode (list "disable" "allow" "prefer" "require" "verify-ca" "verify-full")) -}}
{{- fail "database.external.sslMode must be one of disable, allow, prefer, require, verify-ca, verify-full" -}}
{{- end -}}
{{- end -}}
{{- if .Values.identity.bundled -}}
{{- if not .Values.identity.keycloak.bootstrapExistingSecret -}}
{{- fail "identity.keycloak.bootstrapExistingSecret is required when identity.bundled=true" -}}
{{- end -}}
{{- if not .Values.identity.keycloak.database.existingSecret -}}
{{- fail "identity.keycloak.database.existingSecret is required when identity.bundled=true" -}}
{{- end -}}
{{- if and (not .Values.database.bundled) (not .Values.identity.keycloak.database.external.host) -}}
{{- fail "identity.bundled=true with database.bundled=false requires identity.keycloak.database.external.host" -}}
{{- end -}}
{{- if not .Values.identity.realm -}}
{{- fail "identity.realm is required" -}}
{{- end -}}
{{- else -}}
{{- if not .Values.identity.external.issuerUri -}}
{{- fail "identity.bundled=false requires identity.external.issuerUri: disabling the bundled Keycloak never disables authentication" -}}
{{- end -}}
{{- if not (or (hasPrefix "https://" .Values.identity.external.issuerUri) (hasPrefix "http://" .Values.identity.external.issuerUri)) -}}
{{- fail "identity.external.issuerUri must be an absolute http(s) URL" -}}
{{- end -}}
{{- end -}}
{{- if .Values.postgresql.provisionKeycloakDatabase -}}
{{- if not (and .Values.database.bundled .Values.identity.bundled) -}}
{{- fail "postgresql.provisionKeycloakDatabase=true applies only to a bundled PostgreSQL with a bundled Keycloak (database.bundled=true and identity.bundled=true)" -}}
{{- end -}}
{{- end -}}
{{- if .Values.frontend.enabled -}}
{{- if and (not .Values.frontend.image.tag) (not .Values.frontend.image.digest) -}}
{{- fail "frontend.enabled=true requires frontend.image.tag or frontend.image.digest (artifact delivered by OM-01.04)" -}}
{{- end -}}
{{- end -}}
{{- if .Values.routing.ingress.enabled -}}
{{- if not .Values.routing.ingress.host -}}
{{- fail "routing.ingress.enabled=true requires routing.ingress.host" -}}
{{- end -}}
{{- end -}}
{{- if and .Values.routing.ingress.enabled .Values.routing.gateway.enabled -}}
{{- fail "routing.ingress.enabled and routing.gateway.enabled are both true: choose one routing mechanism (ambiguous exposure is refused)" -}}
{{- end -}}
{{- if .Values.routing.gateway.enabled -}}
{{- include "owl-mast.validateGateway" . -}}
{{- end -}}
{{- range (list .Values.routing.apiPathPrefix .Values.routing.actuatorPathPrefix .Values.routing.frontendPathPrefix) -}}
{{- include "owl-mast.validatePathPrefix" . -}}
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
