from time import time

import jwt
import redis
from cryptography.hazmat.backends import default_backend
from github import Github
from requests import Session

from .settings import Settings


def get_client(settings: Settings) -> Github:
    """
    This could all be async, but since it's call from sync code (that can't be async because of Github)
    there's no point in making it async.
    """
    redis_client = redis.from_url(settings.redis_dsn)
    cache_key = 'github_access_token'

    access_token: bytes | None = redis_client.get(cache_key)
    if access_token:
        return Github(access_token.decode())

    pem_bytes = settings.github_app_secret_key.read_bytes()

    private_key = default_backend().load_pem_private_key(pem_bytes, None)

    now = int(time())
    payload = {'iat': now - 30, 'exp': now + 60, 'iss': settings.github_app_id}
    jwt_value = jwt.encode(payload, private_key, algorithm='RS256')

    headers = {'Authorization': f'Bearer {jwt_value}', 'Accept': 'application/vnd.github+json'}
    session = Session()
    r = session.get('https://api.github.com/app/installations', headers=headers)

    # TODO find the correct installation
    installation_id = r.json()[0]['id']

    r = session.post(f'https://api.github.com/app/installations/{installation_id}/access_tokens', headers=headers)
    access_token = r.json()['token']
    redis_client.setex(cache_key, 3600 - 100, access_token)
    return Github(access_token)