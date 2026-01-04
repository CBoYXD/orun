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
from __future__ import annotations

import importlib
import unittest
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase, mock

try:
    import peewee  # type: ignore
except ImportError:
    peewee = None


@unittest.skipUnless(peewee is not None, "peewee is required for database tests")
class MaintainDbSizeTests(TestCase):
    """Ensure database cleanup removes empty conversations when limits are exceeded."""

    def setUp(self) -> None:
        """Prepare an isolated database in a temporary home directory."""
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)

        # Ensure every db module import uses the temp home directory.
        self.path_home_patcher = mock.patch("pathlib.Path.home", return_value=temp_path)
        self.path_home_patcher.start()

        # Enable importing the package from the repository's src directory.
        project_root = Path(__file__).resolve().parents[1]
        src_path = project_root / "src"
        self.src_path_entry = str(src_path)
        sys.path.insert(0, self.src_path_entry)

        # Reload db module so it binds to the patched home directory.
        sys.modules.pop("orun.db", None)
        import orun.db as db_mod

        self.db_mod = importlib.reload(db_mod)
        self.config_patcher = mock.patch.object(
            self.db_mod.orun_config,
            "get_section",
            return_value={
                "max_size_mb": 0.000001,  # Trigger cleanup aggressively.
                "cleanup_fraction": 0.05,
                "min_age_days": 0.1,
            },
        )
        self.config_patcher.start()
        self.db_mod.initialize()

    def tearDown(self) -> None:
        """Close database connections and restore patched state."""
        self.db_mod.db.close()
        self.config_patcher.stop()
        self.path_home_patcher.stop()
        if self.src_path_entry in sys.path:
            sys.path.remove(self.src_path_entry)
        self.temp_dir.cleanup()

    def test_empty_conversations_are_deleted_when_cleanup_needed(self) -> None:
        """Empty conversations should be eligible for cleanup and removed first."""
        old_time = datetime.now() - timedelta(days=2)
        empty_conv_id = self.db_mod.create_conversation(model="empty")
        self.db_mod.Conversation.update(updated_at=old_time).where(
            self.db_mod.Conversation.id == empty_conv_id
        ).execute()

        recent_time = datetime.now() - timedelta(hours=1)
        kept_conv_id = self.db_mod.create_conversation(model="kept")
        self.db_mod.add_message(
            conversation_id=kept_conv_id,
            role="user",
            content="hello world",
        )
        self.db_mod.Conversation.update(updated_at=recent_time).where(
            self.db_mod.Conversation.id == kept_conv_id
        ).execute()

        self.db_mod.maintain_db_size()

        remaining_ids = {conv.id for conv in self.db_mod.Conversation.select()}
        self.assertNotIn(empty_conv_id, remaining_ids)
        self.assertIn(kept_conv_id, remaining_ids)
