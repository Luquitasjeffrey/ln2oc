# The ln2oc website: static files only, served by its own nginx. The API (FastAPI)
# never serves these; it only redirects GET / to FRONTEND_URL.

# --- Stage 1: build ---
FROM node:20.18-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Public URL of the ln2oc API, baked into the static bundle.
ARG VITE_API_URL=http://127.0.0.1:8000
ENV VITE_API_URL=${VITE_API_URL}
ARG VITE_CONTACT_TELEGRAM=LucasJeffreyP2P
ENV VITE_CONTACT_TELEGRAM=${VITE_CONTACT_TELEGRAM}
RUN npm test && npm run build

# --- Stage 2: serve ---
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
