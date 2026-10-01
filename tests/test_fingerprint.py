from __future__ import annotations

from ingest.fingerprint import build_fingerprint, clear_stale_cache, data_fingerprint


def make_tree(root):
    (root / "data/parquet/observations").mkdir(parents=True)
    (root / "data/parquet/observations/a.parquet").write_bytes(b"one")
    (root / "data/status.json").write_text("{}")
    (root / "site/src").mkdir(parents=True)
    (root / "site/src/index.md").write_text("# hi")
    return root


def test_data_change_changes_both_fingerprints(tmp_path):
    root = make_tree(tmp_path)
    d0, b0 = data_fingerprint(root), build_fingerprint(root)
    (root / "data/parquet/observations/a.parquet").write_bytes(b"two")
    assert data_fingerprint(root) != d0 and build_fingerprint(root) != b0


def test_site_change_changes_build_not_data(tmp_path):
    root = make_tree(tmp_path)
    d0, b0 = data_fingerprint(root), build_fingerprint(root)
    (root / "site/src/index.md").write_text("# changed")
    assert data_fingerprint(root) == d0 and build_fingerprint(root) != b0


def test_observable_cache_and_dist_excluded(tmp_path):
    root = make_tree(tmp_path)
    b0 = build_fingerprint(root)
    (root / "site/src/.observablehq/cache").mkdir(parents=True)
    (root / "site/src/.observablehq/cache/x.json").write_text("cached")
    assert build_fingerprint(root) == b0


def test_cache_cleared_only_when_data_changes(tmp_path):
    root = make_tree(tmp_path)
    cache = root / "site/src/.observablehq/cache"
    assert clear_stale_cache(cache, root) is True  # first build: no stamp
    (cache / "data").mkdir()
    (cache / "data/obs.json").write_text("stale")
    (cache / "_npm").mkdir()
    (cache / "_npm/d3.js").write_text("module")
    assert clear_stale_cache(cache, root) is False
    assert (cache / "data/obs.json").exists()
    (root / "data/parquet/observations/a.parquet").write_bytes(b"revised")
    assert clear_stale_cache(cache, root) is True
    assert not (cache / "data/obs.json").exists()
    assert (cache / "_npm/d3.js").exists()  # npm module cache survives


def test_registry_and_loader_dependencies_invalidate_cached_output(tmp_path):
    root = make_tree(tmp_path)
    cache = root / "site/src/.observablehq/cache"
    for name in ("registry/series.yaml", "ingest/registry.py", "site/src/data/_common.py", "uv.lock"):
        dependency = root / name
        dependency.parent.mkdir(parents=True, exist_ok=True)
        dependency.write_text("before")
        clear_stale_cache(cache, root)
        cached = cache / "observations.json"
        cached.write_text("old metadata")
        dependency.write_text("after")
        assert clear_stale_cache(cache, root)
        assert not cached.exists()
        assert not clear_stale_cache(cache, root)
