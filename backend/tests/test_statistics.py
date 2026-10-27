import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.models import ExecutionType, Stage, WkdStatus
from app.routers.statistics import bucket, export_statistics, parse_period, scoped_wkds, trend_data


def user(superuser=False):
    return SimpleNamespace(id='admin' if superuser else 'member', is_superuser=superuser)


def query_result(rows=None):
    result = Mock()
    result.unique.return_value.all.return_value = rows or []
    return result


def filter_values(**changes):
    values = {
        'scope': 'project', 'project_ids': ['project-1'], 'version_ids': None, 'machine_ids': None,
        'subsystem_ids': None, 'found_version_ids': None, 'planned_version_ids': None, 'statuses': None,
        'execution_types': None, 'activity_scenes': None, 'measure_types': None, 'owner_ids': None,
        'handler_ids': None, 'stages': None, 'keyword': None, 'date_field': 'created',
        'start_date': '2026-10-01', 'end_date': '2026-10-27',
    }
    values.update(changes)
    return values


class StatisticsAccessTests(unittest.TestCase):
    def test_project_and_global_scopes_do_not_depend_on_roles(self):
        for scope, project_ids in (('project', ['project-1']), ('global', []), ('global', ['project-1', 'project-2'])):
            with self.subTest(scope=scope, project_ids=project_ids):
                db = Mock()
                db.scalars.return_value = query_result()
                rows, start, end = scoped_wkds(db, **filter_values(scope=scope, project_ids=project_ids))
                self.assertEqual(rows, [])
                self.assertEqual((start, end), (date(2026, 10, 1), date(2026, 10, 27)))

    def test_project_scope_requires_exactly_one_project(self):
        for project_ids in (None, [], ['project-1', 'project-2']):
            with self.subTest(project_ids=project_ids), self.assertRaises(HTTPException) as raised:
                scoped_wkds(Mock(), **filter_values(project_ids=project_ids))
            self.assertEqual(raised.exception.status_code, 422)


class StatisticsFilterTests(unittest.TestCase):
    def test_all_multi_select_filters_are_applied_to_one_query(self):
        db = Mock()
        db.scalars.return_value = query_result()
        scoped_wkds(db, **filter_values(
            scope='global', project_ids=['project-1', 'project-2'], version_ids=['v1', 'v2'],
            machine_ids=['m1', 'm2'], subsystem_ids=['s1', 's2'], found_version_ids=['v0'],
            planned_version_ids=['v3'], statuses=[WkdStatus.VERIFY, WkdStatus.REVIEW],
            execution_types=[ExecutionType.AUTOMATED, ExecutionType.MANUAL], activity_scenes=['首版本部署'],
            measure_types=['事前规避措施'], owner_ids=['u1', 'u2'], handler_ids=['u2'],
            stages=[Stage.PRE_UPGRADE, Stage.CUSTOM], keyword='issue', date_field='updated',
        ))
        statement = str(db.scalars.call_args.args[0])
        for column in ('project_id', 'version_id', 'subsystem_id', 'found_version_id', 'planned_version_id',
                       'status', 'execution_type', 'activity_scene', 'measure_type', 'owner_id',
                       'current_handler_id', 'stage', 'updated_at'):
            self.assertIn(column, statement)
        self.assertIn('wkd_machines', statement)
        self.assertIn('lower(wkds.number)', statement)
        self.assertIn('lower(wkds.issue_no)', statement)

    def test_invalid_date_field_and_period_are_rejected(self):
        for values in (filter_values(date_field='approved'), filter_values(start_date='bad'),
                       filter_values(start_date='2026-10-28'), filter_values(start_date='2025-01-01', end_date='2026-12-31')):
            with self.subTest(values=values), self.assertRaises(HTTPException) as raised:
                scoped_wkds(Mock(), **values)
            self.assertEqual(raised.exception.status_code, 422)

    def test_period_allows_366_days(self):
        self.assertEqual(parse_period('2026-01-01', '2026-12-31'), (date(2026, 1, 1), date(2026, 12, 31)))

    def test_trend_switches_between_day_week_and_month(self):
        row = SimpleNamespace(created_at=datetime(2026, 10, 8, 9))
        approval = SimpleNamespace(created_at=datetime(2026, 10, 9, 10))
        for start, end, expected in ((date(2026, 10, 1), date(2026, 10, 31), 'day'),
                                     (date(2026, 8, 1), date(2026, 10, 31), 'week'),
                                     (date(2026, 1, 1), date(2026, 12, 31), 'month')):
            with self.subTest(expected=expected):
                granularity, trend = trend_data([row], [approval], start, end)
                self.assertEqual(granularity, expected)
                self.assertEqual(sum(item['created'] for item in trend), 1)
                self.assertEqual(sum(item['approved'] for item in trend), 1)
        self.assertEqual(bucket(date(2026, 10, 8), 'week'), date(2026, 10, 5))
        self.assertEqual(bucket(date(2026, 10, 8), 'month'), date(2026, 10, 1))

    @patch('app.routers.statistics.scoped_wkds')
    def test_export_reuses_identical_filters(self, scoped):
        scoped.return_value = ([], date(2026, 10, 1), date(2026, 10, 27))
        db, current = Mock(), user()
        filters = filter_values(statuses=[WkdStatus.APPROVED])
        response = export_statistics(filters, db, current)
        scoped.assert_called_once_with(db, **filters)
        self.assertEqual(response.media_type, 'text/csv')
        self.assertIn('wmp-statistics.csv', response.headers['Content-Disposition'])


if __name__ == '__main__':
    unittest.main()
