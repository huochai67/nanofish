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
| `acl` | `/auth` | 角色权限、群范围、日配额/冷却、每命令限流、运行时授权 |
| `llm` | `/llm`、`/draw` | 多模态对话（截图回传）；OpenAI 兼容文生图/图生图（默认 user + 日配额） |
| `app` | — | Playwright 截图（长驻 browser + context，聊天数据 page 注入） |
| `ehsearch` | `/eh <书名>` 或回复后 `/eh` | E-Hentai 搜索，结果 HTML 截图回传（默认 admin + 配额） |
| `imgsearch` | `/imgsearch` | 回复或附带图片反向搜索 SauceNAO；可选 Soutubot（默认 user + 配额） |
| `genai_detect` | `/genai` | 自动验证所有接收图片的内嵌可信 C2PA 凭证；`/genai` 使用 Sightengine 检测（默认 user + 配额） |
| `jrrp` | `/jrrp` | 今日祝福/人品（默认 guest） |
| `health` | `/health` | 深度健康检查（默认 superuser） |
| `media_parser` | 自动解析支持平台链接、`/bm` | 前端主题卡片预览与媒体回传（受 ACL 范围和角色限制；初始关闭 YouTube/TikTok/Twitter） |
| `utils` | — | 共享消息解析工具 |

### 权限（acl）

`genai_detect` 仅在图片含有通过官方 C2PA 签名与 TSA 信任列表校验的内嵌凭证时自动回复；信任列表会定期刷新，但不下载远程 manifest 或 OCSP 信息。

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

每命令限流：

- `ACL_RATE_LIMIT_<COMMAND>_PER_MINUTE` 为对应高成本命令跨所有用户共享的滚动 60 秒请求上限；`0` 表示关闭，superuser 也计入。

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

# 复制并填写运行环境与业务配置
cp .env.example .env
cp config.example.yaml config.yaml

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
cp config.example.yaml config.yaml
# 编辑 .env.prod（NoneBot、网络、日志和截图配置）与 config.yaml（业务插件配置）
docker compose up -d --build
```

`docker compose` 会同时启动：

| 服务 | 说明 | 端口 |
|------|------|------|
| `nonebot` | 机器人 + Playwright Chromium + FFmpeg | `PORT`（默认 8080） |
| `frontend` | Next.js 截图页 | `FRONTEND_PORT`（默认 3000） |
| `flaresolverr` | Cloudflare 验证 cookie 获取服务 | 仅 Compose 内部网络 |

容器内 `APP_API_BASE` 固定为 `http://nanofish-frontend:3000`（compose 覆盖 `.env.prod`）。Compose 会将宿主机 `config.yaml` 以只读方式挂载到容器；缺少 `.env.prod` 或 `config.yaml` 时无法启动。
`flaresolverr` 不开放宿主机端口；非 Docker 部署时，将 `FLARESOLVERR_URL` 指向自行运行的内部服务。

## 配置

环境变量见 [`.env.example`](.env.example)，仅用于 NoneBot 基础配置、全局网络与日志，以及截图页面插件。业务插件配置见 [`config.example.yaml`](config.example.yaml)：插件名为一级键、插件配置项为二级键；ACL 的功能配置位于 `acl.plugins` 列表中。`.env`、`.env.prod` 和 `config.yaml` 均不会提交；敏感项（API Key、exhentai cookie、Sightengine 凭证）只写入本地 `config.yaml`。

| 配置项 | 用途 |
|------|------|
| `SUPERUSERS` | 超级用户 QQ 列表 |
| `acl_*` | `config.yaml` 中的权限、群白名单与配额 |
| `parser_*` | `config.yaml` 中的链接解析媒体限制、平台禁用、可选 cookie/代理 |
| `APP_API_BASE` | 前端 base URL |
| `model` / `openai_api_key` / `openai_api_base` | `config.yaml` 中的 LLM 对话参数 |
| `image_model` / `image_size` / `image_response_format` / `image_timeout` | `config.yaml` 中的 `/draw` 生图参数 |
| `sightengine_api_user` / `sightengine_api_secret` / `c2pa_*` | `config.yaml` 中的 AI 图检测凭证和内嵌 C2PA 校验限制 |
| `eh_ipb_*` / `eh_sk` / `eh_igneous` | `config.yaml` 中的 ExHentai cookie |
| `imgsearch_*` | `config.yaml` 中的反向搜图上游参数 |
| `PROXY` | 可选代理，应用于全部后端外部请求（兼容读取 `HTTP_PROXY` / `HTTPS_PROXY`） |
| `FLARESOLVERR_URL` | FlareSolverr API 地址；Compose 默认 `http://flaresolverr:8191/v1` |

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
