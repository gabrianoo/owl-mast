# Owl Mast frontend image (OM-01.04-T1, AD-14): an independent artifact, never bundled into the
# backend image. Build from the repository root or this directory:
#   docker build -t owl-mast/frontend:0.1.0 frontend
# Pins (docs/frontend.md): Node 24.21.0 on Alpine for the build stage; nginx-unprivileged 1.31.7 on
# Alpine for the runtime (listens on 8080 as UID 101, matching the chart's frontend contract).
FROM node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /src
COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-audit --no-fund
COPY tsconfig.json tsconfig.app.json tsconfig.node.json tsconfig.e2e.json vite.config.ts index.html api-compatibility.json ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.31.7-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e
# Routing contract handed to the shell by the chart (deploy/helm/owl-mast/templates/frontend-deployment.yaml).
ENV OWLMAST_API_PATH_PREFIX=/api
# The template is rendered with OWLMAST_* variables only. Without the filter the base image
# substitutes every defined environment variable, so a container variable named `status` or `uri`
# would replace the nginx variable of that name in the template.
ENV NGINX_ENVSUBST_FILTER=^OWLMAST_
# Refuses to start on an API prefix that is unsafe inside the nginx template (must stay executable:
# the base image's entrypoint ignores non-executable files).
COPY --chmod=0755 docker-entrypoint.d/16-owlmast-api-prefix.envsh /docker-entrypoint.d/16-owlmast-api-prefix.envsh
COPY nginx/owlmast-headers.conf /etc/nginx/owlmast-headers.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
