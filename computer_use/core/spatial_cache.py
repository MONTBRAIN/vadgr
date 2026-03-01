"""Muscle memory cache: SQLite + R-Tree spatial index.

Learns from repeated mouse interactions so familiar UI targets are reached
faster and with straighter paths -- like human muscle memory.

Runs on the Windows daemon side. Zero external dependencies (sqlite3 is stdlib).

Usage:
    cache = MuscleMemoryCache("muscle_memory.db")
    entry = cache.lookup("notepad.exe", "File menu", 50, 12)
    if entry:
        # Use entry.hit_count to adapt movement speed
        ...
    cache.record_hit("notepad.exe", "File menu", 50, 12, 80, 24)
    cache.close()
"""

import logging
import math
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("bridge.spatial_cache")

# Power Law of Practice: T(n) = T(1) * n^(-alpha)
# Models motor skill speed-up with repetition.
POWER_LAW_ALPHA = 0.4
POWER_LAW_FLOOR = 0.3  # never faster than 30% of base duration

# Temporal decay: confidence halves every DECAY_HALF_LIFE seconds.
DECAY_HALF_LIFE = 7 * 24 * 3600  # 7 days in seconds
DECAY_MIN_CONFIDENCE = 0.1  # below this, entry is effectively forgotten

# Spatial proximity: max distance (px) for R-Tree lookup to match.
SPATIAL_RADIUS = 50

# EMA smoothing alpha for position updates (0 = no change, 1 = instant snap).
EMA_ALPHA = 0.3

# Cache limits.
MAX_ENTRIES = 10_000

# Navigation batch: stricter thresholds for autonomous (LLM-free) navigation.
MIN_NAV_HIT_COUNT = 3       # need 3+ hits before trusting for autonomous nav
MIN_NAV_CONFIDENCE = 0.5    # minimum decayed confidence for nav
MIN_NAV_SEQ_COUNT = 2        # sequence edge must be seen 2+ times
MAX_NAV_CHAIN_DEPTH = 5      # max BFS depth for path finding


@dataclass
class CacheEntry:
    """A remembered UI target position."""
    id: int
    app_name: str
    element_hint: str
    x: float
    y: float
    width: float
    height: float
    hit_count: int
    miss_count: int
    last_hit_ts: float
    created_ts: float
    confidence: float
    prev_hint: str


class MuscleMemoryCache:
    """Spatially-indexed memory of UI target locations.

    Three-tier lookup:
    1. In-memory dict (exact app + hint match) -- sub-microsecond
    2. SQLite R-Tree (spatial proximity within SPATIAL_RADIUS) -- ~0.1ms
    3. Cache miss -- returns None
    """

    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        self._hot: dict[str, CacheEntry] = {}  # key: "app|hint"
        self._load_hot_cache()

    def _create_tables(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name    TEXT NOT NULL,
                element_hint TEXT NOT NULL,
                x           REAL NOT NULL,
                y           REAL NOT NULL,
                width       REAL NOT NULL DEFAULT 40,
                height      REAL NOT NULL DEFAULT 24,
                hit_count   INTEGER NOT NULL DEFAULT 1,
                miss_count  INTEGER NOT NULL DEFAULT 0,
                last_hit_ts REAL NOT NULL,
                created_ts  REAL NOT NULL,
                confidence  REAL NOT NULL DEFAULT 1.0,
                prev_hint   TEXT NOT NULL DEFAULT ''
            )
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_app_hint
            ON memories (app_name, element_hint)
        """)
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_rtree USING rtree (
                id,
                min_x, max_x,
                min_y, max_y
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sequences (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL,
                from_hint TEXT NOT NULL,
                to_hint  TEXT NOT NULL,
                count    INTEGER NOT NULL DEFAULT 1,
                last_ts  REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_seq_app_from_to
            ON sequences (app_name, from_hint, to_hint)
        """)
        # Cross-app sequences: tracks transitions that cross application
        # boundaries (e.g. clicking "Windows Search" in code.exe leads to
        # "Notepad app" in searchhost.exe). Used by cross-app BFS.
        c.execute("""
            CREATE TABLE IF NOT EXISTS cross_sequences (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                from_app  TEXT NOT NULL,
                from_hint TEXT NOT NULL,
                to_app    TEXT NOT NULL,
                to_hint   TEXT NOT NULL,
                count     INTEGER NOT NULL DEFAULT 1,
                last_ts   REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cross_seq
            ON cross_sequences (from_app, from_hint, to_app, to_hint)
        """)
        c.commit()

    def _load_hot_cache(self) -> None:
        """Load all entries into the in-memory dict."""
        rows = self._conn.execute("SELECT * FROM memories").fetchall()
        for row in rows:
            entry = self._row_to_entry(row)
            key = self._key(entry.app_name, entry.element_hint)
            self._hot[key] = entry
        logger.info("Loaded %d entries into hot cache", len(self._hot))

    @staticmethod
    def _key(app_name: str, element_hint: str) -> str:
        return f"{app_name.lower()}|{element_hint.lower()}"

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> CacheEntry:
        return CacheEntry(
            id=row["id"],
            app_name=row["app_name"],
            element_hint=row["element_hint"],
            x=row["x"],
            y=row["y"],
            width=row["width"],
            height=row["height"],
            hit_count=row["hit_count"],
            miss_count=row["miss_count"],
            last_hit_ts=row["last_hit_ts"],
            created_ts=row["created_ts"],
            confidence=row["confidence"],
            prev_hint=row["prev_hint"],
        )

    def _apply_decay(self, entry: CacheEntry) -> float:
        """Compute time-decayed confidence. Does NOT mutate the entry."""
        elapsed = time.time() - entry.last_hit_ts
        if elapsed <= 0:
            return entry.confidence
        decay = 0.5 ** (elapsed / DECAY_HALF_LIFE)
        return entry.confidence * decay

    def lookup(
        self,
        app_name: str,
        element_hint: str,
        target_x: Optional[int] = None,
        target_y: Optional[int] = None,
    ) -> Optional[CacheEntry]:
        """Look up a remembered target position.

        Tier 1: Exact app+hint match in hot cache (skipped when hint is empty).
        Tier 2: R-Tree spatial proximity (same app, any hint near target coords).
        Returns None on miss.
        """
        # Tier 1: exact match (skip when hint is empty)
        if element_hint:
            key = self._key(app_name, element_hint)
            entry = self._hot.get(key)
            if entry is not None:
                conf = self._apply_decay(entry)
                if conf >= DECAY_MIN_CONFIDENCE:
                    return entry
                return None  # too stale

        # Tier 2: spatial proximity
        if target_x is not None and target_y is not None:
            rows = self._conn.execute(
                """
                SELECT m.* FROM memories m
                JOIN memories_rtree r ON m.id = r.id
                WHERE r.min_x <= ? AND r.max_x >= ?
                  AND r.min_y <= ? AND r.max_y >= ?
                  AND m.app_name = ?
                ORDER BY m.hit_count DESC
                LIMIT 1
                """,
                (
                    target_x + SPATIAL_RADIUS, target_x - SPATIAL_RADIUS,
                    target_y + SPATIAL_RADIUS, target_y - SPATIAL_RADIUS,
                    app_name.lower(),
                ),
            ).fetchall()
            if rows:
                entry = self._row_to_entry(rows[0])
                conf = self._apply_decay(entry)
                if conf >= DECAY_MIN_CONFIDENCE:
                    return entry

        return None

    def record_hit(
        self,
        app_name: str,
        element_hint: str,
        x: int,
        y: int,
        width: int = 40,
        height: int = 24,
        prev_hint: str = "",
        prev_app: str = "",
    ) -> CacheEntry:
        """Record a successful interaction at (x, y).

        If an entry exists, applies EMA position smoothing and increments hit_count.
        Otherwise creates a new entry. Updates the R-Tree and hot cache.

        When prev_app differs from app_name, records a cross-app sequence
        so BFS path finding can traverse application boundaries.
        """
        now = time.time()
        key = self._key(app_name, element_hint)
        existing = self._hot.get(key)

        # Determine if this is a cross-app transition
        is_cross_app = (
            prev_hint
            and prev_app
            and prev_app.lower() != app_name.lower()
        )

        if existing is not None:
            # EMA position smoothing
            new_x = existing.x + EMA_ALPHA * (x - existing.x)
            new_y = existing.y + EMA_ALPHA * (y - existing.y)
            new_w = existing.width + EMA_ALPHA * (width - existing.width)
            new_h = existing.height + EMA_ALPHA * (height - existing.height)
            new_count = existing.hit_count + 1

            self._conn.execute(
                """
                UPDATE memories SET
                    x = ?, y = ?, width = ?, height = ?,
                    hit_count = ?, last_hit_ts = ?,
                    confidence = 1.0, prev_hint = ?
                WHERE id = ?
                """,
                (new_x, new_y, new_w, new_h, new_count, now,
                 prev_hint or existing.prev_hint, existing.id),
            )
            # Update R-Tree
            self._conn.execute(
                "UPDATE memories_rtree SET min_x=?, max_x=?, min_y=?, max_y=? WHERE id=?",
                (new_x, new_x + new_w, new_y, new_y + new_h, existing.id),
            )
            # Record sequence on every hit, not just the first
            if prev_hint:
                if is_cross_app:
                    self._record_cross_sequence(
                        prev_app, prev_hint, app_name, element_hint, now,
                    )
                else:
                    self._record_sequence(app_name, prev_hint, element_hint, now)
            self._conn.commit()

            existing.x = new_x
            existing.y = new_y
            existing.width = new_w
            existing.height = new_h
            existing.hit_count = new_count
            existing.last_hit_ts = now
            existing.confidence = 1.0
            if prev_hint:
                existing.prev_hint = prev_hint
            return existing
        else:
            # Insert new entry
            self._maybe_evict()
            cursor = self._conn.execute(
                """
                INSERT INTO memories
                    (app_name, element_hint, x, y, width, height,
                     hit_count, miss_count, last_hit_ts, created_ts,
                     confidence, prev_hint)
                VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?, 1.0, ?)
                """,
                (app_name.lower(), element_hint.lower(),
                 float(x), float(y), float(width), float(height),
                 now, now, prev_hint),
            )
            row_id = cursor.lastrowid
            self._conn.execute(
                "INSERT INTO memories_rtree (id, min_x, max_x, min_y, max_y) VALUES (?, ?, ?, ?, ?)",
                (row_id, float(x), float(x + width), float(y), float(y + height)),
            )
            self._conn.commit()

            entry = CacheEntry(
                id=row_id, app_name=app_name.lower(),
                element_hint=element_hint.lower(),
                x=float(x), y=float(y),
                width=float(width), height=float(height),
                hit_count=1, miss_count=0,
                last_hit_ts=now, created_ts=now,
                confidence=1.0, prev_hint=prev_hint,
            )
            self._hot[key] = entry

            # Record sequence
            if prev_hint:
                if is_cross_app:
                    self._record_cross_sequence(
                        prev_app, prev_hint, app_name, element_hint, now,
                    )
                else:
                    self._record_sequence(app_name, prev_hint, element_hint, now)

            return entry

    def record_miss(self, app_name: str, element_hint: str) -> None:
        """Record a failed interaction (element was not where expected).

        Reduces confidence by a fixed decay factor.
        """
        key = self._key(app_name, element_hint)
        entry = self._hot.get(key)
        if entry is None:
            return

        new_conf = max(0.0, entry.confidence - 0.3)
        new_miss = entry.miss_count + 1
        self._conn.execute(
            "UPDATE memories SET confidence = ?, miss_count = ? WHERE id = ?",
            (new_conf, new_miss, entry.id),
        )
        self._conn.commit()
        entry.confidence = new_conf
        entry.miss_count = new_miss

    def lookup_for_nav(
        self, app_name: str, element_hint: str
    ) -> Optional[CacheEntry]:
        """Strict lookup for autonomous navigation (no LLM verification).

        Only returns entries that are well-established:
        - Hot cache only (exact app+hint match, no spatial guessing)
        - hit_count >= MIN_NAV_HIT_COUNT
        - Decayed confidence >= MIN_NAV_CONFIDENCE

        If exact app+hint misses, falls back to hint-only search across
        all apps. This handles the common WSL2 case where entries get
        stored under 'wsl2' instead of the real app name (or vice versa)
        due to foreground window detection timing.
        """
        if not element_hint:
            return None

        # Try exact app+hint match first
        entry = self._nav_check(app_name, element_hint)
        if entry is not None:
            return entry

        # Fallback: search by hint across all apps (handles wsl2 mismatch)
        return self._lookup_for_nav_any_app(element_hint)

    def _nav_check(
        self, app_name: str, element_hint: str
    ) -> Optional[CacheEntry]:
        """Check a single app+hint pair against nav thresholds."""
        key = self._key(app_name, element_hint)
        entry = self._hot.get(key)
        if entry is None:
            return None
        if entry.hit_count < MIN_NAV_HIT_COUNT:
            return None
        conf = self._apply_decay(entry)
        if conf < MIN_NAV_CONFIDENCE:
            return None
        return entry

    def _lookup_for_nav_any_app(
        self, element_hint: str
    ) -> Optional[CacheEntry]:
        """Search for a nav-eligible entry by hint alone, across all apps.

        Returns the entry with the highest hit_count that meets nav
        thresholds. Used as fallback when the detected app name doesn't
        match the stored app name (e.g. 'wsl2' vs 'notepad.exe').
        """
        hint_lower = element_hint.lower()
        best: Optional[CacheEntry] = None
        for key, entry in self._hot.items():
            if entry.element_hint.lower() != hint_lower:
                continue
            if entry.hit_count < MIN_NAV_HIT_COUNT:
                continue
            conf = self._apply_decay(entry)
            if conf < MIN_NAV_CONFIDENCE:
                continue
            if best is None or entry.hit_count > best.hit_count:
                best = entry
        return best

    def find_path(
        self,
        app_name: str,
        from_hint: str,
        to_hint: str,
        max_depth: int = MAX_NAV_CHAIN_DEPTH,
    ) -> Optional[list[tuple[str, str]]]:
        """BFS on sequences + cross_sequences to find a navigation path.

        Returns ordered list of (app_name, hint) tuples from source to target
        (inclusive), or None if no path exists within max_depth. Only traverses
        edges with count >= MIN_NAV_SEQ_COUNT.

        For backward compatibility with single-app callers: when the entire
        path stays within one app, the returned tuples all share that app.

        Cross-app example (VS Code -> Search -> Notepad):
            [("code.exe", "windows search"),
             ("searchhost.exe", "notepad app"),
             ("notepad.exe", "text area")]
        """
        app = app_name.lower()
        from_h = from_hint.lower()
        to_h = to_hint.lower()

        if from_h == to_h:
            return [(app, from_hint)]

        # BFS node = (app, hint). Build adjacency from both tables.
        # Type alias: Node = tuple[str, str]
        from collections import deque

        adj: dict[tuple[str, str], list[tuple[str, str]]] = {}

        # Same-app edges from sequences table
        rows = self._conn.execute(
            "SELECT app_name, from_hint, to_hint FROM sequences "
            "WHERE count >= ?",
            (MIN_NAV_SEQ_COUNT,),
        ).fetchall()
        for r in rows:
            src = (r["app_name"], r["from_hint"])
            dst = (r["app_name"], r["to_hint"])
            adj.setdefault(src, []).append(dst)

        # Cross-app edges from cross_sequences table
        try:
            xrows = self._conn.execute(
                "SELECT from_app, from_hint, to_app, to_hint "
                "FROM cross_sequences WHERE count >= ?",
                (MIN_NAV_SEQ_COUNT,),
            ).fetchall()
            for r in xrows:
                src = (r["from_app"], r["from_hint"])
                dst = (r["to_app"], r["to_hint"])
                adj.setdefault(src, []).append(dst)
        except Exception:
            # cross_sequences table may not exist in old DBs
            pass

        start: tuple[str, str] = (app, from_h)

        # BFS -- target matches on hint alone (app may differ)
        queue: deque[list[tuple[str, str]]] = deque([[start]])
        visited: set[tuple[str, str]] = {start}

        while queue:
            path = queue.popleft()
            if len(path) > max_depth + 1:
                return None
            current = path[-1]
            for neighbor in adj.get(current, []):
                if neighbor[1] == to_h:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        return None

    def predict_next(
        self, app_name: str, current_hint: str
    ) -> Optional[CacheEntry]:
        """Predict the most likely next target after current_hint.

        Checks same-app sequences first, then cross-app sequences.
        Based on recorded action sequences (e.g., File menu -> Save).
        """
        # Same-app prediction
        row = self._conn.execute(
            """
            SELECT to_hint FROM sequences
            WHERE app_name = ? AND from_hint = ?
            ORDER BY count DESC LIMIT 1
            """,
            (app_name.lower(), current_hint.lower()),
        ).fetchone()
        if row is not None:
            return self.lookup(app_name, row["to_hint"])

        # Cross-app prediction
        try:
            xrow = self._conn.execute(
                """
                SELECT to_app, to_hint FROM cross_sequences
                WHERE from_app = ? AND from_hint = ?
                ORDER BY count DESC LIMIT 1
                """,
                (app_name.lower(), current_hint.lower()),
            ).fetchone()
            if xrow is not None:
                return self.lookup(xrow["to_app"], xrow["to_hint"])
        except Exception:
            pass

        return None

    def _record_sequence(
        self, app_name: str, from_hint: str, to_hint: str, ts: float
    ) -> None:
        """Upsert a from->to action sequence (same app)."""
        self._conn.execute(
            """
            INSERT INTO sequences (app_name, from_hint, to_hint, count, last_ts)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(app_name, from_hint, to_hint)
            DO UPDATE SET count = count + 1, last_ts = ?
            """,
            (app_name.lower(), from_hint.lower(), to_hint.lower(), ts, ts),
        )
        self._conn.commit()

    def _record_cross_sequence(
        self,
        from_app: str,
        from_hint: str,
        to_app: str,
        to_hint: str,
        ts: float,
    ) -> None:
        """Upsert a cross-app action sequence (different apps)."""
        self._conn.execute(
            """
            INSERT INTO cross_sequences
                (from_app, from_hint, to_app, to_hint, count, last_ts)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(from_app, from_hint, to_app, to_hint)
            DO UPDATE SET count = count + 1, last_ts = ?
            """,
            (from_app.lower(), from_hint.lower(),
             to_app.lower(), to_hint.lower(), ts, ts),
        )
        self._conn.commit()

    def _maybe_evict(self) -> None:
        """Evict oldest entries if at capacity."""
        count = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        if count < MAX_ENTRIES:
            return
        # Delete the oldest 10% by last_hit_ts (LRU)
        to_delete = max(1, MAX_ENTRIES // 10)
        rows = self._conn.execute(
            "SELECT id, app_name, element_hint FROM memories ORDER BY last_hit_ts ASC LIMIT ?",
            (to_delete,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
        self._conn.execute(f"DELETE FROM memories_rtree WHERE id IN ({placeholders})", ids)
        self._conn.commit()
        # Remove from hot cache
        for r in rows:
            key = self._key(r["app_name"], r["element_hint"])
            self._hot.pop(key, None)
        logger.info("Evicted %d stale entries", len(ids))

    def stats(self) -> dict:
        """Return diagnostic info about the cache."""
        count = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        seq_count = self._conn.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]
        try:
            cross_count = self._conn.execute(
                "SELECT COUNT(*) FROM cross_sequences"
            ).fetchone()[0]
        except Exception:
            cross_count = 0
        top = self._conn.execute(
            "SELECT app_name, element_hint, hit_count FROM memories ORDER BY hit_count DESC LIMIT 5"
        ).fetchall()
        return {
            "total_entries": count,
            "hot_entries": len(self._hot),
            "sequences": seq_count,
            "cross_sequences": cross_count,
            "top_targets": [
                {"app": r["app_name"], "hint": r["element_hint"], "hits": r["hit_count"]}
                for r in top
            ],
        }

    def merge_platform_entries(self, platform_name: str) -> int:
        """Merge stray platform-fallback entries into their real app entries.

        When foreground window detection fails, entries get stored under
        the platform name (e.g. 'wsl2') instead of the real app. This
        method finds such duplicates and merges them:

        - If a real-app entry exists for the same hint, merge the hit
          counts and EMA-smooth the positions, then delete the platform entry.
        - If no real-app entry exists, leave the platform entry alone
          (it's the only record we have).

        Returns the number of entries merged (and deleted).
        """
        platform_lower = platform_name.lower()
        merged = 0

        # Find all platform-fallback entries
        platform_entries = [
            e for e in self._hot.values()
            if e.app_name.lower() == platform_lower
        ]

        for pentry in platform_entries:
            # Search for a real-app entry with the same hint
            hint_lower = pentry.element_hint.lower()
            real_entry: Optional[CacheEntry] = None
            for key, entry in self._hot.items():
                if (entry.element_hint.lower() == hint_lower
                        and entry.app_name.lower() != platform_lower):
                    # Prefer the entry with higher hit_count
                    if real_entry is None or entry.hit_count > real_entry.hit_count:
                        real_entry = entry

            if real_entry is None:
                continue  # no real-app counterpart, keep the platform entry

            # Merge into the real-app entry
            combined_hits = real_entry.hit_count + pentry.hit_count
            # Weight-averaged position (by hit_count)
            total = real_entry.hit_count + pentry.hit_count
            new_x = (real_entry.x * real_entry.hit_count + pentry.x * pentry.hit_count) / total
            new_y = (real_entry.y * real_entry.hit_count + pentry.y * pentry.hit_count) / total
            new_ts = max(real_entry.last_hit_ts, pentry.last_hit_ts)

            self._conn.execute(
                """UPDATE memories SET
                    x = ?, y = ?, hit_count = ?, last_hit_ts = ?, confidence = 1.0
                WHERE id = ?""",
                (new_x, new_y, combined_hits, new_ts, real_entry.id),
            )
            self._conn.execute(
                "UPDATE memories_rtree SET min_x=?, max_x=?, min_y=?, max_y=? WHERE id=?",
                (new_x, new_x + real_entry.width, new_y, new_y + real_entry.height,
                 real_entry.id),
            )

            # Delete the platform entry
            self._conn.execute("DELETE FROM memories WHERE id = ?", (pentry.id,))
            self._conn.execute("DELETE FROM memories_rtree WHERE id = ?", (pentry.id,))

            # Update hot cache
            real_entry.x = new_x
            real_entry.y = new_y
            real_entry.hit_count = combined_hits
            real_entry.last_hit_ts = new_ts
            real_entry.confidence = 1.0

            pkey = self._key(pentry.app_name, pentry.element_hint)
            self._hot.pop(pkey, None)

            merged += 1

        if merged > 0:
            self._conn.commit()
            logger.info(
                "Merged %d '%s' entries into real-app entries", merged, platform_name,
            )
        return merged

    def flush(self) -> None:
        """Force WAL checkpoint."""
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass

    def close(self) -> None:
        """Flush and close the database."""
        self.flush()
        self._conn.close()
        logger.info("Cache closed (%s)", self._db_path)


# ── Adaptation functions ──
# These are called by the daemon to adjust movement based on hit_count.


def adapted_fitts_duration(base_duration: float, hit_count: int) -> float:
    """Apply Power Law of Practice to reduce movement duration.

    T(n) = base * n^(-alpha), floored at POWER_LAW_FLOOR * base.

    First interaction (hit_count <= 1) returns base unchanged.
    """
    if hit_count <= 1:
        return base_duration
    scaled = base_duration * (hit_count ** -POWER_LAW_ALPHA)
    floor = base_duration * POWER_LAW_FLOOR
    return max(scaled, floor)


def muscle_memory_windmouse_params(hit_count: int) -> dict:
    """Return adapted WindMouse kwargs based on practice count.

    Returns empty dict for hit_count <= 1 (use defaults).
    As hit_count grows, gravity increases (straighter) and wind
    decreases (less wobble), modeling increasing motor confidence.
    """
    if hit_count <= 1:
        return {}

    # Logarithmic scaling: fast improvement early, plateaus later
    factor = min(1.0, math.log2(hit_count) / 6.0)  # saturates ~64 hits

    return {
        "gravity": 9.0 + factor * 11.0,    # 9 -> 20 (straighter)
        "wind": 3.0 * (1.0 - factor * 0.7),  # 3 -> 0.9 (less wobbly)
        "max_vel": 20.0 + factor * 15.0,    # 20 -> 35 (faster steps)
    }
