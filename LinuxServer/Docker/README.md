# Docker 部署

程序位于 `app/`，配置模板位于 `config/`，实际配置和日志保存在 `data/`。

完整步骤见 [Docker 部署文档](../../docs/Docker部署文档.md)。旧目录升级前先停服、备份，再运行 `python3 migrate_layout.py`。

```bash
cp .env.example .env
# 填写公网地址与两个不同的密码
nano .env
docker compose up -d --build
```
