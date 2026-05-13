import { render, screen } from "@testing-library/react";
import VehicleInfo from "@/components/VehicleInfo";

describe("VehicleInfo", () => {
  it("renders candidate identity metadata without treating it as exact year or trim", () => {
    render(
      <VehicleInfo
        vehicleInfo={{
          type: "car",
          brand: "Toyota",
          model: "Sienta",
          vehicle_category: "compact minivan",
          year_range: "2022-present",
          generation: "third generation",
          variant_candidates: ["Hybrid", "Z", "G", "X"],
          variant_candidate: "Hybrid",
          variant_confidence: 0.72,
          variant_candidates_ranked: [
            { variant: "Hybrid", confidence: 0.72 },
            { variant: "Z", confidence: 0.21 },
          ],
          confidence: 0.56,
          model_confidence: 0.99,
          model_candidates: [
            { model: "Sienta", confidence: 0.9933 },
            { model: "C-HR", confidence: 0.031 },
          ],
          identity_notes:
            "Model and generation metadata are local candidates; exact year and trim require manual verification.",
        }}
      />,
    );

    expect(screen.getByText("Toyota")).toBeInTheDocument();
    expect(screen.getByText("Sienta")).toBeInTheDocument();
    expect(screen.getByText("Category candidate")).toBeInTheDocument();
    expect(screen.getByText("compact minivan")).toBeInTheDocument();
    expect(screen.getByText("Year range candidate")).toBeInTheDocument();
    expect(screen.getByText("2022-present")).toBeInTheDocument();
    expect(screen.getByText("Generation candidate")).toBeInTheDocument();
    expect(screen.getByText("third generation")).toBeInTheDocument();
    expect(screen.getByText("Variant candidates")).toBeInTheDocument();
    expect(screen.getByText("Hybrid, Z, G, X")).toBeInTheDocument();
    expect(screen.getByText("Top variant candidate")).toBeInTheDocument();
    expect(screen.getByText("Variant candidate confidence")).toBeInTheDocument();
    expect(screen.getByText("Ranked variant candidates")).toBeInTheDocument();
    expect(screen.getAllByText("Hybrid 72%")[0]).toBeInTheDocument();
    expect(screen.getByText("Z 21%")).toBeInTheDocument();
    expect(screen.getByText("Model candidate confidence")).toBeInTheDocument();
    expect(screen.getByText("Sienta 99%")).toBeInTheDocument();
    expect(screen.getByText("C-HR 3%")).toBeInTheDocument();
    expect(screen.getByText(/exact year and trim require manual verification/)).toBeInTheDocument();
  });

  it("renders supplied identity evidence source and verified fields", () => {
    render(
      <VehicleInfo
        vehicleInfo={{
          type: "car",
          brand: "Toyota",
          model: "Sienta",
          year: "2024",
          variant: "Hybrid Z",
          vehicle_category: "compact minivan",
          identity_source: "upload_form",
          identity_override_fields: ["year", "variant", "vin"],
          vin: "JTDBR32E720000001",
          confidence: 0.98,
        }}
      />,
    );

    expect(screen.getByText("Identity source")).toBeInTheDocument();
    expect(screen.getByText("upload form")).toBeInTheDocument();
    expect(screen.getByText("Verified fields")).toBeInTheDocument();
    expect(screen.getByText("year, variant, vin")).toBeInTheDocument();
    expect(screen.getByText("VIN / chassis")).toBeInTheDocument();
    expect(screen.getByText("JTDBR32E720000001")).toBeInTheDocument();
  });
});
