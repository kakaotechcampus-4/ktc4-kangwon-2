from ssuksak.dev.verify_evidence_store import verify_evidence_store


def test_reproducibility_tool_verifies_approved_artifact_without_sources():
    report = verify_evidence_store()

    assert report.records == 12_325
    assert report.sources == 349
    assert not report.sources_checked
    assert report.file_sha256 == "5bf84e5a59fd74880b040ea1e545b00f4ddbe8cd1cc07da11a416161dedc8bb4"
    assert report.content_sha256 == "7d6d9bdb29dc5e84c024acc418a092c6e01d72134cf51043ab5dfd38a1332463"
    assert report.missing_sources == 0
    assert report.source_hash_mismatches == 0
    assert report.valid
