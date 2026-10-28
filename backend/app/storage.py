from datetime import datetime
from urllib.parse import quote
import boto3
from botocore.config import Config
from .config import get_settings

settings = get_settings()
client = boto3.client('s3', endpoint_url=settings.rustfs_endpoint, aws_access_key_id=settings.rustfs_access_key,
                      aws_secret_access_key=settings.rustfs_secret_key, region_name=settings.rustfs_region,
                      config=Config(signature_version='s3v4', retries={'max_attempts': 3, 'mode': 'standard'}))


def upload_url(key: str, content_type: str | None) -> str:
    params = {'Bucket': settings.rustfs_bucket, 'Key': key}
    if content_type:
        params['ContentType'] = content_type
    return client.generate_presigned_url('put_object', Params=params, ExpiresIn=settings.presign_expire_seconds)


def download_url(key: str, filename: str) -> str:
    safe_fallback = ''.join(char if 32 <= ord(char) < 127 and char not in '"\\' else '_' for char in filename)
    disposition = f"attachment; filename=\"{safe_fallback}\"; filename*=UTF-8''{quote(filename)}"
    return client.generate_presigned_url('get_object', Params={'Bucket': settings.rustfs_bucket, 'Key': key,
        'ResponseContentDisposition': disposition, 'ResponseContentType': 'application/octet-stream'},
        ExpiresIn=settings.presign_expire_seconds)


def head_size(key: str) -> int:
    return int(client.head_object(Bucket=settings.rustfs_bucket, Key=key)['ContentLength'])


def read_object(key: str):
    """返回附件对象流，由调用方读取并关闭，避免一次性加载大文件。"""
    return client.get_object(Bucket=settings.rustfs_bucket, Key=key)['Body']


def delete_object(key: str) -> None:
    client.delete_object(Bucket=settings.rustfs_bucket, Key=key)


def create_multipart_upload(key: str, content_type: str | None) -> str:
    params = {'Bucket': settings.rustfs_bucket, 'Key': key}
    if content_type:
        params['ContentType'] = content_type
    return client.create_multipart_upload(**params)['UploadId']


def upload_part_url(key: str, upload_id: str, part_number: int) -> str:
    return client.generate_presigned_url('upload_part', Params={'Bucket': settings.rustfs_bucket, 'Key': key,
        'UploadId': upload_id, 'PartNumber': part_number}, ExpiresIn=settings.presign_expire_seconds)


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> None:
    client.complete_multipart_upload(Bucket=settings.rustfs_bucket, Key=key, UploadId=upload_id,
        MultipartUpload={'Parts': sorted(parts, key=lambda item: item['PartNumber'])})


def abort_multipart_upload(key: str, upload_id: str) -> None:
    client.abort_multipart_upload(Bucket=settings.rustfs_bucket, Key=key, UploadId=upload_id)


def abort_stale_multipart_uploads(prefix: str, older_than: datetime) -> int:
    count = 0
    paginator = client.get_paginator('list_multipart_uploads')
    for page in paginator.paginate(Bucket=settings.rustfs_bucket, Prefix=prefix):
        for item in page.get('Uploads', []):
            initiated = item['Initiated']
            if initiated.replace(tzinfo=None) < older_than:
                abort_multipart_upload(item['Key'], item['UploadId'])
                count += 1
    return count
