from ssuksak.dev.verify_evidence_store import verify_evidence_store


def test_reproducibility_tool_verifies_approved_artifact_without_sources():
    report = verify_evidence_store()

    assert report.records == 12_367
    assert report.sources == 349
    assert not report.sources_checked
    assert report.file_sha256 == "8479c0490a002d9336688c1b6cacf47f2d2c083201b15df01258336c07e0ba1a"
    assert report.content_sha256 == "52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea"
    assert report.missing_sources == 0
    assert report.source_hash_mismatches == 0
    assert report.valid
