"""MyTree Professional RC16.18.2 - isolated Demo Mode launcher.

This launcher never replaces the production database. It creates/uses a private
runtime copy under demo_runtime/mytree.db and points MYTREE_DATA_DIR to it
before importing the application.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEMO_SOURCE = BASE / "demo" / "mytree_large_test.db"
DEMO_RUNTIME = BASE / "demo_runtime"
DEMO_DB = DEMO_RUNTIME / "mytree.db"


def ensure_demo_db(reset: bool = False) -> Path:
    if not DEMO_SOURCE.exists():
        raise FileNotFoundError(
            f"Base de démonstration introuvable: {DEMO_SOURCE}\n"
            "Exécutez d'abord generate_large_demo_db.py."
        )
    DEMO_RUNTIME.mkdir(parents=True, exist_ok=True)
    if reset or not DEMO_DB.exists():
        shutil.copy2(DEMO_SOURCE, DEMO_DB)
    return DEMO_DB


def main() -> int:
    parser = argparse.ArgumentParser(description="MyTree Professional RC16.18.2 - Demo Mode")
    parser.add_argument("--reset", action="store_true", help="Réinitialise les données de démonstration")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute (défaut: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port HTTP (défaut: 8080)")
    args = parser.parse_args()

    demo_db = ensure_demo_db(args.reset)

    # Must be set before app.py is imported because DB_PATH is resolved at import time.
    os.environ["MYTREE_DATA_DIR"] = str(DEMO_RUNTIME)
    os.environ.setdefault("MYTREE_SECRET", "mytree-rc16.18.2-demo-local-secret")

    from app import app, init_db  # noqa: E402

    init_db()

    print("=" * 72)
    print(" MyTree Professional RC16.18.2 - DEMO MODE")
    print(" Base isolée :", demo_db)
    print(f" URL locale   : http://{args.host}:{args.port}")
    print(" Super Admin  : 0550002026 / MyTree2026!")
    print(" Bénévoles    : vol001.. / Volunteer2026! (selon écran de connexion)")
    print(" Associations : DEMO-A01.. / Association2026!")
    print(" Réinitialiser: python demo_mode.py --reset")
    print("=" * 72)

    try:
        from waitress import serve
    except ImportError:
        print("Waitress absent. Installez les dépendances avec: pip install -r requirements.txt")
        return 2

    serve(app, host=args.host, port=args.port, threads=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
