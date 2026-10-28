import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from openpyxl import load_workbook

from app.member_import import import_template, parse_import_file, validate_import_rows
from app.models import ProjectMember, Role, User


def rows_result(rows):
    return SimpleNamespace(all=lambda: rows)


class MemberImportTemplateTests(unittest.TestCase):
    def test_template_has_confirmed_five_columns_and_parses(self):
        content = import_template()
        workbook = load_workbook(BytesIO(content))
        self.assertEqual([cell.value for cell in workbook.active[1]], ['工号', '用户名', '所属部门', '项目角色', '邮箱'])
        self.assertNotIn('姓名', [cell.value for cell in workbook.active[1]])
        workbook.active.append(['E1001', 'zhangsan', '研发一部', '开发人员', 'zhangsan@example.internal'])
        output = BytesIO()
        workbook.save(output)
        rows = parse_import_file(output.getvalue(), 'users.xlsx')
        self.assertEqual(rows[0]['employee_id'], 'E1001')
        self.assertEqual(rows[0]['username'], 'zhangsan')
        self.assertEqual(rows[0]['department'], '研发一部')


class MemberImportValidationTests(unittest.TestCase):
    def setUp(self):
        self.developer = Role(id='role-dev', name='开发人员')
        self.initialization = Role(id='role-init', name='初始化用户')
        self.existing = User(id='user-1', employee_id='E1001', username='old-name', is_active=True, is_superuser=False)
        self.member = ProjectMember(id='member-1', project_id='project-1', user_id='user-1', role_id='role-dev')

    def test_existing_member_keeps_role_and_new_user_is_counted(self):
        db = Mock()
        db.scalars.side_effect = [rows_result([self.developer, self.initialization]), rows_result([self.existing]), rows_result([self.member])]
        result = validate_import_rows(db, 'project-1', 'role-dev', [
            {'row_number': 2, 'employee_id': 'E1001', 'username': 'renamed', 'role_name': ''},
            {'row_number': 3, 'employee_id': 'E1002', 'username': 'lisi', 'department': '研发二部', 'role_name': ''},
        ])
        self.assertEqual(result['summary']['existing_members'], 1)
        self.assertEqual(result['summary']['new_users'], 1)
        self.assertEqual(result['summary']['new_members'], 1)
        self.assertEqual(result['summary']['errors'], 0)
        self.assertEqual(result['rows'][0]['action'], 'EXISTING_MEMBER')
        self.assertEqual(result['rows'][1]['action'], 'CREATE_USER_AND_MEMBER')

    def test_duplicate_employee_and_reserved_role_are_row_errors(self):
        db = Mock()
        db.scalars.side_effect = [rows_result([self.developer, self.initialization]), rows_result([]), rows_result([])]
        result = validate_import_rows(db, 'project-1', 'role-dev', [
            {'row_number': 2, 'employee_id': 'E1001', 'username': 'user-a', 'role_name': '初始化用户'},
            {'row_number': 3, 'employee_id': 'E1001', 'username': 'user-b', 'role_name': ''},
        ])
        self.assertEqual(result['summary']['errors'], 2)
        self.assertIn('初始化用户不允许通过批量导入分配', result['rows'][0]['errors'])
        self.assertIn('工号在文件中重复', result['rows'][1]['errors'])


if __name__ == '__main__':
    unittest.main()
