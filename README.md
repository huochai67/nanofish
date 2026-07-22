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
| `llm` | `/llm`、`/draw` | 多模态对话（截图回传）；OpenAI 兼容文生图/图生图（默认 user + 日配额） |
| `app` | — | Playwright 截图（长驻 browser + context，聊天数据 page 注入） |
| `ehsearch` | `/eh <书名>` 或回复后 `/eh` | E-Hentai 搜索，结果 HTML 截图回传（默认 admin + 配额） |
| `imgsearch` | `/imgsearch` | 回复或附带图片反向搜索 SauceNAO；可选 Soutubot（默认 user + 配额） |
| `genai_detect` | `/genai` | AI 生成图片检测（默认 user + 配额） |
| `jrrp` | `/jrrp` | 今日祝福/人品（默认 guest） |
| `health` | `/health` | 深度健康检查（默认 superuser） |
| `nonebot_plugin_parser` | 自动解析支持平台链接、`/bm` | 核心链接解析（受 ACL 范围和角色限制；初始关闭 YouTube/TikTok/Twitter） |
| `parser_acl` | — | 在解析插件执行前应用 Nanofish ACL 策略 |
| `utils` | — | 共享消息解析工具 |

### 权限（acl）

角色从低到高：`guest` < `user` < `admin` < `superuser`（`.env` 的 `SUPERUSERS`）。

| 默认门槛 | 命令 |
|----------|------|
| guest | `/jrrp` |
| user | `/llm`、`/draw`、`/genai`、`/imgsearch`、链接解析、`/bm` |
| admin | `/eh`、`/auth` 管理子命令 |
| superuser | `/health` |

范围：

- `ACL_ALLOWED_GROUPS`：群白名单（空=不限制）
- `ACL_ALLOW_PRIVATE`：是否允许私聊（superuser 始终可）
- 运行时可用 `/auth group enable|disable|reset` 覆盖单群

配额（superuser 不限）：

- `/llm` 默认 10 次/日、冷却 30s
- `/draw` 默认 5 次/日、冷却 60s
- `/genai` 默认 20 次/日、冷却 10s
- `/eh` 默认 20 次/日、冷却 10s
- `/imgsearch` 默认 20 次/日、冷却 10s

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

`docker compose` 会同时启动：

| 服务 | 说明 | 端口 |
|------|------|------|
| `nonebot` | 机器人 + Playwright Chromium + FFmpeg | `PORT`（默认 8080） |
| `frontend` | Next.js 截图页 | `FRONTEND_PORT`（默认 3000） |

容器内 `APP_API_BASE` 固定为 `http://frontend:3000`（compose 覆盖 `.env.prod`）。无 `.env.prod` 时 compose 会报错，请先复制示例文件。

## 环境变量

见 [`.env.example`](.env.example)。敏感项（API Key、exhentai cookie、Sightengine 凭证）**不要**写入源码。

| 变量 | 用途 |
|------|------|
| `SUPERUSERS` | 超级用户 QQ 列表 |
| `ACL_*` | 权限/群白名单/配额（含 `ACL_PERM_PARSER`，见 `.env.example`） |
| `PARSER_*` | 链接解析的媒体限制、平台禁用、可选 cookie/代理 |
| `APP_API_BASE` | 前端 base URL |
| `MODEL` / `OPENAI_API_KEY` / `OPENAI_API_BASE` | LLM 对话 |
| `IMAGE_MODEL` / `IMAGE_SIZE` / `IMAGE_RESPONSE_FORMAT` / `IMAGE_TIMEOUT` | `/draw` 生图（key/base 与对话共用） |
| `SIGHTENGINE_API_USER` / `SIGHTENGINE_API_SECRET` | AI 图检测 |
| `EH_IPB_*` / `EH_SK` / `EH_IGNEOUS` | ExHentai cookie |
| `IMGSEARCH_*` | 反向搜图的上游参数；Soutubot 仅使用自有授权 API key |
| `PROXY` | 可选 HTTP 代理，应用于全部后端外部请求（`HTTP_PROXY` 兼容旧配置） |

标签中文翻译在 **Next 前端**完成（[EhTagTranslation](https://github.com/EhTagTranslation/Database)）。构建/开发时会下载字典到 `app/public/ehtag-dict.json`（不入库）；Bot 只传原始 `namespace:tag`。

```bash
cd app
pnpm ehtag        # 已存在则跳过
pnpm ehtag:force  # 强制重新下载
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
