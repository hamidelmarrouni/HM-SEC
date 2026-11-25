"""Configuration portability and preservation checks (no Docker needed)."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('hmsec', Path(__file__).resolve().parents[1] / 'scripts/hmsec.py')
hmsec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hmsec)


class ConfigurationTests(unittest.TestCase):
    def test_moved_folder_with_spaces_and_unrelated_working_directory(self):
        old_root, old_env = hmsec.ROOT, hmsec.ENV
        with tempfile.TemporaryDirectory(prefix='hm sec ') as directory:
            hmsec.ROOT = Path(directory)
            hmsec.ENV = hmsec.ROOT / 'runtime/.env.docker'
            (hmsec.ROOT / 'docker.env.example').write_text((old_root / 'docker.env.example').read_text())
            try:
                hmsec.initialize()
                initial = hmsec.ENV.read_bytes()
                self.assertNotIn(b'CHANGE_ME', initial)
                values = dict(line.split('=', 1) for line in initial.decode().splitlines() if line and not line.startswith('#'))
                keys = ['HMSEC_POSTGRES_PASSWORD', 'HMSEC_ACCESS_SECRET', 'HMSEC_REFRESH_SECRET', 'HMSEC_RESET_SECRET', 'HMSEC_OTP_SECRET', 'HMSEC_SEED_PASSWORD']
                self.assertEqual(len(set(values[key] for key in keys)), len(keys))
                if os.name != 'nt':
                    self.assertEqual(hmsec.ENV.stat().st_mode & 0o777, 0o600)
                hmsec.initialize()
                self.assertEqual(hmsec.ENV.read_bytes(), initial, 'Restart must preserve credentials')
                self.assertTrue((hmsec.ROOT / 'runtime/media').is_dir())
            finally:
                hmsec.ROOT, hmsec.ENV = old_root, old_env


if __name__ == '__main__':
    unittest.main()
