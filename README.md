# codex-patched-builder

手动触发的 GitHub Actions 构建：拉取 `openai/codex` 最新 release tag → 用精确文本替换脚本打补丁 → 构建 Windows x64 的 `codex.exe` 及配套 helper → 组装官方完整包布局 → 上传 Artifact 并发布到本私有仓库的 Release。

## 目录结构

```
.github/workflows/build-windows-x64.yml   # 构建流水线（手动触发）
patches/reconnect.json                    # 基础重连补丁
patches/runtime-console.json              # 进程内重连设置与 Windows 后台命令窗口修复
scripts/apply_patches.py                  # 补丁应用器（断言锚点唯一命中；支持新建文件）
```

## 使用

1. 把本目录内容推到你的私有仓库。
2. GitHub → Actions → **Build patched Windows x64** → **Run workflow**。
   - `tag` 留空 = 取 `openai/codex` 最新 release（补丁锚点跟随最新 release，已验证锚点兼容 `rust-v0.158.0` / `rust-v0.159.0`）；也可填指定 tag（须与锚点版本一致，否则 apply 步骤会报 anchor mismatch）。
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
codex-path/rg.exe                       # 打包时自动下载（DotSlash manifest）
codex-resources/codex-command-runner.exe
codex-resources/codex-windows-sandbox-setup.exe
```

解压后直接运行 `bin\codex.exe`。普通本地会话默认使用**进程内后端**，不会接入或自动安装共享 daemon，避免前台有补丁而后台被官方更新替换。AnySearch/命令工具从完整包中解析宿主。显式远程会话和 `codex agents` 保留上游行为；远程会话不支持本地 `/reconnect` 覆盖。

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

补丁为捕获输出的后台命令保留 `CREATE_NO_WINDOW`，包括 Job 管理的 Git、hook、凭据命令、shell snapshot，以及 legacy 沙箱的非交互管道分支。交互式命令仍走 ConPTY，不关闭沙箱。

上游相关报告：[Windows daemon 请求期间反复闪出终端窗口 #48074](https://github.com/openai/codex/issues/48074)。

## 成本注意（GitHub Free）

- Windows runner 计时按 **2 倍**分钟数消耗（2000 分钟/月 ≈ 1000 Windows 分钟），单次冷构建约 **60–120 分钟**（缓存命中后约 20–40 分钟）。
- 日志在大 crate（`codex-core`、`codex-tui`）编译期间会长时间没有新输出，这是正常的；5 分钟一行的 `rustc_cpu_s` 心跳会持续刷新，构建步超时 170 分钟、job 总超时 240 分钟。
- Artifact 存储免费额度 500 MB，完整包 zip 含 4 个二进制，打包后仍在额度内，并且只保留 7 天。
- 超额后 Actions 直接不可用（默认 $0 上限，不会扣费）。

## 补丁维护

修改代码逻辑时：

1. 本地 checkout 同一 tag，跑 `python scripts/apply_patches.py --root <checkout>`。
2. 改代码 → `cargo fmt` / `cargo clippy` / `just test -p codex-config` 验证。
3. 把每处改动的原文（`find`）和新文（`replace`）追加进 `patches/reconnect.json`，`expect` 保持 `1`。
4. `python scripts/apply_patches.py --root <干净 checkout> --check` 验证所有锚点仍然唯一命中。
