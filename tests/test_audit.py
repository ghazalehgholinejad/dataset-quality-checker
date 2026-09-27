import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from dataset_quality.audit import audit
from dataset_quality.cli import main
from dataset_quality.demo import create_demo
from dataset_quality.report import render_html, save_report


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = create_demo(self.root/"dataset")

    def test_planted_issues_and_overlap_counts(self):
        s = audit(self.dataset)["summary"]
        self.assertEqual(s, {"files_scanned": 7, "readable_images": 6,
                            "unreadable_files": 1, "skipped_images": 0,
                            "flagged_files": 6, "duplicate_files": 3,
                            "byte_duplicate_groups": 1, "pixel_duplicate_groups": 1,
                            "cross_split_files": 3})

    def test_metadata_variants_have_same_pixels_not_same_bytes(self):
        report = audit(self.dataset)
        self.assertEqual(len(report["pixel_duplicates"][0]["paths"]), 3)
        self.assertEqual(len(report["byte_duplicates"][0]["paths"]), 2)
        self.assertEqual(report["pixel_duplicates"][0]["splits"], ["test", "train", "val"])

    def test_same_split_duplicates_are_not_leakage(self):
        for path in (self.dataset/"test").iterdir():
            path.unlink()
        (self.dataset/"val/scene-metadata.png").rename(self.dataset/"train/second.png")
        report = audit(self.dataset)
        self.assertEqual(report["summary"]["duplicate_files"], 2)
        self.assertEqual(report["summary"]["cross_split_files"], 0)

    def test_bad_files_do_not_stop_scan(self):
        rows = {r["path"]: r for r in audit(self.dataset)["files"]}
        self.assertEqual(rows["test/broken.jpg"]["status"], "unreadable")
        self.assertEqual(rows["train/unique.png"]["status"], "ok")

    def test_dimension_warnings(self):
        rows = {r["path"]: r for r in audit(self.dataset)["files"]}
        self.assertEqual(rows["train/tiny.png"]["flags"], ["small_image"])
        self.assertEqual(rows["val/panorama.png"]["flags"], ["extreme_aspect"])
        self.assertEqual(rows["train/unique.png"]["flags"], [])

    def test_alpha_is_preserved_for_duplicate_detection(self):
        Image.new("RGBA", (100, 100), (10, 20, 30, 255)).save(self.dataset/"train/opaque.png")
        Image.new("RGBA", (100, 100), (10, 20, 30, 0)).save(self.dataset/"test/transparent.png")
        report = audit(self.dataset)
        self.assertEqual(report["summary"]["duplicate_files"], 3)

    def test_exif_orientation_is_normalized(self):
        image = Image.new("RGB", (90, 120), "red")
        image.putpixel((5, 10), (0, 255, 0))
        exif = Image.Exif()
        exif[274] = 6
        image.save(self.dataset/"train/oriented.png", exif=exif)
        image.transpose(Image.Transpose.ROTATE_270).save(self.dataset/"test/rotated.png")
        report = audit(self.dataset)
        groups = [g for g in report["pixel_duplicates"] if "train/oriented.png" in g["paths"]]
        self.assertEqual(groups[0]["paths"], ["test/rotated.png", "train/oriented.png"])
        oriented = next(r for r in report["files"] if r["path"] == "train/oriented.png")
        self.assertEqual((oriented["width"], oriented["height"]), (120, 90))

    def test_pixel_limit_skips_decoding(self):
        report = audit(self.dataset, max_pixels=1000)
        self.assertEqual(report["summary"]["skipped_images"], 5)
        self.assertEqual(report["summary"]["readable_images"], 1)

    def test_animation_not_silently_treated_as_static(self):
        first = Image.new("RGB", (100, 100), "red")
        second = Image.new("RGB", (100, 100), "blue")
        first.save(self.dataset/"train/animated.png", save_all=True, append_images=[second], duration=100, loop=0)
        report = audit(self.dataset)
        row = next(r for r in report["files"] if r["path"] == "train/animated.png")
        self.assertEqual(row["flags"], ["multi_frame"])

    def test_symlinks_and_hidden_files_are_skipped(self):
        (self.dataset/"train/link.png").symlink_to(self.dataset/"train/scene.png")
        (self.dataset/"linked").symlink_to(self.dataset/"train", target_is_directory=True)
        (self.dataset/".hidden.png").write_bytes(b"not an image")
        self.assertEqual(audit(self.dataset)["summary"]["files_scanned"], 7)

    def test_deterministic_and_read_only(self):
        def hashes():
            return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.dataset.rglob("*") if p.is_file()}
        before = hashes()
        a, b = audit(self.dataset), audit(self.dataset)
        self.assertEqual(a, b)
        self.assertEqual(before, hashes())

    def test_threshold_and_split_validation(self):
        for kw in ({"min_side": 0}, {"max_pixels": 0}, {"max_aspect": float("nan")},
                   {"max_aspect": float("inf")}, {"max_aspect": 0.5},
                   {"splits": ["train", "train"]}, {"splits": ["../test"]}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                audit(self.dataset, **kw)

    def test_empty_dataset_rejected(self):
        empty = self.root/"empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "No supported"):
            audit(empty)

    def test_custom_split_names(self):
        (self.dataset/"val").rename(self.dataset/"validation")
        report = audit(self.dataset, splits=("train", "validation", "test"))
        self.assertEqual(report["pixel_duplicates"][0]["splits"], ["test", "train", "validation"])

    def test_html_escapes_filenames(self):
        (self.dataset/"train/<script>alert(1)<img>.png").write_bytes(b"invalid")
        html = render_html(audit(self.dataset))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_json_roundtrip_and_no_overwrite(self):
        report = audit(self.dataset)
        out = save_report(report, self.root/"report")
        self.assertEqual(report, json.loads((out/"report.json").read_text()))
        with self.assertRaises(FileExistsError):
            save_report(report, out)

    def test_cli_failure_gate_still_writes_report(self):
        out = self.root/"gate"
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit:
            main(["scan", str(self.dataset), "--output", str(out), "--fail-on-issues"])
        self.assertEqual(exit.exception.code, 1)
        self.assertTrue((out/"report.html").exists())

    def test_cli_rejects_output_inside_dataset(self):
        out = self.dataset/"report"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit:
            main(["scan", str(self.dataset), "--output", str(out)])
        self.assertEqual(exit.exception.code, 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
