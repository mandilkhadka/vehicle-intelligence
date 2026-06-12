import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/history",
}));

jest.mock("@/lib/api", () => ({
  getInspections: jest.fn(),
  BACKEND_BASE_URL: "http://localhost:3001",
}));

jest.mock("@/lib/toast", () => ({
  showError: jest.fn(),
  showSuccess: jest.fn(),
}));

import HistoryPage from "@/app/history/page";
import { getInspections } from "@/lib/api";

const mockInspections = [
  {
    id: "insp-001",
    vehicle_brand: "Toyota",
    vehicle_model: "Camry",
    vehicle_year: "2024",
    vehicle_variant: "Hybrid XLE",
    vehicle_confidence: 0.95,
    damage_summary: JSON.stringify({
      scratches: { count: 2 },
      dents: { count: 0 },
      rust: { count: 0 },
    }),
    extracted_frames: JSON.stringify([]),
    created_at: "2024-01-15T10:00:00Z",
    job_status: "completed",
    inspection_report: JSON.stringify({
      pipeline_audit: {
        status: "incomplete",
        passed: false,
        checks: [],
        missing: ["vlm_available", "vehicle_identity"],
      },
    }),
  },
  {
    id: "insp-002",
    vehicle_brand: "Honda",
    vehicle_model: "Civic",
    vehicle_confidence: 0.88,
    damage_summary: JSON.stringify({
      scratches: { count: 0 },
      dents: { count: 1 },
      rust: { count: 0 },
    }),
    extracted_frames: JSON.stringify([]),
    created_at: "2024-01-14T10:00:00Z",
    job_status: "completed",
    inspection_report: JSON.stringify({
      pipeline_audit: {
        status: "complete",
        passed: true,
        checks: [],
        missing: [],
      },
    }),
  },
];

describe("HistoryPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders header and inspection rows", async () => {
    (getInspections as jest.Mock).mockResolvedValue(mockInspections);

    render(<HistoryPage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "History" })).toBeInTheDocument();
      expect(screen.getByText(/2024 Toyota Camry Hybrid XLE/)).toBeInTheDocument();
      expect(screen.getByText(/Honda Civic/)).toBeInTheDocument();
    });
  });

  it("surfaces pipeline verification state in the list", async () => {
    (getInspections as jest.Mock).mockResolvedValue(mockInspections);

    render(<HistoryPage />);

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: "Verification" })).toBeInTheDocument();
      expect(screen.getByText("Needs review")).toBeInTheDocument();
      expect(screen.getByText("2 checks")).toBeInTheDocument();
      expect(screen.getByText("Verified")).toBeInTheDocument();
    });
  });

  it("filters by search query", async () => {
    (getInspections as jest.Mock).mockResolvedValue(mockInspections);

    render(<HistoryPage />);

    await waitFor(() => {
      expect(screen.getByText(/2024 Toyota Camry Hybrid XLE/)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Search inspections..."), {
      target: { value: "Honda" },
    });

    await waitFor(() => {
      expect(screen.getByText(/Honda Civic/)).toBeInTheDocument();
      expect(screen.queryByText(/Toyota Camry/)).not.toBeInTheDocument();
    });
  });

  it("shows empty state when no inspections", async () => {
    (getInspections as jest.Mock).mockResolvedValue([]);

    render(<HistoryPage />);

    await waitFor(() => {
      expect(screen.getByText("No inspections found")).toBeInTheDocument();
    });
  });

  it("shows an error row with retry on API failure instead of a fake empty state", async () => {
    const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    (getInspections as jest.Mock)
      .mockRejectedValueOnce(new Error("Network error"))
      .mockResolvedValueOnce(mockInspections);

    try {
      render(<HistoryPage />);

      await waitFor(() => {
        expect(screen.getByText("Network error")).toBeInTheDocument();
        expect(screen.queryByText("No inspections found")).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: "Retry" }));

      await waitFor(() => {
        expect(screen.getByText(/2024 Toyota Camry Hybrid XLE/)).toBeInTheDocument();
      });
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});
