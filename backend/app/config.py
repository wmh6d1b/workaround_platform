from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_name: str = 'WMP 规避措施管理平台'
    environment: str = 'development'
    database_url: str = 'postgresql+psycopg://wmp:wmp@localhost:5432/wmp'
    jwt_secret: str = 'development-only-change-me'
    jwt_expire_minutes: int = 720
    bootstrap_admin_username: str = 'admin'
    bootstrap_admin_password: str = 'wmp2026'
    seed_demo_data: bool = False
    oauth_enabled: bool = False
    oauth_issuer_url: str = ''
    oauth_client_id: str = ''
    oauth_client_secret: str = ''
    oauth_redirect_uri: str = ''
    oauth_scopes: str = 'openid profile email'
    oauth_token_auth_method: str = 'client_secret_basic'
    oauth_id_token_algorithm: str = 'RS256'
    oauth_username_claim: str = 'preferred_username'
    oauth_employee_id_claim: str = 'employee_id'
    oauth_department_claim: str = 'department'
    oauth_email_claim: str = 'email'
    cors_origins: str = 'http://localhost:7100,http://127.0.0.1:7100'
    rustfs_endpoint: str = 'http://localhost:9000'
    rustfs_access_key: str = 'wmp'
    rustfs_secret_key: str = 'wmp-secret'
    rustfs_bucket: str = 'wmp'
    rustfs_region: str = 'us-east-1'
    presign_expire_seconds: int = 300
    max_attachment_size: int = 500 * 1024 * 1024
    attachment_session_expire_hours: int = 24
    attachment_multipart_threshold: int = 64 * 1024 * 1024
    attachment_multipart_part_size: int = 16 * 1024 * 1024
    attachment_cleanup_interval_seconds: int = 3600
    attachment_cleanup_enabled: bool = True

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(',')]

@lru_cache
def get_settings() -> Settings:
    return Settings()
