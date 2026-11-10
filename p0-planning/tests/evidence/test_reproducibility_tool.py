from ssuksak.dev.verify_evidence_store import verify_evidence_store


def test_reproducibility_tool_verifies_approved_artifact_without_sources():
    report = verify_evidence_store()

    assert report.records == 12_324
    assert report.sources == 349
    assert not report.sources_checked
    assert report.file_sha256 == "d680b955ce8efb39b0cd42107e2424af32c54dbf807b525ee5a7242657a5e562"
    assert report.content_sha256 == "4e01195eea06f28c71548b7c091ad8223b322b155e54f2bcbab957132f9cd7cd"
    assert report.missing_sources == 0
    assert report.valid
