from ssuksak.dev.verify_evidence_store import verify_evidence_store


def test_reproducibility_tool_verifies_approved_artifact_without_sources():
    report = verify_evidence_store()

    assert report.records == 12_325
    assert report.sources == 349
    assert not report.sources_checked
    assert report.file_sha256 == "90f2a4a219457de506b8cb103824a6636b78f1e4007004214f85c3a59d4c69bf"
    assert report.content_sha256 == "ab6bb59178106f242225a163963d77b1f4cb038befc0032ba989a18fb57e50eb"
    assert report.missing_sources == 0
    assert report.valid
