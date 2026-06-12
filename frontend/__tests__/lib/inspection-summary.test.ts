jest.mock("@/lib/api", () => ({
  BACKEND_BASE_URL: "http://localhost:3001",
}));

import {
  DAMAGE_CATEGORY_KEYS,
  countDamageIssues,
  toInspectionListItem,
} from "@/lib/inspection-summary";

describe("countDamageIssues", () => {
  it("sums every damage category, not just the original five", () => {
    const damage = Object.fromEntries(
      DAMAGE_CATEGORY_KEYS.map((key) => [key, { count: 1 }]),
    );
    expect(countDamageIssues(damage)).toBe(9);
  });

  it("includes the newer categories in the total", () => {
    expect(
      countDamageIssues({
        scratches: { count: 2 },
        wheel_damage: { count: 1 },
        broken_lights: { count: 1 },
        missing_parts: { count: 1 },
        panel_misalignment: { count: 1 },
      }),
    ).toBe(6);
  });

  it("tolerates missing or malformed categories", () => {
    expect(countDamageIssues({})).toBe(0);
    expect(countDamageIssues({ scratches: undefined })).toBe(0);
  });
});

describe("toInspectionListItem", () => {
  it("builds the display row from JSON-blob fields", () => {
    const item = toInspectionListItem({
      id: "insp-1",
      vehicle_info: JSON.stringify({
        brand: "Toyota",
        model: "Sienta",
        year: 2024,
        variant: "Hybrid Z",
        confidence: 0.91,
      }),
      damage_summary: JSON.stringify({
        scratches: { count: 1 },
        wheel_damage: { count: 2 },
      }),
      extracted_frames: JSON.stringify(["frames/abc/frame_0001.jpg"]),
      created_at: "2026-01-15T10:00:00Z",
      job_status: "completed",
    });

    expect(item.vehicle).toBe("2024 Toyota Sienta Hybrid Z");
    expect(item.issues).toBe(3);
    expect(item.confidence).toBe(0.91);
    expect(item.image).toBe(
      "http://localhost:3001/uploads/frames/abc/frame_0001.jpg",
    );
    expect(item.status).toBe("completed");
  });

  it("falls back to flat columns and skips dead sample frames", () => {
    const item = toInspectionListItem({
      id: "insp-2",
      vehicle_brand: "Honda",
      vehicle_model: "Civic",
      extracted_frames: JSON.stringify(["frames/sample/frame_0001.jpg"]),
    });

    expect(item.vehicle).toBe("Honda Civic");
    expect(item.image).toBeNull();
    expect(item.status).toBe("completed");
    expect(item.date).toBeNull();
  });

  it("labels unidentifiable vehicles with the fallback", () => {
    const item = toInspectionListItem(
      { id: "insp-3", vehicle_brand: "Unknown" },
      { fallbackVehicleLabel: "Unidentified vehicle" },
    );
    expect(item.vehicle).toBe("Unidentified vehicle");
    expect(item.brand).toBe("—");
  });
});
