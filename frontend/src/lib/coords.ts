export interface Size {
  width: number;
  height: number;
}

export interface Rect extends Size {
  x: number;
  y: number;
}

export interface Point {
  x: number;
  y: number;
}

export type ObjectFit = "contain" | "cover" | "fill";

/**
 * Where the video image actually lands inside its element box, in CSS pixels.
 * With object-fit: contain the image is letterboxed (bars top/bottom or left/right);
 * with cover it overflows and is cropped. Landmarks must be mapped into this
 * rect, not the element box, or the skeleton drifts off the body.
 */
export function mediaRect(box: Size, media: Size, fit: ObjectFit = "contain"): Rect {
  if (box.width <= 0 || box.height <= 0 || media.width <= 0 || media.height <= 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }
  if (fit === "fill") return { x: 0, y: 0, width: box.width, height: box.height };
  const sx = box.width / media.width;
  const sy = box.height / media.height;
  const scale = fit === "contain" ? Math.min(sx, sy) : Math.max(sx, sy);
  const width = media.width * scale;
  const height = media.height * scale;
  return { x: (box.width - width) / 2, y: (box.height - height) / 2, width, height };
}

/** Normalised [0, 1] image coordinates to CSS pixels inside the element box. */
export function toPixel(p: Point, rect: Rect): Point {
  return { x: rect.x + p.x * rect.width, y: rect.y + p.y * rect.height };
}

/** Backing-store size for a crisp canvas on high-DPI screens. */
export function canvasBackingSize(css: Size, devicePixelRatio: number): Size {
  const dpr = Math.max(1, devicePixelRatio || 1);
  return { width: Math.round(css.width * dpr), height: Math.round(css.height * dpr) };
}
