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
    vehicle_confidence: 0.95,
    damage_summary: JSON.stringify({
      scratches: { count: 2 },
      dents: { count: 0 },
      rust: { count: 0 },
    }),
    extracted_frames: JSON.stringify([]),
    created_at: "2024-01-15T10:00:00Z",
    job_status: "completed",
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
      expect(screen.getByText(/Toyota Camry/)).toBeInTheDocument();
      expect(screen.getByText(/Honda Civic/)).toBeInTheDocument();
    });
  });

  it("filters by search query", async () => {
    (getInspections as jest.Mock).mockResolvedValue(mockInspections);

    render(<HistoryPage />);

    await waitFor(() => {
      expect(screen.getByText(/Toyota Camry/)).toBeInTheDocument();
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

  it("handles API error gracefully", async () => {
    (getInspections as jest.Mock).mockRejectedValue(new Error("Network error"));

    render(<HistoryPage />);

    await waitFor(() => {
      expect(screen.getByText("No inspections found")).toBeInTheDocument();
    });
  });
});
