#!/usr/bin/env python3
"""WMP 规避子包通用入口，仅依赖 Python 3 标准库。"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys


def resolve_target(value, target_root):
    path = PurePosixPath(value or '.')
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError(f'目标路径必须是安全的绝对路径：{value}')
    if target_root is None:
        return Path(str(path))
    root = Path(target_root).resolve()
    result = root.joinpath(*path.parts[1:]).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f'目标路径超出隔离目录：{value}')
    return result


def read_json(path):
    with path.open('r', encoding='utf-8') as stream:
        return json.load(stream)


def execute_upload(operation, package_dir, target_root):
    params = operation['params']
    destination = resolve_target(params['target_path'], target_root)
    destination.mkdir(parents=True, exist_ok=True)
    overwrite = params.get('overwrite', '覆盖') in ('覆盖', 'overwrite', 'OVERWRITE', True)
    permission = int(str(params.get('permission', '0644')), 8)
    for item in params.get('files', []):
        source = (package_dir / item['stored_path']).resolve()
        if not source.is_relative_to(package_dir.resolve()) or not source.is_file():
            raise ValueError(f"上传文件不存在或路径非法：{item['stored_path']}")
        expected = item.get('sha256')
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if expected and actual != expected:
            raise ValueError(f"文件校验失败：{item['name']}")
        target = destination / PurePosixPath(item['name']).name
        if target.name != item['name']:
            raise ValueError(f"文件名非法：{item['name']}")
        if target.exists() and not overwrite:
            print(f"[SKIP] {target}")
            continue
        target.write_bytes(source.read_bytes())
        os.chmod(target, permission)
        print(f"[UPLOAD] {target}")


def run_command(command, cwd, timeout, expected_exit=0, shell='/bin/bash'):
    print(f'[EXEC] {command}')
    result = subprocess.run(command, cwd=cwd, shell=isinstance(command, str), executable=shell if isinstance(command, str) else None,
                            capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    if result.returncode != expected_exit:
        raise RuntimeError(f'命令退出码 {result.returncode}，期望 {expected_exit}')


def execute_operation(operation, package_dir, target_root):
    operation_type = operation['type']
    params = operation.get('params', {})
    print(f"\n--- 操作 {operation['position']:02d} · {operation_type} ---")
    if operation_type == 'UPLOAD_FILE':
        execute_upload(operation, package_dir, target_root)
        return
    timeout = int(params.get('timeout', 60))
    if operation_type == 'LINUX_COMMAND':
        cwd = resolve_target(params.get('workdir') or '/', target_root)
        if not cwd.is_dir():
            raise ValueError(f'工作目录不存在：{cwd}')
        expected_exit = int(params.get('exit_code', 0))
        run_command(params['command'], cwd, timeout, expected_exit)
        return
    if operation_type == 'SCRIPT':
        arguments = shlex.split(params.get('arguments', ''))
        if params.get('script_type', 'Python') == 'Python':
            command = [sys.executable, '-c', params['script'], *arguments]
        else:
            command = ['/bin/bash', '-c', params['script'], *arguments]
        run_command(command, Path.cwd(), timeout)
        return
    raise ValueError(f'不支持的原子操作类型：{operation_type}')


def main():
    parser = argparse.ArgumentParser(description='执行指定 WKD 规避子包')
    parser.add_argument('package_name', help='规避子包名，即 WKD 编号')
    parser.add_argument('stage', help='pre_upgrade/post_upgrade/post_start/post_init 或自定义阶段名称')
    parser.add_argument('--target-root', help=argparse.SUPPRESS)
    args = parser.parse_args()
    entry_dir = Path(__file__).resolve().parent
    package_dir = (entry_dir / 'packages' / args.package_name).resolve()
    if not package_dir.is_relative_to((entry_dir / 'packages').resolve()):
        raise ValueError('规避子包名非法')
    manifest_path = package_dir / 'package.json'
    if not manifest_path.is_file():
        raise ValueError(f'规避子包不存在：{args.package_name}')
    package = read_json(manifest_path)
    if args.stage != package['stage_parameter']:
        raise ValueError(f"子包 {args.package_name} 不适用于阶段 {args.stage}，应使用 {package['stage_parameter']}")
    if package['wkd'].get('execution_type') != 'AUTOMATED':
        raise ValueError('人工操作 WKD 不支持自动化入口执行')
    print(f"WMP 子包：{args.package_name} · 阶段：{args.stage}")
    for operation in sorted(package['operations'], key=lambda item: item['position']):
        execute_operation(operation, package_dir, args.target_root)
    print('\n[DONE] 规避子包执行完成')


if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        sys.exit(1)
