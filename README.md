# codely-bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node](https://img.shields.io/badge/node-%E2%89%A518-green.svg)](https://nodejs.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)]()

把 [Codely](https://codely.tuanjie.cn) 账号的模型额度变成**标准 OpenAI 兼容接口**，接入
[dsh](https://www.npmjs.com/package/@deepseek-ai/dsh)（DeepSeek Harness）、
[new-api](https://github.com/QuantumNous/new-api) 等任意工具使用。

**背景**：[Codely](https://codely.tuanjie.cn) 是 [Unity 中国](https://www.unity.cn)（Tuanjie / 团结引擎）旗下的
AI 编程智能体，官方 agent 名为 **Tuanjie Cowork**（媒体亦称「团结 Codely」）；账号体系为 Unity ID，
模型推理走 `codely-litellm.tuanjie.cn` 的 LiteLLM 网关。模型额度属于**你自己的 Codely 账号**。

**本项目做什么**：在本地/服务器跑一个小代理，把工具发出的 OpenAI 格式请求转发到 Codely 的 LiteLLM
网关，并自动补上网关强制校验的**客户端身份头、会话标识与请求签名**——这些校验导致第三方工具无法直连
网关（协议细节见 [docs/PROTOCOL.md](docs/PROTOCOL.md)）。**不改造工具、不绕过计费**：用的就是你账号
自己的额度，只是把官方 agent 独占的模型通道「代理」给常用工具用，并提供多账号额度统一管理与一键切换。

> ⚠️ **免责声明**：本项目为**非官方个人项目**，与 Unity 中国 / Codely 无任何隶属关系；接口为个人
> 逆向所得、**随时可能变更**；仅供把自己已购的额度接入常用工具链使用，请遵守 Codely / Unity 服务
> 条款，使用风险自负。如有侵权请联系删除。

## 功能特性

- **OpenAI 兼容代理**：`/v1/chat/completions`、`/v1/models` 全兼容，`sk-` 密钥失效自动刷新
- **网关校验补全**：自动注入身份头、会话标识、`X-Codely-Signature` 请求签名（详见协议笔记）
- **多账号管理**：设备码登录多个 Unity 账号，免重启热切换（凭据、密钥、模型映射全部跟随）
- **额度查询**：CLI / HTTP 双入口，含每日赠送、充值余额、套餐窗口、月度统计
- **每日额度自动调度**：systemd timer 定时检查，主账号额度耗尽自动切备用，0 点重置自动切回
- **真实后端探测**：读取网关透传的 `resp.model`，自动映射别名 → 真实模型代号 + 上下文窗口
- **new-api 集成**：一键把本代理注册为 new-api 渠道（幂等，自动同步 abilities 索引）

## 架构

```
本地形态（dsh 桥接）：

┌─────────┐  OpenAI 格式     ┌────────────────────┐  注入身份头/会话/签名  ┌──────────────────────────────┐
│   dsh   │ ───────────────▶ │   codely-bridge    │ ────────────────────▶ │ codely-litellm.tuanjie.cn/v1 │
│ (任意端) │   :8790/v1      │    （本地代理）      │    sk- 密钥           │      （Codely 额度后端）       │
└─────────┘                  └────────────────────┘                       └──────────────────────────────┘
                                     │  sk- 密钥失效时自动刷新
                                     ▼
   登录凭据（codely-creds.json 或 ~/.codely-cli）──▶ codely.tuanjie.cn/api/api-token/cli-api-key


服务器形态（new-api 集成 + 公网暴露）：

┌──────────┐   OpenAI 格式   ┌─────────────┐  Bearer Key   ┌──────────────────────┐
│  new-api │ ──────────────▶ │ auth-gate   │ ────────────▶ │ codely-proxy         │ ──▶ Codely 网关
│  网关     │  (渠道 upstream) │ :8790 公网  │  校验后转发    │ :8791 仅 loopback    │
└──────────┘                 └─────────────┘               └──────────────────────┘
                                      ▲                            │
                              api-key.txt (600)        额度调度 timer（每 5 分钟）
                                                       耗尽自动切备用账号，0 点回切
```

## 环境要求

- Node.js ≥ 18
- Codely 账号（Unity 账号）——**无需安装 codely CLI**，内置设备码登录；如本机已装并登录过 codely CLI，也可直接复用其登录态
- 本地 dsh 桥接形态还需：已运行过至少一次 dsh（`~/.dsh/` 目录存在）

## 快速开始（本地 dsh 桥接）

```bash
git clone https://github.com/ChisaAlter/codely-bridge.git
cd codely-bridge
npm install

# 1. 设备码登录：终端给出验证链接，浏览器用 Unity 账号授权（无需安装 codely CLI）
npm run login

# 2. 一键安装：换取密钥 + 注册 dsh provider + 写入凭据（幂等，可重复运行）
npm run setup

# 3. 启动代理（保持窗口开启）
npm start
```

然后：

```bash
dsh web          # 模型列表里选 codely 系列
# 或非交互验证：
dsh --profile headless "你好"
```

**启动即实时映射**：代理启动时会自动探测每个 `codely-*` 别名的真实后端（网关透传的 `resp.model`），
把「真实模型代号 + 上下文窗口」同步写入 `~/.dsh/settings.yaml`，dsh 模型选择界面自动刷新真实代号，
官方新放行模型也会自动纳入：

```text
[proxy] 探测真实后端（经本代理，共 5 个 alias）...
[probe]   codely-flash    -> deepseek-v4-flash-0731  (上下文 1M)
[probe]   codely-vl       -> qwen3.5-397b-a17b       (上下文 128K, 支持图片)
[probe]   codely-core     -> glm-5-2-260617          (上下文 128K)
[probe] 已同步模型到 ~/.dsh/settings.yaml，dsh 模型选择界面将自动刷新
```

> `codely-core` 每次探测显示的代号**可能不同**（GLM-5 系多后端负载均衡轮换），属正常现象，见「可用模型」。

把 codely 设为 dsh 默认模型（跳过手选）：

```bash
npm run setup -- --set-default --model codely-core
```

> Windows 下也可以直接双击 `start.cmd` 启动代理。

## 服务器部署形态（new-api 集成 + 公网暴露）

本仓库在生产环境以「公网网关 + 内部代理 + new-api 渠道 + 额度调度」的形态部署在 Linux 服务器上：

### 组件与端口

| 组件 | 端口 | 说明 |
|---|---|---|
| `auth-gate.js` | `0.0.0.0:8790` | **公网入口**。校验 `Authorization: Bearer <key>` 后转发到内部代理；Key 首次运行自动生成到 `api-key.txt`（权限 600），支持 `?key=` 查询参数兜底 |
| `codely-proxy.js` | `127.0.0.1:8791` | 核心代理，**只绑 loopback**。除转发外提供管理端点：`GET /quota`、`GET /accounts`、`POST /account/switch?name=`、`POST /account/login/start|status|cancel` |
| `quota_failover.py` | systemd timer | 每 5 分钟检查当前账号额度，耗尽自动切换（见下） |

```bash
# systemd 单元示例（codely-gate.service / codely-proxy.service）
[Service]
WorkingDirectory=/opt/codely-bridge
ExecStart=/usr/bin/node auth-gate.js          # 或 codely-proxy.js
Restart=always
```

### new-api 渠道集成

```bash
python3 add_codely_channel.py            # 默认写 /opt/new-api/data/one-api.db，也可传自定义 db 路径
```

幂等：同名渠道已存在则合并模型列表并重新同步 abilities 索引（new-api 实际按 abilities 路由，
只插 channels 不同步索引会导致所有请求 `503 model_not_found`）。

### 每日额度自动调度（quota_failover.py）

个人部署用的示例调度器，`systemd timer` 每 5 分钟运行一次，策略：

1. 读取代理内部口 `GET /quota?force=1`，计算当前账号可用额度
2. **主账号剩余 < 100 积分** → 自动切到备用账号，并标记「耗尽至今日重置」
3. **每日 0 点（Asia/Shanghai）额度重置后** → 自动切回主账号
4. **两个账号都耗尽** → 维持现状不抖动，等重置
5. 手动切换过账号的状态会被尊重，调度不抢占

```bash
# 手动跑一次看看
python3 quota_failover.py
```

## 额度结构（实测口径）

Codely 账号每日可用额度由**三个池子**组成（`GET /quota` 的 JSON 各自独立）：

| 池子 | 字段 | 说明 |
|---|---|---|
| **giftCredits 赠送积分** | `giftCredits.remaining_points` | 免费档 **10,000 点/天**，当日 `expires_at`（北京 0 点）过期重发，是每日额度的大头 |
| dailyAllowance 每日津贴 | `dailyAllowance.remaining_points` | 每日 300 点的小额池，同在 0 点重置 |
| billing 充值余额 | `billing.effective_available_points` | 充值积分，不清零 |

> 消耗参考：`codely-core`（GLM-5 系，128K 上下文）单次结算约 200+ 积分，是重度使用的大头；
> `codely-flash/air/basic`（DeepSeek-V4-Flash）单次消耗通常 < 1 积分。

## 多账号管理

支持把**多个 Codely 账号**登录并保存，随时切换（额度 / 模型 / 密钥全部跟随，**无需重启代理**）：

```
账号注册表（accounts/，已 gitignore）
  accounts/index.json     当前账号 + 账号列表
  accounts/<name>.json    各账号登录凭据
  codely-creds.json       始终等于「当前激活账号」凭据（老链路零改动）
```

```bash
npm run account -- list                 # 列出已登录账号（* 标记当前）
npm run account -- login my-team-a      # 设备码登录新账号并设为当前（浏览器授权）
npm run account -- switch my-team-b     # 切到另一账号（代理运行时自动重探模型映射）
npm run account -- show                 # 查看当前账号详情
npm run account -- remove my-team-a     # 删除账号（删当前账号时自动切到剩下的第一个）
```

> ⚠️ 设备码授权跟随浏览器会话：官方授权页是 Unity ID 登录页，**主浏览器直接打开会瞬间授权当前账号
> 并消耗设备码**。添加另一个账号请：复制验证链接 → **无痕窗口 / 另一浏览器**打开 → 登录另一 Unity
> 账号 → 授权。

## 可用模型

模型列表在 `npm run setup` 时**实时查询** `/v1/models` 自动写入，不写死——不同账号可用的模型不同。
下表为实测（2026-09，随网关部署可能变化）：

| 别名（必须用 alias） | 真实后端（网关透传 `resp.model`） | 上下文窗口 |
|---|---|---|
| `codely-core` | `glm-5-fp8-128k` / `glm-5-2-260617`（GLM-5 多部署轮换） | **128K**（非 1M） |
| `codely-flash` / `codely-air` / `codely-basic` | `deepseek-v4-flash-0731` | 1M |
| `codely-vl` | `qwen3.5-397b-a17b`（Qwen3.5 MoE，支持图片） | 128K |

> - `id` 必须是 alias：网关只放行 `codely-*`，直接改真实代号会 `401 team not allowed to access model`
> - 判断一个 alias「是什么」应看**系/家族**（core=GLM-5 系、flash/air/basic=DeepSeek-V4-Flash、vl=Qwen3.5），
>   而非某一次透传的精确版本号
> - 查看当前账号实际可用模型：`npm run models`；核对真实后端：`npm run backend-probe`

## 命令一览

| 命令 | 作用 |
|---|---|
| `npm run login` | 独立登录（设备码流程，凭据存 `codely-creds.json`，同时登记到账号注册表） |
| `npm run account -- <sub>` | 多账号管理（list / switch / login / remove / show） |
| `npm run models` | 查询当前账号可用的模型列表 |
| `npm run backend-probe` | 探测 `codely-*` 别名背后的真实后端模型 |
| `npm run quota` | 终端查看积分余额（每日赠送/充值余额/月度统计，`--force` 强制刷新） |
| `npm run setup` | 安装/更新 dsh 配置（幂等；修改前自动备份为 `*.bak-codely`） |
| `npm start` | 启动代理（默认 `127.0.0.1:8790`，`--port N` 可改端口） |
| `node auth-gate.js` | 启动公网网关（环境变量 `GATE_PORT` / `GATE_BIND` / `UPSTREAM_PORT` / `CODELY_PROXY_API_KEY`） |
| `python3 add_codely_channel.py [db]` | 注册为 new-api 渠道（幂等） |
| `python3 quota_failover.py` | 额度调度检查（配合 systemd timer 使用） |
| `npm test` | 冒烟测试（healthz / models / 一次对话） |
| `npm run uninstall` | 回滚 dsh 配置（优先恢复备份） |

## 它改了哪些东西

| 文件 | 改动 |
|---|---|
| `~/.dsh/settings.yaml` | `llm-pi-ai.providers` 下新增 `codely` 条目（指向 `http://127.0.0.1:8790/v1`） |
| `~/.dsh/.credentials.yaml` | 新增 `CODELY_API_KEY` |
| 本目录 `codely-creds.json` | 当前激活账号凭据（已 gitignore） |
| 本目录 `accounts/` | 多账号注册表（已 gitignore） |
| 本目录 `key.cache` / `session.cache` | 代理运行时状态（已 gitignore） |
| 本目录 `api-key.txt` | auth-gate 的公网 API Key（已 gitignore，自动生成，权限 600） |

> setup 会用 YAML 库重写 dsh 配置文件，**原文件中的注释会丢失**，因此修改前会先做备份。
>
> 注：上游版本还附带一个 dsh「额度悬浮圈」插件（`plugins/dsh-codely-quota`），本仓库为服务器精简版
> **未包含该插件**，`setup` 检测到缺失时自动跳过装配，其余功能不受影响。

## 故障排查

| 现象 | 原因与处理 |
|---|---|
| 客户端报 `ECONNREFUSED 127.0.0.1:8790` | 代理没启动，先 `npm start`（或服务器的 `auth-gate`） |
| 网关返回欢迎语 `欢迎使用Codely, 访问 …` | 请求没走代理直连了网关，UA 校验未过——检查 baseURL 指向代理 |
| `非法session` | 会话标识缺失——请求必须经过代理（或代理版本过旧） |
| 代理日志反复 `上游返回 401` | 密钥失效且自动刷新失败 → 重新 `npm run login`，再 `npm run setup` |
| `team not allowed to access model` | 团队白名单只含 `codely-*` 别名，GLM 等命名不可直连 → 改用列表内别名 |
| 想确认代理状态 | `curl http://127.0.0.1:8790/healthz` |

## 安全须知

- `codely-creds.json`、`accounts/`、`key.cache`、`session.cache`、`api-key.txt` 都含账号级密钥，
  **已全部 gitignore，请勿外传**
- 代理与 auth-gate 默认只在该暴露的地址监听：`codely-proxy` 仅 loopback，公网暴露必须走 `auth-gate`
  （带 Bearer Key 校验）；不要把 8791 直接绑到 `0.0.0.0`
- 本项目仅供个人把自己已购的 Codely 额度接入自己常用的工具；请遵守 Codely 服务条款

## 目录结构

```
codely-bridge/
├── codely-proxy.js    # 核心代理（转发 + 注入身份头/会话/签名 + /quota /accounts /account/switch 端点）
├── auth-gate.js       # 公网网关层（Bearer Key 校验 → 转发内部代理）
├── codely-auth.js     # 凭据管理（本地 creds 优先，官方 CLI 回退，access_token 自动刷新 + 请求签名）
├── codely-config.js   # 端口/上游/别名等配置
├── login.js           # 设备码登录（免装 codely CLI）
├── account.js         # 多账号管理 CLI（list / switch / login / remove / show）
├── codely-accounts.js # 多账号注册表（accounts/ 读写、切换、凭据指纹）
├── codely-quota.js    # 积分余额查询（CLI：npm run quota）
├── models.js          # 可用模型查询
├── backend-probe.js   # 真实后端探测（读网关透传 resp.model）
├── setup.js           # dsh 安装脚本（幂等）
├── uninstall.js       # dsh 回滚脚本
├── start.cmd          # Windows 一键启动
├── quota_failover.py  # 每日额度自动调度（配合 systemd timer）
├── add_codely_channel.py       # new-api 渠道注册（幂等，同步 abilities）
├── rotate_keys.py              # 轮换 new-api 对外 token 与网关内部 key
├── verify_newapi.py            # new-api 端到端验证（从库中取 token 实测对话）
├── inspect_api.py / probe_*.py / check_*.py / what_is_core.py / compare_glm.py / dump_core.py / list_call_info.py
│                               # 协议逆向与调试工具集（探测别名/视觉能力/上下文/GLM 通道等）
├── accounts/          # 多账号注册表（运行时生成，gitignored）
├── test/smoke.js      # 冒烟测试
└── docs/PROTOCOL.md   # 网关协议逆向笔记（维护必读）
```

## License

[MIT](LICENSE)
