"""SQL migration runner: ordering, idempotency, and partial-failure recovery.

The runner is the startup gatekeeper for every migration but previously had no
tests. The partial-failure case matters operationally: on this project's Unraid
host the data volume can flip read-only mid-write, which can abort a migration
between statements and (because pysqlite runs DDL in autocommit) leave earlier
DDL applied with no _migrations row. The runner must converge on the next boot
rather than boot-loop.
"""

from sqlalchemy import create_engine, text

from app.migrations import runner


def _write(versions_dir, name, sql):
    (versions_dir / name).write_text(sql)


def _applied(engine):
    with engine.begin() as conn:
        return {
            row[0]
            for row in conn.execute(text("SELECT filename FROM _migrations")).fetchall()
        }


def _table_exists(engine, table):
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": table},
        ).first()
    return row is not None


def test_runs_in_order_and_records_each(tmp_path, monkeypatch):
    versions = tmp_path / "versions"
    versions.mkdir()
    _write(versions, "001_a.sql", "CREATE TABLE a (id INTEGER PRIMARY KEY);")
    _write(versions, "002_b.sql", "CREATE TABLE b (id INTEGER PRIMARY KEY);")
    monkeypatch.setattr(runner, "VERSIONS_DIR", versions)

    engine = create_engine(f"sqlite:///{tmp_path}/db.sqlite")
    runner.run_migrations(engine)

    assert _applied(engine) == {"001_a.sql", "002_b.sql"}
    assert _table_exists(engine, "a")
    assert _table_exists(engine, "b")


def test_idempotent_second_run_is_noop(tmp_path, monkeypatch):
    versions = tmp_path / "versions"
    versions.mkdir()
    _write(versions, "001_a.sql", "CREATE TABLE a (id INTEGER PRIMARY KEY);")
    monkeypatch.setattr(runner, "VERSIONS_DIR", versions)

    engine = create_engine(f"sqlite:///{tmp_path}/db.sqlite")
    runner.run_migrations(engine)
    # Second run must not raise (already-applied migrations are skipped).
    runner.run_migrations(engine)
    assert _applied(engine) == {"001_a.sql"}


def test_partial_failure_recovers_on_rerun(tmp_path, monkeypatch):
    """Simulate a crash after the first statement of a multi-statement migration
    (table created, but no _migrations row). The re-run must tolerate the
    already-existing table, finish the rest, and record the migration."""
    versions = tmp_path / "versions"
    versions.mkdir()
    _write(
        versions,
        "001_two_tables.sql",
        "CREATE TABLE a (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE b (id INTEGER PRIMARY KEY);",
    )
    monkeypatch.setattr(runner, "VERSIONS_DIR", versions)

    engine = create_engine(f"sqlite:///{tmp_path}/db.sqlite")
    # Simulate the partial apply: table `a` exists, `_migrations` is empty.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE a (id INTEGER PRIMARY KEY)"))

    runner.run_migrations(engine)  # must NOT raise on "table a already exists"

    assert _table_exists(engine, "a")
    assert _table_exists(engine, "b")
    assert "001_two_tables.sql" in _applied(engine)


def test_replayed_drop_column_converges(tmp_path, monkeypatch):
    """F-6: a DROP COLUMN migration that gets replayed (its _migrations row was
    never written) must tolerate 'no such column' and converge, not boot-loop."""
    versions = tmp_path / "versions"
    versions.mkdir()
    _write(versions, "001_base.sql", "CREATE TABLE t (id INTEGER PRIMARY KEY, gone TEXT);")
    _write(versions, "002_drop.sql", "ALTER TABLE t DROP COLUMN gone;")
    monkeypatch.setattr(runner, "VERSIONS_DIR", versions)

    engine = create_engine(f"sqlite:///{tmp_path}/db.sqlite")
    runner.run_migrations(engine)  # applies both cleanly

    # Simulate a partial apply of 002: the column is already dropped but the
    # _migrations row was never written, so the runner will replay it.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM _migrations WHERE filename = '002_drop.sql'"))

    runner.run_migrations(engine)  # must NOT raise on "no such column: gone"
    assert "002_drop.sql" in _applied(engine)


def test_real_error_still_raises(tmp_path, monkeypatch):
    versions = tmp_path / "versions"
    versions.mkdir()
    _write(versions, "001_bad.sql", "CREATE TABLE oops (id INTEGER PRIMARY KEY);\nTHIS IS NOT SQL;")
    monkeypatch.setattr(runner, "VERSIONS_DIR", versions)

    engine = create_engine(f"sqlite:///{tmp_path}/db.sqlite")
    try:
        runner.run_migrations(engine)
        raised = False
    except Exception:
        raised = True
    assert raised, "a genuine SQL syntax error must propagate, not be swallowed"
