"""Installer mirrors must not write into RAG or change the downloaded bytes."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/scripts/publish-installer-mirror.py'
spec = importlib.util.spec_from_file_location('installer_mirror', SCRIPT)
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class InstallerMirrorTests(unittest.TestCase):
    def test_hosts_upload_exact_artifact_and_per_file_checksum_to_realease(self):
        for host, branch in [('ms', 'master'), ('hf', 'main')]:
            for suffix in ('.exe', '.dmg'):
                with self.subTest(host=host, suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                    installer = Path(tmp) / ('LazyMind-test' + suffix)
                    content = b'installer artifact fixture'
                    installer.write_bytes(content)
                    api = Mock()
                    uploads = []
                    api.upload_file.side_effect = lambda **kw: uploads.append((kw, Path(kw['path_or_fileobj']).read_bytes()))
                    with patch.dict(mirror.os.environ, {'GITHUB_STEP_SUMMARY': str(Path(tmp) / 'summary')}):
                        mirror.publish(installer, host, 'owner/repo', 'fixture-token', api=api)
                    self.assertEqual(len(uploads), 2)
                    self.assertEqual(uploads[0][1], content)
                    self.assertEqual(uploads[0][0]['path_in_repo'], 'Realease/' + installer.name)
                    self.assertEqual(uploads[1][0]['path_in_repo'], 'Realease/' + installer.name + '.sha256')
                    self.assertEqual(uploads[1][1].decode(), f'{hashlib.sha256(content).hexdigest()}  {installer.name}\n')
                    for args, _ in uploads:
                        self.assertEqual(args['revision'], branch)
                        self.assertEqual(args['repo_type'], 'dataset')
                    self.assertNotIn('fixture-token', (Path(tmp) / 'summary').read_text())

    def test_missing_token_and_invalid_artifacts_never_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = Mock()
            installer = Path(tmp) / 'LazyMind.exe'
            installer.write_bytes(b'fixture')
            with self.assertRaisesRegex(ValueError, 'token'):
                mirror.publish(installer, 'ms', 'owner/repo', '', api=api)
            for name in ('missing.dmg', 'rag.zip', 'empty.exe'):
                path = Path(tmp) / name
                if name != 'missing.dmg':
                    path.write_bytes(b'fixture' if name.endswith('.zip') else b'')
                with self.assertRaises(ValueError):
                    mirror.publish(path, 'hf', 'owner/repo', 'fixture-token', api=api)
            api.upload_file.assert_not_called()

    def test_failed_installer_upload_does_not_publish_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / 'LazyMind.dmg'
            installer.write_bytes(b'fixture')
            api = Mock()
            api.upload_file.side_effect = RuntimeError('upload failed')
            with self.assertRaisesRegex(RuntimeError, 'upload failed'):
                mirror.publish(installer, 'ms', 'owner/repo', 'fixture-token', api=api)
            self.assertEqual(api.upload_file.call_count, 1)


if __name__ == '__main__':
    unittest.main()
