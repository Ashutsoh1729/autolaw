FROM node:22-alpine AS builder

WORKDIR /app

# Copy dependency files first for better layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy application source code
COPY . .

# Build the application
RUN npm run build

# Runtime stage: serve with nginx
FROM nginx:stable-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD sed -i "s/listen 5173/listen ${PORT:-80}/" /etc/nginx/conf.d/default.conf && nginx -g "daemon off;"
