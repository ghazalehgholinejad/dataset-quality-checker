"""One-file-at-a-time image inspection; no source files are modified."""

from collections import Counter, defaultdict
import hashlib
import math
import os
from pathlib import Path
import platform
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
import PIL

from . import __version__

EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def discover(root):
    """Sorted recursive paths. Skip symlinks and hidden entries."""
    paths = []

    def on_error(error):
        raise error

    for base, dirs, files in os.walk(root, followlinks=False, onerror=on_error):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (Path(base)/d).is_symlink())
        for name in sorted(files):
            path = Path(base)/name
            if not name.startswith(".") and not path.is_symlink() and path.suffix.lower() in EXTENSIONS:
                paths.append(path)
    return sorted(paths)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect(path, root, splits, min_side, max_aspect, max_pixels):
    relative = path.relative_to(root)
    split = relative.parts[0] if len(relative.parts) > 1 and relative.parts[0] in splits else None
    row = {"path": relative.as_posix(), "split": split, "status": "ok", "flags": []}
    try:
        row["bytes"] = path.stat().st_size
        row["file_sha256"] = file_hash(path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as original:
                if original.width * original.height > max_pixels:
                    row.update(status="skipped", flags=["pixel_limit"])
                    return row
                if getattr(original, "n_frames", 1) != 1:
                    row.update(status="skipped", flags=["multi_frame"])
                    return row
                row["format"] = original.format
                row["original_mode"] = original.mode
                # Preserve alpha, normalize orientation and channel representation.
                image = ImageOps.exif_transpose(original).convert("RGBA")
                image.load()
                width, height = image.size
                row.update(width=width, height=height)
                digest = hashlib.sha256(f"RGBA:{width}:{height}:".encode("ascii"))
                digest.update(image.tobytes())
                row["pixel_sha256"] = digest.hexdigest()
                if min(width, height) < min_side:
                    row["flags"].append("small_image")
                if max(width, height) / min(width, height) > max_aspect:
                    row["flags"].append("extreme_aspect")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        row.update(status="skipped", flags=["pillow_pixel_limit"])
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError) as exc:
        row.update(status="unreadable", flags=["unreadable"], error=type(exc).__name__)
    return row


def duplicate_groups(rows, key):
    groups = defaultdict(list)
    for row in rows:
        if key in row:
            groups[row[key]].append(row)
    result = []
    for digest, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        splits = sorted({r["split"] for r in members if r["split"] is not None})
        result.append({"sha256": digest, "paths": [r["path"] for r in members],
                       "splits": splits, "cross_split": len(splits) > 1})
    return result


def audit(root, *, min_side=64, max_aspect=4.0, max_pixels=40_000_000,
          splits=("train", "val", "test")):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Dataset must be an existing directory")
    if min_side < 1 or max_pixels < 1 or not math.isfinite(max_aspect) or max_aspect < 1:
        raise ValueError("min-side and max-pixels must be positive; max-aspect must be finite and >= 1")
    if len(set(splits)) != len(splits) or any(not s or s in {".", ".."} or "/" in s or "\\" in s for s in splits):
        raise ValueError("Split names must be unique immediate directory names")
    paths = discover(root)
    if not paths:
        raise ValueError("No supported images found (PNG, JPEG, BMP, WebP)")
    rows = [inspect(p, root, splits, min_side, max_aspect, max_pixels) for p in paths]
    byte_groups = duplicate_groups(rows, "file_sha256")
    pixel_groups = duplicate_groups(rows, "pixel_sha256")
    duplicate_paths = {p for group in byte_groups+pixel_groups for p in group["paths"]}
    cross_paths = {p for group in byte_groups+pixel_groups if group["cross_split"] for p in group["paths"]}
    flagged = {r["path"] for r in rows if r["flags"]} | duplicate_paths
    dimensions = Counter(f'{r["width"]} x {r["height"]}' for r in rows if r["status"] == "ok")
    return {
        "schema_version": 1,
        "tool_version": __version__,
        "environment": {"python": platform.python_version(), "pillow": PIL.__version__},
        "settings": {"min_side": min_side, "max_aspect": max_aspect,
                     "max_pixels": max_pixels, "splits": list(splits)},
        "summary": {
            "files_scanned": len(rows), "readable_images": sum(r["status"] == "ok" for r in rows),
            "unreadable_files": sum(r["status"] == "unreadable" for r in rows),
            "skipped_images": sum(r["status"] == "skipped" for r in rows),
            "flagged_files": len(flagged), "duplicate_files": len(duplicate_paths),
            "byte_duplicate_groups": len(byte_groups), "pixel_duplicate_groups": len(pixel_groups),
            "cross_split_files": len(cross_paths),
        },
        "dimensions": dict(sorted(dimensions.items())),
        "byte_duplicates": byte_groups,
        "pixel_duplicates": pixel_groups,
        "files": rows,
    }
