from src.services.vehicle_identifier import VehicleIdentifier


def test_context_brand_overrides_weak_crop_brand():
    brand, confidence = VehicleIdentifier._choose_brand_result(
        crop_brand="Nissan",
        crop_confidence=0.36,
        context_brand="Toyota",
        context_confidence=0.44,
    )

    assert brand == "Toyota"
    assert confidence == 0.44


def test_context_brand_does_not_override_without_margin():
    brand, confidence = VehicleIdentifier._choose_brand_result(
        crop_brand="Nissan",
        crop_confidence=0.50,
        context_brand="Toyota",
        context_confidence=0.51,
    )

    assert brand == "Nissan"
    assert confidence == 0.50


def test_context_brand_paths_prefer_logo_bearing_views():
    selected = VehicleIdentifier._context_brand_frame_paths([
        "/tmp/angle_left.jpg",
        "/tmp/angle_rear.jpg",
        "/tmp/angle_front.jpg",
        "/tmp/angle_dashboard.jpg",
    ])

    assert selected == ["/tmp/angle_front.jpg", "/tmp/angle_dashboard.jpg"]


def test_model_paths_prefer_organized_vehicle_and_dashboard_views():
    selected = VehicleIdentifier._model_frame_paths([
        "/tmp/raw_0001.jpg",
        "/tmp/angle_left.jpg",
        "/tmp/angle_rear.jpg",
        "/tmp/angle_dashboard.jpg",
    ])

    assert selected == [
        "/tmp/angle_left.jpg",
        "/tmp/angle_rear.jpg",
        "/tmp/angle_dashboard.jpg",
    ]


def test_model_identity_metadata_returns_generation_candidates():
    metadata = VehicleIdentifier._model_identity_metadata("Toyota", "Sienta")

    assert metadata["vehicle_category"] == "compact minivan"
    assert metadata["year_range"] == "2022-present"
    assert "Hybrid" in metadata["variant_candidates"]


def test_variant_candidate_returns_none_without_variant_options():
    identifier = object.__new__(VehicleIdentifier)

    result = identifier._identify_variant_candidate(
        brand="Toyota",
        model="Sienta",
        variant_options=[],
        frame_paths=["/tmp/angle_front.jpg"],
    )

    assert result is None
