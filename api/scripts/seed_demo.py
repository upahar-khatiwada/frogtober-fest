"""Seed the fictional demo company and its KB documents from data/demo_company/.

Overwrites the (single) company profile and re-ingests the manifest's
documents, so it is safe to re-run. Needs migrated Postgres
(`uv run alembic upgrade head`) and Ollama with EMBED_MODEL pulled.

    cd api && uv run python -m scripts.seed_demo [--data-dir PATH] [--database-url URL]
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from config import get_settings
from db.models import Document
from db.runs import make_run_recorder
from db.session import make_engine
from ingest.kb import create_document, ingest_document
from nepal.dates import bs_to_ad, parse_bs_date
from pipeline.llm import LLMClient
from routers.company import upsert_company_profile
from schemas import CompanyProfile, DocType, IngestStatus

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_company"
CONTENT_TYPES = {".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
                 ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def seed(data_dir: Path, database_url: str, client: LLMClient | None = None) -> dict[str, IngestStatus]:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    profile = CompanyProfile.model_validate_json((data_dir / "profile.json").read_text(encoding="utf-8"))
    engine = make_engine(database_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    owns_client = client is None
    client = client or LLMClient(make_run_recorder(factory))
    results: dict[str, IngestStatus] = {}
    try:
        with factory() as session:
            company = upsert_company_profile(session, profile)
            filenames = [entry["file"] for entry in manifest["documents"]]
            session.execute(delete(Document).where(Document.company_id == company.id, Document.filename.in_(filenames)))
            session.commit()
            for entry in manifest["documents"]:
                path = data_dir / entry["file"]
                expires_bs = entry.get("expires_on_bs")
                document = create_document(
                    session,
                    company_id=company.id,
                    filename=path.name,
                    content=path.read_bytes(),
                    content_type=CONTENT_TYPES.get(path.suffix.lower()),
                    doc_type=DocType(entry["doc_type"]),
                    expires_on=bs_to_ad(parse_bs_date(expires_bs)) if expires_bs else None,
                    fiscal_year_bs=entry.get("fiscal_year_bs"),
                    value_npr=entry.get("value_npr"),
                )
                results[path.name] = ingest_document(session, document, client)
                expiry = f", expires {document.expires_on}" if document.expires_on else ""
                error = f" ({document.ingest_error})" if document.ingest_error else ""
                print(f"  {path.name}: {results[path.name]}{expiry}{error}")
    finally:
        if owns_client:
            client.close()
        engine.dispose()
    return results


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--database-url", default=get_settings().database_url)
    args = parser.parse_args()
    print(f"Seeding demo company from {args.data_dir}")
    results = seed(args.data_dir, args.database_url)
    failed = [name for name, status in results.items() if status is not IngestStatus.READY]
    if failed:
        print(f"Not ready: {', '.join(failed)}. Is Ollama up with {get_settings().embed_model} pulled? Re-run to retry.")
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
