import base64
from contextlib import closing
import hashlib
import io
import json
import tarfile
from datetime import datetime
from pathlib import Path, PurePosixPath

ENTRY_TEMPLATE = Path(__file__).parent / 'templates' / 'wmp_entry.py'


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2).encode('utf-8')


def _tar_info(name: str, size: int, mode: int = 0o644) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = mode
    info.mtime = int(datetime.utcnow().timestamp())
    return info


def _add_bytes(tar: tarfile.TarFile, name: str, content: bytes, mode: int = 0o644) -> None:
    tar.addfile(_tar_info(name, len(content), mode), io.BytesIO(content))


class _HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.size = 0
        self.sha256 = hashlib.sha256()

    def read(self, size=-1):
        content = self.stream.read(size)
        if content:
            self.size += len(content)
            self.sha256.update(content)
        return content


def _add_attachments(tar, package_dir, package_name, items, attachment_reader):
    stored = []
    for index, item in enumerate(items, 1):
        filename = item['filename']
        if (not filename or '/' in filename or '\\' in filename or PurePosixPath(filename).name != filename
                or any(ord(char) < 32 for char in filename)):
            raise ValueError(f'{package_name} 的附件文件名非法：{filename}')
        if attachment_reader is None:
            raise ValueError(f'{package_name} 缺少附件读取器')
        stored_path = f'attachments/{index:02d}/{filename}'
        reader = _HashingReader(attachment_reader(item['object_key']))
        with closing(reader.stream):
            tar.addfile(_tar_info(f'{package_dir}/{stored_path}', int(item['size'])), reader)
        if reader.size != int(item['size']):
            raise ValueError(f"附件大小校验失败：{package_name}/{filename}")
        actual_sha256 = reader.sha256.hexdigest()
        if item.get('sha256') and actual_sha256 != item['sha256']:
            raise ValueError(f"附件 SHA-256 校验失败：{package_name}/{filename}")
        stored.append({
            'id': item['id'], 'name': filename, 'stored_path': stored_path,
            'size': reader.size, 'sha256': actual_sha256,
            'content_type': item.get('content_type'), 'created_at': item.get('created_at'),
        })
    return stored


def write_executable_package(output, *, artifact_id: str, kind: str, project_id: str, machine_id: str,
                             wkds: list[dict], attachments=None, attachment_reader=None) -> None:
    """将 WKD、原子操作文件和普通附件流式写入 tar.gz 输出对象。"""
    attachments = attachments or {}
    created_at = datetime.utcnow().isoformat()
    package_index = []
    detailed_wkds = []
    with tarfile.open(fileobj=output, mode='w:gz') as tar:
        _add_bytes(tar, 'wmp_entry.py', ENTRY_TEMPLATE.read_bytes(), 0o755)
        for wkd in wkds:
            package_name = wkd.get('number') or wkd['id']
            stage = wkd.get('stage')
            stage_parameter = wkd.get('custom_stage_name') if stage == 'custom' else stage
            if wkd.get('execution_type') == 'AUTOMATED' and not stage_parameter:
                raise ValueError(f"{package_name} 缺少可执行阶段参数")
            package_dir = f'packages/{package_name}'
            operations = []
            for operation in sorted(wkd.get('operations', []), key=lambda item: item['position']):
                params = dict(operation.get('params') or {})
                if operation['type'] == 'UPLOAD_FILE':
                    stored_files = []
                    for file_index, item in enumerate(params.get('files') or [], 1):
                        filename = item['name']
                        content = (base64.b64decode(item.get('content', ''), validate=True)
                                   if item.get('encoding') == 'base64' else str(item.get('content', '')).encode('utf-8'))
                        stored_path = f'files/{operation["position"]:02d}/{file_index:02d}/{filename}'
                        _add_bytes(tar, f'{package_dir}/{stored_path}', content)
                        stored_files.append({'name': filename, 'stored_path': stored_path,
                                             'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
                    params['files'] = stored_files
                operations.append({'position': operation['position'], 'type': operation['type'], 'params': params})
            stored_attachments = _add_attachments(
                tar, package_dir, package_name, attachments.get(wkd['id'], []), attachment_reader)
            package = {
                'schema_version': 1, 'package_name': package_name, 'stage': stage,
                'stage_parameter': stage_parameter,
                'wkd': {key: value for key, value in wkd.items() if key != 'operations'},
                'operations': operations, 'attachments': stored_attachments,
            }
            _add_bytes(tar, f'{package_dir}/package.json', _json_bytes(package))
            package_index.append({'package_name': package_name, 'wkd_id': wkd['id'], 'stage_parameter': stage_parameter,
                                  'manifest': f'{package_dir}/package.json', 'operation_count': len(operations),
                                  'attachment_count': len(stored_attachments)})
            detailed_wkd = dict(wkd)
            detailed_wkd['attachments'] = stored_attachments
            detailed_wkds.append(detailed_wkd)
        manifest = {'schema_version': 1, 'artifact_id': artifact_id, 'type': kind.upper(), 'project_id': project_id,
                    'machine_id': machine_id, 'created_at': created_at, 'entry': 'wmp_entry.py', 'packages': package_index}
        _add_bytes(tar, 'MANIFEST.json', _json_bytes(manifest))
        _add_bytes(tar, 'WKD_LIST.json', _json_bytes(detailed_wkds))
        usage = ('# WMP 规避措施软件包\n\n'
                 '```bash\n'
                 '# 查看包内 WKD 和阶段，不执行\npython3 wmp_entry.py --list\n\n'
                 '# 按 MANIFEST.json 顺序执行所有匹配阶段的 WKD\npython3 wmp_entry.py <阶段参数>\n'
                 '# 示例：python3 wmp_entry.py post_start\n'
                 '# 自定义阶段：python3 wmp_entry.py <自定义阶段名称>\n\n'
                 '# 仅执行一个 WKD\npython3 wmp_entry.py <阶段参数> --wkd <WKD编号>\n\n'
                 '# 兼容旧调用方式\npython3 wmp_entry.py <WKD编号> <阶段参数>\n```\n\n'
                 '普通阶段为 pre_upgrade、post_upgrade、post_start、post_init。'
                 '子包按 packages/<WKD编号> 隔离，package.json 包含属性、有序原子操作和普通附件清单，'
                 'files 目录包含原子操作上传文件，attachments 目录包含 WKD 普通附件。'
                 '人工操作 WKD 也可打包；普通附件只随包携带，不会自动执行。'
                 '默认整包执行时自动跳过不匹配阶段的 WKD；任一操作失败即停止后续执行并以非零码退出。\n')
        _add_bytes(tar, 'README.md', usage.encode('utf-8'))


def build_executable_package(*, artifact_id: str, kind: str, project_id: str, machine_id: str,
                             wkds: list[dict], attachments=None, attachment_reader=None) -> bytes:
    """生成包含独立 WKD 子包、详细清单、附件和通用入口的 tar.gz。"""
    buffer = io.BytesIO()
    write_executable_package(buffer, artifact_id=artifact_id, kind=kind, project_id=project_id,
                             machine_id=machine_id, wkds=wkds, attachments=attachments,
                             attachment_reader=attachment_reader)
    return buffer.getvalue()
