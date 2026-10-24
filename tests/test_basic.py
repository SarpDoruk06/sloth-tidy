import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sloth_tidy as st  # noqa: E402

OLD = time.time() - 3600  # files must look older than a minute to be picked up


def make(path: Path, text: str = "hello", age: float = OLD) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (age, age))
    return path


def fake_model(monkeypatch, reply: dict):
    monkeypatch.setattr(
        st.ollama, "chat", lambda **kw: {"message": {"content": json.dumps(reply)}}
    )


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


def test_rule_category():
    assert st.rule_category(Path("a.PNG")) == "Photos"
    assert st.rule_category(Path("setup.exe")) == "Installers"
    assert st.rule_category(Path("notes.pdf")) is None


def test_extension_rules_skip_the_model(tmp_path):
    photo = tmp_path / "holiday.JPG"
    photo.write_bytes(b"x")
    assert st.classify(photo, st.DEFAULT_CATEGORIES, "unused-model") == ("Photos", None)


def test_parse_event_accepts_future_dates():
    today = date(2026, 10, 24)
    event = st.parse_event({"title": "Flight", "date": "2026-11-04", "time": "16:35"}, today)
    assert event == {"title": "Flight", "date": "2026-11-04", "time": "16:35"}


def test_parse_event_rejects_bad_input():
    today = date(2026, 10, 24)
    assert st.parse_event(None, today) is None
    assert st.parse_event({"title": "Old", "date": "2026-01-01", "time": ""}, today) is None
    assert st.parse_event({"title": "Bad", "date": "next friday", "time": ""}, today) is None
    assert st.parse_event({"title": "", "date": "2026-11-04", "time": ""}, today) is None
    # a broken time is dropped but the event is kept
    event = st.parse_event({"title": "Exam", "date": "2026-11-04", "time": "25:99"}, today)
    assert event["time"] == ""


def test_make_ics_has_event_and_alarm():
    timed = st.make_ics({"title": "Flight, Rome", "date": "2026-11-04", "time": "16:35"}, "ticket.pdf")
    assert "BEGIN:VEVENT" in timed and "BEGIN:VALARM" in timed
    assert "DTSTART:20261104T163500" in timed
    assert "SUMMARY:Flight\\, Rome" in timed
    all_day = st.make_ics({"title": "Deadline", "date": "2026-11-04", "time": ""}, "x.pdf")
    assert "DTSTART;VALUE=DATE:20261104" in all_day
    assert "DTEND;VALUE=DATE:20261105" in all_day


def test_find_duplicate_groups(tmp_path):
    a = make(tmp_path / "a.txt", "same content", age=OLD - 100)
    b = make(tmp_path / "b.txt", "same content")
    c = make(tmp_path / "c.txt", "different")
    empty1 = make(tmp_path / "e1.txt", "")
    empty2 = make(tmp_path / "e2.txt", "")
    groups = st.find_duplicate_groups([a, b, c, empty1, empty2])
    assert groups == [[a, b]]  # oldest first, empty files ignored


def test_choose_duplicates_keeps_oldest_when_not_interactive(tmp_path):
    a = make(tmp_path / "a.txt", "same", age=OLD - 100)
    b = make(tmp_path / "b.txt", "same")
    assert st.choose_duplicates([[a, b]], interactive=False) == {b: a}


def test_choose_duplicates_asks_user(tmp_path, monkeypatch):
    a = make(tmp_path / "a.txt", "same", age=OLD - 100)
    b = make(tmp_path / "b.txt", "same")
    monkeypatch.setattr(st, "ask", lambda prompt: "2")
    assert st.choose_duplicates([[a, b]], interactive=True) == {a: b}
    monkeypatch.setattr(st, "ask", lambda prompt: "s")
    assert st.choose_duplicates([[a, b]], interactive=True) == {}


def test_tidy_moves_and_creates_guide(tmp_path, monkeypatch):
    fake_model(monkeypatch, {"folder": "Receipts", "name": "Pizza Receipt!", "event": None})
    make(tmp_path / "scan.txt", "pizza total 12 EUR")
    make(tmp_path / "photo.png", "x")
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=True)
    assert stats["files"] == 2 and stats["by_rule"] == 1 and stats["by_model"] == 1
    assert (tmp_path / "Receipts" / "pizza-receipt.txt").exists()
    assert (tmp_path / "Photos" / "photo.png").exists()
    assert (tmp_path / "_Sloth" / "GUIDE.md").exists()


def test_dry_run_moves_nothing_and_writes_no_guide(tmp_path, monkeypatch):
    fake_model(monkeypatch, {"folder": "Uni", "name": "notes", "event": None})
    make(tmp_path / "scan.txt", "lecture")
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=False)
    assert stats["files"] == 1
    assert (tmp_path / "scan.txt").exists()
    assert not (tmp_path / "_Sloth").exists()


def test_duplicates_go_to_duplicates_folder_and_undo_works(tmp_path, monkeypatch):
    fake_model(monkeypatch, {"folder": "Other", "name": None, "event": None})
    make(tmp_path / "a.txt", "same", age=OLD - 100)
    make(tmp_path / "b.txt", "same")
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=True)
    assert stats["duplicates"] == 1
    assert (tmp_path / "Duplicates" / "b.txt").exists()
    assert (tmp_path / "Other" / "a.txt").exists()
    st.undo(tmp_path)
    assert (tmp_path / "a.txt").exists() and (tmp_path / "b.txt").exists()
    assert not (tmp_path / "Duplicates").exists()  # empty folders are cleaned up


def test_reminder_is_created_only_after_confirmation(tmp_path, monkeypatch):
    event = {"title": "Flight Rome-Sofia", "date": "2099-01-01", "time": "16:35"}
    fake_model(monkeypatch, {"folder": "Travel", "name": "ticket", "event": event})
    opened = []
    monkeypatch.setattr(st, "open_file", lambda p: opened.append(p))
    make(tmp_path / "ticket.txt", "flight on 2099-01-01")

    monkeypatch.setattr(st, "ask", lambda prompt: "n")
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=True, interactive=True)
    assert stats["reminders"] == 0
    assert not (tmp_path / "_Sloth" / "Reminders").exists()

    # run again with a fresh file and say yes
    make(tmp_path / "ticket2.txt", "flight on 2099-01-01")
    monkeypatch.setattr(st, "ask", lambda prompt: "y")
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=True, interactive=True)
    assert stats["reminders"] == 1
    assert len(list((tmp_path / "_Sloth" / "Reminders").glob("*.ics"))) == 1
    assert len(opened) == 1


def test_watch_mode_writes_reminder_list(tmp_path, monkeypatch):
    event = {"title": "Exam", "date": "2099-02-02", "time": ""}
    fake_model(monkeypatch, {"folder": "Uni", "name": "exam", "event": event})
    make(tmp_path / "exam.txt", "exam on 2099-02-02")
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=True, interactive=False)
    assert stats["reminders"] == 1
    assert "Exam" in (tmp_path / "_Sloth" / "reminders.md").read_text()


def test_similar_events_are_flagged_not_merged(tmp_path):
    ticket = tmp_path / "flixbus-munchen-innsbruck.pdf"
    receipt = tmp_path / "flixbus-ticket-sarp.pdf"
    other = tmp_path / "flixbus-verona-bologna.pdf"
    items = [
        {"file": ticket, "event": {"title": "Flixbus Trip", "date": "2026-11-07", "time": "10:00"}},
        {"file": receipt, "event": {"title": "Flixbus Munich to Innsbruck", "date": "2026-11-07", "time": "10:00"}},
        {"file": other, "event": {"title": "Flixbus Trip", "date": "2026-11-10", "time": "21:15"}},
    ]
    linked = st.link_similar_events(items)
    assert len(linked) == 3  # nothing is hidden
    assert linked[0]["similar"] == [receipt.name]
    assert linked[1]["similar"] == [ticket.name]
    assert linked[2]["similar"] == []


def test_different_all_day_events_are_not_similar():
    a = {"file": Path("a.pdf"), "event": {"title": "Essay deadline", "date": "2026-12-01", "time": ""}}
    b = {"file": Path("b.pdf"), "event": {"title": "Exam registration", "date": "2026-12-01", "time": ""}}
    linked = st.link_similar_events([a, b])
    assert linked[0]["similar"] == [] and linked[1]["similar"] == []


def test_code_files_keep_their_name(tmp_path, monkeypatch):
    fake_model(monkeypatch, {"folder": "Other", "name": "Prove Py", "event": None})
    make(tmp_path / "Prove.py", "print('hi')")
    st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=True)
    assert (tmp_path / "Other" / "Prove.py").exists()  # keeps its own name, not prove-py.py


def test_files_without_text_are_flagged(tmp_path, monkeypatch, capsys):
    fake_model(monkeypatch, {"folder": "Other", "name": None, "event": None})
    make(tmp_path / "scan.txt", "   \n  ")  # nothing readable
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=False)
    assert stats["no_text"] == 1
    assert "no readable text" in capsys.readouterr().out


def test_both_similar_reminders_are_asked_with_a_warning(tmp_path, monkeypatch, capsys):
    event = {"title": "Flixbus Munich to Innsbruck", "date": "2099-01-01", "time": "10:00"}
    fake_model(monkeypatch, {"folder": "Travel", "name": "ticket", "event": event})
    make(tmp_path / "boarding-pass.txt", "bus 2099-01-01 10:00")
    make(tmp_path / "payment-receipt.txt", "paid for bus 2099-01-01 10:00 and more text")
    prompts, answers = [], iter(["y", "n"])
    monkeypatch.setattr(st, "open_file", lambda p: None)
    monkeypatch.setattr(st, "ask", lambda prompt: (prompts.append(prompt), next(answers))[1])
    stats = st.tidy(tmp_path, "m", st.DEFAULT_CATEGORIES, apply=True, interactive=True)
    assert len(prompts) == 2  # you are asked about both
    assert "already added" in prompts[1]  # and warned the second time
    assert stats["reminders"] == 1
    assert "maybe the same event" in capsys.readouterr().out


def test_undo_restores_files(tmp_path):
    src = tmp_path / "a.txt"
    dst_dir = tmp_path / "Other"
    dst_dir.mkdir()
    dst = dst_dir / "a.txt"
    dst.write_text("hello")
    st.write_log(tmp_path, [{"from": str(src), "to": str(dst)}])
    st.undo(tmp_path)
    assert src.exists() and not dst.exists()
