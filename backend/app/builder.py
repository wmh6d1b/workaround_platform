import hashlib
import io
import json
import tarfile
from datetime import datetime
from pathlib import Path

ENTRY_TEMPLATE = Path(__file__).parent / 'templates' / 'wmp_entry.py'


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2).encode('utf-8')


def _add_bytes(tar: tarfile.TarFile, name: str, content: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = mode
    info.mtime = int(datetime.utcnow().timestamp())
    tar.addfile(info, io.BytesIO(content))


def build_executable_package(*, artifact_id: str, kind: str, project_id: str, machine_id: str,
                             wkds: list[dict]) -> bytes:
    """生成包含独立 WKD 子包、详细清单和通用入口的 tar.gz。"""
    created_at = datetime.utcnow().isoformat()
    package_index = []
    detailed_wkds = []
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
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
                        content = str(item.get('content', '')).encode('utf-8')
                        stored_path = f'files/{operation["position"]:02d}/{file_index:02d}/{filename}'
                        _add_bytes(tar, f'{package_dir}/{stored_path}', content)
                        stored_files.append({'name': filename, 'stored_path': stored_path,
                                             'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
                    params['files'] = stored_files
                operations.append({'position': operation['position'], 'type': operation['type'], 'params': params})
            package = {
                'schema_version': 1, 'package_name': package_name, 'stage': stage,
                'stage_parameter': stage_parameter,
                'wkd': {key: value for key, value in wkd.items() if key != 'operations'},
                'operations': operations,
            }
            _add_bytes(tar, f'{package_dir}/package.json', _json_bytes(package))
            package_index.append({'package_name': package_name, 'wkd_id': wkd['id'], 'stage_parameter': stage_parameter,
                                  'manifest': f'{package_dir}/package.json', 'operation_count': len(operations)})
            detailed_wkds.append(wkd)
        manifest = {'schema_version': 1, 'artifact_id': artifact_id, 'type': kind.upper(), 'project_id': project_id,
                    'machine_id': machine_id, 'created_at': created_at, 'entry': 'wmp_entry.py', 'packages': package_index}
        _add_bytes(tar, 'MANIFEST.json', _json_bytes(manifest))
        _add_bytes(tar, 'WKD_LIST.json', _json_bytes(detailed_wkds))
        usage = ('# WMP 规避措施软件包\n\n'
                 '```bash\npython3 wmp_entry.py <WKD编号> <阶段参数>\n'
                 '# 示例：python3 wmp_entry.py WKD202610270001 post_start\n'
                 '# 自定义阶段：python3 wmp_entry.py WKD202610270001 <自定义阶段名称>\n```\n\n'
                 '子包按 packages/<WKD编号> 隔离，package.json 包含属性与有序原子操作，'
                 'files 目录包含上传操作的实际文件。入口逐序执行操作，任一失败即以非零码退出。\n')
        _add_bytes(tar, 'README.md', usage.encode('utf-8'))
    return buffer.getvalue()
