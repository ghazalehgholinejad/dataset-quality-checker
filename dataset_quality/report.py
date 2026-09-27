"""Self-contained HTML and machine-readable JSON reports."""

from html import escape
import json
from pathlib import Path


def render_html(report):
    summary = report["summary"]
    cards = "".join(
        f'<div class="card"><span>{label}</span><strong>{summary[key]}</strong></div>'
        for key, label in [("files_scanned", "FILES SCANNED"), ("readable_images", "READABLE"),
                           ("flagged_files", "NEED REVIEW"), ("cross_split_files", "CROSS-SPLIT COPIES")]
    )
    duplicate_paths = {p for group in report["byte_duplicates"]+report["pixel_duplicates"] for p in group["paths"]}
    rows = []
    for row in report["files"]:
        flags = row["flags"] + (["duplicate"] if row["path"] in duplicate_paths else [])
        size = f'{row["width"]} × {row["height"]}' if "width" in row else "—"
        rows.append("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in
                    (row["path"], row["split"] or "unassigned", row["status"], size, ", ".join(flags) or "—")) + "</tr>")
    groups = []
    for key, label in [("byte_duplicates", "Identical bytes"), ("pixel_duplicates", "Identical decoded pixels")]:
        for group in report[key]:
            tag = ' <span class="tag">CROSS-SPLIT</span>' if group["cross_split"] else ""
            names = "".join(f"<li><code>{escape(path)}</code></li>" for path in group["paths"])
            groups.append(f'<div class="group"><h3>{label}{tag}</h3><ul>{names}</ul></div>')
    group_html = "".join(groups) or '<p class="muted">No exact duplicates detected.</p>'
    dims = "".join(f"<tr><td>{escape(k)}</td><td>{v}</td></tr>" for k, v in report["dimensions"].items())
    settings = escape(json.dumps(report["settings"], indent=2))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Image dataset quality report</title>
<style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f8;color:#172638;font:15px/1.6 system-ui,sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:48px 24px}}.eyebrow{{color:#006859;font-size:12px;letter-spacing:2px;font-weight:750}}
h1{{font-size:38px;line-height:1.15;margin:12px 0}}h2{{font-size:22px;margin:0 0 14px}}h3{{font-size:15px;margin:0 0 8px}}
.muted{{color:#576779}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0}}
.card,section{{background:white;border:1px solid #dce3eb;border-radius:12px;padding:22px}}.card span{{font-size:10px;letter-spacing:1px;color:#576779}}
.card strong{{display:block;font-size:36px}}section{{margin-top:18px}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;text-align:left}}
th{{color:#576779;font-size:11px;text-transform:uppercase;letter-spacing:1px}}th,td{{padding:12px 10px;border-bottom:1px solid #e6ebf1;vertical-align:top}}
td:first-child{{overflow-wrap:anywhere}}.group{{padding:16px;background:#f5f8fb;border-radius:8px;margin:12px 0}}
.tag{{color:#9a3412;background:#ffedd5;border-radius:4px;padding:3px 7px;font-size:10px;margin-left:10px}}code,pre{{font:13px/1.6 ui-monospace,monospace}}
code{{overflow-wrap:anywhere}}pre{{white-space:pre-wrap}}ul{{margin:0;padding-left:20px}}footer{{margin-top:24px;font-size:12px;color:#576779}}
@media(max-width:640px){{main{{padding:24px 12px}}h1{{font-size:30px}}.cards{{grid-template-columns:repeat(2,1fr)}}section{{padding:16px}}}}
</style></head><body><main>
<div class="eyebrow">DATASET QUALITY CHECKER / LOCAL AUDIT</div>
<h1>Know your images before training.</h1>
<p class="muted">Read-only inspection for unreadable files, exact copies and dimension warnings.</p>
<div class="cards">{cards}</div>
<section><h2>Duplicate review</h2><p class="muted">Cross-split copies are potential leakage. Review before changing a dataset. Byte and pixel groups can overlap.</p>{group_html}</section>
<section><h2>File inventory</h2><div class="scroll"><table><thead><tr><th>Relative path</th><th>Split</th><th>Status</th><th>Dimensions</th><th>Flags</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section><h2>Dimension distribution</h2><table><thead><tr><th>Width × height</th><th>Images</th></tr></thead><tbody>{dims}</tbody></table></section>
<section><h2>Audit settings</h2><pre>{settings}</pre><p class="muted">Only supported extensions are counted. No perceptual similarity, label validation or model accuracy is measured. Small or unusually shaped images are warnings, not automatic defects.</p></section>
<footer>Dataset Quality Checker {escape(report['tool_version'])} · Python {escape(report['environment']['python'])} · Pillow {escape(report['environment']['pillow'])} · No source files modified.</footer>
</main></body></html>'''


def save_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    (output/"report.html").write_text(render_html(report), encoding="utf-8")
    return output
