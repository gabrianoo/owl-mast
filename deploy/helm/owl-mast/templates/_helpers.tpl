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
{{- end -}}
