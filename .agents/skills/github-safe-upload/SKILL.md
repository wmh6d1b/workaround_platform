---
name: github-safe-upload
description: 将当前工程安全上传、提交或更新到 GitHub。用户说“上传 GitHub”“推送工程”“一键更新远程仓库”“提交并同步代码”时使用。执行敏感文件检查、自动测试、提交、快进检查和远程推送核验；优先使用项目脚本 scripts/github-upload.sh。
---

# GitHub 安全上传

使用项目根目录的 `scripts/github-upload.sh`，不要另写一次性上传流程。

## 操作前

1. 确认当前目录是工程根目录，远程是用户指定的 GitHub 仓库。
2. 不打印 Token，不要求用户在聊天中粘贴 Token。优先复用本机 Git 凭证。
3. 当前没有可用 Git 时，脚本使用项目 `.venv` 中的 Dulwich；此模式优先读取终端的 `GITHUB_TOKEN` 或 `GH_TOKEN`，未设置时读取 `.secrets/github-token`。该目录已被 Git 忽略，文件必须只有一行且权限为 `600`，Token 仅授予目标仓库 Contents 读写权限。
4. 不自动强推、不自动合并远程冲突、不跳过远程核验。

## 标准流程

先做安全预检：

```bash
./scripts/github-upload.sh --dry-run
```

正式上传并写明本次变更：

```bash
./scripts/github-upload.sh --message "feat: 简要说明本次修改"
```

也可使用：

```bash
npm run github:upload -- --message "feat: 简要说明本次修改"
```

脚本默认推送到 `origin/main`。仅在用户指定其他远程或分支时添加 `--remote`、`--branch`。

脚本会依次：

1. 检查 `.env`、私钥、GitHub Token 等敏感内容。
2. 执行项目已有的测试与构建；只有用户明确要求时才使用 `--skip-tests`。
3. 检查远程分支是否可快进，发现分叉则停止并提示先同步。
4. 暂存全部已检查修改并提交。
5. 推送后重新读取远程分支，确认远程 SHA 与本地 HEAD 一致。

## 认证故障

- 有 Git：让用户先在本机完成一次 GitHub 授权，不在聊天中接收凭证。
- 无 Git、使用 Dulwich：优先提示用户在当前终端安全设置环境变量，也可由用户亲自将 Token 写入本地忽略文件；不要在聊天中接收或打印 Token：

```bash
read -s GITHUB_TOKEN
export GITHUB_TOKEN
```

本地文件方式（环境变量优先于文件）：

```bash
mkdir -p .secrets
chmod 700 .secrets
umask 077
read -s GITHUB_TOKEN
printf '%s\n' "$GITHUB_TOKEN" > .secrets/github-token
unset GITHUB_TOKEN
```

不要在命令参数中直接写 Token。文件权限不是 `600`、内容为空或超过一行时，脚本必须停止。

- 远程拒绝时，保留本地提交，报告未推送，不反复重试，不改写远程历史。

## 完成标准

只有推送后远程 SHA 与本地 HEAD 一致，才报告上传成功。最终给出仓库、分支、提交 SHA 和测试结果；若认证或网络阻塞，明确区分“已本地提交”和“已远程上传”。
