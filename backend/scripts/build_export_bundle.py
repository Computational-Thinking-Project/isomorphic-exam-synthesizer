"""Compile a supplied approved display snapshot into a local ZIP, without DB or AI.

Run: python backend/scripts/build_export_bundle.py snapshot.json --output-dir .artifacts/export
The caller must supply a genuinely locked snapshot; this CLI cannot verify DB approval.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.exporter.bundle_models import ApprovedExportSnapshot  # noqa: E402
from app.services.exporter.export_pipeline import build_compiled_bundle  # noqa: E402
from app.services.exporter.typst_compiler import TypstCompiler  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--typst-binary", default="typst")
    args = parser.parse_args()
    snapshot = ApprovedExportSnapshot.model_validate_json(args.snapshot.read_bytes())
    artifact = build_compiled_bundle(
        snapshot, compiler=TypstCompiler(binary_path=args.typst_binary)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    destination = args.output_dir / artifact.filename
    # Never replace an earlier bundle silently. No output is opened until compilation succeeds.
    with destination.open("xb") as output:
        output.write(artifact.data)
    print(json.dumps({
        "path": str(destination.resolve()), "revision": snapshot.revision,
        "size_bytes": artifact.size_bytes, "sha256": artifact.sha256,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
