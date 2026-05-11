{{/* Service / app name. Defaults to release name so each helm release owns its objects. */}}
{{- define "bitirme.name" -}}
{{- default .Release.Name .Values.app.name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "bitirme.fullname" -}}
{{- include "bitirme.name" . }}
{{- end }}

{{- define "bitirme.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "bitirme.selectorLabels" -}}
app: {{ include "bitirme.name" . }}
app.kubernetes.io/name: {{ include "bitirme.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "bitirme.labels" -}}
helm.sh/chart: {{ include "bitirme.chart" . }}
{{ include "bitirme.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- end }}
