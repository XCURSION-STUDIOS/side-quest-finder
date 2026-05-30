from sqlmodel import create_engine, SQLModel
from sqlalchemy import text

DATABASE_URL = "sqlite:///./data.db"
engine = create_engine(DATABASE_URL, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    ensure_sqlite_columns()

def ensure_sqlite_columns():
    """Lightweight local migration support for the prototype SQLite database."""
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        if "preference" in tables:
            pref_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(preference)"))
            }
            if "focus" not in pref_columns:
                conn.execute(text("ALTER TABLE preference ADD COLUMN focus TEXT DEFAULT '[]'"))
            if "settings" not in pref_columns:
                conn.execute(text("ALTER TABLE preference ADD COLUMN settings TEXT DEFAULT '{}'"))

        if "item" in tables:
            item_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(item)"))
            }
            migrations = {
                "activity_when": "ALTER TABLE item ADD COLUMN activity_when TEXT",
                "venue": "ALTER TABLE item ADD COLUMN venue TEXT",
                "location": "ALTER TABLE item ADD COLUMN location TEXT",
                "contact": "ALTER TABLE item ADD COLUMN contact TEXT",
                "score": "ALTER TABLE item ADD COLUMN score FLOAT DEFAULT 0",
                "shortlisted": "ALTER TABLE item ADD COLUMN shortlisted BOOLEAN DEFAULT 0",
                "feedback": "ALTER TABLE item ADD COLUMN feedback TEXT",
                "metadata_json": "ALTER TABLE item ADD COLUMN metadata_json TEXT DEFAULT '{}'",
            }
            for column, statement in migrations.items():
                if column not in item_columns:
                    conn.execute(text(statement))

        if "discoveryrun" in tables:
            run_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(discoveryrun)"))
            }
            run_migrations = {
                "completed_at": "ALTER TABLE discoveryrun ADD COLUMN completed_at DATETIME",
                "status": "ALTER TABLE discoveryrun ADD COLUMN status TEXT DEFAULT 'running'",
                "query_count": "ALTER TABLE discoveryrun ADD COLUMN query_count INTEGER DEFAULT 0",
                "source_count": "ALTER TABLE discoveryrun ADD COLUMN source_count INTEGER DEFAULT 0",
                "candidate_count": "ALTER TABLE discoveryrun ADD COLUMN candidate_count INTEGER DEFAULT 0",
                "accepted_count": "ALTER TABLE discoveryrun ADD COLUMN accepted_count INTEGER DEFAULT 0",
                "rejected_count": "ALTER TABLE discoveryrun ADD COLUMN rejected_count INTEGER DEFAULT 0",
                "summary": "ALTER TABLE discoveryrun ADD COLUMN summary TEXT",
                "settings_json": "ALTER TABLE discoveryrun ADD COLUMN settings_json TEXT DEFAULT '{}'",
            }
            for column, statement in run_migrations.items():
                if column not in run_columns:
                    conn.execute(text(statement))
