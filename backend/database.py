
import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("backend.db")

# Database Configuration
# Use a persistent 'data' directory.
BASE_DIR = Path(__file__).resolve().parent

# Check for Docker Environment (Flattened structure at /app)
if Path("/app").exists():
    DATA_DIR = Path("/app/data")
else:
    # Local Environment (backend/database.py -> project/data)
    DATA_DIR = BASE_DIR.parent / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)       # Ensure it exists

from contextlib import contextmanager

DB_PATH = DATA_DIR / "soniq.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db_context():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initializes the database schema."""
    with get_db_context() as conn:
        c = conn.cursor()
        
        # Playlists Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS playlists (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                track_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # URLs Table (One-to-Many)
        c.execute('''
            CREATE TABLE IF NOT EXISTS playlist_urls (
                playlist_id TEXT,
                url TEXT,
                FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
            )
        ''')
        
        # History Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS job_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_name TEXT, 
                status TEXT,
                items_downloaded INTEGER DEFAULT 0,
                total_items INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
    logger.info(f"Database initialized at {DB_PATH}")

def get_playlists() -> List[Dict]:
    results = []
    with get_db_context() as conn:
        c = conn.cursor()
        rows = c.execute("SELECT * FROM playlists ORDER BY created_at DESC").fetchall()
        
        for row in rows:
            pl = dict(row)
            # Fetch URLs
            urls = c.execute("SELECT url FROM playlist_urls WHERE playlist_id = ?", (pl["id"],)).fetchall()
            pl["urls"] = [u["url"] for u in urls]
            results.append(pl)
            
    return results

def get_playlist(id: str) -> Optional[Dict]:
    with get_db_context() as conn:
        row = conn.execute("SELECT * FROM playlists WHERE id = ?", (id,)).fetchone()
        if not row:
            return None
            
        pl = dict(row)
        urls = conn.execute("SELECT url FROM playlist_urls WHERE playlist_id = ?", (id,)).fetchall()
        pl["urls"] = [u["url"] for u in urls]
        return pl

def save_playlist(id: str, name: str, urls: List[str], track_count: int = 0):
    with get_db_context() as conn:
        c = conn.cursor()
        try:
            # Upsert Playlist
            exists = c.execute("SELECT 1 FROM playlists WHERE id = ?", (id,)).fetchone()
            
            if exists:
                c.execute("UPDATE playlists SET name = ?, track_count = ? WHERE id = ?", (name, track_count, id))
                c.execute("DELETE FROM playlist_urls WHERE playlist_id = ?", (id,))
            else:
                c.execute("INSERT INTO playlists (id, name, track_count) VALUES (?, ?, ?)", (id, name, track_count))
                
            if urls:
                c.executemany("INSERT INTO playlist_urls (playlist_id, url) VALUES (?, ?)", 
                            [(id, u) for u in urls])
                            
            conn.commit()
        except Exception as e:
            conn.rollback() # Context manager doesn't catch exception, we handle transaction logic here
            raise e

def delete_playlist(id: str):
    with get_db_context() as conn:
        conn.execute("DELETE FROM playlists WHERE id = ?", (id,))
        conn.execute("DELETE FROM playlist_urls WHERE playlist_id = ?", (id,))
        conn.commit()

def update_track_count(id: str, count: int):
    with get_db_context() as conn:
        conn.execute("UPDATE playlists SET track_count = ? WHERE id = ?", (count, id))
        conn.commit()

def add_history_entry(playlist_name: str, status: str, downloaded: int, total: int, duration: float):
    with get_db_context() as conn:
        conn.execute(
            "INSERT INTO job_history (playlist_name, status, items_downloaded, total_items, duration_seconds) VALUES (?, ?, ?, ?, ?)",
            (playlist_name, status, downloaded, total, duration)
        )
        conn.commit()

def get_history(limit: int = 50) -> List[Dict]:
    with get_db_context() as conn:
        rows = conn.execute("SELECT * FROM job_history ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
