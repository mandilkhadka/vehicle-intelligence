import { render, screen, waitFor, act } from "@testing-library/react";
import JobStatus from "@/components/JobStatus";

jest.mock("@/lib/api", () => ({
  getJobStatus: jest.fn(),
}));

jest.mock("@/lib/toast", () => ({
  showError: jest.fn(),
  showSuccess: jest.fn(),
}));

jest.mock("@/lib/constants", () => ({
  PROGRESS: {
    THRESHOLDS: {
      UPLOAD_COMPLETE: 10,
      FRAME_EXTRACTION: 25,
      VEHICLE_IDENTIFIED: 40,
      ODOMETER_READ: 55,
      DAMAGE_DETECTED: 75,
      REPORT_GENERATED: 90,
    },
  },
}));

import { getJobStatus } from "@/lib/api";
import { showError } from "@/lib/toast";

describe("JobStatus", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders pending status", async () => {
    (getJobStatus as jest.Mock).mockResolvedValue({
      id: "job-123",
      status: "pending",
      progress: 0,
    });

    render(<JobStatus jobId="job-123" />);

    await waitFor(() => {
      expect(screen.getByText("pending")).toBeInTheDocument();
      expect(screen.getByText("0%")).toBeInTheDocument();
    });
  });

  it("shows processing progress", async () => {
    (getJobStatus as jest.Mock).mockResolvedValue({
      id: "job-123",
      status: "processing",
      progress: 50,
    });

    render(<JobStatus jobId="job-123" />);

    await waitFor(() => {
      expect(screen.getByText("50%")).toBeInTheDocument();
      expect(screen.getByText("processing")).toBeInTheDocument();
    });
  });

  it("shows completed state", async () => {
    (getJobStatus as jest.Mock).mockResolvedValue({
      id: "job-123",
      status: "completed",
      progress: 100,
      inspectionId: "insp-456",
    });

    render(<JobStatus jobId="job-123" />);

    await waitFor(() => {
      expect(screen.getByText(/Complete/)).toBeInTheDocument();
    });
  });

  it("shows failed state with error message", async () => {
    (getJobStatus as jest.Mock).mockResolvedValue({
      id: "job-123",
      status: "failed",
      progress: 30,
      error_message: "Video processing failed",
    });

    render(<JobStatus jobId="job-123" />);

    await waitFor(() => {
      expect(screen.getByText("Video processing failed")).toBeInTheDocument();
    });
  });

  it("surfaces API errors via toast", async () => {
    (getJobStatus as jest.Mock).mockRejectedValue(new Error("Network error"));

    render(<JobStatus jobId="job-123" />);

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith("Failed to fetch job status", expect.anything());
    });
  });

  it("polls status periodically", async () => {
    (getJobStatus as jest.Mock)
      .mockResolvedValueOnce({ id: "job-123", status: "processing", progress: 25 })
      .mockResolvedValue({ id: "job-123", status: "processing", progress: 50 });

    render(<JobStatus jobId="job-123" />);

    await waitFor(() => {
      expect(getJobStatus as jest.Mock).toHaveBeenCalled();
    });

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect((getJobStatus as jest.Mock).mock.calls.length).toBeGreaterThan(1);
    });
  });
});
