import { afterEach, describe, expect, it, vi } from "vitest";

import { AvatarFileError, prepareAvatar } from "./avatar";

afterEach(() => vi.unstubAllGlobals());

describe("preparing a profile picture", () => {
  it("refuses files that aren't pictures, or are huge, before opening them", async () => {
    const open = vi.fn();
    vi.stubGlobal("createImageBitmap", open);
    await expect(prepareAvatar(new File(["x"], "serve.mp4", { type: "video/mp4" }))).rejects.toThrow("Choose a picture");
    const huge = new File(["x"], "big.jpg", { type: "image/jpeg" });
    Object.defineProperty(huge, "size", { value: 26 * 1024 * 1024 });
    await expect(prepareAvatar(huge)).rejects.toThrow("over 25 MB");
    expect(open).not.toHaveBeenCalled();
  });

  it("explains a picture the browser can't open (HEIC in some browsers)", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("unsupported")));
    const error = await prepareAvatar(new File(["x"], "me.heic", { type: "image/heic" })).catch((e) => e);
    expect(error).toBeInstanceOf(AvatarFileError);
    expect(error.message).toContain("Try a JPEG or PNG");
  });

  it("refuses a tiny picture", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 40, height: 60, close: vi.fn() }));
    await expect(prepareAvatar(new File(["x"], "tiny.png", { type: "image/png" }))).rejects.toThrow("at least 64 pixels");
  });

  it("crops the centre square and shrinks it to 512 px", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 2000, height: 1000, close: vi.fn() }));
    const drawImage = vi.fn();
    const canvas = {
      width: 0, height: 0,
      getContext: () => ({ drawImage, imageSmoothingQuality: "low" }),
      toBlob: (done: (b: Blob) => void, type: string) => done(new Blob(["jpeg"], { type })),
    };
    const create = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) =>
      (tag === "canvas" ? (canvas as unknown as HTMLCanvasElement) : create(tag)));
    const blob = await prepareAvatar(new File(["x"], "wide.jpg", { type: "image/jpeg" }));
    expect(blob.type).toBe("image/jpeg");
    expect([canvas.width, canvas.height]).toEqual([512, 512]);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 500, 0, 1000, 1000, 0, 0, 512, 512);
  });
});
