import asyncio
import json
import sys
from pathlib import Path

ML_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_SERVICE_ROOT))

from scripts.retry_vlm_analysis import (  # noqa: E402
    build_external_vlm_request,
    main_async,
    merge_identity_override,
    merge_vlm_retry_result,
    normalize_process_response,
    prepare_vlm_retry_inputs,
    validate_vlm_result_import,
)


def test_prepare_vlm_retry_inputs_absolutizes_representative_frames(tmp_path):
    uploads_root = tmp_path / "uploads"
    frame = uploads_root / "frames" / "inspection-1" / "organized" / "angle_front.jpg"
    crop = uploads_root / "frames" / "inspection-1" / "organized" / "dashboard_crop.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"frame")
    crop.write_bytes(b"crop")

    frames, frame_analysis = prepare_vlm_retry_inputs(
        {
            "frame_analysis": {
                "angle_shots": {
                    "front": {
                        "view": "front",
                        "frame": "frames/inspection-1/organized/angle_front.jpg",
                    }
                },
                "dashboard_candidates": [
                    {
                        "view": "dashboard",
                        "crop_path": "frames/inspection-1/organized/dashboard_crop.jpg",
                    }
                ],
                "representative_frames": [
                    {
                        "view": "front",
                        "frame": "frames/inspection-1/organized/angle_front.jpg",
                    }
                ],
            }
        },
        uploads_root=uploads_root,
    )

    assert frames == [str(frame)]
    assert frame_analysis["representative_frames"][0]["frame"] == str(frame)
    assert frame_analysis["angle_shots"]["front"]["frame"] == str(frame)
    assert frame_analysis["dashboard_candidates"][0]["crop_path"] == str(crop)


def test_normalize_process_response_accepts_backend_inspection_record(tmp_path):
    uploads_root = tmp_path / "uploads"
    frame = uploads_root / "frames" / "inspection-1" / "organized" / "angle_front.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"frame")
    persisted_report = {
        "frame_analysis": {
            "representative_frames": [
                {
                    "view": "front",
                    "frame": "frames/inspection-1/organized/angle_front.jpg",
                }
            ]
        },
        "vehicle_details": {
            "brand": "Toyota",
            "model": "Sienta",
            "year_range": "2022-present",
        },
        "gemini_analysis": {
            "available": False,
            "reason": "Gemini billing cap exceeded",
        },
    }

    normalized = normalize_process_response(
        {
            "id": "inspection-1",
            "vehicle_info": json.dumps({"brand": "Toyota", "model": "Sienta"}),
            "inspection_report": json.dumps(persisted_report),
        }
    )
    frames, _ = prepare_vlm_retry_inputs(normalized, uploads_root=uploads_root)

    assert normalized["report"] == persisted_report
    assert normalized["vehicle_info"] == {"brand": "Toyota", "model": "Sienta"}
    assert normalized["frame_analysis"] == persisted_report["frame_analysis"]
    assert normalized["gemini_analysis"] == persisted_report["gemini_analysis"]
    assert frames == [str(frame)]


def test_merge_vlm_retry_result_updates_auditable_process_response():
    process_response = {
        "vehicle_info": {
            "brand": "Toyota",
            "model": "Sienta",
            "type": "car",
            "vehicle_category": "compact minivan",
            "year_range": "2022-present",
            "confidence": 0.55,
        },
        "report": {
            "visual_analysis": {
                "available": False,
                "reason": "Gemini billing cap exceeded",
            },
            "pipeline_audit": {
                "status": "incomplete",
                "missing": ["vlm_available"],
            },
            "vehicle_details": {
                "brand": "Toyota",
                "model": "Sienta",
                "year_range": "2022-present",
            },
        },
    }
    vlm_result = {
        "available": True,
        "provider": "openai",
        "vehicle": {
            "brand": "Toyota",
            "model": "Sienta",
            "year": "2024",
            "variant": "Hybrid Z",
            "type": "car",
            "vehicle_category": "compact minivan",
            "confidence": 0.92,
        },
        "overall_condition": "good",
        "damage_items": [],
        "modification_items": [
            {"part": "wheels", "status": "stock", "confidence": 0.8},
        ],
    }

    merged = merge_vlm_retry_result(process_response, vlm_result)

    assert process_response["vehicle_info"].get("year") is None
    assert merged["gemini_analysis"] == vlm_result
    assert merged["vehicle_info"]["year"] == "2024"
    assert merged["vehicle_info"]["variant"] == "Hybrid Z"
    assert merged["vehicle_info"]["confidence"] == 0.92
    assert merged["report"]["gemini_analysis"] == vlm_result
    assert merged["report"]["visual_analysis"] == {
        "available": True,
        "reason": None,
        "provider": "openai",
    }
    assert merged["report"]["vehicle_details"]["year"] == "2024"
    assert merged["report"]["vehicle_details"]["variant"] == "Hybrid Z"
    assert "pipeline_audit" not in merged["report"]


def test_skip_vlm_merges_identity_override_without_frame_files(tmp_path, monkeypatch):
    inspection_json = tmp_path / "inspection.json"
    identity_json = tmp_path / "identity.json"
    merged_json = tmp_path / "merged.json"
    inspection_json.write_text(
        json.dumps(
            {
                "vehicle_info": {
                    "brand": "Toyota",
                    "model": "Sienta",
                    "confidence": 0.55,
                },
                "report": {
                    "pipeline_audit": {
                        "status": "incomplete",
                        "missing": ["vlm_available", "vehicle_identity"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    identity_json.write_text(
        json.dumps(
            {
                "source": "manual_review",
                "year": "2024",
                "variant": "Hybrid Z",
                "type": "car",
                "vehicle_category": "compact minivan",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retry_vlm_analysis.py",
            "--inspection-json",
            str(inspection_json),
            "--identity-override-json",
            str(identity_json),
            "--merged-output-json",
            str(merged_json),
            "--skip-vlm",
        ],
    )

    assert asyncio.run(main_async()) == 0

    merged = json.loads(merged_json.read_text(encoding="utf-8"))
    assert merged["vehicle_info"]["year"] == "2024"
    assert merged["vehicle_info"]["variant"] == "Hybrid Z"
    assert merged["vehicle_info"]["identity_source"] == "manual_review"
    assert merged["report"]["vehicle_details"]["vehicle_category"] == "compact minivan"
    assert "pipeline_audit" not in merged["report"]


def test_vlm_result_json_merges_without_provider_call_or_frame_files(tmp_path, monkeypatch):
    inspection_json = tmp_path / "inspection.json"
    vlm_json = tmp_path / "vlm.json"
    output_json = tmp_path / "vlm-output.json"
    merged_json = tmp_path / "merged.json"
    inspection_json.write_text(
        json.dumps(
            {
                "vehicle_info": {
                    "brand": "Toyota",
                    "model": "Sienta",
                    "confidence": 0.55,
                },
                "report": {
                    "pipeline_audit": {
                        "status": "incomplete",
                        "missing": ["vlm_available", "vehicle_identity"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    vlm_result = {
        "available": True,
        "provider": "external_vlm_review",
        "vehicle": {
            "brand": "Toyota",
            "model": "Sienta",
            "year": "2024",
            "variant": "Hybrid Z",
            "type": "car",
            "vehicle_category": "compact minivan",
            "confidence": 0.92,
        },
        "overall_condition": "good",
        "damage_items": [],
    }
    vlm_json.write_text(json.dumps(vlm_result), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retry_vlm_analysis.py",
            "--inspection-json",
            str(inspection_json),
            "--vlm-result-json",
            str(vlm_json),
            "--output-json",
            str(output_json),
            "--merged-output-json",
            str(merged_json),
        ],
    )

    assert asyncio.run(main_async()) == 0

    merged = json.loads(merged_json.read_text(encoding="utf-8"))
    assert json.loads(output_json.read_text(encoding="utf-8")) == vlm_result
    assert merged["gemini_analysis"] == vlm_result
    assert merged["vehicle_info"]["year"] == "2024"
    assert merged["report"]["visual_analysis"] == {
        "available": True,
        "reason": None,
        "provider": "external_vlm_review",
    }
    assert "pipeline_audit" not in merged["report"]


def test_validate_vlm_result_import_requires_explicit_availability():
    assert validate_vlm_result_import({"vehicle": {"brand": "Toyota"}}) == (
        False,
        "VLM result must include boolean field 'available'.",
    )
    assert validate_vlm_result_import({"available": True}) == (
        False,
        "Available VLM result must include a vehicle object.",
    )
    assert validate_vlm_result_import({"available": False, "reason": "manual rejection"}) == (
        True,
        None,
    )


def test_build_external_vlm_request_exports_prompt_and_selected_frames(tmp_path):
    uploads_root = tmp_path / "uploads"
    frame = uploads_root / "frames" / "inspection-1" / "organized" / "angle_front.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"fake jpeg")

    request_package = build_external_vlm_request(
        {
            "frame_analysis": {
                "angle_shots": {
                    "front": {
                        "view": "front",
                        "frame": "frames/inspection-1/organized/angle_front.jpg",
                        "timestamp_seconds": 1.25,
                        "quality_score": 0.9,
                        "high_confidence": True,
                    }
                },
                "representative_frames": [
                    {
                        "view": "front",
                        "frame": "frames/inspection-1/organized/angle_front.jpg",
                    }
                ],
            }
        },
        uploads_root=uploads_root,
        include_image_data=True,
    )

    assert "STRICT JSON response" in request_package["prompt"]
    assert request_package["frames"][0]["path"] == str(frame)
    assert request_package["frames"][0]["view"] == "front"
    assert request_package["frames"][0]["data_url"].startswith("data:image/jpeg;base64,")
    assert request_package["expected_response_schema"]["vehicle"]["brand"] == "string"


def test_export_request_json_writes_external_vlm_package_without_provider_call(tmp_path, monkeypatch):
    uploads_root = tmp_path / "uploads"
    frame = uploads_root / "frames" / "inspection-1" / "organized" / "angle_front.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"fake jpeg")
    inspection_json = tmp_path / "inspection.json"
    export_json = tmp_path / "external-request.json"
    inspection_json.write_text(
        json.dumps(
            {
                "frame_analysis": {
                    "angle_shots": {
                        "front": {
                            "view": "front",
                            "frame": "frames/inspection-1/organized/angle_front.jpg",
                        }
                    },
                    "representative_frames": [
                        {
                            "view": "front",
                            "frame": "frames/inspection-1/organized/angle_front.jpg",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retry_vlm_analysis.py",
            "--inspection-json",
            str(inspection_json),
            "--uploads-root",
            str(uploads_root),
            "--export-request-json",
            str(export_json),
        ],
    )

    assert asyncio.run(main_async()) == 0

    exported = json.loads(export_json.read_text(encoding="utf-8"))
    assert exported["frames"][0]["path"] == str(frame)
    assert exported["expected_response_schema"]["available"] is True


def test_merge_identity_override_updates_auditable_process_response():
    process_response = {
        "vehicle_info": {
            "brand": "Toyota",
            "model": "Sienta",
            "type": "car",
            "vehicle_category": "compact minivan",
            "year_range": "2022-present",
            "confidence": 0.55,
        },
        "report": {
            "pipeline_audit": {
                "status": "incomplete",
                "missing": ["vehicle_identity"],
            },
            "vehicle_details": {
                "brand": "Toyota",
                "model": "Sienta",
                "year_range": "2022-present",
            },
        },
    }
    identity_override = {
        "source": "registration_certificate",
        "year": "2024",
        "variant": "Hybrid Z",
        "vin": "NHP170-1234567",
        "registration": "Tokyo 500 A 12-34",
    }

    merged = merge_identity_override(process_response, identity_override)

    assert process_response["vehicle_info"].get("year") is None
    assert merged["vehicle_info"]["year"] == "2024"
    assert merged["vehicle_info"]["variant"] == "Hybrid Z"
    assert merged["vehicle_info"]["vin"] == "NHP170-1234567"
    assert merged["vehicle_info"]["registration"] == "Tokyo 500 A 12-34"
    assert merged["vehicle_info"]["identity_source"] == "registration_certificate"
    assert merged["vehicle_info"]["identity_override_fields"] == [
        "year",
        "variant",
        "vin",
        "registration",
    ]
    assert merged["vehicle_info"]["confidence"] == 0.95
    assert merged["report"]["vehicle_details"]["year"] == "2024"
    assert merged["report"]["vehicle_details"]["variant"] == "Hybrid Z"
    assert "pipeline_audit" not in merged["report"]
