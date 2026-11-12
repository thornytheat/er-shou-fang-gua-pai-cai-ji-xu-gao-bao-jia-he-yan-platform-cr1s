FROM node:20-alpine AS build
WORKDIR /app
# 镜像站可覆盖：docker compose build --build-arg NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_REGISTRY=https://registry.npmmirror.com
ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY}
COPY package.json /app/package.json
RUN npm install --no-audit --no-fund || npm install --no-audit --no-fund --registry=https://registry.npmjs.org
COPY . /app
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
