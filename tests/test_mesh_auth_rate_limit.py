from klod.mesh.auth import AuthStore


def test_auth_rate_limiter_uses_persistent_window_and_returns_retry(tmp_path):
    store = AuthStore(str(tmp_path / "auth.sqlite"))
    assert store.consume_rate_limit("login:ip:test", 2, 600) == 0
    assert store.consume_rate_limit("login:ip:test", 2, 600) == 0
    assert store.consume_rate_limit("login:ip:test", 2, 600) > 0
