# Web image, built from the repository root (it bundles the files in samples/).
FROM node:26-alpine AS build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
COPY samples/ ../samples/
ARG VITE_API_URL=http://localhost:8102
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /app/web/dist /usr/share/nginx/html
EXPOSE 80
