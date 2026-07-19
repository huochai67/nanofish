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
| `llm` | `/llm` | 多模态 LLM 对话，结果截图回传 |
| `app` | — | Playwright 截图服务 |
| `ehsearch` | `/eh` | E-Hentai 搜索（仅超级用户） |
| `genai_detect` | `/genai` | AI 生成图片检测（仅超级用户） |
| `jrrp` | `/jrrp` | 今日祝福/人品 |
| `utils` | — | 共享消息解析工具 |

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
# 编辑 .env.prod
docker compose up -d --build
```

## 环境变量

见 [`.env.example`](.env.example)。敏感项（API Key、exhentai cookie、Sightengine 凭证）**不要**写入源码。

| 变量 | 用途 |
|------|------|
| `APP_API_BASE` | 前端 base URL |
| `MODEL` / `OPENAI_API_KEY` / `OPENAI_API_BASE` | LLM |
| `SIGHTENGINE_API_USER` / `SIGHTENGINE_API_SECRET` | AI 图检测 |
| `EH_DB` / `EH_IPB_*` / `EH_SK` / `EH_IGNEOUS` | EH 搜索与标签库 |
| `PROXY` | 可选 HTTP 代理 |

## 开发

```bash
uv run ruff check src
uv run ruff format src
uv run pyright
```

## 文档

- NoneBot: https://nonebot.dev/
- 前端: `app/` 目录下 Next.js + HeroUI
