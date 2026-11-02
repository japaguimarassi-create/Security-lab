from klod.mesh.relativity import (
    RELATIVITY_CANONICAL_TEXT,
    RELATIVITY_CORPUS_VERSION,
    canonical_relativity_bytes,
    relativity_fingerprint,
    verify_relativity_corpus,
)


def test_canonical_corpus_is_stable_and_versioned():
    assert RELATIVITY_CORPUS_VERSION == "GR-CANONICAL-CORE-1.0.0"
    assert b"einstein field equations" in canonical_relativity_bytes().lower()
    assert len(relativity_fingerprint()) == 64


def test_corpus_verification_accepts_its_digest_and_rejects_changes():
    digest = relativity_fingerprint()
    assert verify_relativity_corpus(digest)
    assert not verify_relativity_corpus("0" * 64)
    assert not verify_relativity_corpus("not-a-digest")


def test_corpus_contains_core_geometric_and_physical_equations():
    lowered = RELATIVITY_CANONICAL_TEXT.lower()
    for term in ("riemann", "ricci", "einstein field equations", "geodesic",
                 "schwarzschild", "kerr", "friedmann", "adm 3+1"):
        assert term in lowered
