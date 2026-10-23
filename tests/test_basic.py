import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sloth_tidy as st  # noqa: E402


def test_slugify():
    assert st.slugify("My Flight Ticket (Rome)!") == "my-flight-ticket-rome"
    assert st.slugify("   ") == ""
    assert len(st.slugify("a" * 200)) == 60


def test_unique_path_adds_suffix(tmp_path):
    first = tmp_path / "note.txt"
    first.write_text("hi")
    assert st.unique_path(first).name == "note-1.txt"
    (tmp_path / "note-1.txt").write_text("hi")
    assert st.unique_path(first).name == "note-2.txt"


def test_extension_rules_skip_the_model(tmp_path):
    photo = tmp_path / "holiday.JPG"
    photo.write_bytes(b"x")
    assert st.classify(photo, st.DEFAULT_CATEGORIES, "unused-model") == ("Photos", None)


def test_undo_restores_files(tmp_path):
    src = tmp_path / "a.txt"
    dst_dir = tmp_path / "Other"
    dst_dir.mkdir()
    dst = dst_dir / "a.txt"
    dst.write_text("hello")
    st.write_log(tmp_path, [{"from": str(src), "to": str(dst)}])
    st.undo(tmp_path)
    assert src.exists() and not dst.exists()
