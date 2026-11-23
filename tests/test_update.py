import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alvenus import update as up

NOTES = """# What's new
## 1.2.0 (25 Nov 2026)
- Faster previews.
- New paper.

## 1.1.0 (20 Nov 2026)
- Fixes.

## 0.1.0
- First.
"""


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"VENUS_HOME": str(self.tmp / "home")})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_versions_and_notes(self):
        self.assertTrue(up.newer("1.10.0", "1.9.3"))
        self.assertFalse(up.newer("0.9.0", "0.9.0"))
        rel = up.read_notes(NOTES)
        self.assertEqual([r["version"] for r in rel], ["1.2.0", "1.1.0", "0.1.0"])
        self.assertEqual(rel[0]["notes"], ["Faster previews.", "New paper."])

    def test_check_from_a_local_copy(self):
        src = self.tmp / "venus"
        src.mkdir()
        (src / "CHANGES.md").write_text(NOTES)
        with mock.patch.object(up, "__version__", "1.0.0"):
            res = up.check(str(src))
        self.assertTrue(res["update"])
        self.assertEqual(res["latest"], "1.2.0")
        self.assertEqual([r["version"] for r in res["whats_new"]], ["1.2.0", "1.1.0"])
        self.assertIn("Faster previews", up.say_check(res))

    def test_offline_is_quiet(self):
        with mock.patch.object(up, "_fetch", side_effect=OSError("offline")):
            res = up.check()
        self.assertFalse(res["update"])
        self.assertIn("could not check", res["error"])

    def test_only_its_own_repository(self):
        with self.assertRaises(ValueError):
            up._fetch("https://example.com/venus.tar.gz")
        with self.assertRaises(ValueError):
            up._fetch("http://codeload.github.com/x")

    def test_unsafe_download_is_refused(self):
        tar = self.tmp / "bad.tar.gz"
        with tarfile.open(tar, "w:gz") as t:
            data = b"x"
            info = tarfile.TarInfo("../escape.txt")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        out = self.tmp / "out"
        out.mkdir()
        with self.assertRaises(ValueError):
            up._safe_extract(tar, out)
        self.assertFalse((self.tmp / "escape.txt").exists())

    def test_backup_and_restore_put_the_old_version_back(self):
        site = self.tmp / "site"
        pkg = site / "alvenus"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text('__version__ = "1.0.0"\n')
        info = site / "alvenus-1.0.0.dist-info"
        info.mkdir()
        (info / "METADATA").write_text("Name: alvenus\n")
        with mock.patch.object(up, "installed_files", return_value=(pkg, [info])), mock.patch.object(up, "__version__", "1.0.0"):
            b = up.backup()
        # a "new version" replaces it
        (pkg / "__init__.py").write_text('__version__ = "2.0.0"\n')
        info.rename(site / "alvenus-2.0.0.dist-info")
        self.assertEqual(up.restore(b), "1.0.0")
        self.assertIn("1.0.0", (pkg / "__init__.py").read_text())
        self.assertTrue((site / "alvenus-1.0.0.dist-info").exists())
        self.assertFalse((site / "alvenus-2.0.0.dist-info").exists())
        self.assertEqual(json.loads((b / "backup.json").read_text())["version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
