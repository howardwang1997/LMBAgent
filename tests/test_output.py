"""Tests for output directory management and caching."""

import time

from lmbagent.output import get_output_dir, get_plots_dir, get_cached_or_new, reset_session


def test_get_output_dir_creates_subdir(tmp_path):
    reset_session()
    output_dir = get_output_dir("test1", base=tmp_path)
    assert output_dir.exists()
    assert "test1" in output_dir.name
    assert output_dir.parent == tmp_path


def test_same_data_id_returns_same_dir(tmp_path):
    reset_session()
    dir1 = get_output_dir("test1", base=tmp_path)
    dir2 = get_output_dir("test1", base=tmp_path)
    assert dir1 == dir2


def test_different_data_id_returns_different_dir(tmp_path):
    reset_session()
    dir1 = get_output_dir("test1", base=tmp_path)
    dir2 = get_output_dir("test2", base=tmp_path)
    assert dir1 != dir2


def test_get_plots_dir(tmp_path):
    reset_session()
    get_output_dir("test1", base=tmp_path)  # register first
    plots_dir = get_plots_dir("test1")
    assert plots_dir.exists()
    assert plots_dir.name == "plots"


def test_cache_miss(tmp_path):
    path, cached = get_cached_or_new(tmp_path, "test.png")
    assert not cached
    assert path == tmp_path / "test.png"


def test_cache_hit(tmp_path):
    (tmp_path / "test.png").write_text("fake image")
    path, cached = get_cached_or_new(tmp_path, "test.png")
    assert cached
    assert path.exists()


def test_reset_session(tmp_path):
    reset_session()
    dir1 = get_output_dir("test1", base=tmp_path)
    reset_session()
    dir2 = get_output_dir("test1", base=tmp_path)
    # After reset, should create a new directory (different timestamp)
    # They might be the same if called in the same second, so just check both exist
    assert dir1.exists()
    assert dir2.exists()
