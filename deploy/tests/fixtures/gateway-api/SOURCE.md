# Pinned upstream schema: Gateway API v1.4.0 standard HTTPRoute, version v1

- Origin: https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.4.0/config/crd/standard/gateway.networking.k8s.io_httproutes.yaml
- Downloaded 2026-11-07 (tagged release v1.4.0, standard channel CRD).
- SHA256 of the downloaded CRD file: `c2539410dec72b793ef840f484c19d13b48210074ec801b730e9fce2c5fc825c`
- `httproute-v1.4.0-openapi-v1.json` is the `openAPIV3Schema` of the `v1` version of that CRD, extracted verbatim
  (JSON, sorted keys). The deploy test suite validates rendered HTTPRoutes against it offline with the Python
  `jsonschema` library. That checks the ordinary OpenAPI/JSON-Schema constraints (types, patterns, lengths,
  cardinalities, enums). It does not evaluate the CRD's `x-kubernetes-validations` CEL rules, which the chart
  enforces separately for the inputs it exposes, and it is not controller acceptance or runtime qualification.
- Kubernetes Ingress API remains frozen (GA, no removal planned); Gateway API is the recommended successor.
