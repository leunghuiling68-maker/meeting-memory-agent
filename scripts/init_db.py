"""Initialize the local SQLite database."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meeting_memory.db.connection import get_connection, init_db
from meeting_memory.db.seed import ensure_demo_project


def main() -> None:
    db_path = Path("data/meeting_memory.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        init_db(conn)
        project_id = ensure_demo_project(conn)
    print(f"SQLite database ready at {db_path} with demo project #{project_id}")


if __name__ == "__main__":
    main()
