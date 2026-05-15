import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useParams: () => ({ id: "test-insp-123" }),
  usePathname: () => "/inspection/test-insp-123",
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ fill, unoptimized, ...props }: any) => <img {...props} />,
}));

jest.mock("@/lib/api", () => ({
  getInspection: jest.fn(),
  retryInspectionVlmAnalysis: jest.fn(),
  updateInspectionIdentity: jest.fn(),
  updateInspectionVlmEvidence: jest.fn(),
  BACKEND_BASE_URL: "http://localhost:3001",
}));

jest.mock("@/lib/toast", () => ({
  showError: jest.fn(),
  showSuccess: jest.fn(),
}));

jest.mock("@/components/VehicleInfo", () => ({
  __esModule: true,
  default: ({ vehicleInfo }: any) => (
    <div data-testid="vehicle-info">
      {vehicleInfo.brand} {vehicleInfo.model} {vehicleInfo.year} {vehicleInfo.variant}
      {vehicleInfo.year_range ? ` ${vehicleInfo.year_range}` : ""}
      {vehicleInfo.generation ? ` ${vehicleInfo.generation}` : ""}
      {vehicleInfo.variant_candidates?.length
        ? ` ${vehicleInfo.variant_candidates.join(", ")}`
        : ""}
      {vehicleInfo.variant_candidate ? ` ${vehicleInfo.variant_candidate}` : ""}
      {vehicleInfo.identity_notes ? ` ${vehicleInfo.identity_notes}` : ""}
    </div>
  ),
}));

jest.mock("@/components/OdometerInfo", () => ({
  __esModule: true,
  default: ({ odometer }: any) => (
    <div data-testid="odometer-info">
      {odometer.value} {odometer.source_frame_index}
    </div>
  ),
}));

jest.mock("@/components/DamageInfo", () => ({
  __esModule: true,
  default: ({ damage }: any) => (
    <div data-testid="damage-info">Scratches: {damage.scratches?.count || 0}</div>
  ),
}));

jest.mock("@/components/ExhaustInfo", () => ({
  __esModule: true,
  default: ({ exhaust }: any) => <div data-testid="exhaust-info">{exhaust.type}</div>,
}));

import InspectionPage from "@/app/inspection/[id]/page";
import {
  getInspection,
  retryInspectionVlmAnalysis,
  updateInspectionIdentity,
  updateInspectionVlmEvidence,
} from "@/lib/api";

const mockInspectionData = {
  id: "test-insp-123",
  vehicle_brand: "Toyota",
  vehicle_model: "Camry",
  vehicle_year: "2024",
  vehicle_variant: "Hybrid XLE",
  vehicle_confidence: 0.95,
  odometer_value: "45,230 km",
  odometer_confidence: 0.92,
  damage_summary: JSON.stringify({
    scratches: { count: 2, detected: true },
    dents: { count: 1, detected: true },
    rust: { count: 0, detected: false },
    severity: "medium",
  }),
  exhaust_type: "stock",
  exhaust_confidence: 0.88,
  extracted_frames: JSON.stringify(["frame1.jpg", "frame2.jpg"]),
  inspection_report: JSON.stringify({
    summary: "Vehicle is in good condition with minor cosmetic damage.",
    recommendations: ["Address scratches", "Monitor dent"],
  }),
  created_at: "2024-01-15T10:00:00Z",
};

describe("InspectionPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders loading state initially", () => {
    (getInspection as jest.Mock).mockReturnValue(new Promise(() => {}));

    render(<InspectionPage />);

    expect(screen.getByText(/Loading inspection/)).toBeInTheDocument();
  });

  it("renders inspection data", async () => {
    (getInspection as jest.Mock).mockResolvedValue(mockInspectionData);

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Inspection Results")).toBeInTheDocument();
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Toyota Camry 2024 Hybrid XLE");
      expect(screen.getByTestId("odometer-info")).toHaveTextContent("45,230 km");
      expect(screen.getByTestId("damage-info")).toHaveTextContent("Scratches: 2");
      expect(screen.getByTestId("exhaust-info")).toHaveTextContent("stock");
    });
  });

  it("uses persisted odometer metadata when available", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      odometer_value: 11111,
      odometer_confidence: 0.4,
      odometer_info: JSON.stringify({
        value: 45230,
        confidence: 0.92,
        speedometer_image_path: "frames/test/organized/odometer_crop.jpg",
        source_frame_index: 210,
        timestamp_seconds: 3.5,
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByTestId("odometer-info")).toHaveTextContent("45230 210");
    });
  });

  it("falls back to report vehicle details for year and variant", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      vehicle_year: undefined,
      vehicle_variant: undefined,
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete.",
        vehicle_details: {
          type: "car",
          brand: "Toyota",
          model: "Camry",
          year: "2023",
          variant: "SE",
          confidence: 0.89,
        },
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Toyota Camry 2023 SE");
    });
  });

  it("falls back to report vehicle candidate metadata", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      vehicle_brand: undefined,
      vehicle_model: undefined,
      vehicle_year: undefined,
      vehicle_variant: undefined,
      vehicle_info: undefined,
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete.",
        vehicle_details: {
          type: "car",
          brand: "Toyota",
          model: "Sienta",
          year_range: "2022-present",
          generation: "third generation",
          variant_candidates: ["Hybrid", "Z", "G", "X"],
          variant_candidate: "Hybrid",
          variant_confidence: 0.72,
          variant_candidates_ranked: [
            { variant: "Hybrid", confidence: 0.72 },
            { variant: "Z", confidence: 0.21 },
          ],
          identity_notes: "Exact year and trim require manual verification.",
          confidence: 0.56,
        },
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Toyota Sienta");
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("2022-present");
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("third generation");
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Hybrid, Z, G, X");
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Hybrid");
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent(
        "Exact year and trim require manual verification.",
      );
    });
  });

  it("renders summary and recommendations", async () => {
    (getInspection as jest.Mock).mockResolvedValue(mockInspectionData);

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Summary")).toBeInTheDocument();
      expect(
        screen.getByText("Vehicle is in good condition with minor cosmetic damage."),
      ).toBeInTheDocument();
      expect(screen.getByText("Address scratches")).toBeInTheDocument();
      expect(screen.getByText("Monitor dent")).toBeInTheDocument();
    });
  });

  it("renders extracted frames gallery", async () => {
    (getInspection as jest.Mock).mockResolvedValue(mockInspectionData);

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Extracted Frames")).toBeInTheDocument();
      expect(screen.getAllByRole("img").length).toBeGreaterThan(0);
    });
  });

  it("renders organized vehicle shots when frame analysis is available", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      damage_summary: JSON.stringify({
        scratches: { count: 1, detected: true },
        dents: { count: 0, detected: false },
        rust: { count: 0, detected: false },
        cracks: { count: 0, detected: false },
        paint_damage: { count: 0, detected: false },
        severity: "low",
        locations: [
          {
            type: "scratch",
            frame: "frames/test/organized/angle_front.jpg",
            confidence: 0.81,
            severity: "low",
            bbox: [10, 20, 90, 80],
            angle: "front",
            linked_view: "front",
          },
        ],
      }),
      inspection_report: JSON.stringify({
        summary: "Vehicle is in good condition with minor cosmetic damage.",
        recommendations: ["Address scratches"],
        frame_analysis: {
          angle_shots: {
            front: {
              view: "front",
              frame: "frames/test/frame_0001.jpg",
              organized_path: "frames/test/organized/angle_front.jpg",
              score: 0.86,
            },
            dashboard: {
              view: "dashboard",
              frame: "frames/test/frame_0002.jpg",
              organized_path: "frames/test/organized/angle_dashboard.jpg",
              score: 0.73,
            },
          },
          dashboard_candidates: [
            {
              view: "dashboard",
              frame: "frames/test/frame_0002.jpg",
              crop_path: "frames/test/organized/dashboard_candidate_01_crop.jpg",
              score: 0.81,
            },
          ],
          representative_frames: [],
          coverage: {
            required_views: ["front", "dashboard"],
            present_views: ["front", "dashboard"],
            high_confidence_views: ["dashboard"],
            low_confidence_views: ["front"],
            missing_views: [],
            ratio: 1,
            high_confidence_ratio: 0.5,
          },
          frames_analyzed: 29,
          frames_total: 29,
          method: "heuristic_temporal_quality",
        },
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Interactive 360 Inspection Viewer")).toBeInTheDocument();
      expect(screen.getByText("100% selected")).toBeInTheDocument();
      expect(screen.getByText("50% high confidence")).toBeInTheDocument();
      expect(screen.getByText("360 Frames")).toBeInTheDocument();
      expect(screen.getByText("AI Damage Report")).toBeInTheDocument();
      expect(screen.getByText(/scratch · front/i)).toBeInTheDocument();
      expect(screen.getByText("Dashboard candidates")).toBeInTheDocument();
      expect(screen.getByText("29 frames analyzed")).toBeInTheDocument();
    });
  });

  it("renders structured visual damage and modification findings", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      inspection_report: JSON.stringify({
        summary: "Vehicle has visible cosmetic issues.",
        recommendations: ["Inspect bumper paint"],
        gemini_analysis: {
          available: true,
          provider: "openai",
          summary: "Minor visible damage detected.",
          vehicle: { brand: "Toyota", model: "Camry", confidence: 0.9 },
          damage_findings: "Paint damage is visible on the front bumper.",
          damage_items: [
            {
              type: "paint_damage",
              location: "front bumper",
              severity: "moderate",
              confidence: 0.82,
              notes: "Paint scuffing is visible near the lower bumper.",
            },
          ],
          modification_findings: "Wheels appear aftermarket; other parts appear stock.",
          modification_items: [
            {
              part: "wheels",
              status: "modified",
              confidence: 0.76,
              notes: "Non-factory wheel design.",
            },
          ],
          per_frame: [],
        },
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Visible damage items")).toBeInTheDocument();
      expect(screen.getByText("OpenAI Vision")).toBeInTheDocument();
      expect(screen.getByText("front bumper")).toBeInTheDocument();
      expect(screen.getByText("Modification assessment")).toBeInTheDocument();
      expect(screen.getByText("Wheels appear aftermarket; other parts appear stock.")).toBeInTheDocument();
      expect(screen.getByText("modified")).toBeInTheDocument();
    });
  });

  it("renders unavailable visual analysis status", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete, but visual analysis was unavailable.",
        visual_analysis: {
          available: false,
          reason: "Gemini API unavailable: quota, rate limit, or billing cap exceeded",
        },
        gemini_analysis: {
          available: false,
          reason: "Gemini API unavailable: quota, rate limit, or billing cap exceeded",
        },
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("AI Visual Analysis Unavailable")).toBeInTheDocument();
      expect(screen.getByText("Manual review")).toBeInTheDocument();
      expect(
        screen.getByText("Gemini API unavailable: quota, rate limit, or billing cap exceeded"),
      ).toBeInTheDocument();
    });
  });

  it("renders pipeline verification failures from the runtime audit", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete.",
        pipeline_audit: {
          status: "incomplete",
          checks: [
            {
              id: "visual_analysis_available",
              passed: false,
              requirement: "Send organized frames and metadata to a live LLM/VLM analysis path.",
              evidence: {
                reason: "Gemini quota exceeded and OpenAI fallback is not configured.",
              },
            },
            {
              id: "vehicle_identity",
              passed: false,
              requirement: "Determine maker, model, year, trim/version, and vehicle type/category.",
              evidence: {
                brand: "Toyota",
                model: "Sienta",
                year: null,
                variant: null,
                type: "car",
                vehicle_category: "compact minivan",
                year_range: "2022-present",
                variant_candidates: ["Hybrid", "Z", "G", "X"],
                confidence: 0.555,
                threshold: 0.7,
                identity_source: "visual_inference",
                identity_override_fields: [],
                vin_supplied: false,
                registration_supplied: false,
                identity_notes: "Exact year and trim require VLM, VIN, or registration.",
              },
            },
            {
              id: "full_video_temporal_coverage",
              passed: false,
              requirement: "Sample frames across the full uploaded walkaround video duration.",
              evidence: {
                temporal_coverage_ratio: 0.42,
                threshold: 0.9,
              },
            },
            {
              id: "modification_detection",
              passed: false,
              requirement: "Detect stock versus modified parts across multiple visible part categories.",
              evidence: {
                concrete_part_category_count: 1,
                threshold: 3,
              },
            },
          ],
        },
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Pipeline Verification")).toBeInTheDocument();
      expect(screen.getByText("incomplete")).toBeInTheDocument();
      expect(screen.getByText("visual analysis available")).toBeInTheDocument();
      expect(screen.getByText("vehicle identity")).toBeInTheDocument();
      expect(
        screen.getByText("Gemini quota exceeded and OpenAI fallback is not configured."),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Notes: Exact year and trim require VLM, VIN, or registration\./),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Vehicle: Toyota Sienta 2022-present\./),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Type\/category: car \/ compact minivan\./),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Confidence 0.555 is below threshold 0.7\./),
      ).toBeInTheDocument();
      expect(screen.getByText(/Source: visual_inference\./)).toBeInTheDocument();
      expect(screen.getByText(/Override fields: none\./)).toBeInTheDocument();
      expect(
        screen.getByText(/Supplied evidence: VIN no, registration no\./),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Missing exact year and trim\/version; provide VIN or registration to resolve\./),
      ).toBeInTheDocument();
      expect(screen.getByText(/Variant candidates: Hybrid, Z, G, X\./)).toBeInTheDocument();
      expect(screen.getByText("full video temporal coverage")).toBeInTheDocument();
      expect(screen.getByText("Temporal coverage 0.42 (threshold 0.9).")).toBeInTheDocument();
      expect(screen.getByText("modification detection")).toBeInTheDocument();
      expect(screen.getByText("Modification part coverage 1 (threshold 3).")).toBeInTheDocument();
    });
  });

  it("saves verified identity evidence from a failed identity audit", async () => {
    const inspectionWithIdentityFailure = {
      ...mockInspectionData,
      vehicle_info: JSON.stringify({
        brand: "Toyota",
        model: "Sienta",
        type: "car",
        vehicle_category: "compact minivan",
      }),
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete.",
        pipeline_audit: {
          status: "incomplete",
          checks: [
            {
              id: "vehicle_identity",
              passed: false,
              requirement: "Determine maker, model, year, trim/version, and vehicle type/category.",
              evidence: {
                brand: "Toyota",
                model: "Sienta",
                year: null,
                variant: null,
                type: "car",
                vehicle_category: "compact minivan",
                confidence: 0.55,
                threshold: 0.7,
              },
            },
          ],
        },
      }),
    };
    (getInspection as jest.Mock).mockResolvedValue(inspectionWithIdentityFailure);
    (updateInspectionIdentity as jest.Mock).mockResolvedValue({
      ...inspectionWithIdentityFailure,
      vehicle_info: {
        brand: "Toyota",
        model: "Sienta",
        year: "2024",
        variant: "Hybrid Z",
        type: "car",
        vehicle_category: "compact minivan",
        identity_notes: "Exact identity fields merged from manual_review.",
      },
      inspection_report: {
        summary: "Vehicle report complete.",
        vehicle_details: {
          brand: "Toyota",
          model: "Sienta",
          year: "2024",
          variant: "Hybrid Z",
        },
      },
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Verified Identity Evidence")).toBeInTheDocument();
    });
    expect(screen.getByText("Save Evidence")).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Year"), {
      target: { value: "2024" },
    });
    fireEvent.change(screen.getByLabelText("Trim / variant"), {
      target: { value: "Hybrid Z" },
    });
    fireEvent.click(screen.getByText("Save Evidence"));

    await waitFor(() => {
      expect(updateInspectionIdentity).toHaveBeenCalledWith("test-insp-123", {
        vehicle_identity_source: "manual_review",
        vehicle_brand: "",
        vehicle_model: "",
        vehicle_year: "2024",
        vehicle_variant: "Hybrid Z",
        vehicle_type: "",
        vehicle_category: "",
        vin: "",
        registration: "",
      });
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Toyota Sienta 2024 Hybrid Z");
    });
  });

  it("imports external VLM evidence when visual analysis is unavailable", async () => {
    const inspectionWithUnavailableVlm = {
      ...mockInspectionData,
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete.",
        gemini_analysis: {
          available: false,
          reason: "Live provider not configured.",
        },
      }),
    };
    (getInspection as jest.Mock).mockResolvedValue(inspectionWithUnavailableVlm);
    (updateInspectionVlmEvidence as jest.Mock).mockResolvedValue({
      ...inspectionWithUnavailableVlm,
      vehicle_info: {
        brand: "Toyota",
        model: "Sienta",
        year: "2024",
        variant: "Hybrid Z",
      },
      inspection_report: {
        summary: "Vehicle report complete.",
        gemini_analysis: {
          available: true,
          provider: "external",
          vehicle: {
            brand: "Toyota",
            model: "Sienta",
            year: "2024",
            variant: "Hybrid Z",
          },
        },
      },
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("External VLM Evidence")).toBeInTheDocument();
    });
    expect(screen.getByText("Save VLM Evidence")).toBeDisabled();

    fireEvent.change(screen.getByLabelText("VLM result JSON"), {
      target: {
        value: JSON.stringify({
          available: true,
          provider: "external",
          vehicle: {
            brand: "Toyota",
            model: "Sienta",
            year: "2024",
            variant: "Hybrid Z",
          },
        }),
      },
    });
    fireEvent.click(screen.getByText("Save VLM Evidence"));

    await waitFor(() => {
      expect(updateInspectionVlmEvidence).toHaveBeenCalledWith("test-insp-123", {
        available: true,
        provider: "external",
        vehicle: {
          brand: "Toyota",
          model: "Sienta",
          year: "2024",
          variant: "Hybrid Z",
        },
      });
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Toyota Sienta 2024 Hybrid Z");
    });
  });

  it("retries live VLM analysis when visual analysis is unavailable", async () => {
    const inspectionWithUnavailableVlm = {
      ...mockInspectionData,
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete.",
        gemini_analysis: {
          available: false,
          reason: "OpenAI key not configured.",
        },
        frame_analysis: {
          representative_frames: [{ view: "front", frame: "frames/test/front.jpg" }],
        },
      }),
    };
    (getInspection as jest.Mock).mockResolvedValue(inspectionWithUnavailableVlm);
    (retryInspectionVlmAnalysis as jest.Mock).mockResolvedValue({
      ...inspectionWithUnavailableVlm,
      vehicle_info: {
        brand: "Toyota",
        model: "Sienta",
        year: "2024",
        variant: "Hybrid Z",
      },
      inspection_report: {
        summary: "Vehicle report complete.",
        gemini_analysis: {
          available: true,
          provider: "openai",
          vehicle: {
            brand: "Toyota",
            model: "Sienta",
            year: "2024",
            variant: "Hybrid Z",
          },
        },
      },
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Retry VLM Analysis")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Retry VLM Analysis"));

    await waitFor(() => {
      expect(retryInspectionVlmAnalysis).toHaveBeenCalledWith("test-insp-123");
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Toyota Sienta 2024 Hybrid Z");
    });
  });

  it("renders report-level modification assessment", async () => {
    (getInspection as jest.Mock).mockResolvedValue({
      ...mockInspectionData,
      inspection_report: JSON.stringify({
        summary: "Vehicle report complete.",
        recommendations: ["Review wheel fitment"],
        modification_assessment: {
          summary: "Wheels appear aftermarket based on visual analysis.",
          items: [
            {
              part: "wheels",
              status: "modified",
              confidence: 0.76,
              notes: "Non-factory wheel design.",
            },
          ],
        },
      }),
    });

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Modification assessment")).toBeInTheDocument();
      expect(screen.getByText("Wheels appear aftermarket based on visual analysis.")).toBeInTheDocument();
      expect(screen.getByText("wheels: modified")).toBeInTheDocument();
    });
  });

  it("renders error state on API failure", async () => {
    const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    (getInspection as jest.Mock).mockRejectedValue(new Error("Network error"));

    try {
      render(<InspectionPage />);

      await waitFor(() => {
        expect(screen.getByText("Failed to load inspection data")).toBeInTheDocument();
      });
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it("shows not-found state when inspection is null", async () => {
    (getInspection as jest.Mock).mockResolvedValue(null);

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Inspection not found")).toBeInTheDocument();
    });
  });

  it("renders download JSON button when data is loaded", async () => {
    (getInspection as jest.Mock).mockResolvedValue(mockInspectionData);

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Download JSON")).toBeInTheDocument();
    });
  });
});
