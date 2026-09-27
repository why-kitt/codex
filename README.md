# codex-patched-builder

手动触发的 GitHub Actions 构建：拉取 `openai/codex` 最新 release tag → 用精确文本替换脚本打补丁 → 构建 Windows x64 的 `codex.exe` → 上传 Artifact 并发布到本私有仓库的 Release。

## 目录结构

```
.github/workflows/build-windows-x64.yml   # 构建流水线（手动触发）
patches/reconnect.json                    # 13 条精确替换规则
scripts/apply_patches.py                  # 补丁应用器（断言锚点唯一命中）
```

## 使用

1. 把本目录内容推到你的私有仓库。
2. GitHub → Actions → **Build patched Windows x64** → **Run workflow**。
   - `tag` 留空 = 取 `openai/codex` 最新 release（当前为 `rust-v0.157.1`）；也可填指定 tag。
   - `publish_release` 控制是否发 Release（只跑构建时取消勾选，省存储）。
3. 产物：
   - **Artifact** `codex-windows-x64`（保留 7 天）：`codex-<tag>-windows-x64.zip` + `.patch`（打过的完整 diff）。
   - **Release** `patched-<tag>`：同样的 zip 和 patch。

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

## 成本注意（GitHub Free）

- Windows runner 计时按 **2 倍**分钟数消耗（2000 分钟/月 ≈ 1000 Windows 分钟），单次冷构建约 20–30 分钟。
- Artifact 存储免费额度 500 MB，`codex.exe` 约 200 MB，所以默认打成 zip（约几十 MB）并只保留 7 天。
- 超额后 Actions 直接不可用（默认 $0 上限，不会扣费）。

## 补丁维护

修改代码逻辑时：

1. 本地 checkout 同一 tag，跑 `python scripts/apply_patches.py --root <checkout>`。
2. 改代码 → `cargo fmt` / `cargo clippy` / `just test -p codex-config` 验证。
3. 把每处改动的原文（`find`）和新文（`replace`）追加进 `patches/reconnect.json`，`expect` 保持 `1`。
4. `python scripts/apply_patches.py --root <干净 checkout> --check` 验证所有锚点仍然唯一命中。
