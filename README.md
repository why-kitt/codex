# codex-patched-builder

手动触发的 GitHub Actions 构建：拉取 `openai/codex` 最新 release tag → 用精确文本替换脚本打补丁 → 构建 Windows x64 的 `codex.exe` 及配套 helper → 组装官方完整包布局 → 上传 Artifact 并发布到本私有仓库的 Release。

## 目录结构

```
.github/workflows/build-windows-x64.yml   # 构建流水线（手动触发）
patches/reconnect.json                    # 基础重连补丁
patches/runtime-console.json              # 进程内重连设置与 Windows 后台命令窗口修复
patches/stateless-responses.json           # 轮换上游资源的中转站兼容模式
patches/subagent-full-access.json          # 主对话 Full Access 权限同步
scripts/apply_patches.py                  # 补丁应用器（断言锚点唯一命中；支持新建文件）
```

## 使用

1. 把本目录内容推到你的私有仓库。
2. GitHub → Actions → **Build patched Windows x64** → **Run workflow**。
   - `tag` 留空 = 取 `openai/codex` 最新正式 release；本版已适配 `rust-v0.172.0`（2026-11-24 发布，源码 commit `3d86e43b075adeba2193ec5c22ac92f55afd82e6`）。指定这个 tag 可复现本版轻量检查；其他版本须重新核对锚点和接口。
   - `publish_release` 控制是否发 Release（只跑构建时取消勾选，省存储）。
3. 产物：
   - **Artifact** `codex-windows-x64`（保留 7 天）：`codex-<tag>-windows-x64.zip`（完整包）+ `.patch`（打过的完整 diff）。
   - **Release** `patched-<tag>`：同样的 zip 和 patch。

### 完整包布局与使用

zip 由官方 `scripts/build_codex_package.py` 组装，和 `openai/codex` 发布的包同一布局：

```
codex-package.json                      # daemon 识别包用的 manifest
bin/codex.exe                           # 入口
bin/codex-code-mode-host.exe            # code mode / AnySearch 宿主
bin/codex-exec-server.exe               # 上游新增的独立执行服务
codex-path/rg.exe                       # 打包时自动下载（DotSlash manifest）
codex-resources/codex-command-runner.exe
codex-resources/codex-windows-sandbox-setup.exe
```

解压后直接运行 `bin\codex.exe`。普通本地会话默认使用**进程内后端**，不会接入或自动安装共享 daemon，避免前台有补丁而后台被官方更新替换。AnySearch/命令工具从完整包中解析宿主。显式远程会话和 `codex agents` 保留上游行为；远程会话不支持本地 `/reconnect` 覆盖。

流水线从上游 `codex-rs/rust-toolchain.toml` 读取 Rust 版本（本版为 `1.99.1`），并显式构建、打包 `codex-exec-server.exe`，避免打包步骤另行启动默认配置的 Cargo 构建。

Windows CI 在依赖解析前启用 Git 长路径，并设置 `CARGO_NET_GIT_FETCH_WITH_CLI=true`，与上游 `setup-ci` 一致，支持检出新版 `rusty_v8` 的 Chromium/Rust 子模块。

上游如果重构了锚点代码，`apply_patches.py` 会直接报锚点命中数不符并让构建失败（不会输出半打补丁的产物）。

## `[reconnect]` 启动默认配置

`config.toml`：

```toml
[reconnect]
mode = "fixed"        # "default" = 原有指数退避+抖动；"fixed" = 固定间隔
interval_ms = 3000    # fixed 模式下每次重连固定等待 3 秒（必填，> 0）
max_retries = 5000    # 可选：覆盖 stream_max_retries（默认 5，原硬上限 100 → 现 10000）
```

- `mode = "fixed"` 时忽略服务端 `Retry-After`，始终按 `interval_ms` 重试；若服务端建议更长，会打一条 `warn!` 日志（不改变行为）。
- `max_retries` 之所以需要单独一个开关：`openai` 是保留的 provider id，不能用 `[model_providers.openai]` 设置 `stream_max_retries`。
- 不配置 `[reconnect]` 时重试策略沿用上游默认；本地会话仍默认使用进程内后端。

## `/reconnect` 命令（TUI 内动态调整）

启动时读取配置作为默认值。TUI 的 `/reconnect` **只覆盖当前 CLI 进程的内存设置**，不写入 `config.toml`；普通请求在下一次决定是否重试时采用新设置，已经开始的等待不被中断。覆盖持续到进程退出，新进程重新读取配置默认值。

```
/reconnect                      # 查看当前生效设置
/reconnect default              # 使用指数退避 + 抖动，保留当前重试次数覆盖
/reconnect fixed 3000           # 本进程固定 3 秒重连间隔
/reconnect retries 5000         # 本进程覆盖重试次数为 5000
/reconnect retries default      # 本进程使用 provider 重试次数
```

- 无参 `/reconnect` 回显：`Reconnect settings: mode=fixed every 3000ms, max_retries=provider default`。
- 修改成功后回显 `Reconnect settings updated: ...; active until this process exits; config.toml unchanged`。
- 参数非法时回显 `Usage: /reconnect [default | fixed <interval_ms> | retries <max_retries|default>]`，不改变运行参数，也不写配置。
- 显式设置重试次数时，网络连接失败也遵循该上限；不设上限时保留上游的网络恢复重试策略。
- 重试次数接受 1–10000；远程压缩仍保留上游独立的重试上限。
- 命令在任务运行中、side conversation、queued（排队）场景下均可用，行为与 `/status` 一致。
- `fixed` 要求 `interval_ms > 0`；配置层加载时会校验，`/reconnect fixed 0` 直接被解析层拒绝。

## Windows 命令窗口

`rust-v0.162.1` 已包含捕获输出的后台命令窗口修复，包括 Job 管理的 Git、hook、凭据命令、shell snapshot，以及 legacy 沙箱的非交互管道分支。本版移除这些重复旧补丁，保留上游实现。交互式命令仍走 ConPTY，不关闭沙箱。

上游相关报告：[Windows daemon 请求期间反复闪出终端窗口 #48074](https://github.com/openai/codex/issues/48074)。

## 轮换上游资源的中转站

仅在会轮换 Azure/OpenAI 上游资源的自定义 provider 上显式开启：

```toml
[model_providers.custom.capabilities]
stateless_responses = true
```

`custom` 必须与实际 `model_provider` 一致。无需添加 `store = false` 或 `disable_response_storage`；上游已经固定发送 `store: false`，这两个配置键不是本补丁的开关。

- 主对话和继承同一 provider 的子代理、工具续接、普通历史恢复均使用公共出站处理，不需要分别配置子代理。
- 每次请求清除历史条目的 `id`，保留工具配对用的 `call_id`、工具参数、结果和可见消息；只改请求副本，不改本地 rollout 或历史存储。
- 不再请求或回传加密 reasoning，避免资源绑定的推理状态随路由切换失效。这会放弃跨请求的隐藏推理连续性，但不关闭当前请求的模型推理。
- 强制使用完整历史 HTTP 请求，不使用 WebSocket 增量续接或 `previous_response_id`；强制本地压缩，避免生成资源绑定的远程压缩状态。
- 已含远程 `compaction` / `context_compaction` 的旧历史无法无损还原。补丁明确报错并提示新建对话或回到原资源，不会偷偷丢弃压缩上下文。
- 默认关闭，官方 `OpenAI` provider 忽略该开关；不影响未开启该选项的 provider。

这是客户端的可移植历史兼容模式，不会控制中转站选路，也不保证支持中转站私有工具或其他资源绑定资产。开启后建议新建会话；已经运行的进程需要重启才能加载新配置。

## 子代理继承 Full Access

在 `config.toml` 中启用，重新启动 Codex 后生效：

```toml
[agents]
inherit_full_access = true
```

默认关闭。启用后，主对话选择 Full Access 时，同一代理树中的已有、新建及重新加载的子代理同步执行权限；主对话启动时已经是 Full Access 也会继承。首次启用 Full Access 后，主对话切回受限权限也同步子代理。

已有子代理的后续工具调用和未来轮次使用新权限，已经启动的工具进程沿用启动时的权限。同步保留子代理的模型、角色、执行环境和工作目录，通过现有的权限约束校验；无法同步时发出警告。内部审查代理保留自身策略。

针对两种子代理后端、开关关闭、运行中工具调用和卸载后重新加载的回归测试：

```powershell
just test -p codex-core --test subagent_permissions
```

## 成本注意（GitHub Free）

- Windows runner 计时按 **2 倍**分钟数消耗（2000 分钟/月 ≈ 1000 Windows 分钟），单次冷构建约 **60–120 分钟**（缓存命中后约 20–40 分钟）。
- 日志在大 crate（`codex-core`、`codex-tui`）编译期间会长时间没有新输出，这是正常的；5 分钟一行的 `rustc_cpu_s` 心跳会持续刷新，构建步超时 170 分钟、job 总超时 240 分钟。
- Artifact 存储免费额度 500 MB，完整包 zip 含 5 个 Codex 二进制及 `rg.exe`，只保留 7 天。
- 超额后 Actions 直接不可用（默认 $0 上限，不会扣费）。

本次 tag 适配的验证结果及未执行检查见 [VALIDATION.md](VALIDATION.md)。

## 补丁维护

适配新 release 时先做轻量检查，将完整构建交给 GitHub Actions：

1. 本地 checkout 同一 tag，跑 `python scripts/apply_patches.py --root <checkout> --check`，一次列出失效锚点。
2. 核对上游构造器、请求参数、配置结构和打包接口；新建文件中的代码也需要核对。用现有 `rustfmt` 做语法与格式检查，不必为版本适配先全量编译。行为变更需要时再跑针对性回归。
3. 把每处改动的原文（`find`）和新文（`replace`）追加进对应补丁 JSON，`expect` 保持 `1`；补丁按文件名顺序应用，后续锚点应匹配前序补丁的结果。
4. 在干净 checkout 上检查并应用补丁，核对最终 diff；更新 [VALIDATION.md](VALIDATION.md)，明确本次执行及跳过的检查。
