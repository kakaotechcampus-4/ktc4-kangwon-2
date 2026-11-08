from ssuksak.dev.verify_evidence_store import verify_evidence_store


def test_reproducibility_tool_verifies_approved_artifact_without_sources():
    report = verify_evidence_store()

    assert report.records == 12_325
    assert report.sources == 349
    assert not report.sources_checked
    assert report.file_sha256 == "3e76eb5ccdaef50f16658397da0a1e2023b6ac2283a462414d1c16cc9e263c64"
    assert report.content_sha256 == "64c007e12366f57b2affdae1f55f77bea874906d9320cf227b84680fec46eced"
    assert report.missing_sources == 0
    assert report.valid
