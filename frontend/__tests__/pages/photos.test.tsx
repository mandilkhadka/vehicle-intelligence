import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const push = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: jest.fn() }),
  usePathname: () => "/photos",
}));

jest.mock("@/lib/api", () => ({
  uploadPhotos: jest.fn(),
}));

import PhotosPage from "@/app/photos/page";
import { uploadPhotos } from "@/lib/api";

function makePhoto(name: string, type = "image/jpeg"): File {
  return new File(["photo"], name, { type });
}

function getPhotoInput(): HTMLInputElement {
  // The photos input is the first hidden file input on the page; the
  // odometer input comes after it.
  return document.querySelectorAll('input[type="file"]')[0] as HTMLInputElement;
}

describe("PhotosPage", () => {
  beforeAll(() => {
    let counter = 0;
    Object.defineProperty(global.URL, "createObjectURL", {
      configurable: true,
      value: jest.fn(() => `blob:mock-${counter++}`),
    });
    Object.defineProperty(global.URL, "revokeObjectURL", {
      configurable: true,
      value: jest.fn(),
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    (uploadPhotos as jest.Mock).mockResolvedValue({
      jobId: "job-123",
      fileId: "file-123",
      photoCount: 2,
    });
  });

  it("renders selected photo thumbnails with remove buttons", async () => {
    render(<PhotosPage />);

    fireEvent.change(getPhotoInput(), {
      target: { files: [makePhoto("front.jpg"), makePhoto("rear.png", "image/png"), makePhoto("side.webp", "image/webp")] },
    });

    expect(await screen.findByAltText("front.jpg")).toBeInTheDocument();
    expect(screen.getByAltText("rear.png")).toBeInTheDocument();
    expect(screen.getByAltText("side.webp")).toBeInTheDocument();
    expect(screen.getByText("Selected photos (3/24)")).toBeInTheDocument();
    expect(screen.getByLabelText("Remove front.jpg")).toBeInTheDocument();

    // Removing a photo drops its thumbnail.
    fireEvent.click(screen.getByLabelText("Remove front.jpg"));
    expect(screen.queryByAltText("front.jpg")).not.toBeInTheDocument();
    expect(screen.getByText("Selected photos (2/24)")).toBeInTheDocument();
  });

  it("rejects files with unsupported extensions", async () => {
    render(<PhotosPage />);

    fireEvent.change(getPhotoInput(), {
      target: {
        files: [makePhoto("good.jpg"), makePhoto("bad.heic", "image/heic")],
      },
    });

    expect(
      await screen.findByText(/Unsupported file type: bad\.heic/),
    ).toBeInTheDocument();
    expect(screen.getByAltText("good.jpg")).toBeInTheDocument();
    expect(screen.queryByAltText("bad.heic")).not.toBeInTheDocument();
  });

  it("caps the selection at 24 photos", async () => {
    render(<PhotosPage />);

    const files = Array.from({ length: 25 }, (_, i) => makePhoto(`photo-${i}.jpg`));
    fireEvent.change(getPhotoInput(), { target: { files } });

    expect(
      await screen.findByText(/Maximum 24 photos per inspection/),
    ).toBeInTheDocument();
    expect(screen.getByText("Selected photos (24/24)")).toBeInTheDocument();
    expect(screen.queryByAltText("photo-24.jpg")).not.toBeInTheDocument();
  });

  it("uploads selected photos and navigates to the job page", async () => {
    render(<PhotosPage />);

    fireEvent.change(getPhotoInput(), {
      target: { files: [makePhoto("front.jpg"), makePhoto("rear.jpg")] },
    });

    fireEvent.click(
      await screen.findByRole("button", { name: /Start inspection \(2 photos\)/ }),
    );

    await waitFor(() => expect(push).toHaveBeenCalledWith("/job/job-123"));

    const [files, odometerImage] = (uploadPhotos as jest.Mock).mock.calls[0];
    expect(files).toHaveLength(2);
    expect(files[0].name).toBe("front.jpg");
    expect(odometerImage).toBeNull();
  });

  it("shows the backend error message when the upload fails", async () => {
    (uploadPhotos as jest.Mock).mockRejectedValue(new Error("Disk full"));
    render(<PhotosPage />);

    fireEvent.change(getPhotoInput(), {
      target: { files: [makePhoto("front.jpg")] },
    });

    fireEvent.click(
      await screen.findByRole("button", { name: /Start inspection \(1 photo\)/ }),
    );

    expect(await screen.findByText("Disk full")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
