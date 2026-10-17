"""Run the explicitly local sample-derived demo seed; never imported by Flask startup."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app.config import normalize_database_url
from app.seed.dev_seed import SeedInputError, load_seed, seed_demo, validate_seed


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed only the sample-derived local development fixture.")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "dev_demo_seed.json")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without opening a database connection.")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "seed-import-report.json")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env", override=False)
    environment = os.environ.get("APP_ENV", "").lower()
    report: dict = {"input": str(args.input), "mode": "dry-run" if args.dry_run else "database-import", "errors": [], "inserted": False}
    try:
        if not args.dry_run and environment != "development":
            raise SeedInputError([{"row": "APP_ENV", "message": "Development seed is disabled unless APP_ENV=development."}])
        payload = load_seed(args.input)
        errors = validate_seed(payload)
        report["format"] = payload.get("format")
        report["notice"] = payload.get("notice")
        if errors:
            raise SeedInputError(errors)
        report["validated"] = True
        report["record_counts"] = {
            "academic_years": len(payload["academic_years"]), "courses": len(payload["courses"]),
            "subjects": len(payload["subjects"]), "sections": len(payload["sections"]),
            "rooms": len(payload["rooms"]), "students": len(payload["students"]),
            "teachers": len(payload["teachers"]), "admins": len(payload["admins"]),
            "timetable_entries": sum(len(item.get("entries", [])) for item in payload["timetable_versions"] if isinstance(item, dict)),
        }
        if args.dry_run:
            report["inserted"] = False
        else:
            database_url = normalize_database_url(os.environ.get("DATABASE_URL"))
            demo_password = os.environ.get("DEMO_PASSWORD")
            if not database_url:
                raise SeedInputError([{"row": "DATABASE_URL", "message": "Set a development PostgreSQL URL before importing."}])
            database_host = make_url(database_url).host
            if database_host not in {"localhost", "127.0.0.1", "::1"}:
                raise SeedInputError([{"row": "DATABASE_URL", "message": "Development seed accepts loopback PostgreSQL hosts only."}])
            if not demo_password:
                raise SeedInputError([{"row": "DEMO_PASSWORD", "message": "Set a local-only demo password; it will be stored as a hash."}])
            engine = create_engine(database_url, pool_pre_ping=True)
            try:
                with Session(engine) as session, session.begin():
                    report["inserted_counts"] = seed_demo(session, payload, generate_password_hash(demo_password))
                report["inserted"] = True
            finally:
                engine.dispose()
    except SeedInputError as error:
        report.setdefault("validated", False)
        report["errors"] = error.errors
    except Exception as error:
        report["inserted"] = False
        report["errors"] = [{"row": "$database", "message": f"Transaction rolled back ({type(error).__name__}). Check the database constraints and local diagnostics."}]

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("validated") and (args.dry_run or report.get("inserted")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
