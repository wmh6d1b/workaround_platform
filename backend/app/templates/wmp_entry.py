#!/usr/bin/env python3
"""WMP 规避子包通用入口，仅依赖 Python 3 标准库。"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import signal
import subprocess
import sys
import tempfile
import threading


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
        target = destination / PurePosixPath(item['name']).name
        if target.name != item['name']:
            raise ValueError(f"文件名非法：{item['name']}")
        if target.exists() and not overwrite:
            print(f"[SKIP] {target}")
            continue
        digest = hashlib.sha256()
        temp_path = None
        try:
            with source.open('rb') as src, tempfile.NamedTemporaryFile(dir=destination, prefix=f'.{target.name}.', delete=False) as tmp:
                temp_path = Path(tmp.name)
                while chunk := src.read(1024 * 1024):
                    digest.update(chunk)
                    tmp.write(chunk)
            expected = item.get('sha256')
            if expected and digest.hexdigest() != expected:
                raise ValueError(f"文件校验失败：{item['name']}")
            os.replace(temp_path, target)
            temp_path = None
            os.chmod(target, permission)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        print(f"[UPLOAD] {target}")


def run_command(command, cwd, timeout, expected_exit=0, shell='/bin/bash'):
    print(f'[EXEC] {command}')
    process = subprocess.Popen(command, cwd=cwd, shell=isinstance(command, str),
        executable=shell if isinstance(command, str) else None, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)

    def forward_output():
        for line in process.stdout:
            print(line, end='')

    output_thread = threading.Thread(target=forward_output, daemon=True)
    output_thread.start()
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        output_thread.join(timeout=5)
        raise
    output_thread.join(timeout=5)
    process.stdout.close()
    if returncode != expected_exit:
        raise RuntimeError(f'命令退出码 {returncode}，期望 {expected_exit}')


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


def load_package(entry_dir, package_name):
    package_dir = (entry_dir / 'packages' / package_name).resolve()
    if not package_dir.is_relative_to((entry_dir / 'packages').resolve()):
        raise ValueError('规避子包名非法')
    manifest_path = package_dir / 'package.json'
    if not manifest_path.is_file():
        raise ValueError(f'规避子包不存在：{package_name}')
    return package_dir, read_json(manifest_path)


def execute_package(entry_dir, package_name, stage, target_root):
    package_dir, package = load_package(entry_dir, package_name)
    if stage != package['stage_parameter']:
        raise ValueError(f"子包 {package_name} 不适用于阶段 {stage}，应使用 {package['stage_parameter']}")
    if package['wkd'].get('execution_type') != 'AUTOMATED':
        raise ValueError('人工操作 WKD 不支持自动化入口执行')
    title = package['wkd'].get('title') or package_name
    print(f"\n===== WMP 子包：{package_name} · {title} · 阶段：{stage} =====")
    for operation in sorted(package['operations'], key=lambda item: item['position']):
        execute_operation(operation, package_dir, target_root)
    print(f'[DONE] {package_name} 执行完成')


def list_packages(entries, entry_dir):
    print('WKD 编号\t阶段参数\t操作数\t标题')
    for item in entries:
        _, package = load_package(entry_dir, item['package_name'])
        stage = item['stage_parameter'] or ('人工操作' if package['wkd'].get('execution_type') == 'MANUAL' else '-')
        print(f"{item['package_name']}\t{stage}\t{item['operation_count']}\t{package['wkd'].get('title', '')}")


def main():
    parser = argparse.ArgumentParser(
        description='按阶段执行 WKD 规避包；默认执行全部匹配子包，可用 --wkd 指定单个子包')
    parser.add_argument('targets', nargs='*', metavar='参数',
                        help='新用法：<阶段参数>；兼容旧用法：<WKD编号> <阶段参数>')
    parser.add_argument('--wkd', dest='package_name', help='仅执行指定 WKD 编号')
    parser.add_argument('--list', action='store_true', help='列出包内 WKD 和阶段，不执行')
    parser.add_argument('--target-root', help=argparse.SUPPRESS)
    args = parser.parse_args()
    entry_dir = Path(__file__).resolve().parent
    manifest = read_json(entry_dir / 'MANIFEST.json')
    entries = manifest.get('packages', [])
    if args.list:
        if args.targets or args.package_name:
            parser.error('--list 不能与阶段或 WKD 参数同时使用')
        list_packages(entries, entry_dir)
        return
    if len(args.targets) == 1:
        stage = args.targets[0]
    elif len(args.targets) == 2 and not args.package_name:
        args.package_name, stage = args.targets
    else:
        parser.error('用法：wmp_entry.py <阶段参数> [--wkd <WKD编号>]；兼容：wmp_entry.py <WKD编号> <阶段参数>')
    if args.package_name:
        entries = [item for item in entries if item['package_name'] == args.package_name]
        if not entries:
            raise ValueError(f"规避子包不存在：{args.package_name}")
    matched = [item for item in entries if item['stage_parameter'] == stage]
    skipped = [item for item in entries if item['stage_parameter'] != stage]
    if args.package_name and not matched:
        execute_package(entry_dir, args.package_name, stage, args.target_root)
        return
    if not matched:
        raise ValueError(f'软件包内没有适用于阶段 {stage} 的 WKD')
    for item in skipped:
        print(f"[SKIP] {item['package_name']} 不适用于阶段 {stage}")
    for item in matched:
        execute_package(entry_dir, item['package_name'], stage, args.target_root)
    print(f'\n[DONE] 阶段 {stage} 执行完成：共 {len(matched)} 个 WKD，跳过 {len(skipped)} 个')


if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        sys.exit(1)
