import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException

from app.deps import ensure_operational_project
from app.models import Project, WkdStatus
from app.routers.admin import create_business
from app.routers.builds import build
from app.routers.wkd import create_wkd, transition
from app.schemas import EntityInput


class InitializationProjectTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.admin = SimpleNamespace(id='admin', is_superuser=True)
        self.project = Project(id='init-project', name='用户初始化', code='WMP-USER-INIT')
        self.db.get.return_value = self.project

    def assert_blocked(self, call):
        with self.assertRaises(HTTPException) as raised:
            call()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn('用户初始化项目仅用于账号落地', raised.exception.detail)

    def test_guard_blocks_initialization_project(self):
        self.assert_blocked(lambda: ensure_operational_project(self.db, 'init-project'))

    def test_business_resource_creation_is_blocked_even_for_superuser(self):
        self.assert_blocked(lambda: create_business(
            'versions', EntityInput(name='V1.0.0', project_id='init-project'), self.db, self.admin))
        self.db.add.assert_not_called()

    def test_wkd_creation_is_blocked_even_for_superuser(self):
        self.assert_blocked(lambda: create_wkd(SimpleNamespace(project_id='init-project'), self.db, self.admin))
        self.db.add.assert_not_called()

    def test_wkd_transition_is_blocked_even_for_superuser(self):
        wkd = SimpleNamespace(id='wkd-1', project_id='init-project', status=WkdStatus.NEW_WKD)
        self.db.get.side_effect = [wkd, self.project]
        self.assert_blocked(lambda: transition('wkd-1', 'disable', SimpleNamespace(), self.db, self.admin))
        self.assertEqual(wkd.status, WkdStatus.NEW_WKD)

    def test_build_is_blocked_even_for_superuser(self):
        self.assert_blocked(lambda: build('debug', SimpleNamespace(project_id='init-project'), self.db, self.admin))
        self.db.add.assert_not_called()


class OperationalProjectTests(unittest.TestCase):
    def test_real_project_passes_guard(self):
        db = Mock()
        db.get.return_value = Project(id='real-project', name='真实项目', code='REAL-PROJECT')
        ensure_operational_project(db, 'real-project')


if __name__ == '__main__':
    unittest.main()
