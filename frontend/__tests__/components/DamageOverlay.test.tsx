import { render, screen, fireEvent } from "@testing-library/react";
import DamageInfo from "@/components/DamageInfo";
import DamageOverlayViewer from "@/components/DamageOverlayViewer";

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ fill, unoptimized, ...props }: any) => <img {...props} />,
}));

jest.mock("@/lib/api", () => ({
  BACKEND_BASE_URL: "http://localhost:3001",
  listDamageFeedback: jest.fn().mockResolvedValue([]),
  submitDamageFeedback: jest.fn(),
}));

const detectorLocation = {
  type: "scratch",
  part: "front_bumper",
  part_label: "Front bumper",
  confidence: 0.91,
  severity: "medium",
  frame: "frames/insp-1/front.jpg",
  snapshot: "frames/insp-1/damage_snapshots/detector_scratch_001.jpg",
  bbox: [100, 200, 300, 260] as [number, number, number, number],
  mask: [
    [0.1, 0.3],
    [0.23, 0.3],
    [0.23, 0.36],
    [0.1, 0.36],
  ] as Array<[number, number]>,
  frame_width: 1280,
  frame_height: 720,
  source: "detector",
};

const damage = {
  scratches: { count: 1, detected: true },
  severity: "medium",
  locations: [detectorLocation],
};

describe("DamageInfo overlay integration", () => {
  it("opens the full-frame overlay viewer from a damage card", () => {
    render(<DamageInfo damage={damage} />);

    // Expand the part group, then open the viewer from the card.
    fireEvent.click(screen.getByRole("button", { name: /front bumper/i }));
    fireEvent.click(screen.getByRole("button", { name: /view damage location on full frame/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByAltText(/full frame with scratch highlighted/i)).toHaveAttribute(
      "src",
      "http://localhost:3001/uploads/frames/insp-1/front.jpg",
    );

    // Closes again.
    fireEvent.click(screen.getByRole("button", { name: /close viewer/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not offer the viewer when a location has no bbox", () => {
    render(
      <DamageInfo
        damage={{
          ...damage,
          locations: [{ ...detectorLocation, bbox: undefined, mask: undefined }],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /front bumper/i }));
    expect(
      screen.queryByRole("button", { name: /view damage location on full frame/i }),
    ).not.toBeInTheDocument();
  });
});

describe("DamageOverlayViewer", () => {
  it("renders bbox rect, mask polygon, and zoom controls", () => {
    const { container } = render(
      <DamageOverlayViewer
        location={detectorLocation}
        frameSrc="http://localhost:3001/uploads/frames/insp-1/front.jpg"
        onClose={jest.fn()}
      />,
    );

    const rect = container.querySelector("svg rect");
    expect(rect).toHaveAttribute("x", "100");
    expect(rect).toHaveAttribute("y", "200");
    expect(rect).toHaveAttribute("width", "200");
    expect(rect).toHaveAttribute("height", "60");

    const polygon = container.querySelector("svg polygon");
    expect(polygon).toHaveAttribute("points", "128.0,216.0 294.4,216.0 294.4,259.2 128.0,259.2");

    expect(screen.getByText("91%")).toBeInTheDocument();
    expect(screen.getByText("scratch")).toBeInTheDocument();
    expect(screen.getByText("damage model")).toBeInTheDocument();

    // Zoom in twice: 1.0x -> 2.0x
    const zoomIn = screen.getByRole("button", { name: /zoom in/i });
    fireEvent.click(zoomIn);
    fireEvent.click(zoomIn);
    expect(screen.getByText("2.0x")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /reset zoom/i }));
    expect(screen.getByText("1.0x")).toBeInTheDocument();
  });

  it("closes on Escape", () => {
    const onClose = jest.fn();
    render(
      <DamageOverlayViewer location={detectorLocation} frameSrc="/frame.jpg" onClose={onClose} />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
