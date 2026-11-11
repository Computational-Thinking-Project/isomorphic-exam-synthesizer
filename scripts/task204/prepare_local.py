"""Prepare migrations for a dedicated, unlinked Supabase Local workspace."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "task204-supabase-local"


def prepare(workdir: Path):
    workdir = workdir.resolve()
    config = workdir / "supabase/config.toml"
    text = config.read_text(encoding="utf-8-sig")
    if f'project_id = "{PROJECT}"' not in text:
        raise SystemExit("Refusing a workspace without the dedicated TASK-204 project ID")
    if (workdir / "supabase/.temp/project-ref").exists():
        raise SystemExit("Refusing a workspace linked to a remote project")
    destination = workdir / "supabase/migrations"
    if destination.exists() and list(destination.glob("*.sql")):
        raise SystemExit("Migration destination must be empty; never overwrite migration history")
    sources = [ROOT / "backend/scripts/schema.sql", *sorted((ROOT / "backend/migrations").glob("*.sql"))]
    manifest = []
    destination.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(sources):
        body = source.read_text(encoding="utf-8-sig")
        name = f"2026110800{index:04d}_{source.stem}.sql"
        (destination / name).write_text(body, encoding="utf-8")
        manifest.append({"source": source.relative_to(ROOT).as_posix(), "migration": name,
                         "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                         "empty": not body.strip()})
    (workdir / "migration-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path)
    result = prepare(parser.parse_args().workdir)
    print(f"Prepared {len(result)} migrations; manifest contains no credentials")
