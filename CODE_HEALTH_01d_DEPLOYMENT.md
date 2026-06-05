# 部署与运行入口 (Phase 1.4)

## A. Docker Compose 架构

`docker-compose.yml` 定义 2 个 service + 1 个命名 volume + 1 个 bridge 网络：

| Service | 镜像 | 暴露 | 用途 |
|---------|------|------|------|
| `backend` | `novelforge-backend:0.1.0` | 8000 (内部) | FastAPI + 进程内 asyncio worker |
| `frontend` | `novelforge-frontend:0.1.0` | `${FRONTEND_PORT:-8080}:80` (主机) | Nginx 静态服务 + `/api` 反代 |

| Volume | 挂载 | 说明 |
|--------|------|------|
| `novelforge_data` | `/app/backend/data` | SQLite 持久化 + 上传/日志子目录 |

| Network | 驱动 | 用途 |
|---------|------|------|
| `nfnet` | bridge | backend ↔ frontend 互通 |

启动：`docker compose up -d --build`，主机访问 `http://localhost:8080`。

## B. 后端 Dockerfile (`Dockerfile`)

- **多阶段**：仅一个 stage（python:3.11-slim），先装 deps 再 copy 源码以利用 layer cache
- **关键环境变量**：`PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1`
- **CMD**：`uvicorn app.main:app --host 0.0.0.0 --port 8000`（**workers=1**，注释明确说明因有 in-process asyncio worker，避免 SQLite 竞争）
- **Entrypoint**：`/app/backend/docker-entrypoint.sh`（先 idempotent seed 再启 uvicorn）
- **Volume 准备**：`data/`、`data/storage/`、`data/logs/`

## C. 前端 Dockerfile (`Dockerfile.frontend`)

- **多阶段**：
  1. `node:20-alpine`：安装 deps → `npm run build`
  2. `nginx:1.27-alpine`：替换 default.conf、COPY `dist/`
- **EXPOSE 80**
- **HEALTHCHECK**：30s 间隔 wget `/`

## D. Nginx 配置 (`docker/nginx.conf`)

关键设计：
- **SPA fallback**：`location / { try_files $uri $uri/ /index.html; }` —— 支持 `/dashboard`、`/projects/1/chapters/2` 等前端路由
- **静态资源缓存**：`/assets/*` 设 `expires 1y; Cache-Control: public, immutable`（Vite hashed）
- **API 反代**：`location /api/ → proxy_pass http://novelforge_backend`（upstream keepalive 16）
- **SSE 优化**：`proxy_buffering off; proxy_cache off; proxy_read_timeout 1h` —— 适配 chat 流
- **上传大小**：`client_max_body_size 32m`
- **健康探针**：`/nginx-health → 200 ok\n`

## E. 环境变量入口

- `backend/.env.example` — 后端开发模板（DATABASE_URL / NOVELFORGE_API_KEY / CORS_ORIGINS）
- `frontend/.env.development` — 前端 Vite 代理配置
- `docker-compose.yml` —— 通过 `${VAR:-default}` 注入，可直接覆盖

## F. 部署风险提示

1. **SQLite 单文件** —— 注释明示「小团队/单作者 OK」，但不支持水平扩展，迁移 Postgres 需改 `DATABASE_URL` + 加 db service
2. **单 worker 限制** —— uvicorn 不可启多 worker，水平扩展需改为外部 worker
3. **无 frontend healthcheck 依赖 backend** —— `depends_on.condition: service_healthy` 已正确配置
4. **Nginx 32M body** —— 拆书上传有大小门槛，超大文件需调整
