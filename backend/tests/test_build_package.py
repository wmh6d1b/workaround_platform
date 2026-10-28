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
    def build(self, tmp, wkd=None, wkds=None, attachments=None):
        selected_wkds = wkds if wkds is not None else [wkd or wkd_fixture()]
        attachments = attachments or {}
        contents = {item['object_key']: item['content'] for items in attachments.values() for item in items}
        content = build_executable_package(artifact_id='artifact-test', kind='debug', project_id='project-1',
                                           machine_id='machine-1', wkds=selected_wkds, attachments=attachments,
                                           attachment_reader=lambda key: io.BytesIO(contents[key]))
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

    def test_default_stage_execution_follows_manifest_order(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            early = wkd_fixture()
            early.update({'id': 'wkd-early', 'number': 'WKD202610270001', 'title': '先登记的 WKD',
                          'created_at': '2026-10-27T08:00:00'})
            late = wkd_fixture()
            late.update({'id': 'wkd-late', 'number': 'WKD202610270002', 'title': '后登记的 WKD',
                         'created_at': '2026-10-27T09:00:00'})
            output = self.build(tmp, wkds=[early, late])
            manifest = json.loads((output / 'MANIFEST.json').read_text())
            self.assertEqual([item['package_name'] for item in manifest['packages']],
                             ['WKD202610270001', 'WKD202610270002'])
            result = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), 'post_start',
                                     '--target-root', str(Path(tmp) / 'sandbox')],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(result.stdout.index('先登记的 WKD'), result.stdout.index('后登记的 WKD'))
            self.assertIn('共 2 个 WKD，跳过 0 个', result.stdout)

    def test_list_skip_and_optional_single_wkd(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            start = wkd_fixture()
            start.update({'id': 'wkd-start', 'number': 'WKD202610270001', 'title': '启动后措施'})
            init = wkd_fixture(stage='post_init')
            init.update({'id': 'wkd-init', 'number': 'WKD202610270002', 'title': '初始化后措施'})
            output = self.build(tmp, wkds=[start, init])
            listed = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), '--list'],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn('WKD202610270001\tpost_start', listed.stdout)
            self.assertIn('WKD202610270002\tpost_init', listed.stdout)
            result = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), 'post_start',
                                     '--target-root', str(Path(tmp) / 'sandbox')],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('[SKIP] WKD202610270002', result.stdout)
            self.assertIn('共 1 个 WKD，跳过 1 个', result.stdout)
            single = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), 'post_init',
                                     '--wkd', 'WKD202610270002', '--target-root', str(Path(tmp) / 'single')],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(single.returncode, 0, single.stderr)
            self.assertIn('初始化后措施', single.stdout)
            self.assertNotIn('启动后措施', single.stdout)

    def test_default_stage_without_matching_wkd_fails(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            output = self.build(tmp)
            result = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), 'post_init',
                                     '--target-root', str(Path(tmp) / 'sandbox')],
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('没有适用于阶段 post_init', result.stderr)

    def test_manual_wkd_and_regular_attachments_are_packaged(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            manual = wkd_fixture()
            manual.update({'execution_type': 'MANUAL', 'stage': None, 'custom_stage_name': None, 'operations': []})
            payload = b'\x00\x01manual-attachment\xff'
            attachments = {'wkd-test-1': [{
                'id': 'attachment-1', 'object_key': 'attachments/session-1/attachment-1',
                'filename': '人工操作说明.bin', 'size': len(payload), 'sha256': None,
                'content_type': 'application/octet-stream', 'created_at': '2026-10-27T12:02:00', 'content': payload,
            }]}
            output = self.build(tmp, manual, attachments=attachments)
            stored = output / 'packages/WKD202610270099/attachments/01/人工操作说明.bin'
            self.assertEqual(stored.read_bytes(), payload)
            package = json.loads((output / 'packages/WKD202610270099/package.json').read_text())
            self.assertEqual(package['wkd']['execution_type'], 'MANUAL')
            self.assertEqual(package['operations'], [])
            self.assertEqual(package['attachments'][0]['stored_path'], 'attachments/01/人工操作说明.bin')
            self.assertEqual(package['attachments'][0]['size'], len(payload))
            self.assertEqual(len(package['attachments'][0]['sha256']), 64)
            manifest = json.loads((output / 'MANIFEST.json').read_text())
            self.assertEqual(manifest['packages'][0]['attachment_count'], 1)
            detailed = json.loads((output / 'WKD_LIST.json').read_text())
            self.assertEqual(detailed[0]['attachments'][0]['name'], '人工操作说明.bin')
            listed = subprocess.run([sys.executable, str(output / 'wmp_entry.py'), '--list'],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn('WKD202610270099\t人工操作', listed.stdout)

    def test_attachment_checksum_mismatch_fails_build(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            payload = b'actual-content'
            attachments = {'wkd-test-1': [{
                'id': 'attachment-1', 'object_key': 'attachments/session-1/attachment-1',
                'filename': 'broken.txt', 'size': len(payload), 'sha256': '0' * 64, 'content': payload,
            }]}
            with self.assertRaisesRegex(ValueError, 'SHA-256 校验失败'):
                self.build(tmp, attachments=attachments)


if __name__ == '__main__':
    unittest.main()
