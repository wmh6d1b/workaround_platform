import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.deps import require_superuser
from app.models import Permission, ProjectMember, Role, Version
from app.routers.admin import (
    add_member,
    assignable_role,
    create_business,
    create_role,
    ensure_project_admin_retained,
    list_business,
    remove_member,
    update_business,
    update_global_role,
    update_member,
)
from app.schemas import EntityInput, GlobalRoleInput, MemberInput, RoleInput
from app.seed import LEGACY_PERMISSION_MAP, PERMISSIONS, migrate_legacy_permissions


def user(superuser=False):
    return SimpleNamespace(id='admin' if superuser else 'project-admin', is_superuser=superuser)


class GlobalAuthorizationTests(unittest.TestCase):
    def test_only_superuser_passes_global_guard(self):
        require_superuser(user(True))
        with self.assertRaises(HTTPException) as raised:
            require_superuser(user())
        self.assertEqual(raised.exception.status_code, 403)

    def test_project_admin_cannot_create_project(self):
        db = Mock()
        with self.assertRaises(HTTPException) as raised:
            create_business('projects', EntityInput(name='越权项目', code='DENIED'), db, user())
        self.assertEqual(raised.exception.status_code, 403)
        db.add.assert_not_called()

    def test_project_admin_cannot_create_global_role(self):
        with self.assertRaises(HTTPException) as raised:
            create_role(RoleInput(name='越权角色'), Mock(), user())
        self.assertEqual(raised.exception.status_code, 403)

    def test_project_scoped_list_requires_explicit_project(self):
        with self.assertRaises(HTTPException) as raised:
            list_business('versions', None, Mock(), user())
        self.assertEqual(raised.exception.status_code, 422)


class ProjectResourceBoundaryTests(unittest.TestCase):
    @patch('app.routers.admin.commit')
    @patch('app.routers.admin.audit')
    @patch('app.routers.admin.authorize')
    def test_version_creation_uses_version_permission_and_project(self, authorize, _audit, _commit):
        db = Mock()
        result = create_business('versions', EntityInput(name='V1.0.0', project_id='project-1'), db, user())
        authorize.assert_called_once_with(db, user(), 'business.version.edit', 'project-1')
        self.assertEqual(result['number'], 'V1.0.0')
        self.assertEqual(result['project_id'], 'project-1')

    @patch('app.routers.admin.authorize')
    def test_business_resource_cannot_move_to_another_project(self, authorize):
        db = Mock()
        item = Version(project_id='project-1', number='V1.0.0')
        db.get.return_value = item
        with self.assertRaises(HTTPException) as raised:
            update_business('versions', item.id, EntityInput(name='V1.0.1', project_id='project-2'), db, user())
        self.assertEqual(raised.exception.status_code, 403)
        authorize.assert_called_once_with(db, user(), 'business.version.edit', 'project-1')
        self.assertEqual(item.project_id, 'project-1')


class ProjectMembershipSafetyTests(unittest.TestCase):
    def test_system_admin_role_is_not_assignable(self):
        db = Mock()
        db.get.return_value = Role(name='系统管理员', built_in=True)
        with self.assertRaises(HTTPException) as raised:
            assignable_role(db, 'role-system-admin')
        self.assertEqual(raised.exception.status_code, 403)

    @patch('app.routers.admin.authorize')
    def test_system_admin_cannot_be_added_as_project_member(self, authorize):
        db = Mock()
        db.get.side_effect = [Role(name='系统管理员', built_in=True)]
        with self.assertRaises(HTTPException) as raised:
            add_member('project-1', MemberInput(user_id='user-1', role_id='role-system-admin'), db, user())
        self.assertEqual(raised.exception.status_code, 403)
        db.add.assert_not_called()

    @patch('app.routers.admin.authorize')
    def test_project_admin_cannot_remove_system_admin_member(self, _authorize):
        member = SimpleNamespace(project_id='project-1', role_id='role-system-admin',
                                 role=SimpleNamespace(name='系统管理员'), user=SimpleNamespace(is_superuser=True))
        db = Mock()
        db.get.return_value = member
        with self.assertRaises(HTTPException) as raised:
            remove_member('project-1', 'member-1', db, user())
        self.assertEqual(raised.exception.status_code, 403)
        db.delete.assert_not_called()

    @patch('app.routers.admin.authorize')
    def test_project_admin_cannot_demote_system_admin_member(self, _authorize):
        member = SimpleNamespace(project_id='project-1', role_id='role-system-admin',
                                 role=SimpleNamespace(name='系统管理员'), user=SimpleNamespace(is_superuser=True))
        db = Mock()
        db.get.side_effect = [member, Role(name='开发人员')]
        with self.assertRaises(HTTPException) as raised:
            update_member('project-1', 'member-1', MemberInput(user_id='admin-id', role_id='role-developer'), db, user())
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(member.role_id, 'role-system-admin')

    def test_last_project_admin_cannot_be_removed_or_demoted(self):
        member = SimpleNamespace(role_id='role-admin', role=SimpleNamespace(name='项目管理员'))
        db = Mock()
        db.scalar.return_value = 1
        for new_role_id in (None, 'role-developer'):
            with self.subTest(new_role_id=new_role_id), self.assertRaises(HTTPException) as raised:
                ensure_project_admin_retained(db, 'project-1', member, new_role_id)
            self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(db.get.call_args.kwargs, {'with_for_update': True})

    def test_project_admin_can_be_changed_when_another_admin_remains(self):
        member = SimpleNamespace(role_id='role-admin', role=SimpleNamespace(name='项目管理员'))
        db = Mock()
        db.scalar.return_value = 2
        ensure_project_admin_retained(db, 'project-1', member, 'role-developer')


class GlobalRoleAssignmentTests(unittest.TestCase):
    def test_project_admin_cannot_assign_all_projects_role(self):
        with self.assertRaises(HTTPException) as raised:
            update_global_role('user-1', GlobalRoleInput(role_id='role-auditor'), Mock(), user())
        self.assertEqual(raised.exception.status_code, 403)

    @patch('app.routers.admin.commit')
    @patch('app.routers.admin.audit')
    def test_superuser_assigns_global_role_without_creating_project_membership(self, _audit, _commit):
        target = SimpleNamespace(id='user-1', is_active=True, is_superuser=False, global_role_id=None)
        role = Role(id='role-auditor', name='系统质量审计员')
        db = Mock()
        db.get.side_effect = [target, role]
        result = update_global_role(target.id, GlobalRoleInput(role_id=role.id), db, user(True))
        self.assertEqual(target.global_role_id, role.id)
        self.assertEqual(result['global_role_id'], role.id)
        db.add.assert_not_called()

    @patch('app.routers.admin.commit')
    @patch('app.routers.admin.audit')
    def test_global_role_can_be_revoked_independently(self, _audit, _commit):
        target = SimpleNamespace(id='user-1', is_active=True, is_superuser=False, global_role_id='role-auditor')
        db = Mock()
        db.get.return_value = target
        result = update_global_role(target.id, GlobalRoleInput(role_id=None), db, user(True))
        self.assertIsNone(target.global_role_id)
        self.assertIsNone(result['global_role_id'])


class PermissionMigrationTests(unittest.TestCase):
    def test_legacy_permissions_are_mapped_without_retaining_global_role_edit(self):
        codes = [*PERMISSIONS, *LEGACY_PERMISSION_MAP]
        permissions = {code: Permission(code=code, module=code.split('.')[0]) for code in codes}
        role = Role(name='自定义角色', permissions=[permissions[code] for code in ['wkd.view', *LEGACY_PERMISSION_MAP]])
        db = Mock()
        migrate_legacy_permissions(db, permissions, [role])
        migrated = {permission.code for permission in role.permissions}
        self.assertIn('wkd.view', migrated)
        self.assertIn('business.version.edit', migrated)
        self.assertIn('project.member.manage', migrated)
        self.assertIn('project.role.view', migrated)
        self.assertFalse(migrated.intersection(LEGACY_PERMISSION_MAP))
        self.assertEqual(db.delete.call_count, len(LEGACY_PERMISSION_MAP))


if __name__ == '__main__':
    unittest.main()
