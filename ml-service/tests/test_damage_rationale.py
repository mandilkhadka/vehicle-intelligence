"""Regression tests for damage rationale snapshot resolution.

The bug: _resolve_snapshot_path hardcoded backend_root/backend/uploads and
ignored UPLOADS_ROOT, so in Docker (UPLOADS_ROOT=/app/uploads) every snapshot
failed os.path.exists and attach_rationales silently attached zero rationales.
"""

import asyncio

from src.services.damage_rationale import _resolve_snapshot_path, attach_rationales


def test_resolve_snapshot_path_honors_uploads_root(tmp_path, monkeypatch):
    uploads = tmp_path / "app-uploads"
    snapshot = uploads / "frames" / "i1" / "damage_snapshots" / "scratch_001.jpg"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"jpg")
    monkeypatch.setenv("UPLOADS_ROOT", str(uploads))

    # backend_root deliberately points at a layout that does NOT contain the file.
    resolved = _resolve_snapshot_path(
        "frames/i1/damage_snapshots/scratch_001.jpg", str(tmp_path / "repo")
    )

    assert resolved == str(snapshot)


def test_resolve_snapshot_path_falls_back_to_backend_layout(tmp_path, monkeypatch):
    monkeypatch.delenv("UPLOADS_ROOT", raising=False)
    root = tmp_path / "repo"
    snapshot = root / "backend" / "uploads" / "frames" / "i1" / "damage_snapshots" / "dent_001.jpg"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"jpg")

    resolved = _resolve_snapshot_path("frames/i1/damage_snapshots/dent_001.jpg", str(root))

    assert resolved == str(snapshot)


def test_resolve_snapshot_path_returns_none_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_ROOT", str(tmp_path / "uploads"))
    assert _resolve_snapshot_path("frames/i1/missing.jpg", str(tmp_path)) is None


class _FakeOllama:
    available = True


class _FakeAnalyzer:
    def __init__(self, text):
        self.ollama = _FakeOllama()
        self._text = text
        self.calls = []

    def vlm_generate_text(self, prompt, image_paths):
        self.calls.append(list(image_paths))
        return self._text


def test_attach_rationales_resolves_snapshots_under_uploads_root(tmp_path, monkeypatch):
    uploads = tmp_path / "app-uploads"
    snapshot = uploads / "frames" / "i1" / "damage_snapshots" / "scratch_001.jpg"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"jpg")
    monkeypatch.setenv("UPLOADS_ROOT", str(uploads))

    damage = {
        "locations": [
            {
                "type": "scratch",
                "confidence": 0.9,
                "snapshot": "frames/i1/damage_snapshots/scratch_001.jpg",
            }
        ]
    }
    analyzer = _FakeAnalyzer(
        '{"rationales": [{"index": 0, "rationale": "Clear linear scratch.", "likely_real": true}]}'
    )

    asyncio.run(attach_rationales(damage, analyzer, backend_root=str(tmp_path / "repo")))

    assert analyzer.calls == [[str(snapshot)]]
    assert damage["rationale_available"] is True
    assert damage["rationale_count"] == 1
    assert damage["locations"][0]["rationale"] == "Clear linear scratch."
    assert damage["locations"][0]["rationale_likely_real"] is True
