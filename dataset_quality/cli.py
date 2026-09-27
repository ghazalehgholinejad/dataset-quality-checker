import argparse
from pathlib import Path

from .audit import audit
from .demo import create_demo
from .report import save_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only quality checks for image datasets")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="Write HTML/JSON audit reports")
    scan.add_argument("dataset", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--min-side", type=int, default=64)
    scan.add_argument("--max-aspect", type=float, default=4.0)
    scan.add_argument("--max-pixels", type=int, default=40_000_000)
    scan.add_argument("--splits", nargs="+", default=["train", "val", "test"])
    scan.add_argument("--fail-on-issues", action="store_true", help="Exit 1 if any file needs review")
    demo = commands.add_parser("demo", help="Generate and audit a synthetic dataset")
    demo.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            args.output.mkdir(parents=True, exist_ok=False)
            dataset = create_demo(args.output/"dataset")
            report = audit(dataset)
            output = save_report(report, args.output/"report")
        else:
            if args.output.resolve().is_relative_to(args.dataset.resolve()):
                raise ValueError("Report output must be outside the dataset directory")
            if args.output.exists():
                raise FileExistsError("Report output already exists; choose a new directory")
            report = audit(args.dataset, min_side=args.min_side, max_aspect=args.max_aspect,
                           max_pixels=args.max_pixels, splits=args.splits)
            output = save_report(report, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    summary = report["summary"]
    print(f"Scanned {summary['files_scanned']} files; {summary['flagged_files']} need review.")
    print(f"Report: {output/'report.html'}")
    if getattr(args, "fail_on_issues", False) and summary["flagged_files"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
