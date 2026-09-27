"""Generate original synthetic fixtures with deliberately planted issues."""

from pathlib import Path
import shutil
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo


def create_demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for split in ("train", "val", "test"):
        (output/split).mkdir()
    image = Image.new("RGB", (256, 192), "#dbeafe")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 50, 115, 165), fill="#0f766e")
    draw.ellipse((150, 30, 225, 105), fill="#eab308")
    image.save(output/"train/scene.png")
    shutil.copyfile(output/"train/scene.png", output/"test/scene-copy.png")
    info = PngInfo()
    info.add_text("note", "Same pixels, different metadata")
    image.save(output/"val/scene-metadata.png", pnginfo=info)
    Image.new("RGB", (24, 24), "#d97706").save(output/"train/tiny.png")
    Image.new("RGB", (800, 80), "#4338ca").save(output/"val/panorama.png")
    Image.new("RGB", (200, 200), "#db2777").save(output/"train/unique.png")
    (output/"test/broken.jpg").write_bytes(b"Deliberately invalid synthetic JPEG fixture\n")
    (output/"ABOUT.txt").write_text("Synthetic demo: 7 candidate files, 6 readable, 1 unreadable, 3 duplicate files across splits.\n")
    return output
