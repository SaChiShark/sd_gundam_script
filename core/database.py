"""SQLite database manager for tracking SSR unit development status."""
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ssr_development_status.db")


class SSRDevelopmentDB:
    """Manages the developable_ssr_status table in SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create the table schema if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS developable_ssr_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_name TEXT NOT NULL,
                    route_name TEXT NOT NULL,
                    unit_name TEXT NOT NULL,
                    owned_count INTEGER DEFAULT 0,
                    current_stars INTEGER DEFAULT 0,
                    required_per_craft INTEGER NOT NULL,
                    held_books INTEGER DEFAULT 0,
                    crafts_needed INTEGER DEFAULT 0,
                    total_books_needed INTEGER DEFAULT 0,
                    books_shortage INTEGER DEFAULT 0,
                    is_deficient INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(series_name, route_name, unit_name)
                );
                """
            )
            conn.commit()
            logger.info(f"Database initialized at: {self.db_path}")

    def upsert_unit(
        self,
        series_name: str,
        route_name: str,
        unit_name: str,
        owned_count: int,
        current_stars: int,
        required_per_craft: int,
        held_books: int,
    ) -> Dict:
        """
        Calculate shortage and upsert SSR unit development status.

        Rules:
        - If unowned (owned_count == 0):
            crafts_needed = 1 (base craft) + 3 (star limit breaks) = 4
        - If owned (owned_count >= 1):
            crafts_needed = max(0, 3 - current_stars)
        - If current_stars == 3 (3 purple stars):
            crafts_needed = 0
        - total_books_needed = crafts_needed * required_per_craft
        - books_shortage = max(0, total_books_needed - held_books)
        - is_deficient = 1 if books_shortage > 0 else 0
        """
        if current_stars >= 3:
            crafts_needed = 0
        elif owned_count == 0:
            crafts_needed = 4
        else:
            crafts_needed = max(0, 3 - current_stars)

        total_books_needed = crafts_needed * required_per_craft
        books_shortage = max(0, total_books_needed - held_books)
        is_deficient = 1 if books_shortage > 0 else 0

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO developable_ssr_status (
                    series_name, route_name, unit_name, owned_count, current_stars,
                    required_per_craft, held_books, crafts_needed, total_books_needed,
                    books_shortage, is_deficient, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(series_name, route_name, unit_name) DO UPDATE SET
                    owned_count = excluded.owned_count,
                    current_stars = excluded.current_stars,
                    required_per_craft = excluded.required_per_craft,
                    held_books = excluded.held_books,
                    crafts_needed = excluded.crafts_needed,
                    total_books_needed = excluded.total_books_needed,
                    books_shortage = excluded.books_shortage,
                    is_deficient = excluded.is_deficient,
                    updated_at = excluded.updated_at
                """,
                (
                    series_name,
                    route_name,
                    unit_name,
                    owned_count,
                    current_stars,
                    required_per_craft,
                    held_books,
                    crafts_needed,
                    total_books_needed,
                    books_shortage,
                    is_deficient,
                    now_str,
                ),
            )
            conn.commit()

        logger.info(
            f"[{series_name} | {route_name}] {unit_name}: owned={owned_count}, stars={current_stars}★, "
            f"crafts_needed={crafts_needed}, held={held_books}/{total_books_needed}, shortage={books_shortage}"
        )

        return {
            "series_name": series_name,
            "route_name": route_name,
            "unit_name": unit_name,
            "owned_count": owned_count,
            "current_stars": current_stars,
            "required_per_craft": required_per_craft,
            "held_books": held_books,
            "crafts_needed": crafts_needed,
            "total_books_needed": total_books_needed,
            "books_shortage": books_shortage,
            "is_deficient": is_deficient,
        }

    def get_deficient_units(self) -> List[Dict]:
        """Fetch all SSR units that are deficient in technical books."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM developable_ssr_status
                WHERE is_deficient = 1
                ORDER BY series_name, unit_name
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_units(self) -> List[Dict]:
        """Fetch all recorded developable SSR units."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM developable_ssr_status
                ORDER BY series_name, unit_name
                """
            )
            return [dict(row) for row in cursor.fetchall()]
