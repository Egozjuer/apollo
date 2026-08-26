# 极空间 Docker 部署 HK7709 看板

可以。这个看板是纯 Python，不需要数据库，适合放在极空间 Docker 里 24 小时跑。

手机或电脑访问：

```text
http://你的极空间IP:8770
```

## 极空间上怎么放

### 1. 把这个目录拷到 NAS

把整个 `tools/quant_07709` 文件夹拷到极空间共享目录，例如：

```text
/极空间/Docker/hk7709
```

这个目录里至少要有：

```text
Dockerfile
docker-compose.yml
app.py
snapshot.py
market_data.py
static/
```

### 2. 用 Docker Compose 启动

SSH 进极空间后：

```bash
cd /path/to/hk7709
docker compose up -d --build
```

如果极空间 Docker 套件里有“项目 / Compose”，也可以直接导入这个 `docker-compose.yml`。

### 3. 确认容器在跑

```bash
docker ps
curl http://127.0.0.1:8770/api/health
```

健康检查正常会返回：

```json
{"ok": true, "service": "quant-07709-snapshot"}
```

### 4. 局域网打开看板

```text
http://192.168.x.x:8770
```

把 `192.168.x.x` 换成极空间的局域网 IP。  
如果 8770 被占用，改 `docker-compose.yml` 里的端口，例如：

```yaml
ports:
  - "18770:8770"
```

然后访问 `http://192.168.x.x:18770`。

## 极空间注意点

1. 容器必须能访问外网，否则腾讯行情和 CSOP 净值拉不下来。
2. 建议用桥接网络，不要用仅内部网络。
3. `restart: unless-stopped` 已经写好，NAS 重启后会自动拉起。
4. 这是估值看板，不是自动交易，也不会登录你的券商账户。
5. 当前没有通达信 MCP。容器里优先用腾讯行情和 CSOP 官方净值。

## 常用命令

查看日志：

```bash
docker logs -f hk7709-snapshot
```

更新代码后重建：

```bash
docker compose up -d --build
```

停止：

```bash
docker compose down
```
