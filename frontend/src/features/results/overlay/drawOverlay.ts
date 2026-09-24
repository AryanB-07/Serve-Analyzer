import type { LandmarkName, MetricName } from "../../../api/types";
import { toPixel, type Rect, type Size } from "../../../lib/coords";
import { SKELETON_EDGES, type AngleLabel, type MarkedStatus, type Pose } from "../../../lib/skeleton";

/**
 * Overlay colours are fixed rather than themed: they sit on video, whose
 * background is the same in light and dark mode.
 */
export const OVERLAY_COLORS = {
  line: "rgba(255, 255, 255, 0.92)",
  outline: "rgba(0, 0, 0, 0.55)",
  good: "#2fbf71",
  borderline: "#f0a92b",
  off: "#f06363",
  labelBg: "rgba(8, 12, 18, 0.78)",
  labelText: "#ffffff",
} as const;

export interface OverlayScene {
  size: Size;
  rect: Rect;
  pose: Pose;
  jointStatus: Partial<Record<LandmarkName, MarkedStatus>>;
  labels: AngleLabel[];
  labelStatus: Partial<Record<MetricName, MarkedStatus>>;
  showSkeleton: boolean;
  showLabels: boolean;
}

/**
 * Status is encoded by shape as well as colour (circle = good,
 * triangle = borderline, diamond = off) so it survives colour blindness.
 */
export function drawStatusMarker(
  ctx: CanvasRenderingContext2D,
  status: MarkedStatus,
  x: number,
  y: number,
  r: number,
): void {
  ctx.beginPath();
  if (status === "good") {
    ctx.arc(x, y, r, 0, Math.PI * 2);
  } else if (status === "borderline") {
    ctx.moveTo(x, y - r * 1.15);
    ctx.lineTo(x + r * 1.1, y + r * 0.8);
    ctx.lineTo(x - r * 1.1, y + r * 0.8);
    ctx.closePath();
  } else {
    ctx.moveTo(x, y - r * 1.2);
    ctx.lineTo(x + r * 1.2, y);
    ctx.lineTo(x, y + r * 1.2);
    ctx.lineTo(x - r * 1.2, y);
    ctx.closePath();
  }
  ctx.fillStyle = OVERLAY_COLORS[status];
  ctx.fill();
  ctx.lineWidth = Math.max(1.5, r * 0.3);
  ctx.strokeStyle = OVERLAY_COLORS.outline;
  ctx.stroke();
}

export function drawOverlay(ctx: CanvasRenderingContext2D, scene: OverlayScene): void {
  const { size, rect, pose } = scene;
  ctx.clearRect(0, 0, size.width, size.height);
  if (rect.width === 0) return;

  const scale = Math.max(0.6, Math.min(rect.width, rect.height) / 480);
  const px = (name: LandmarkName) => {
    const p = pose[name];
    return p ? toPixel(p, rect) : null;
  };

  if (scene.showSkeleton) {
    ctx.lineCap = "round";
    for (const pass of ["outline", "line"] as const) {
      ctx.strokeStyle = OVERLAY_COLORS[pass];
      ctx.lineWidth = (pass === "outline" ? 5 : 2.5) * scale;
      for (const [a, b] of SKELETON_EDGES) {
        const pa = px(a);
        const pb = px(b);
        if (!pa || !pb) continue;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      }
    }
    for (const name of Object.keys(pose) as LandmarkName[]) {
      const p = px(name)!;
      const status = scene.jointStatus[name];
      if (status) {
        drawStatusMarker(ctx, status, p.x, p.y, 6.5 * scale);
      } else {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3.2 * scale, 0, Math.PI * 2);
        ctx.fillStyle = OVERLAY_COLORS.line;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = OVERLAY_COLORS.outline;
        ctx.stroke();
      }
    }
  }

  if (scene.showLabels) {
    const fontSize = Math.max(11, Math.round(12 * scale));
    ctx.font = `600 ${fontSize}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textBaseline = "middle";
    for (const label of scene.labels) {
      const p = px(label.anchor);
      if (!p) continue;
      const status = scene.labelStatus[label.metric];
      const marker = status ? fontSize * 0.9 : 0;
      const padX = 6 * scale;
      const width = ctx.measureText(label.text).width + padX * 2 + marker;
      const height = fontSize + 8 * scale;
      const gap = 10 * scale;
      // Put the pill on whichever side of the joint has room.
      let x = p.x + gap;
      if (x + width > size.width - 4) x = p.x - gap - width;
      const y = Math.min(Math.max(p.y - height / 2, 4), size.height - height - 4);
      ctx.fillStyle = OVERLAY_COLORS.labelBg;
      ctx.beginPath();
      ctx.roundRect(x, y, width, height, height / 2);
      ctx.fill();
      if (status) drawStatusMarker(ctx, status, x + padX + marker / 2 - 1, y + height / 2, fontSize * 0.33);
      ctx.fillStyle = OVERLAY_COLORS.labelText;
      ctx.fillText(label.text, x + padX + marker, y + height / 2 + 0.5);
    }
  }
}
