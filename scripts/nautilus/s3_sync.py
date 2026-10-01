#!/usr/bin/env python
"""Sync between the private bucket ``s3://keck-etcs`` and the local mirror ``$KECK_ETCS_DATA``.

Usage:
    python scripts/nautilus/s3_sync.py ls   PREFIX
    python scripts/nautilus/s3_sync.py push PREFIX [--include GLOB ...] [--force] [--dry-run] [--jobs N]
    python scripts/nautilus/s3_sync.py pull PREFIX [--include GLOB ...] [--dry-run] [--jobs N]

PREFIX is a bucket key prefix such as ``mosfire/20220409/raw``; the matching
local directory is ``$KECK_ETCS_DATA/PREFIX`` (``keck_etcs.paths``), so the
two layouts are the same by construction (design 4.2).

- ``ls``   lists the objects under PREFIX with their sizes and whether the
  local copy is present and the same size.
- ``push`` uploads every local file under PREFIX (symlinks are followed)
  whose key is missing from the bucket or has a different size.
- ``pull`` downloads every object under PREFIX whose local copy is missing
  or has a different size.
- ``--include GLOB ...`` (push and pull) restricts the transfer to keys
  whose path relative to PREFIX matches one of the globs (``fnmatch``, so
  ``redux/*`` includes subdirectories).

Both transfers are idempotent by key and size, so a re-run after an
interruption only moves what is missing; ``--dry-run`` shows what would move.
``push --force`` uploads the selected files even when an object of the same
size exists (a ``REPLACE=1`` re-reduction produces new files of the same
size, e.g. FITS with new header dates).

Environment:
    ENDPOINT_URL      S3 endpoint (default https://s3-west.nrp-nautilus.io;
                      in a pod, http://rook-ceph-rgw-nautiluss3.rook)
    AWS_PROFILE       credentials profile (default ``default``), or
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
    KECK_ETCS_BUCKET  bucket (default keck-etcs)
    KECK_ETCS_DATA    local mirror root

The bucket is private. There is no anonymous fallback: missing credentials
or ``AccessDenied`` is a hard error (exit 3) that names the profile. No
credential value is ever printed.
"""
import argparse
import fnmatch
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

from keck_etcs import paths

ENDPOINT = os.environ.get('ENDPOINT_URL', 'https://s3-west.nrp-nautilus.io')
DENIED = {'AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch', '403', 'Forbidden'}


class AccessError(RuntimeError):
    pass


def credential_source():
    """Describe where the credentials come from (never their values)."""
    if os.environ.get('AWS_ACCESS_KEY_ID'):
        return 'environment variables AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY'
    return f"AWS profile '{os.environ.get('AWS_PROFILE', 'default')}'"


def make_client():
    if os.environ.get('AWS_ACCESS_KEY_ID'):
        session = boto3.session.Session()
    else:
        session = boto3.session.Session(profile_name=os.environ.get('AWS_PROFILE', 'default'))
    if session.get_credentials() is None:
        raise AccessError(f'no credentials found for {credential_source()}')
    return session.client('s3', endpoint_url=ENDPOINT,
                          config=Config(s3={'addressing_style': 'path'},
                                        retries={'max_attempts': 5, 'mode': 'standard'}))


def check_denied(exc, what):
    code = exc.response.get('Error', {}).get('Code', '')
    status = str(exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode', ''))
    if code in DENIED or status == '403':
        raise AccessError(f'{code or status} on {what} with {credential_source()} '
                          f'at {ENDPOINT}') from exc
    raise exc


def remote_sizes(client, bucket, prefix):
    """``{key: size}`` for every object under ``prefix/``."""
    out = {}
    try:
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket,
                                                                     Prefix=prefix + '/'):
            for obj in page.get('Contents', []):
                out[obj['Key']] = obj['Size']
    except ClientError as exc:
        check_denied(exc, f'list s3://{bucket}/{prefix}/')
    return out


def local_sizes(root, prefix):
    """``{key: (path, size)}`` for every file under ``root/prefix`` (symlinks followed)."""
    base = root / prefix
    out = {}
    if not base.exists():
        return out
    for dirpath, _dirs, files in os.walk(base, followlinks=True):
        for name in files:
            p = Path(dirpath) / name
            if p.is_file():
                out[f'{prefix}/{p.relative_to(base).as_posix()}'] = (p, p.stat().st_size)
    return out


def transfer(items, fn, jobs, label):
    done = failed = nbytes = 0
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(fn, *item): item for item in items}
        for fut in as_completed(futs):
            key = futs[fut][1]
            try:
                nbytes += fut.result()
                done += 1
                print(f'  {label} {key}', flush=True)
            except ClientError as exc:
                try:
                    check_denied(exc, key)
                except AccessError:
                    raise
                except ClientError:
                    failed += 1
                    print(f'  FAILED {key}: {exc}', flush=True)
    return done, failed, nbytes


def cmd_ls(client, bucket, root, prefix, args):
    remote = remote_sizes(client, bucket, prefix)
    local = local_sizes(root, prefix)
    print(f's3://{bucket}/{prefix}/  ({ENDPOINT}, {credential_source()})')
    for key in sorted(remote):
        size = remote[key]
        if key not in local:
            state = 'not local'
        elif local[key][1] == size:
            state = 'local same size'
        else:
            state = f'local size {local[key][1]} DIFFERS'
        print(f'  {size:>12d}  {key}  [{state}]')
    print(f'{len(remote)} objects, {sum(remote.values()) / 1e6:.1f} MB')
    return 0


def selected(key, prefix, globs):
    return not globs or any(fnmatch.fnmatch(key[len(prefix) + 1:], g) for g in globs)


def cmd_push(client, bucket, root, prefix, args):
    remote = remote_sizes(client, bucket, prefix)
    local = {k: v for k, v in local_sizes(root, prefix).items() if selected(k, prefix, args.include)}
    todo = [(p, key) for key, (p, size) in sorted(local.items())
            if args.force or remote.get(key) != size]
    print(f'push {root / prefix} -> s3://{bucket}/{prefix}/  ({ENDPOINT}, {credential_source()})')
    print(f'local files: {len(local)}  in bucket: {len(remote)}  to upload: {len(todo)}  '
          f'current (skipped): {len(local) - len(todo)}')
    if args.dry_run:
        for p, key in todo:
            print(f'  would upload {key} ({p.stat().st_size} bytes)')
        print('(dry run)')
        return 0

    def upload(p, key):
        client.upload_file(str(p), bucket, key)
        return p.stat().st_size

    done, failed, nbytes = transfer(todo, upload, args.jobs, 'uploaded')
    print(f'uploaded {done}, failed {failed}, {nbytes / 1e6:.1f} MB')
    return 1 if failed else 0


def cmd_pull(client, bucket, root, prefix, args):
    remote = {k: s for k, s in remote_sizes(client, bucket, prefix).items()
              if selected(k, prefix, args.include)}
    local = local_sizes(root, prefix)
    todo = [(root / key, key) for key, size in sorted(remote.items())
            if key not in local or local[key][1] != size]
    print(f'pull s3://{bucket}/{prefix}/ -> {root / prefix}  ({ENDPOINT}, {credential_source()})')
    print(f'selected objects: {len(remote)}  to download: {len(todo)}  '
          f'current (skipped): {len(remote) - len(todo)}')
    if args.dry_run:
        for _p, key in todo:
            print(f'  would download {key} ({remote[key]} bytes)')
        print('(dry run)')
        return 0

    def download(p, key):
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.is_symlink():          # never write through a symlink into another tree
            p.unlink()
        client.download_file(bucket, key, str(p))
        return p.stat().st_size

    done, failed, nbytes = transfer(todo, download, args.jobs, 'downloaded')
    print(f'downloaded {done}, failed {failed}, {nbytes / 1e6:.1f} MB')
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('command', choices=('ls', 'push', 'pull'))
    parser.add_argument('prefix', help='bucket key prefix, e.g. mosfire/20220409/raw')
    parser.add_argument('--dry-run', action='store_true', help='show what would be transferred')
    parser.add_argument('--jobs', type=int, default=8, help='parallel transfers (default 8)')
    parser.add_argument('--include', nargs='+', metavar='GLOB',
                        help='push/pull only keys (relative to PREFIX) matching these globs')
    parser.add_argument('--force', action='store_true',
                        help='push: upload even when an object of the same size exists')
    args = parser.parse_args(argv)

    prefix = args.prefix.strip('/')
    if not prefix or '..' in prefix.split('/'):
        parser.error(f'invalid prefix {args.prefix!r}')
    root = paths.data_root()
    try:
        client = make_client()
        return {'ls': cmd_ls, 'push': cmd_push, 'pull': cmd_pull}[args.command](
            client, paths.BUCKET, root, prefix, args)
    except (AccessError, NoCredentialsError, ProfileNotFound) as exc:
        print(f'ERROR: access to s3://{paths.BUCKET} denied: {exc}. The bucket is private; '
              f'set AWS_PROFILE to a profile with the Nautilus keys.', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
