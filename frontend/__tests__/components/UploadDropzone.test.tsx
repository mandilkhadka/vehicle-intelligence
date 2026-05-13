import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("@/lib/api", () => ({
  uploadVideo: jest.fn(),
}));

import { UploadDropzone } from "@/components/inspect/upload-dropzone";
import { uploadVideo } from "@/lib/api";

describe("UploadDropzone", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (uploadVideo as jest.Mock).mockResolvedValue({ jobId: "job-123", fileId: "file-123" });
  });

  it("passes optional vehicle identity evidence with the uploaded video", async () => {
    render(<UploadDropzone onFilesUploaded={jest.fn()} />);

    fireEvent.change(screen.getByLabelText("Make"), {
      target: { value: " Toyota " },
    });
    fireEvent.change(screen.getByLabelText("Model"), {
      target: { value: " Sienta " },
    });
    fireEvent.change(screen.getByLabelText("VIN / chassis"), {
      target: { value: " JTDBR32E720000001 " },
    });
    fireEvent.change(screen.getByLabelText("Year"), {
      target: { value: "2024" },
    });
    fireEvent.change(screen.getByLabelText("Trim / variant"), {
      target: { value: "Hybrid Z" },
    });
    fireEvent.change(screen.getByLabelText("Vehicle type"), {
      target: { value: " car " },
    });
    fireEvent.change(screen.getByLabelText("Category"), {
      target: { value: " compact minivan " },
    });

    const file = new File(["video"], "walkaround.mov", { type: "video/quicktime" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(uploadVideo).toHaveBeenCalled());
    expect((uploadVideo as jest.Mock).mock.calls[0][3]).toEqual({
      vehicle_identity_source: "upload_form",
      vehicle_brand: "Toyota",
      vehicle_model: "Sienta",
      vin: "JTDBR32E720000001",
      registration: "",
      vehicle_year: "2024",
      vehicle_variant: "Hybrid Z",
      vehicle_type: "car",
      vehicle_category: "compact minivan",
    });
  });
});
