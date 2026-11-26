# rust-v0.172.0 轻量适配验证

2026-11-26 拉取上游最新正式 release：[`rust-v0.172.0`](https://github.com/openai/codex/releases/tag/rust-v0.172.0)（2026-11-24 发布）。源码基线：`3d86e43b075adeba2193ec5c22ac92f55afd82e6`。

- 4 组补丁在干净 release 源码上检查、应用：100 项编辑全部通过，覆盖 41 个文件；最终源码与补丁预览逐文件一致。
- 40 个 Rust 文件通过本机已有的 Rust 1.95.0 `rustfmt --check --edition 2024 --config skip_children=true`。这是语法与格式检查，不是 Rust 1.99.1 类型检查。
- 核对并适配模型客户端构造器、`Arc<Prompt>` 请求参数、会话权限同步和子代理环境快照；移除上游已包含的 `StepContext` 共享数据补丁。现有回归测试源码已适配，未执行测试。
- 工作流 YAML、7 段 Bash 和 6 段 PowerShell 通过语法检查。CI 自动读取上游工具链 `1.99.1`，显式构建并提供新增的 `codex-exec-server.exe`。
- 配置 schema 的 JSON、本地引用和 3 个补丁配置入口检查通过；未运行 Cargo schema 生成器。
- 用 6 个占位文件运行上游官方 Windows 打包脚本：完整布局、ZIP 和 manifest 的 `execServer` 字段检查通过，未调用 Cargo。占位包不代表真实二进制构建或运行通过。
- 按用户要求未运行本地 `cargo build`、`cargo check`、测试或 Clippy，未安装新 Rust 工具链，未构建最终 Windows 发布包；尚未运行本次 GitHub Actions 构建。
- 临时源码和检查产物位于 `.tmp/upstream-rust-v0.172.0` 与 `.tmp/v172-adaptation`，不属于发布产物。
