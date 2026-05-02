# Build stage
FROM node:20-slim AS build-stage

WORKDIR /app

# 复制依赖定义
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制源码并构建
COPY . .
RUN npm run build

# Production stage
FROM nginx:stable-alpine AS production-stage

# 复制构建产物到 nginx 目录
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 复制自定义 nginx 配置（支持 SPA 路由和 API 代理）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
