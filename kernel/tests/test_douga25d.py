"""実機試験は SEISEI_25D=1 の明示時だけ行う。"""
import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("SEISEI_25D") == "1", "SEISEI_25D=1 の時だけ実機試験")
class Douga25DDeviceTest(unittest.TestCase):
    def test_make_small_video(self):
        from douga25d import make

        image = Path(os.environ["SEISEI_25D_IMAGE"]).expanduser()
        with tempfile.TemporaryDirectory(prefix="test-douga25d-") as temp:
            result = make(image, Path(temp) / "result", seconds=1, motion="dolly", strength=0.12)
            self.assertTrue(result["ok"], result["結果"])
            self.assertTrue(Path(result["動画"]).is_file())
            self.assertTrue(Path(result["画像"][0]).is_file())


if __name__ == "__main__" and os.environ.get("SEISEI_25D") == "1":
    unittest.main()
