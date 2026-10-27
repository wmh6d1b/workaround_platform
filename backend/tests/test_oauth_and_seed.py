import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, Response

from app.config import get_settings
from app.models import Permission, Project
from app.oauth import begin_oauth_login, bind_oauth_user, complete_oauth_login, require_oauth_settings
from app.routers.auth import oauth_callback, oauth_login
from app.schemas import OAuthCallbackInput
from app.seed import PERMISSIONS, seed

OIDC_ENV = {
    'OAUTH_ENABLED': 'true',
    'OAUTH_ISSUER_URL': 'https://idp.example.internal',
    'OAUTH_CLIENT_ID': 'wmp-client',
    'OAUTH_CLIENT_SECRET': 'test-secret',
    'OAUTH_REDIRECT_URI': 'https://wmp.example.internal/oauth/callback',
}


def local_user(**changes):
    values = dict(id='user-1', username='zhangsan', employee_id='E1001', oauth_subject=None,
                  is_superuser=False, is_active=True, name='张三', email=None)
    values.update(changes)
    return SimpleNamespace(**values)


class OAuthConfigurationTests(unittest.TestCase):
    def setUp(self):
        get_settings.cache_clear()
        self.env = patch.dict(os.environ, OIDC_ENV, clear=False)
        self.env.start()
        get_settings.cache_clear()

    def tearDown(self):
        self.env.stop()
        get_settings.cache_clear()

    def test_authorization_url_contains_oidc_security_parameters(self):
        metadata = {'authorization_endpoint': 'https://idp.example.internal/authorize'}
        with patch('app.oauth.oidc_discovery', return_value=metadata):
            url, state, nonce = begin_oauth_login()
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query['response_type'], ['code'])
        self.assertEqual(query['client_id'], ['wmp-client'])
        self.assertEqual(query['redirect_uri'], [OIDC_ENV['OAUTH_REDIRECT_URI']])
        self.assertEqual(query['state'], [state])
        self.assertEqual(query['nonce'], [nonce])
        self.assertGreaterEqual(len(state), 32)
        self.assertGreaterEqual(len(nonce), 32)

    def test_production_requires_https_callback(self):
        with patch.dict(os.environ, {'ENVIRONMENT': 'production', 'OAUTH_REDIRECT_URI': 'http://wmp.internal/oauth/callback'}):
            get_settings.cache_clear()
            with self.assertRaises(HTTPException) as raised:
                require_oauth_settings()
        self.assertEqual(raised.exception.status_code, 503)

    def test_symmetric_id_token_algorithm_is_rejected(self):
        with patch.dict(os.environ, {'OAUTH_ID_TOKEN_ALGORITHM': 'HS256'}):
            get_settings.cache_clear()
            with self.assertRaises(HTTPException) as raised:
                require_oauth_settings()
        self.assertEqual(raised.exception.status_code, 503)

    def test_disabled_oauth_fails_closed(self):
        with patch.dict(os.environ, {'OAUTH_ENABLED': 'false'}):
            get_settings.cache_clear()
            with self.assertRaises(HTTPException) as raised:
                begin_oauth_login()
        self.assertEqual(raised.exception.status_code, 503)

    def test_login_sets_http_only_state_and_nonce_cookies(self):
        response = Response()
        with patch('app.routers.auth.begin_oauth_login', return_value=('https://idp/authorize', 'state', 'nonce')):
            result = oauth_login(response)
        self.assertEqual(result['authorization_url'], 'https://idp/authorize')
        cookies = response.headers.getlist('set-cookie')
        self.assertEqual(len(cookies), 2)
        self.assertTrue(all('HttpOnly' in item and 'SameSite=lax' in item for item in cookies))

    def test_callback_rejects_mismatched_state_before_token_exchange(self):
        request = SimpleNamespace(cookies={'wmp_oauth_state': 'expected', 'wmp_oauth_nonce': 'nonce'})
        with self.assertRaises(HTTPException) as raised:
            oauth_callback(OAuthCallbackInput(code='code', state='forged'), request, Response(), Mock())
        self.assertEqual(raised.exception.status_code, 401)

    def test_nonce_is_verified_against_id_token(self):
        metadata = {
            'issuer': OIDC_ENV['OAUTH_ISSUER_URL'], 'token_endpoint': 'https://idp/token',
            'jwks_uri': 'https://idp/jwks',
        }
        tokens = {'id_token': 'signed-id-token'}
        with patch('app.oauth._token_request', return_value=tokens), \
             patch('app.oauth.oidc_discovery', return_value=metadata), \
             patch('app.oauth.jwt.PyJWKClient') as jwks, \
             patch('app.oauth.jwt.decode', return_value={'sub': 'subject-1', 'nonce': 'expected'}) as decode:
            jwks.return_value.get_signing_key_from_jwt.return_value.key = 'public-key'
            claims = complete_oauth_login('code', 'expected')
        self.assertEqual(claims['sub'], 'subject-1')
        self.assertEqual(decode.call_args.kwargs['audience'], 'wmp-client')
        self.assertEqual(decode.call_args.kwargs['issuer'], OIDC_ENV['OAUTH_ISSUER_URL'])
        self.assertEqual(decode.call_args.kwargs['algorithms'], ['RS256'])


class OAuthUserBindingTests(unittest.TestCase):
    def setUp(self):
        get_settings.cache_clear()
        self.db = Mock()
        self.db.flush = Mock()

    def tearDown(self):
        get_settings.cache_clear()

    def test_existing_oidc_binding_uses_local_identity(self):
        user = local_user(oauth_subject='subject-1')
        self.db.scalar.return_value = user
        result = bind_oauth_user(self.db, {'sub': 'subject-1', 'name': '张三丰', 'email': 'zhangsan@example.internal'})
        self.assertIs(result, user)
        self.assertEqual(user.name, '张三丰')
        self.assertEqual(user.email, 'zhangsan@example.internal')
        self.db.flush.assert_called_once()

    def test_imported_user_is_bound_by_username_without_creating_user(self):
        user = local_user()
        self.db.scalar.side_effect = [None, user, user]
        result = bind_oauth_user(self.db, {'sub': 'subject-1', 'preferred_username': 'zhangsan', 'employee_id': 'E1001'})
        self.assertIs(result, user)
        self.assertEqual(user.oauth_subject, 'subject-1')
        self.db.add.assert_not_called()

    def test_unknown_enterprise_user_is_not_auto_registered(self):
        self.db.scalar.side_effect = [None, None, None]
        with self.assertRaises(HTTPException) as raised:
            bind_oauth_user(self.db, {'sub': 'unknown', 'preferred_username': 'unknown'})
        self.assertEqual(raised.exception.status_code, 403)
        self.db.add.assert_not_called()

    def test_superuser_must_use_local_admin_login(self):
        self.db.scalar.return_value = local_user(oauth_subject='admin-subject', is_superuser=True)
        with self.assertRaises(HTTPException) as raised:
            bind_oauth_user(self.db, {'sub': 'admin-subject'})
        self.assertEqual(raised.exception.status_code, 403)

    def test_disabled_user_cannot_login(self):
        self.db.scalar.return_value = local_user(oauth_subject='subject-1', is_active=False)
        with self.assertRaises(HTTPException) as raised:
            bind_oauth_user(self.db, {'sub': 'subject-1'})
        self.assertEqual(raised.exception.status_code, 403)

    def test_account_already_bound_to_other_subject_is_rejected(self):
        user = local_user(oauth_subject='other-subject')
        self.db.scalar.side_effect = [None, user, user]
        with self.assertRaises(HTTPException) as raised:
            bind_oauth_user(self.db, {'sub': 'subject-1', 'preferred_username': 'zhangsan', 'employee_id': 'E1001'})
        self.assertEqual(raised.exception.status_code, 409)


class SeedConfigurationTests(unittest.TestCase):
    def tearDown(self):
        get_settings.cache_clear()

    def test_demo_business_data_is_disabled_by_default(self):
        get_settings.cache_clear()
        self.assertFalse(get_settings().seed_demo_data)

    def test_empty_database_does_not_create_demo_project_when_disabled(self):
        get_settings.cache_clear()
        permissions = [Permission(code=code, module=code.split('.')[0], description=description)
                       for code, description in PERMISSIONS.items()]
        roles = [SimpleNamespace(id=f'role-{index}', name=name) for index, name in enumerate(('开发人员', '软件经理', '项目管理员', '系统管理员'))]
        db = Mock()
        db.get.side_effect = lambda model, code: next(item for item in permissions if item.code == code)
        db.scalars.return_value.all.return_value = permissions
        db.scalar.side_effect = [*roles, SimpleNamespace(id='admin-id'), None]
        with patch.dict(os.environ, {'SEED_DEMO_DATA': 'false'}), patch('app.seed.commit'):
            get_settings.cache_clear()
            seed(db)
        added_models = [call.args[0] for call in db.add.call_args_list]
        self.assertFalse(any(isinstance(item, Project) for item in added_models))


if __name__ == '__main__':
    unittest.main()
