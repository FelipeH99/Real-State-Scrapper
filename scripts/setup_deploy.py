"""Create a local deployment token without printing or overwriting it."""
import os
import secrets
from pathlib import Path

root=Path(__file__).resolve().parents[1]
folder=root/'.secrets';folder.mkdir(exist_ok=True,mode=0o700);folder.chmod(0o700)
path=folder/'api_key'
try:
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
except FileExistsError:
    print('Existing deployment token preserved.')
else:
    with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(48)+'\n')
    print('Deployment token created in .secrets/api_key (not printed).')

# Compose mounts the secret into a non-root container; the host directory stays 0700.
path.chmod(0o444)
