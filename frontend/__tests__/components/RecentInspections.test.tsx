import { render, screen, waitFor } from "@testing-library/react";

jest.mock("@/lib/api", () => ({
  getInspections: jest.fn(),
  BACKEND_BASE_URL: "http://localhost:3001",
}));

jest.mock("@/lib/toast", () => ({
  showError: jest.fn(),
}));

import { RecentInspections } from "@/components/dashboard/recent-inspections";
import { getInspections } from "@/lib/api";

describe("RecentInspections", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows pipeline audit status for recent inspections", async () => {
    (getInspections as jest.Mock).mockResolvedValue([
      {
        id: "insp-001",
        vehicle_brand: "Toyota",
        vehicle_model: "Sienta",
        vehicle_confidence: 0.88,
        damage_summary: JSON.stringify({ scratches: { count: 0 }, dents: { count: 0 }, rust: { count: 0 } }),
        extracted_frames: JSON.stringify([]),
        created_at: "2026-05-12T08:00:00Z",
        job_status: "completed",
        inspection_report: JSON.stringify({
          pipeline_audit: {
            status: "incomplete",
            passed: false,
            checks: [],
            missing: ["vlm_available"],
          },
        }),
      },
    ]);

    render(<RecentInspections />);

    await waitFor(() => {
      expect(screen.getByText("Toyota Sienta")).toBeInTheDocument();
      expect(screen.getByText("Needs review")).toBeInTheDocument();
    });
  });
});
