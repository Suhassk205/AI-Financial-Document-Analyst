# syntax=docker/dockerfile:1
# Frontend dev image (Vite dev server). A multi-stage prod build (static assets
# served via nginx/CDN) is added in Phase 11.
FROM node:20-alpine

WORKDIR /app

# Install deps first for layer caching.
COPY package.json ./
RUN npm install

# Source is bind-mounted in dev (see docker-compose) for hot reload.
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
