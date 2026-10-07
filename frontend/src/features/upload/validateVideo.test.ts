import { describe, expect, it } from "vitest";

import { ACCEPT, checkFile, checkMetadata, MAX_UPLOAD_BYTES } from "./validateVideo";

const file = (name: string, type: string, size = 1000) => ({ name, type, size });

describe("checkFile", () => {
  it("accepts MP4 and MOV by MIME type", () => {
    expect(checkFile(file("a.mp4", "video/mp4"))).toEqual({ ok: true, contentType: "video/mp4" });
    expect(checkFile(file("a.mov", "video/quicktime"))).toEqual({ ok: true, contentType: "video/quicktime" });
  });

  it("falls back to the extension when the browser gives no MIME type", () => {
    expect(checkFile(file("IMG_0042.MOV", ""))).toEqual({ ok: true, contentType: "video/quicktime" });
    expect(checkFile(file("clip.m4v", ""))).toEqual({ ok: true, contentType: "video/mp4" });
  });

  it("rejects other types, empty files and oversized files", () => {
    expect(checkFile(file("serve.flv", "video/x-flv"))).toMatchObject({ ok: false });
    expect(checkFile(file("notes.txt", "text/plain"))).toMatchObject({ ok: false, message: expect.stringContaining("MP4, MOV") });
    expect(checkFile(file("a.mp4", "video/mp4", 0))).toMatchObject({ ok: false, message: "That file is empty." });
    const big = checkFile(file("a.mp4", "video/mp4", MAX_UPLOAD_BYTES + 1));
    expect(big.ok).toBe(false);
    expect(!big.ok && big.message).toMatch(/limit is 200 MB/);
  });
});

describe("checkMetadata", () => {
  it("enforces the duration limit", () => {
    expect(checkMetadata({ durationS: 5, width: 1920, height: 1080 })).toBeNull();
    expect(checkMetadata({ durationS: 15, width: 1920, height: 1080 })).toBeNull();
    expect(checkMetadata({ durationS: 16.2, width: 1920, height: 1080 })).toMatch(/16.2 s long/);
    expect(checkMetadata({ durationS: 0.2, width: 1920, height: 1080 })).toMatch(/too short/);
  });

  it("lets unreadable metadata or unknown durations through for the server to check", () => {
    expect(checkMetadata(null)).toBeNull();
    expect(checkMetadata({ durationS: Infinity, width: 1080, height: 1920 })).toBeNull();
    expect(checkMetadata({ durationS: NaN, width: 1080, height: 1920 })).toBeNull();
  });

  it("rejects files with no video track", () => {
    expect(checkMetadata({ durationS: 5, width: 0, height: 0 })).toMatch(/only audio/);
  });
});

describe("supported formats", () => {
  it.each([
    ["IMG_0001.MOV", "", "video/quicktime"],
    ["serve.mov", "video/quicktime", "video/quicktime"],
    ["serve.mp4", "video/mp4", "video/mp4"],
    ["export.m4v", "video/x-m4v", "video/mp4"],
    ["screen.webm", "video/webm", "video/webm"],
    ["clip.mkv", "", "video/x-matroska"],
    ["old.avi", "video/avi", "video/x-msvideo"],
    ["android.3gp", "video/3gpp", "video/3gpp"],
    ["00001.MTS", "model/vnd.mts", "video/mp2t"],
    ["camcorder.m2ts", "video/vnd.dlna.mpeg-tts", "video/mp2t"],
    ["no-extension", "video/webm", "video/webm"],
  ])("%s (browser says %j) is sent as %s", (name, type, expected) => {
    expect(checkFile(file(name, type))).toEqual({ ok: true, contentType: expected });
  });

  it("lets the picker choose any video and the listed extensions", () => {
    expect(ACCEPT.split(",")).toEqual(expect.arrayContaining(["video/*", ".mov", ".mp4", ".mkv", ".mts"]));
  });
});
