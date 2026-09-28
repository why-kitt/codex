# codex-patched-builder

手动触发的 GitHub Actions 构建：拉取 `openai/codex` 最新 release tag → 用精确文本替换脚本打补丁 → 构建 Windows x64 的 `codex.exe` 及配套 helper → 组装官方完整包布局 → 上传 Artifact 并发布到本私有仓库的 Release。

## 目录结构

```
.github/workflows/build-windows-x64.yml   # 构建流水线（手动触发）
patches/reconnect.json                    # 29 条精确替换规则（含 2 个新增文件）
scripts/apply_patches.py                  # 补丁应用器（断言锚点唯一命中；支持新建文件）
```

## 使用

1. 把本目录内容推到你的私有仓库。
2. GitHub → Actions → **Build patched Windows x64** → **Run workflow**。
   - `tag` 留空 = 取 `openai/codex` 最新 release（当前为 `rust-v0.157.1`）；也可填指定 tag。
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

解压后直接运行 `bin\codex.exe` 即可：**无需 `--no-daemon`**（后台 daemon 通过 `validate_package` 检查），AnySearch/命令工具也能找到宿主。注意 `CODEX_HOME`（默认 `~/.codex`）不要放在解压目录里面。

上游如果重构了锚点代码，`apply_patches.py` 会直接报锚点命中数不符并让构建失败（不会输出半打补丁的产物）。

## `[reconnect]` 配置

`config.toml`：

```toml
[reconnect]
mode = "fixed"        # "default" = 原有指数退避+抖动；"fixed" = 固定间隔
interval_ms = 3000    # fixed 模式下每次重连固定等待 3 秒（必填，> 0）
max_retries = 5000    # 可选：覆盖 stream_max_retries（默认 5，原硬上限 100 → 现 10000）
```

- `mode = "fixed"` 时忽略服务端 `Retry-After`，始终按 `interval_ms` 重试；若服务端建议更长，会打一条 `warn!` 日志（不改变行为）。
- `max_retries` 之所以需要单独一个开关：`openai` 是保留的 provider id，不能用 `[model_providers.openai]` 设置 `stream_max_retries`。
- 不配置 `[reconnect]` 时行为与上游完全一致。

## `/reconnect` 命令（TUI 内动态调整）

构建出的 `codex.exe` 在 TUI 里新增一个斜杠命令，**运行时直接读改写 `~/.codex/config.toml`，下一回合生效**（通过 app-server 的 `config/batchWrite`，无需重启）：

```
/reconnect                      # 查看当前生效设置
/reconnect default              # 恢复上游默认：指数退避 + 抖动，重试次数用 provider 默认值
/reconnect fixed 3000           # 固定 3 秒重连间隔（写 mode="fixed", interval_ms=3000）
/reconnect retries 5000         # 覆盖 stream_max_retries = 5000
/reconnect retries default      # 取消覆盖，回到 provider 默认
```

- 无参 `/reconnect` 回显：`Reconnect settings: mode=fixed every 3000ms, max_retries=provider default`。
- 修改成功后回显 `Reconnect settings updated: ...; applies from the next turn`。
- 参数非法时回显 `Usage: /reconnect [default | fixed <interval_ms> | retries <max_retries|default>]`，不写任何配置。
- 命令在任务运行中、side conversation、queued（排队）场景下均可用，行为与 `/status` 一致。
- `fixed` 要求 `interval_ms > 0`；配置层加载时会校验，`/reconnect fixed 0` 直接被解析层拒绝。

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
