"""Verify that upstream drift fails closed and preserves previously prepared sources."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class HttpSourcePreparationTest(unittest.TestCase):
    def test_reproducible_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(ROOT / 'prepare-http-transport.py', root / 'prepare-http-transport.py')
            shutil.copytree(ROOT / 'http-compat', root / 'http-compat')
            shutil.copytree(ROOT / 'build/http-source-deps', root / 'build/http-source-deps')
            sdk = root / 'sdk'
            entry = json.loads((root / 'http-compat/sources.json').read_text())[-1]
            # Reconstruct the pinned original fixture from the prepared source and reverse patch.
            source = sdk / entry['sdk_prefix']
            shutil.copytree(ROOT / 'build/http-transport-src/sender', source)
            subprocess.run(['patch', '--batch', '--fuzz=0', '-R', '-p1', '-i',
                            str(root / 'http-compat/sender.patch')], cwd=source,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            command = [sys.executable, str(root / 'prepare-http-transport.py'), '--sdk', str(sdk)]
            def run():
                return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            def hashes():
                output = root / 'build/http-transport-src'
                return {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in output.rglob('*') if p.is_file()}
            first = run()
            self.assertEqual(0, first.returncode, first.stdout)
            expected = hashes()
            second = run()
            self.assertEqual(0, second.returncode, second.stdout)
            self.assertEqual(expected, hashes())
            original_file = source / next(iter(entry['sources']))
            original = original_file.read_bytes()
            original_file.write_bytes(original + b'\n// unexpected upstream change\n')
            drift = run()
            self.assertNotEqual(0, drift.returncode)
            self.assertIn(b'checksum mismatch', drift.stdout)
            self.assertEqual(expected, hashes())
            original_file.write_bytes(original)
            archive = next((root / 'build/http-source-deps').glob('*.jar'))
            archive.write_bytes(archive.read_bytes() + b'corrupt')
            corrupt = run()
            self.assertNotEqual(0, corrupt.returncode)
            self.assertIn(b'checksum mismatch', corrupt.stdout)
            self.assertEqual(expected, hashes())

if __name__ == '__main__':
    unittest.main()
