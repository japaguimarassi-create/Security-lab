from klod.db import _postgres_sql, connect, is_postgres, prepare_database_path


def test_postgres_detection_and_schema_translation(tmp_path):
    assert is_postgres("postgresql://user:pass@host/db")
    assert is_postgres("postgres://user:pass@host/db")
    assert not is_postgres(str(tmp_path / "local.sqlite3"))

    sql = _postgres_sql("CREATE TABLE sample (id INTEGER PRIMARY KEY AUTOINCREMENT, payload BLOB NOT NULL, amount REAL NOT NULL)")
    assert "BIGSERIAL PRIMARY KEY" in sql
    assert "BYTEA NOT NULL" in sql
    assert "DOUBLE PRECISION NOT NULL" in sql


def test_postgres_qmark_parameters_are_translated():
    assert _postgres_sql("SELECT * FROM sample WHERE owner_id=? AND task_id=?") == (
        "SELECT * FROM sample WHERE owner_id=%s AND task_id=%s"
    )


def test_prepare_postgres_path_does_not_create_local_directories(tmp_path):
    prepare_database_path("postgresql://user:pass@db.example.invalid/app")
    assert list(tmp_path.iterdir()) == []


def test_database_factory_keeps_sqlite_compatibility(tmp_path):
    database = tmp_path / "state.sqlite3"
    with connect(str(database)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample(value) VALUES(?)", ("persisted",))
    with connect(str(database)) as connection:
        row = connection.execute("SELECT value FROM sample").fetchone()
    assert row[0] == "persisted"
