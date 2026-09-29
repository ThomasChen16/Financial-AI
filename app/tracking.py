# Keeps track of the filename
import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = "data/uploads.db"

# create table to keep track of the uploaded files
_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    id          INTEGER    PRIMARY KEY AUTOINCREMENT,
    filename    TEXT       NOT NULL,
    file_type   TEXT       NOT NULL,
    chunk_count INTEGER    NOT NULL DEFAULT 0,
    uploaded_at TEXT       NOT NULL,
    UNIQUE (filename, file_type)
    
)
"""


def get_connection() -> sqlite3.Connection:
    # Ensure the database's parent directory exists before opening the connection.
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    # Establish connection to the SQLite database
    conn = sqlite3.connect(DB_PATH)
    
    # Create table
    conn.execute(_SCHEMA)
    
    # Save
    conn.commit()
    
    return conn

# retrieve from database and return if exist
def find_upload(filename: str, file_type: str) -> dict | None:
    conn = get_connection()
    
    try:
        row = conn.execute(
            "SELECT id, filename, file_type, chunk_count, uploaded_at "
            "FROM uploads WHERE filename = ? AND file_type = ?",
            (filename, file_type)
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0], "filename": row[1], "file_type": row[2],
            "chunk_count": row[3], "uploaded_at": row[4],
        }
    finally:
        conn.close()
        
# save into database after upload
def upsert_upload(filename: str, file_type: str, chunk_count: int) -> None:
    conn = get_connection()
    
    try:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        existing = conn.execute(
            "SELECT id FROM uploads WHERE filename = ? AND file_type = ?",
            (filename, file_type),
        ).fetchone()
        # if new upload, insert
        if existing is None:
            conn.execute(
                "INSERT INTO uploads (filename, file_type, chunk_count, uploaded_at)"
                "VALUES (?, ?, ?, ?)",
                (filename, file_type, chunk_count, now)
            )
        # if old upload, update
        else:
            conn.execute(
                "UPDATE uploads SET chunk_count = ?, uploaded_at = ? WHERE id = ?",
                (chunk_count, now, existing[0])
            )
        # save change
        conn.commit()
    finally:
        conn.close()

# retrieve uploaded files in table from newest first
def list_uploads() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, filename, file_type, chunk_count, uploaded_at "
            "FROM uploads ORDER BY uploaded_at DESC, id DESC"
        ).fetchall()
        return [
            {
                "id": row[0],
                "filename": row[1],
                "file_type": row[2],
                "chunk_count": row[3],
                "uploaded_at": row[4],
            }
            for row in rows
        ]
    finally:
        conn.close()
    


