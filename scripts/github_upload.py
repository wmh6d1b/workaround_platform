#!/usr/bin/env python3
"""Safely commit and push the current project without storing GitHub credentials."""

import argparse
import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
TOKEN_ENV = next((os.environ.get(name) for name in ('GITHUB_TOKEN', 'GH_TOKEN') if os.environ.get(name)), None)
SECRET_PATTERNS = {
    'GitHub Token': re.compile(rb'(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|ghu_[A-Za-z0-9]{20,})'),
    'Private Key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}
SENSITIVE_NAMES = re.compile(r'(?:^|/)(?:id_rsa|id_ed25519|credentials(?:\.[^/]+)?|[^/]*\.(?:pem|key|p12|pfx))$', re.I)


def log(message):
    print(f'[github-upload] {message}', flush=True)


def fail(message):
    raise SystemExit(f'[github-upload] 错误：{message}')


def run(command, *, check=True, capture=False, env=None):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=capture, env=env)
    if check and result.returncode:
        if capture:
            sys.stderr.write(result.stdout + result.stderr)
        fail(f'命令执行失败（{result.returncode}）：{" ".join(command)}')
    return result


def git_available():
    git = shutil.which('git')
    if not git:
        return False
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    return subprocess.run([git, '--version'], cwd=ROOT, capture_output=True, env=env).returncode == 0


def is_ancestor(repo, ancestor, descendant):
    if ancestor == descendant:
        return True
    pending = [descendant]
    visited = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        try:
            commit = repo[current]
        except KeyError:
            continue
        for parent in commit.parents:
            if parent == ancestor:
                return True
            pending.append(parent)
    return False


class GitBackend:
    name = 'Git'

    def __init__(self):
        self.git = shutil.which('git')
        self.env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
        self.tempdir = None
        if TOKEN_ENV:
            self.tempdir = tempfile.TemporaryDirectory(dir=ROOT / '.git')
            askpass = Path(self.tempdir.name) / 'askpass.sh'
            askpass.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" "${GITHUB_USERNAME:-x-access-token}" ;; *) printf "%s\\n" "$GITHUB_TOKEN" ;; esac\n')
            askpass.chmod(0o700)
            self.env.update({'GIT_ASKPASS': str(askpass), 'GITHUB_TOKEN': TOKEN_ENV})

    def close(self):
        if self.tempdir:
            self.tempdir.cleanup()

    def call(self, *args, capture=False, check=True):
        return run([self.git, *args], capture=capture, check=check, env=self.env)

    def head(self):
        result = self.call('rev-parse', 'HEAD', capture=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def branch(self):
        return self.call('symbolic-ref', '--short', 'HEAD', capture=True).stdout.strip()

    def set_branch(self, branch):
        current = self.branch()
        if current != branch:
            self.call('branch', '-m', branch)

    def candidates(self):
        output = self.call('ls-files', '--cached', '--others', '--exclude-standard', capture=True).stdout
        return [line for line in output.splitlines() if line]

    def remote_url(self, remote):
        result = self.call('config', '--get', f'remote.{remote}.url', capture=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def remote_head(self, remote, branch):
        result = self.call('ls-remote', '--heads', remote, f'refs/heads/{branch}', capture=True)
        return result.stdout.split()[0] if result.stdout.strip() else None

    def ensure_fast_forward(self, remote_head, branch):
        local = self.head()
        if not remote_head or not local or remote_head == local:
            return
        if self.call('merge-base', '--is-ancestor', remote_head, local, check=False).returncode == 0:
            return
        fail(f'远程 {branch} 包含本地没有的提交。请先备份修改并执行 git pull --rebase，再重新上传；脚本不会自动合并或强推。')

    def stage(self):
        self.call('add', '-A')

    def has_staged_changes(self):
        return self.call('diff', '--cached', '--quiet', check=False).returncode == 1

    def commit(self, message):
        self.call('commit', '-m', message)

    def push(self, remote, branch):
        self.call('push', '-u', remote, f'HEAD:refs/heads/{branch}')


class DulwichBackend:
    name = 'Dulwich'

    def __init__(self, require_auth=True):
        if require_auth and not TOKEN_ENV:
            fail('当前没有可用 Git，Dulwich 后备模式需要通过环境变量 GITHUB_TOKEN 或 GH_TOKEN 提供认证。请仅在当前终端设置，不要写入脚本或仓库。')
        from dulwich import porcelain
        from dulwich.repo import Repo
        self.p = porcelain
        self.repo = Repo(str(ROOT))
        self.auth = {'username': os.environ.get('GITHUB_USERNAME', 'x-access-token'), 'password': TOKEN_ENV}

    def close(self):
        self.repo.close()

    def head(self):
        try:
            return self.repo.head().decode()
        except KeyError:
            return None

    def branch(self):
        value = self.repo.refs.read_ref(b'HEAD').decode()
        return value.rsplit('/', 1)[-1]

    def set_branch(self, branch):
        head = self.head()
        if not head:
            fail('空仓库请先创建初始提交')
        self.repo.refs.set_if_equals(f'refs/heads/{branch}'.encode(), None, head.encode())
        self.repo.refs.set_symbolic_ref(b'HEAD', f'refs/heads/{branch}'.encode())

    def candidates(self):
        tracked = [path.decode() for path in self.repo.open_index()]
        status = self.p.status(self.repo)
        return sorted(set(tracked + [path.decode() if isinstance(path, bytes) else path for path in status.untracked]))

    def remote_url(self, remote):
        try:
            return self.repo.get_config().get((b'remote', remote.encode()), b'url').decode()
        except KeyError:
            return None

    def remote_head(self, remote, branch):
        refs = self.p.ls_remote(self.remote_url(remote), **self.auth)
        value = refs.get(f'refs/heads/{branch}'.encode())
        return value.decode() if value else None

    def ensure_fast_forward(self, remote_head, branch):
        local = self.head()
        if not remote_head or not local or remote_head == local:
            return
        if is_ancestor(self.repo, remote_head.encode(), local.encode()):
            return
        fail(f'远程 {branch} 包含本地没有的提交。请先备份修改并同步远程，再重新上传；脚本不会自动合并或强推。')

    def stage(self):
        status = self.p.status(self.repo)
        deleted = [path for path in status.unstaged if not (ROOT / (path.decode() if isinstance(path, bytes) else path)).exists()]
        self.p.add(self.repo, paths=['.'])
        if deleted:
            self.p.rm(self.repo, paths=deleted)

    def has_staged_changes(self):
        staged = self.p.status(self.repo).staged
        return any(staged.values())

    def commit(self, message):
        self.p.commit(self.repo, message=message)

    def push(self, remote, branch):
        self.p.push(self.repo, remote_location=remote, refspecs=f'HEAD:refs/heads/{branch}', set_upstream=True, **self.auth)


def validate_files(paths):
    problems = []
    for relative in paths:
        normalized = relative.replace('\\', '/')
        basename = normalized.rsplit('/', 1)[-1].lower()
        if (basename == '.env' or basename.startswith('.env.')) and basename not in {'.env.example', '.env.sample', '.env.template'}:
            problems.append(f'{relative}：环境文件可能包含密钥')
            continue
        if SENSITIVE_NAMES.search(normalized):
            problems.append(f'{relative}：疑似私钥或凭证文件')
            continue
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            continue
        content = path.read_bytes()
        if b'\0' in content:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                problems.append(f'{relative}：检测到 {label}')
    if problems:
        fail('安全检查未通过：\n  - ' + '\n  - '.join(problems) + '\n请移除敏感内容或加入 .gitignore 后重试。')
    log(f'敏感文件检查通过（{len(paths)} 个候选文件）')


def run_tests(skip):
    if skip:
        log('已按参数跳过自动测试')
        return
    package = ROOT / 'package.json'
    if package.exists():
        import json
        scripts = json.loads(package.read_text()).get('scripts', {})
        for name in ('test', 'backend:test', 'build'):
            if name in scripts:
                log(f'执行 npm run {name}')
                run(['npm', 'run', name])
    elif (ROOT / 'backend/requirements.txt').exists():
        python = ROOT / '.venv/bin/python'
        if python.exists():
            log('执行后端单元测试')
            run([str(python), '-m', 'unittest', 'discover', '-s', 'backend/tests'])


def parse_args():
    parser = argparse.ArgumentParser(description='安全检查、提交并推送当前项目到 GitHub')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--branch', default='main')
    parser.add_argument('--message', '-m', help='提交说明；有修改时建议显式填写')
    parser.add_argument('--skip-tests', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='只做检查和测试，不提交、不访问远程、不推送')
    return parser.parse_args()


def main():
    args = parse_args()
    if not (ROOT / '.git').exists():
        fail('当前目录尚未初始化 Git，请先初始化并配置远程仓库')
    backend = GitBackend() if git_available() else DulwichBackend(require_auth=not args.dry_run)
    try:
        log(f'使用 {backend.name} 后端')
        paths = backend.candidates()
        validate_files(paths)
        run_tests(args.skip_tests)
        if args.dry_run:
            log('Dry-run 完成：未提交、未访问远程、未推送')
            return
        remote_url = backend.remote_url(args.remote)
        if not remote_url or not remote_url.startswith(('https://github.com/', 'git@github.com:')):
            fail(f'远程 {args.remote} 未配置或不是 GitHub 地址')
        if TOKEN_ENV:
            os.environ['GITHUB_TOKEN'] = TOKEN_ENV
        backend.set_branch(args.branch)
        local_before = backend.head()
        log(f'检查远程 {args.remote}/{args.branch}')
        remote_before = backend.remote_head(args.remote, args.branch)
        backend.ensure_fast_forward(remote_before, args.branch)
        backend.stage()
        if backend.has_staged_changes():
            message = args.message or f'chore: update project {datetime.now():%Y-%m-%d %H:%M}'
            backend.commit(message)
            log(f'已创建提交：{backend.head()}')
        else:
            log('没有需要提交的修改，继续检查是否需要推送')
        local = backend.head()
        if not local:
            fail('没有可推送的提交')
        if local == remote_before:
            log(f'远程已是最新：{local}')
            return
        if local_before and local == local_before:
            backend.ensure_fast_forward(remote_before, args.branch)
        log(f'推送到 {args.remote}/{args.branch}')
        backend.push(args.remote, args.branch)
        remote_after = backend.remote_head(args.remote, args.branch)
        if remote_after != local:
            fail(f'推送后核验失败：本地 {local}，远程 {remote_after}')
        log(f'上传成功并完成远程核验：{remote_after}')
    finally:
        backend.close()


if __name__ == '__main__':
    main()
