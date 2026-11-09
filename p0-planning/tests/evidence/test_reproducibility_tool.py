from ssuksak.dev.verify_evidence_store import verify_evidence_store


def test_reproducibility_tool_verifies_approved_artifact_without_sources():
    report = verify_evidence_store()

    assert report.records == 12_325
    assert report.sources == 349
    assert not report.sources_checked
    assert report.file_sha256 == "7c051742a4e74628b8c4e2497c58e61dfa4e8399e72847a77539bfe92eeb7c98"
    assert report.content_sha256 == "99260c65df0ba0d1c5d010c93a17762c3aa134ea93836e6b8e04348afe27b3ce"
    assert report.missing_sources == 0
    assert report.valid
