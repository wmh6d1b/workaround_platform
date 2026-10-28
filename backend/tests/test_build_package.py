import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from app.builder import build_executable_package


def wkd_fixture(stage='post_start', custom_stage_name=None):
    return {
        'id': 'wkd-test-1', 'number': 'WKD202610270099', 'title': 'hello/world 构建验证',
        'description': '验证两个文件在同一上传操作内打包并执行', 'issue_no': None, 'requirement_no': 'REQ-HELLO',
        'project_id': 'project-1', 'project': '测试项目', 'version_id': 'version-1', 'version': 'V1.0.0',
        'found_version_id': None, 'found_version': None, 'planned_version_id': 'version-1', 'planned_version': 'V1.0.0',
        'subsystem_id': 'subsystem-1', 'subsystem': '测试子系统', 'owner_id': 'user-1', 'owner': '测试人员',
        'current_handler_id': 'user-1', 'current_handler': '测试人员', 'machine_ids': ['machine-1'],
        'machines': [{'id': 'machine-1', 'name': 'AQ-TEST'}], 'execution_type': 'AUTOMATED',
        'activity_scene': '常规版本升级', 'measure_type': '事前规避措施', 'remark': '端到端测试',
        'status': 'VERIFY', 'stage': stage, 'custom_stage_name': custom_stage_name, 'lock_version': 2,
        'disabled_reason': None, 'disabled_from': None,
        'operations': [
            {'id': 'op-1', 'position': 1, 'type': 'UPLOAD_FILE', 'params': {
                'target_path': '/root/temp', 'overwrite': '覆盖', 'permission': '0644',
                'files': [{'name': 'hello.py', 'content': 'print("hello")'}, {'name': 'world.py', 'content': 'print("world")'}],
            }},
            {'id': 'op-2', 'position': 2, 'type': 'LINUX_COMMAND', 'params': {
                'command': 'python3 hello.py; python3 world.py', 'workdir': '/root/temp', 'timeout': '30', 'exit_code': '0',
            }},
        ],
        'created_at': '2026-10-27T12:00:00', 'updated_at': '2026-10-27T12:01:00',
    }


class ExecutablePackageTests(unittest.TestCase):
    def build(self, tmp, wkd=None):
        content = build_executable_package(artifact_id='artifact-test', kind='debug', project_id='project-1',
                                           machine_id='machine-1', wkds=[wkd or wkd_fixture()])
        artifact = Path(tmp) / 'debug.tar.gz'
        artifact.write_bytes(content)
        output = Path(tmp) / 'unpacked'
        output.mkdir()
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as tar:
            tar.extractall(output, filter='data')
        return output

    def test_package_contains_detailed_subpackage_and_executes_hello_world(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            output = self.build(tmp)
            manifest = json.loads((output / 'MANIFEST.json').read_text())
            self.assertEqual(manifest['entry'], 'wmp_entry.py')
            self.assertEqual(manifest['packages'][0]['package_name'], 'WKD202610270099')
            detailed = json.loads((output / 'WKD_LIST.json').read_text())
            self.assertEqual(detailed[0]['operations'][0]['params']['files'][0]['content'], 'print("hello")')
            package = json.loads((output / 'packages/WKD202610270099/package.json').read_text())
            self.assertEqual(package['stage_parameter'], 'post_start')
            self.assertEqual(len(package['operations']), 2)
            self.assertEqual(len(package['operations'][0]['params']['files']), 2)
            self.assertEqual((output / 'packages/WKD202610270099/files/01/01/hello.py').read_text(), 'print("hello")')
            self.assertEqual((output / 'packages/WKD202610270099/files/01/02/world.py').read_text(), 'print("world")')

            sandbox = Path(tmp) / 'sandbox'
            result = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), 'WKD202610270099', 'post_start',
                                     '--target-root', str(sandbox)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('hello\nworld\n', result.stdout)
            self.assertIn('[DONE]', result.stdout)
            self.assertEqual((sandbox / 'root/temp/hello.py').read_text(), 'print("hello")')
            self.assertEqual((sandbox / 'root/temp/world.py').read_text(), 'print("world")')

    def test_package_preserves_base64_binary_file_bytes(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            wkd = wkd_fixture()
            wkd['operations'] = wkd['operations'][:1]
            wkd['operations'][0]['params']['files'] = [
                {'name': 'payload.bin', 'content': 'AAECAwQ=', 'encoding': 'base64', 'size': 5},
            ]
            output = self.build(tmp, wkd)
            stored = output / 'packages/WKD202610270099/files/01/01/payload.bin'
            self.assertEqual(stored.read_bytes(), b'\x00\x01\x02\x03\x04')
            package = json.loads((output / 'packages/WKD202610270099/package.json').read_text())
            self.assertEqual(package['operations'][0]['params']['files'][0]['size'], 5)

    def test_custom_stage_is_entry_parameter_and_wrong_stage_fails(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            output = self.build(tmp, wkd_fixture(stage='custom', custom_stage_name='after_service_check'))
            package = json.loads((output / 'packages/WKD202610270099/package.json').read_text())
            self.assertEqual(package['stage_parameter'], 'after_service_check')
            wrong = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), 'WKD202610270099', 'custom',
                                    '--target-root', str(Path(tmp) / 'wrong')], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(wrong.returncode, 0)
            correct = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), 'WKD202610270099', 'after_service_check',
                                      '--target-root', str(Path(tmp) / 'correct')], capture_output=True, text=True, timeout=30)
            self.assertEqual(correct.returncode, 0, correct.stderr)
            self.assertIn('hello\nworld\n', correct.stdout)


if __name__ == '__main__':
    unittest.main()
