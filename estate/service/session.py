"""Short-lived signed web sessions; the API key never goes into browser storage."""
import hashlib
import hmac
import secrets
import time

COOKIE='estate_session'
LIFETIME=8*60*60


def issue(key):
    payload=f'{int(time.time())+LIFETIME}.{secrets.token_urlsafe(24)}'
    signature=hmac.new(key.encode(),payload.encode(),hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def valid(value,key):
    try:
        expiry,nonce,signature=value.split('.')
        payload=f'{expiry}.{nonce}'
        expected=hmac.new(key.encode(),payload.encode(),hashlib.sha256).hexdigest()
        return (int(time.time())<int(expiry)<=int(time.time())+LIFETIME
                and bool(nonce) and hmac.compare_digest(signature,expected))
    except (ValueError,TypeError,AttributeError):return False
