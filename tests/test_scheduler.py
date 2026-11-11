from datetime import datetime

from app.scheduler import in_window, is_due

D = ["mon", "tue", "wed", "thu", "fri"]


def test_window():
    assert in_window(datetime(2026, 11, 5, 9, 0), "08:30", "16:30", D)       # quinta
    assert not in_window(datetime(2026, 11, 5, 8, 29), "08:30", "16:30", D)
    assert not in_window(datetime(2026, 11, 5, 16, 31), "08:30", "16:30", D)
    assert not in_window(datetime(2026, 11, 7, 10, 0), "08:30", "16:30", D)  # sábado


def test_due():
    assert is_due(1000, None, 60)
    assert not is_due(1000 + 3599, 1000, 60)
    assert is_due(1000 + 3600, 1000, 60)


def test_disabled_scheduler_never_syncs(tmp_path, monkeypatch):
    """Com o interruptor desligado, o laço nunca chama run_once, mesmo dentro da janela."""
    from app import scheduler
    from app.config import Settings
    from app.repo import Repo

    repo = Repo(tmp_path / "s.db")
    repo.set_scheduler_enabled(False)
    calls = []
    monkeypatch.setattr(scheduler, "Repo", lambda p: repo)
    monkeypatch.setattr(scheduler, "run_once", lambda *a: calls.append(1))
    monkeypatch.setattr(scheduler, "in_window", lambda *a: True)
    monkeypatch.setattr(scheduler, "Settings", lambda: type("S", (), {"validate": lambda s: None, "db_path": tmp_path / "s.db"})())
    monkeypatch.setattr(scheduler, "ROOT", tmp_path)
    n = {"i": 0}

    def fake_sleep(_):
        n["i"] += 1
        if n["i"] >= 2:
            raise KeyboardInterrupt
    monkeypatch.setattr(scheduler.time, "sleep", fake_sleep)
    try:
        scheduler.main()
    except KeyboardInterrupt:
        pass
    assert calls == [] and repo.get_state("scheduler_heartbeat")

    repo.set_scheduler_enabled(True)
    n["i"] = 0
    try:
        scheduler.main()
    except KeyboardInterrupt:
        pass
    assert calls == [1]
