#!/usr/bin/env python3
"""Publish a verified ZIP and its online tag catalog to ModelScope (catalog last)."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

spec = importlib.util.spec_from_file_location('verify_components', Path(__file__).with_name('verify-python-components.py'))
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def publish(directory, repo, python=None, api=None):
    catalog_path = directory / 'python-components.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    entry = catalog['components']['rag']
    tag = entry.get('tag', '')
    verify.require(re.fullmatch(r'[a-f0-9]{64}', tag), 'Invalid component tag')
    verify.require(Path(entry['filename']).name == entry['filename'], 'Invalid ZIP filename')
    prefix = f'RAG/tags/{tag}'
    base = f'https://modelscope.cn/datasets/{repo}/resolve/master/{prefix}/'
    verify.require(entry['url'] == base + entry['filename'] and
                   entry['catalogUrl'] == base + 'python-components.json',
                   'Catalog URLs do not match the ModelScope upload destination')
    archive = directory / entry['filename']
    verify.check_archive(archive, entry)
    with tempfile.TemporaryDirectory(prefix='rag-publish-') as temporary:
        temp = Path(temporary)
        overlay = verify.extract_bundle(archive, temp / 'payload', entry)
        if entry['platform'] == 'darwin':
            verify.require(python is not None, 'Mac publication requires the signed bundled Python')
            verify.verify_macos_team_id(overlay, python)
        sums = temp / 'SHA256SUMS'
        sums.write_text(f'{entry["sha256"]}  {entry["filename"]}\n', encoding='utf-8')
        if api is None:
            from modelscope_hub import HubApi
            token = os.environ.get('MODELSCOPE_API_TOKEN')
            verify.require(token, 'MODELSCOPE_API_TOKEN is required')
            api = HubApi(token=token)
        # Make the payload available before changing the channel pointer.
        for source in (archive, sums, catalog_path):
            api.upload_file(repo_id=repo, repo_type='dataset', path_or_fileobj=str(source),
                            path_in_repo=f'{prefix}/{source.name}', revision='master',
                            commit_message=f'Publish RAG {tag}: {source.name}')
        published = verify.resolve_catalog_entry(entry)
        verify.require(published['sha256'] == entry['sha256'] and published['revision'] == entry['revision'],
                       'Published catalog does not match this build')
        verify.acquire_bundle(published, temp, None)
    print(f'Published and downloaded/verified {entry["catalogUrl"]}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--python', type=Path)
    args = parser.parse_args()
    publish(args.directory, args.repo, args.python)
