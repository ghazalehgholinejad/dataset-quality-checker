# Dataset Quality Checker

[![tests](https://github.com/ghazalehgholinejad/dataset-quality-checker/actions/workflows/tests.yml/badge.svg)](https://github.com/ghazalehgholinejad/dataset-quality-checker/actions/workflows/tests.yml)

A small, read-only Python tool to inspect image datasets before training. Find unreadable files, exact duplicates, potential train/test leakage, and images with unusual dimensions. Get a portable **HTML report** and a **JSON inventory** without a GPU, model download, or external service.

## Quick start

Python 3.10+ and Pillow are the only runtime requirements.

```bash
git clone https://github.com/ghazalehgholinejad/dataset-quality-checker.git
cd dataset-quality-checker
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install .
dataset-check demo runs/demo
```

Open `runs/demo/report/report.html` in your browser. The demo creates its own synthetic images and deliberately plants known issues; no dataset is downloaded.

## What it detects

| Check | How it works |
| --- | --- |
| Unreadable images | Open and fully decode each supported image with Pillow |
| Byte duplicates | SHA-256 of the original file, streamed in chunks |
| Pixel duplicates | SHA-256 of dimensions and RGBA pixels after EXIF orientation correction |
| Cross-split copies | Duplicate groups spanning two or more configured split directories |
| Small images | Shortest side below a configurable threshold (default: 64 px) |
| Extreme aspect ratio | Longest side / shortest side above a threshold (default: 4) |
| Skipped images | Oversized and multi-frame images are explicitly reported |

Pixel comparison catches lossless files that contain the same decoded pixels but different metadata. It preserves alpha and dimensions; it does **not** treat resized, cropped, or recompressed images as exact duplicates.

## Scan your dataset

```bash
dataset-check scan ./data/images --output runs/audit
dataset-check scan ./data/images --output runs/custom \
  --min-side 96 --max-aspect 5 --splits train validation test
```

Default split recognition uses the **first directory below the dataset root**, with exact, case-sensitive names `train`, `val`, and `test`:

```text
data/images/
  train/cat/a.png
  val/cat/b.png
  test/cat/c.png
```

Other paths are marked `unassigned`. They still participate in duplicate detection, but do not establish cross-split leakage. Point the tool at the directory containing the split folders.

The scanner recursively considers `.png`, `.jpg`, `.jpeg`, `.bmp`, and `.webp` (case insensitive). Hidden entries, symbolic links, and other extensions are ignored and excluded from counts. Directory traversal failures abort the scan; individual unreadable image files appear in the report.

Output must be outside the dataset folder and must not already exist. Source images are never deleted, renamed, or repaired.

## Use as a CI check

```bash
dataset-check scan ./data/images --output runs/quality-gate --fail-on-issues
```

| Exit code | Meaning |
| --- | --- |
| `0` | Scan succeeded; findings are allowed unless the gate is enabled |
| `1` | Gate enabled and at least one file needs review; reports are still written |
| `2` | Invalid input, empty candidate set, or an operational error |

The gate includes duplicate files, dimension warnings, unreadable files, and skipped images. These are review signals, not proof that data should be removed.

## Reproducible demo results

The included synthetic demo produces these verified counts:

| Metric | Count |
| --- | ---: |
| Candidate files | 7 |
| Readable images | 6 |
| Unreadable files | 1 |
| Files in exact duplicate groups | 3 |
| Files in cross-split duplicate groups | 3 |
| Files needing review | 6 |

One scene is copied byte-for-byte into `test`, and another copy with different PNG metadata is placed in `val`. A small image, a panoramic image, and a broken JPEG illustrate the other checks. The remaining image has no warnings.

Byte and pixel groups overlap; summary file counts are **deduplicated**. The demo demonstrates software behavior, not performance on a real-world benchmark. A generated example is in [docs/sample-report.html](docs/sample-report.html); download it to view in a browser. Its machine-readable counterpart is [docs/sample-report.json](docs/sample-report.json).

## Python API

```python
from dataset_quality.audit import audit
from dataset_quality.report import save_report

report = audit("data/images", min_side=64, max_aspect=4.0)
print(report["summary"])
save_report(report, "runs/python-audit")
```

The CLI enforces the outside-dataset output rule; API callers should use the same convention.

## Tests

```bash
python -m unittest discover -s tests -v
```

18 tests cover planted issues, metadata variants, split detection, alpha preservation, EXIF orientation, animation and pixel limits, file safety, deterministic output, HTML escaping, and CLI exit codes. GitHub Actions runs tests and the demo on Python 3.10 and 3.12.

## Design and limits

- Processing is sequential, keeping decoded-image memory bounded by one image plus conversion buffers; inventory storage grows with the number of files. Hashing is linear in file bytes and decoded pixels, with no all-pairs image comparison.
- The default pixel cap is 40 million pixels per image. Pillow's own decompression-bomb protections also remain enabled. Increase `--max-pixels` only when appropriate for your available memory.
- Pixel normalization converts to 8-bit RGBA without ICC color management. Use this tool primarily for ordinary 8-bit image datasets; high-bit-depth imagery needs a specialized comparison policy.
- Animated or multi-frame inputs are reported as skipped, not compared using only their first frame. Byte duplicates may still be reported for these files or for unreadable files.
- Reports record tool, Python, and Pillow versions, thresholds, relative paths, and hashes. Keep inputs unchanged during a scan. Decoder-version differences can affect exact pixel hashes.
- Near duplicates, semantic similarity, labels, subject overlap, and image quality scores are outside this version's scope. A clean report does not establish that a train/test split is independent.

Built with [Pillow](https://python-pillow.github.io/) and Python's standard library. Original code and synthetic fixtures are MIT licensed.

Related project: [Image Robustness Kit](https://github.com/ghazalehgholinejad/image-robustness-kit) generates controlled image corruptions; this tool audits the input dataset.
