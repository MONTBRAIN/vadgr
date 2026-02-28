"""Tests for the muscle memory spatial cache."""

import time
import tempfile
import os

import pytest

from computer_use.core.spatial_cache import (
    MuscleMemoryCache,
    CacheEntry,
    adapted_fitts_duration,
    muscle_memory_windmouse_params,
    POWER_LAW_FLOOR,
    DECAY_HALF_LIFE,
    DECAY_MIN_CONFIDENCE,
    SPATIAL_RADIUS,
    EMA_ALPHA,
    MAX_ENTRIES,
    MIN_NAV_HIT_COUNT,
    MIN_NAV_CONFIDENCE,
    MIN_NAV_SEQ_COUNT,
    MAX_NAV_CHAIN_DEPTH,
)


@pytest.fixture
def cache():
    c = MuscleMemoryCache(":memory:")
    yield c
    c.close()


class TestCacheCRUD:
    def test_record_hit_creates_entry(self, cache):
        entry = cache.record_hit("notepad.exe", "File menu", 50, 12, 80, 24)
        assert entry.hit_count == 1
        assert entry.app_name == "notepad.exe"
        assert entry.element_hint == "file menu"  # lowercased

    def test_lookup_exact_match(self, cache):
        cache.record_hit("app.exe", "Save", 100, 200, 60, 20)
        found = cache.lookup("app.exe", "Save")
        assert found is not None
        assert found.hit_count == 1

    def test_hit_count_increments(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        cache.record_hit("app.exe", "btn", 10, 20)
        cache.record_hit("app.exe", "btn", 10, 20)
        found = cache.lookup("app.exe", "btn")
        assert found.hit_count == 3

    def test_ema_position_smoothing(self, cache):
        cache.record_hit("app.exe", "btn", 100, 200, 40, 24)
        cache.record_hit("app.exe", "btn", 110, 210, 40, 24)
        entry = cache.lookup("app.exe", "btn")
        # EMA: 100 + 0.3*(110-100) = 103
        assert abs(entry.x - 103.0) < 0.1
        assert abs(entry.y - 203.0) < 0.1

    def test_case_insensitive_lookup(self, cache):
        cache.record_hit("App.EXE", "File Menu", 50, 12)
        found = cache.lookup("app.exe", "file menu")
        assert found is not None

    def test_miss_returns_none(self, cache):
        assert cache.lookup("nope.exe", "nothing") is None

    def test_record_miss_reduces_confidence(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        cache.record_miss("app.exe", "btn")
        entry = cache.lookup("app.exe", "btn")
        assert entry.confidence == pytest.approx(0.7, abs=0.01)

    def test_multiple_misses_reduce_to_zero(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        for _ in range(5):
            cache.record_miss("app.exe", "btn")
        entry = cache._hot.get(cache._key("app.exe", "btn"))
        assert entry.confidence == pytest.approx(0.0, abs=0.01)

    def test_record_miss_unknown_is_noop(self, cache):
        cache.record_miss("nope.exe", "nothing")  # should not raise


class TestSpatialProximity:
    def test_finds_nearby_target(self, cache):
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        # Look up with coordinates near (100, 200)
        found = cache.lookup("app.exe", "unknown hint", target_x=110, target_y=205)
        assert found is not None
        assert found.element_hint == "button a"

    def test_rejects_far_target(self, cache):
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        # Look up far away
        found = cache.lookup("app.exe", "unknown", target_x=500, target_y=500)
        assert found is None

    def test_different_app_not_matched(self, cache):
        cache.record_hit("app1.exe", "btn", 100, 200, 40, 24)
        found = cache.lookup("app2.exe", "unknown", target_x=100, target_y=200)
        assert found is None


class TestDecayScoring:
    def test_fresh_entry_full_confidence(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        entry = cache.lookup("app.exe", "btn")
        assert entry is not None

    def test_half_life_decay(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        entry = cache._hot[cache._key("app.exe", "btn")]
        # Simulate entry from DECAY_HALF_LIFE seconds ago
        entry.last_hit_ts = time.time() - DECAY_HALF_LIFE
        decayed = cache._apply_decay(entry)
        assert abs(decayed - 0.5) < 0.05  # ~50% after one half-life

    def test_very_old_entry_returns_none(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        entry = cache._hot[cache._key("app.exe", "btn")]
        # 10 half-lives ago -> confidence ~0.001
        entry.last_hit_ts = time.time() - DECAY_HALF_LIFE * 10
        result = cache.lookup("app.exe", "btn")
        assert result is None


class TestPowerLawAdaptation:
    def test_first_hit_returns_base(self):
        assert adapted_fitts_duration(1.0, 0) == 1.0
        assert adapted_fitts_duration(1.0, 1) == 1.0

    def test_monotonically_decreasing(self):
        durations = [adapted_fitts_duration(1.0, n) for n in range(1, 20)]
        for i in range(1, len(durations)):
            assert durations[i] <= durations[i - 1]

    def test_floor_respected(self):
        # Even at very high hit counts, never below floor
        result = adapted_fitts_duration(1.0, 10000)
        assert result >= POWER_LAW_FLOOR * 1.0

    def test_windmouse_empty_for_low_hits(self):
        assert muscle_memory_windmouse_params(0) == {}
        assert muscle_memory_windmouse_params(1) == {}

    def test_windmouse_params_change_with_hits(self):
        params = muscle_memory_windmouse_params(10)
        assert "gravity" in params
        assert "wind" in params
        assert "max_vel" in params
        assert params["gravity"] > 9.0  # higher than default
        assert params["wind"] < 3.0  # lower than default

    def test_windmouse_params_saturate(self):
        p32 = muscle_memory_windmouse_params(32)
        p1000 = muscle_memory_windmouse_params(1000)
        # Should be very close once saturated
        assert abs(p32["gravity"] - p1000["gravity"]) < 2.0


class TestSequenceTracking:
    def test_record_and_predict(self, cache):
        # Simulate: File menu -> Save (3 times), File menu -> Print (1 time)
        for _ in range(3):
            cache.record_hit("app.exe", "Save", 200, 100, prev_hint="File menu")
        cache.record_hit("app.exe", "Print", 200, 150, prev_hint="File menu")

        predicted = cache.predict_next("app.exe", "File menu")
        assert predicted is not None
        assert predicted.element_hint == "save"

    def test_unknown_returns_none(self, cache):
        assert cache.predict_next("app.exe", "nonexistent") is None


class TestEmptyHintAndCoordGuard:
    def test_empty_hint_skips_tier1_goes_to_rtree(self, cache):
        """When element_hint is empty, skip exact match, use R-Tree proximity."""
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        # Lookup with empty hint but nearby coords should find via R-Tree
        found = cache.lookup("app.exe", "", target_x=110, target_y=205)
        assert found is not None
        assert found.element_hint == "button a"

    def test_empty_hint_no_coords_returns_none(self, cache):
        """Empty hint with no coords should return None (no Tier 1, no Tier 2)."""
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        found = cache.lookup("app.exe", "")
        assert found is None

    def test_coords_at_zero_zero_still_work(self, cache):
        """target_x=0, target_y=0 should still trigger R-Tree lookup."""
        cache.record_hit("app.exe", "origin btn", 5, 5, 40, 24)
        found = cache.lookup("app.exe", "unknown", target_x=0, target_y=0)
        assert found is not None
        assert found.element_hint == "origin btn"

    def test_none_coords_skip_rtree(self, cache):
        """When target_x/target_y are None, R-Tree is skipped."""
        cache.record_hit("app.exe", "btn", 100, 200, 40, 24)
        found = cache.lookup("app.exe", "nonexistent")
        assert found is None

    def test_coord_based_entry_records_and_lookups(self, cache):
        """Synthetic coord-based hints like '@100,200' work normally."""
        cache.record_hit("app.exe", "@100,200", 100, 200, 40, 24)
        found = cache.lookup("app.exe", "@100,200")
        assert found is not None
        assert found.hit_count == 1


class TestPersistenceAndEviction:
    def test_stats_reports_counts(self, cache):
        cache.record_hit("app.exe", "a", 10, 20)
        cache.record_hit("app.exe", "b", 30, 40)
        s = cache.stats()
        assert s["total_entries"] == 2
        assert s["hot_entries"] == 2

    def test_close_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.db")
            cache = MuscleMemoryCache(path)
            cache.record_hit("app.exe", "btn", 10, 20)
            cache.record_hit("app.exe", "btn", 10, 20)
            cache.close()

            cache2 = MuscleMemoryCache(path)
            entry = cache2.lookup("app.exe", "btn")
            assert entry is not None
            assert entry.hit_count == 2
            cache2.close()

    def test_eviction_at_capacity(self, cache):
        # Insert MAX_ENTRIES + 10 entries
        for i in range(MAX_ENTRIES + 10):
            cache.record_hit("app.exe", f"btn_{i}", i, i)
        count = cache._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        assert count <= MAX_ENTRIES


class TestNavLookup:
    """Tests for the strict navigation lookup."""

    def test_rejects_low_hits(self, cache):
        """Entries with hit_count < MIN_NAV_HIT_COUNT are rejected."""
        cache.record_hit("app.exe", "btn", 100, 200)
        cache.record_hit("app.exe", "btn", 100, 200)  # hit_count=2
        result = cache.lookup_for_nav("app.exe", "btn")
        assert result is None

    def test_accepts_high_hits(self, cache):
        """Entries with hit_count >= MIN_NAV_HIT_COUNT are accepted."""
        for _ in range(MIN_NAV_HIT_COUNT + 2):
            cache.record_hit("app.exe", "btn", 100, 200)
        result = cache.lookup_for_nav("app.exe", "btn")
        assert result is not None
        assert result.hit_count >= MIN_NAV_HIT_COUNT

    def test_rejects_stale(self, cache):
        """Entries with decayed confidence below threshold are rejected."""
        for _ in range(5):
            cache.record_hit("app.exe", "btn", 100, 200)
        # Simulate old timestamp
        entry = cache._hot[cache._key("app.exe", "btn")]
        entry.last_hit_ts = time.time() - DECAY_HALF_LIFE * 5  # ~3% confidence
        result = cache.lookup_for_nav("app.exe", "btn")
        assert result is None

    def test_rejects_empty_hint(self, cache):
        """Empty hint always returns None."""
        for _ in range(5):
            cache.record_hit("app.exe", "btn", 100, 200)
        assert cache.lookup_for_nav("app.exe", "") is None


class TestPathFinding:
    """Tests for BFS path finding on sequences."""

    def test_direct_path(self, cache):
        """A->B with direct sequence returns [(app, A), (app, B)]."""
        for _ in range(MIN_NAV_SEQ_COUNT):
            cache.record_hit("app.exe", "B", 200, 100, prev_hint="A")
        path = cache.find_path("app.exe", "A", "B")
        assert path is not None
        assert path == [("app.exe", "a"), ("app.exe", "b")]

    def test_multi_hop(self, cache):
        """A->B->C returns [(app, A), (app, B), (app, C)]."""
        for _ in range(MIN_NAV_SEQ_COUNT):
            cache.record_hit("app.exe", "B", 200, 100, prev_hint="A")
            cache.record_hit("app.exe", "C", 300, 100, prev_hint="B")
        path = cache.find_path("app.exe", "A", "C")
        assert path is not None
        assert path == [("app.exe", "a"), ("app.exe", "b"), ("app.exe", "c")]

    def test_no_route(self, cache):
        """No connection returns None."""
        for _ in range(MIN_NAV_SEQ_COUNT):
            cache.record_hit("app.exe", "B", 200, 100, prev_hint="A")
        path = cache.find_path("app.exe", "A", "D")
        assert path is None

    def test_max_depth(self, cache):
        """Path longer than max_depth returns None."""
        # Create chain: step0 -> step1 -> step2 -> ... -> stepN
        chain_len = MAX_NAV_CHAIN_DEPTH + 3
        for i in range(chain_len):
            for _ in range(MIN_NAV_SEQ_COUNT):
                cache.record_hit(
                    "app.exe", f"step{i+1}", (i+1)*100, 100,
                    prev_hint=f"step{i}",
                )
        # Path from step0 to step(MAX+3) exceeds max depth
        path = cache.find_path("app.exe", "step0", f"step{chain_len}")
        assert path is None

    def test_same_source_and_target(self, cache):
        """from == to returns single-element path."""
        path = cache.find_path("app.exe", "A", "A")
        assert path == [("app.exe", "A")]

    def test_low_count_edges_ignored(self, cache):
        """Edges with count < MIN_NAV_SEQ_COUNT are not traversed."""
        # Only 1 occurrence (below threshold)
        cache.record_hit("app.exe", "B", 200, 100, prev_hint="A")
        path = cache.find_path("app.exe", "A", "B")
        assert path is None


class TestCrossAppSequences:
    """Tests for cross-app sequence recording and path finding."""

    def test_cross_app_sequence_recorded(self, cache):
        """Cross-app transitions are stored in cross_sequences table."""
        for _ in range(MIN_NAV_SEQ_COUNT):
            cache.record_hit(
                "search.exe", "notepad app", 200, 100,
                prev_hint="windows search", prev_app="code.exe",
            )
        count = cache._conn.execute(
            "SELECT count FROM cross_sequences "
            "WHERE from_app='code.exe' AND to_app='search.exe'"
        ).fetchone()
        assert count is not None
        assert count[0] >= MIN_NAV_SEQ_COUNT

    def test_same_app_not_in_cross_table(self, cache):
        """Same-app transitions go to sequences, not cross_sequences."""
        for _ in range(MIN_NAV_SEQ_COUNT):
            cache.record_hit(
                "app.exe", "B", 200, 100,
                prev_hint="A", prev_app="app.exe",
            )
        cross = cache._conn.execute(
            "SELECT COUNT(*) FROM cross_sequences"
        ).fetchone()[0]
        assert cross == 0

    def test_cross_app_path_finding(self, cache):
        """BFS finds paths across app boundaries."""
        # code.exe:search_btn -> search.exe:notepad_app -> notepad.exe:text_area
        for _ in range(MIN_NAV_SEQ_COUNT):
            cache.record_hit(
                "search.exe", "notepad app", 200, 100,
                prev_hint="search btn", prev_app="code.exe",
            )
            cache.record_hit(
                "notepad.exe", "text area", 300, 200,
                prev_hint="notepad app", prev_app="search.exe",
            )
        # Also need the source entry to exist
        cache.record_hit("code.exe", "search btn", 50, 12)

        path = cache.find_path("code.exe", "search btn", "text area")
        assert path is not None
        assert len(path) == 3
        assert path[0] == ("code.exe", "search btn")
        assert path[1] == ("search.exe", "notepad app")
        assert path[2] == ("notepad.exe", "text area")

    def test_cross_app_predict_next(self, cache):
        """predict_next returns cross-app targets when no same-app match."""
        cache.record_hit("search.exe", "notepad app", 200, 100)
        for _ in range(3):
            cache.record_hit(
                "search.exe", "notepad app", 200, 100,
                prev_hint="search btn", prev_app="code.exe",
            )
        predicted = cache.predict_next("code.exe", "search btn")
        assert predicted is not None
        assert predicted.element_hint == "notepad app"

    def test_stats_includes_cross_sequences(self, cache):
        """Stats report cross_sequences count."""
        cache.record_hit(
            "app2.exe", "B", 200, 100,
            prev_hint="A", prev_app="app1.exe",
        )
        s = cache.stats()
        assert "cross_sequences" in s
        assert s["cross_sequences"] >= 1
