# nanofish

基于 [NoneBot2](https://nonebot.dev/) 的 QQ 机器人（OneBot V11），附带 Next.js 前端用于渲染对话截图。

## 结构

```
src/plugins/     # NoneBot 插件
app/             # Next.js 前端（聊天页截图）
docker/          # 容器启动脚本
```

## 插件

| 插件 | 命令 | 说明 |
|------|------|------|
| `acl` | `/auth` | 角色权限、群范围、日配额/冷却、运行时授权 |
| `llm` | `/llm` | 多模态 LLM 对话，结果截图回传（默认 user + 日配额） |
| `app` | — | Playwright 截图（长驻 browser + context，聊天数据 page 注入） |
| `ehsearch` | `/eh <书名>` 或回复后 `/eh` | E-Hentai 搜索，结果 HTML 截图回传（默认 admin + 配额） |
| `genai_detect` | `/genai` | AI 生成图片检测（默认 user + 配额） |
| `jrrp` | `/jrrp` | 今日祝福/人品（默认 guest） |
| `health` | `/health` | 深度健康检查（默认 superuser） |
| `utils` | — | 共享消息解析工具 |

### 权限（acl）

角色从低到高：`guest` < `user` < `admin` < `superuser`（`.env` 的 `SUPERUSERS`）。

| 默认门槛 | 命令 |
|----------|------|
| guest | `/jrrp` |
| user | `/llm`、`/genai` |
| admin | `/eh`、`/auth` 管理子命令 |
| superuser | `/health` |

范围：

- `ACL_ALLOWED_GROUPS`：群白名单（空=不限制）
- `ACL_ALLOW_PRIVATE`：是否允许私聊（superuser 始终可）
- 运行时可用 `/auth group enable|disable|reset` 覆盖单群

配额（superuser 不限）：

- `/llm` 默认 10 次/日、冷却 30s
- `/genai` 默认 20 次/日、冷却 10s
- `/eh` 默认 20 次/日、冷却 10s

常用管理：

```text
/auth whoami
/auth list
/auth set <qq|@> user|admin|guest
/auth ban|unban <qq|@>
/auth group enable|disable|reset [群号]
```

## 快速开始

### 1. 后端

```bash
# 安装依赖（uv）
uv sync

# 复制并填写环境变量
cp .env.example .env

# 启动（开发热重载）
nb run --reload
```

### 2. 前端（截图用）

```bash
cd app
pnpm install
pnpm dev   # 默认 http://localhost:3000
```

将 `APP_API_BASE` 指向该地址。

### 3. Docker

```bash
cp .env.example .env.prod
# 编辑 .env.prod（含 DRIVER、API Key 等）
docker compose up -d --build
```

镜像已内置 Chromium（Playwright 截图）。无 `.env.prod` 时仍可构建启动，但需自行注入环境变量。

## 环境变量

见 [`.env.example`](.env.example)。敏感项（API Key、exhentai cookie、Sightengine 凭证）**不要**写入源码。

| 变量 | 用途 |
|------|------|
| `SUPERUSERS` | 超级用户 QQ 列表 |
| `ACL_*` | 权限/群白名单/配额（见 `.env.example`） |
| `APP_API_BASE` | 前端 base URL |
| `MODEL` / `OPENAI_API_KEY` / `OPENAI_API_BASE` | LLM |
| `SIGHTENGINE_API_USER` / `SIGHTENGINE_API_SECRET` | AI 图检测 |
| `EH_DB` / `EH_IPB_*` / `EH_SK` / `EH_IGNEOUS` | EH 搜索与标签库 |
| `PROXY` | 可选 HTTP 代理 |

标签翻译库 `EH_DB`（默认 `src/plugins/ehsearch/sql/o.db`）由 `db.text.json` **生成**，不入库。首次加载插件时会自动构建；也可手动：

```bash
python src/plugins/ehsearch/sql/ehsql.py
# 或指定路径
python src/plugins/ehsearch/sql/ehsql.py -j src/plugins/ehsearch/sql/db.text.json -o "$EH_DB"
```

## 开发

```bash
uv run ruff check src
uv run ruff format src
uv run pyright
```

## 文档

- NoneBot: https://nonebot.dev/
- 前端: `app/` 目录下 Next.js + HeroUI
