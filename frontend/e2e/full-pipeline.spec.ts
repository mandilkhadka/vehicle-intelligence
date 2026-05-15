import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

test("uploads bundled walkaround video and renders the 360 inspection report", async ({ page, request }) => {
  test.setTimeout(20 * 60 * 1000);

  await page.goto("/inspect");
  await expect(page.getByRole("heading", { name: "New Inspection" })).toBeVisible();
  await expect(page.getByText("Drop your 360° vehicle video here")).toBeVisible();

  await expect
    .poll(async () => {
      const response = await request.get("http://127.0.0.1:3001/api/jobs/health-check").catch(() => null);
      return response?.ok() || false;
    }, { timeout: 180_000 })
    .toBe(true);
  await expect
    .poll(async () => {
      const response = await request.get("http://127.0.0.1:8000/health").catch(() => null);
      return response?.ok() || false;
    }, { timeout: 180_000 })
    .toBe(true);

  const videoPath = path.resolve(__dirname, "../../360.mov");
  const uploadResponse = await request.post("http://127.0.0.1:3001/api/upload", {
    multipart: {
      video: {
        name: "360.mov",
        mimeType: "video/quicktime",
        buffer: fs.readFileSync(videoPath),
      },
    },
    timeout: 120_000,
  });
  expect(uploadResponse.ok()).toBeTruthy();
  const upload = await uploadResponse.json();
  expect(upload.jobId).toEqual(expect.any(String));

  await page.goto(`/job/${upload.jobId}`);
  await expect(page.getByText(/failed/i)).toHaveCount(0);

  await page.waitForURL(/\/inspection\//, { timeout: 15 * 60 * 1000 });
  await expect(page.getByRole("heading", { name: "Inspection Results" })).toBeVisible();
  await expect(page.getByTestId("inspection-360-viewer")).toBeVisible();
  await expect(page.getByTestId("active-360-image")).toBeVisible();
  await expect(page.getByText("360 Frames")).toBeVisible();

  await expect(page.getByText("Vehicle", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Odometer", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Damage", { exact: true }).last()).toBeVisible();

  const activeImage = page.getByTestId("active-360-image");
  const frameButtons = page.getByRole("button").filter({ has: page.locator("img") });
  const frameCount = await frameButtons.count();
  const srcBefore = await activeImage.getAttribute("src");
  const box = await activeImage.boundingBox();
  if (box && frameCount > 1) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 180, box.y + box.height / 2, { steps: 8 });
    await page.mouse.up();
    if ((await activeImage.getAttribute("src")) === srcBefore) {
      await page.getByRole("button", { name: "Next image" }).click();
    }
    await expect
      .poll(() => activeImage.getAttribute("src"), { timeout: 5_000 })
      .not.toBe(srcBefore);
  }

  const damageRows = page.getByTestId("damage-report-row");
  if ((await damageRows.count()) > 0) {
    await damageRows.first().click();
    await expect(page.getByTestId("active-360-image")).toBeVisible();
  }

  await expect(
    page.getByText(/Summary|Pipeline Verification|AI Visual Analysis/).first(),
  ).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("inspection-360-viewer")).toBeVisible();
  await expect(page.getByText("360 Frames")).toBeVisible();
});
