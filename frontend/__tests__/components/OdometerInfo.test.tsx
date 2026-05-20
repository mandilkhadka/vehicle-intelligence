import { render, screen } from "@testing-library/react";
import OdometerInfo from "@/components/OdometerInfo";

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ fill, unoptimized, ...props }: any) => <img {...props} />,
}));

jest.mock("@/lib/api", () => ({
  BACKEND_BASE_URL: "http://localhost:3001",
}));

describe("OdometerInfo", () => {
  it("marks low-confidence readings as candidates and shows alternatives", () => {
    render(
      <OdometerInfo
        odometer={{
          value: 112028,
          confidence: 0.42,
          speedometer_image_path: null,
          reason: "Local OCR produced only low-confidence or conflicting odometer candidates; manual/VLM verification is required",
          alternatives: [
            { value: 45472, confidence: 0.42, occurrences: 1 },
            { value: 9230, confidence: 0.31, occurrences: 1 },
          ],
        }}
      />,
    );

    expect(screen.getByText("112,028 km")).toBeInTheDocument();
    expect(screen.getByText("Candidate")).toBeInTheDocument();
    expect(screen.getByText(/manual\/VLM verification is required/)).toBeInTheDocument();
    expect(screen.getByText("Alternative OCR candidates")).toBeInTheDocument();
    expect(screen.getByText("45,472 km")).toBeInTheDocument();
    expect(screen.getByText("9,230 km")).toBeInTheDocument();
  });

  it("prefers the tight odometer readout crop over broader dashboard images", () => {
    render(
      <OdometerInfo
        odometer={{
          value: 12292,
          confidence: 0.76,
          speedometer_image_path: "frames/test/organized/dashboard.jpg",
          crop_path: "frames/test/organized/dashboard_crop.jpg",
          readout_crop_path: "frames/test/organized/dashboard_readout.jpg",
        }}
      />,
    );

    expect(screen.getByText("12,292 km")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByAltText("Odometer readout")).toHaveAttribute(
      "src",
      expect.stringContaining("dashboard_readout.jpg"),
    );
  });
});
