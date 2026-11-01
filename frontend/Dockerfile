FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# nginx sin privilegios: el proceso corre como usuario no root.
FROM nginxinc/nginx-unprivileged:1.27-alpine
# Archivos del build de solo lectura para el servidor (propiedad de root).
COPY --from=build --chown=root:root /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER 101
EXPOSE 8443
