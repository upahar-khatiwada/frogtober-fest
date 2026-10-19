"""The synthetic seed tender set (data/seed_tenders/): the demo's primary source (spec section 17).

The manifest lists every notice file plus hand-labelled ground truth (`expected`)
for Scout golden-set checks. Only the raw text goes to the DB.
"""

import json
from pathlib import Path

from ingest.notices import RawNotice

SEED_URL_PREFIX = "seed://seed_tenders/"


class SeedDataError(RuntimeError):
    pass


def load_manifest(seed_dir: Path) -> dict:
    path = seed_dir / "manifest.json"
    if not path.is_file():
        raise SeedDataError(f"seed manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("synthetic") is not True:
        raise SeedDataError("seed manifest must be labelled synthetic: true")
    return manifest


def seed_source_url(file: str) -> str:
    """Stable, clearly non-web source_url, so seeds never collide with scraped notices."""
    return SEED_URL_PREFIX + file


def load_seed_notices(seed_dir: Path) -> list[RawNotice]:
    notices = []
    for entry in load_manifest(seed_dir)["notices"]:
        path = seed_dir / entry["file"]
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SeedDataError(f"cannot read seed notice {path}: {exc}") from exc
        notices.append(RawNotice(seed_source_url(entry["file"]), text))
    return notices
