import { render, screen, waitFor } from "@testing-library/react";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useParams: () => ({ id: "test-insp-123" }),
  usePathname: () => "/inspection/test-insp-123",
}));

jest.mock("@/lib/api", () => ({
  getInspection: jest.fn(),
  BACKEND_BASE_URL: "http://localhost:3001",
}));

jest.mock("@/lib/toast", () => ({
  showError: jest.fn(),
  showSuccess: jest.fn(),
}));

jest.mock("@/components/VehicleInfo", () => ({
  __esModule: true,
  default: ({ vehicleInfo }: any) => (
    <div data-testid="vehicle-info">{vehicleInfo.brand} {vehicleInfo.model}</div>
  ),
}));

jest.mock("@/components/OdometerInfo", () => ({
  __esModule: true,
  default: ({ odometer }: any) => <div data-testid="odometer-info">{odometer.value}</div>,
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
import { getInspection } from "@/lib/api";

const mockInspectionData = {
  id: "test-insp-123",
  vehicle_brand: "Toyota",
  vehicle_model: "Camry",
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
      expect(screen.getByTestId("vehicle-info")).toHaveTextContent("Toyota Camry");
      expect(screen.getByTestId("odometer-info")).toHaveTextContent("45,230 km");
      expect(screen.getByTestId("damage-info")).toHaveTextContent("Scratches: 2");
      expect(screen.getByTestId("exhaust-info")).toHaveTextContent("stock");
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

  it("renders error state on API failure", async () => {
    (getInspection as jest.Mock).mockRejectedValue(new Error("Network error"));

    render(<InspectionPage />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load inspection data")).toBeInTheDocument();
    });
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
