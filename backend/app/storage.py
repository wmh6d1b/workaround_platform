import boto3
from botocore.config import Config
from .config import get_settings

settings = get_settings()
client = boto3.client('s3', endpoint_url=settings.rustfs_endpoint, aws_access_key_id=settings.rustfs_access_key,
                      aws_secret_access_key=settings.rustfs_secret_key, region_name=settings.rustfs_region,
                      config=Config(signature_version='s3v4'))

def upload_url(key: str, content_type: str | None) -> str:
    params = {'Bucket': settings.rustfs_bucket, 'Key': key}
    if content_type:
        params['ContentType'] = content_type
    return client.generate_presigned_url('put_object', Params=params, ExpiresIn=settings.presign_expire_seconds)

def download_url(key: str, filename: str) -> str:
    return client.generate_presigned_url('get_object', Params={'Bucket': settings.rustfs_bucket, 'Key': key,
        'ResponseContentDisposition': f'attachment; filename="{filename}"'}, ExpiresIn=settings.presign_expire_seconds)

def head_size(key: str) -> int:
    return int(client.head_object(Bucket=settings.rustfs_bucket, Key=key)['ContentLength'])
