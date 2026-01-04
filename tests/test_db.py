from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

try:
    from orun import db
except ModuleNotFoundError as import_error:  # pragma: no cover - environment guard
    db = None  # type: ignore[assignment]
    IMPORT_ERROR = import_error
else:
    IMPORT_ERROR = None


class ShutdownDbTestCase(unittest.TestCase):
    def test_shutdown_db_closes_open_connection(self) -> None:
        """Ensure shutdown_db closes the database when open."""
        if db is None:
            self.skipTest(f"Peewee is not available: {IMPORT_ERROR}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_db_path = Path(tmp_dir) / "history.db"
            original_db_path = db.DB_PATH
            original_db_dir = db.DB_DIR
            original_database = db.db.database

            try:
                db.DB_DIR = temp_db_path.parent
                db.DB_PATH = temp_db_path
                db.DB_DIR.mkdir(parents=True, exist_ok=True)
                db.db.init(temp_db_path)

                db.initialize()
                self.assertFalse(db.db.is_closed())

                db.shutdown_db()
                self.assertTrue(db.db.is_closed())
            finally:
                db.DB_DIR = original_db_dir
                db.DB_PATH = original_db_path
                db.db.init(original_database)
                if not db.db.is_closed():
                    db.db.close()


if __name__ == "__main__":
    unittest.main()
