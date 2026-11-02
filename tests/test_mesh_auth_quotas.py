import pytest

from klod.mesh.auth import AccountExists, AuthStore, AuthenticationError
from klod.mesh.quotas import QuotaExceeded, QuotaLedger


PASSWORD = "M3sh-Secret-Password-2026"


def test_passwords_are_hashed_and_sessions_are_revocable(tmp_path):
    store = AuthStore(str(tmp_path / "auth.sqlite"))
    account = store.register("User@example.com", PASSWORD)
    with store._connect() as db:
        row = db.execute("SELECT password_hash FROM mesh_users WHERE user_id=?",
                         (account["user_id"],)).fetchone()
    assert row["password_hash"] != PASSWORD
    assert row["password_hash"].startswith("$argon2id$")
    login = store.login("user@example.com", PASSWORD)
    assert store.resolve_session(login["access_token"])["user_id"] == account["user_id"]
    assert store.revoke_session(login["access_token"])
    assert store.resolve_session(login["access_token"]) is None


def test_duplicate_accounts_and_weak_passwords_are_rejected(tmp_path):
    store = AuthStore(str(tmp_path / "auth.sqlite"))
    store.register("user@example.com", PASSWORD)
    with pytest.raises(AccountExists):
        store.register("USER@example.com", PASSWORD)
    with pytest.raises(AuthenticationError):
        store.register("weak@example.com", "short")
    with pytest.raises(AuthenticationError):
        store.login("user@example.com", "incorrect-password")


def test_weekly_quota_is_atomic_and_resets_at_monday_utc(tmp_path):
    ledger = QuotaLedger(str(tmp_path / "quota.sqlite"), {"gpu_seconds": 100.0, "cpu_core_seconds": 1000.0})
    monday = 1793664000.0
    ledger.reserve("user-1", {"gpu_seconds": 80.0, "cpu_core_seconds": 100.0}, at=monday)
    with pytest.raises(QuotaExceeded):
        ledger.reserve("user-1", {"gpu_seconds": 30.0, "cpu_core_seconds": 200.0}, at=monday)
    summary = ledger.summary("user-1", at=monday)
    assert summary["resources"]["gpu_seconds"]["used"] == 80.0
    assert summary["resources"]["cpu_core_seconds"]["used"] == 100.0
    next_week = monday + 7 * 24 * 60 * 60
    assert ledger.summary("user-1", at=next_week)["resources"]["gpu_seconds"]["used"] == 0.0


def test_unknown_and_nonfinite_quota_values_are_rejected(tmp_path):
    ledger = QuotaLedger(str(tmp_path / "quota.sqlite"))
    with pytest.raises(ValueError):
        ledger.reserve("user-1", {"made_up_metric": 1})
    with pytest.raises(ValueError):
        ledger.reserve("user-1", {"gpu_seconds": float("nan")})
