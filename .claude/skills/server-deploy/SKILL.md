---
name: server-deploy
description: >
  Rebuild and restart all production Docker services (KataGo GPU engines + KaTrain web/cron).
  Use when deploying code changes to the server, restarting services after updates, or
  troubleshooting container issues. Triggers on: deploy, 部署, restart services, rebuild
  docker, 重启服务, 重新部署, server update, 更新服务器.
---

# Server Deploy

Rebuild and restart the production Docker services for KaTrain and KataGo.

## Service Architecture

```
                 ┌──────────────┐
  :8001          │  katrain-web │──▶ :8000 katago-gpu0 (GPU 0) ← user gameplay
                 └──────────────┘
                 ┌──────────────┐
                 │ katrain-cron │──▶ :8002 katago-gpu1 (GPU 1) ← batch analysis
                 └──────────────┘
                 ┌──────────────────┐
  :5432          │ katrain-postgres │  ← persistent, never restart during deploy
                 └──────────────────┘
```

| Container | Image | Port | GPU | Source Repo |
|-----------|-------|------|-----|-------------|
| katago-gpu0 | katago-trt:latest | 8000 | 0 | /home/fan/Repositories/KataGo (develop) |
| katago-gpu1 | katago-trt:latest | 8002 | 1 | /home/fan/Repositories/KataGo (develop) |
| katrain-web | docker-compose build | 8001 | — | /home/fan/Repositories/katrain (develop) |
| katrain-cron | docker-compose build | — | — | /home/fan/Repositories/katrain (develop) |
| katrain-postgres | postgres | 5432 | — | **DO NOT restart** |

## Execution Steps

### 1. Ensure .env exists

```bash
# /home/fan/Repositories/katrain/.env must contain:
DASHSCOPE_API_KEY=<key>
```

If missing, the cron container's translation feature will be skipped. Check previous container
for the key:

```bash
docker inspect katrain-cron --format '{{range .Config.Env}}{{println .}}{{end}}' | grep DASHSCOPE
```

### 2. Rebuild KataGo image (~2-20 min depending on cache)

Only needed when KataGo repo (/home/fan/Repositories/KataGo) has changes.

```bash
cd /home/fan/Repositories/KataGo
docker build -t katago-trt:latest -f Dockerfile .
```

The build compiles KataGo C++ with TensorRT backend and downloads models if `/app/models/`
is empty in the image layer. Model download from China mirror can take ~15 min.

### 3. Restart KataGo containers

```bash
docker stop katago-gpu0 katago-gpu1
docker rm katago-gpu0 katago-gpu1

# GPU 0 — serves katrain-web for user gameplay
docker run -d \
  --name katago-gpu0 \
  --gpus '"device=0"' \
  --restart unless-stopped \
  -p 8000:8000 \
  katago-trt:latest

# GPU 1 — serves katrain-cron for batch analysis
docker run -d \
  --name katago-gpu1 \
  --gpus '"device=1"' \
  --restart unless-stopped \
  -p 8002:8000 \
  katago-trt:latest
```

### 4. Verify KataGo health

TensorRT engine warmup takes ~30s-2min. Wait then check:

```bash
curl http://localhost:8000/health
curl http://localhost:8002/health
```

Expected: `{"status":"ok","pid":...,"has_human_model":true,"model":"..."}`

### 5. Rebuild and restart KaTrain services

```bash
cd /home/fan/Repositories/katrain
docker compose up -d --build
```

This rebuilds both `katrain-web` (Dockerfile.web) and `katrain-cron` (Dockerfile.cron).
The web build includes `npm run build` for the React frontend (~45s).

### 6. Verify all services

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
curl http://localhost:8001/api/v1/health
docker logs katrain-cron --tail 20
```

## Selective Deployment

- **KataGo changes only**: Steps 2-4, skip 5-6
- **KaTrain changes only**: Steps 1, 5-6, skip 2-4
- **Frontend-only changes**: Step 5-6 (the Dockerfile.web runs `npm run build`)
- **Cron-only changes**: `docker compose up -d --build katrain-cron`

## Troubleshooting

- **katrain-web can't reach KataGo**: Containers use `host.docker.internal` to reach host ports. Check `docker logs katrain-web` for engine connection errors.
- **"orphan containers" warning**: Normal — postgres is not in docker-compose.yml. Ignore.
- **KataGo OOM on startup**: TensorRT plan cache may be stale. Remove and restart: `docker exec katago-gpu0 rm -rf /tmp/*.engine`
- **Cron not analyzing**: Check `KATAGO_URL` env points to port 8002 and katago-gpu1 is healthy.
