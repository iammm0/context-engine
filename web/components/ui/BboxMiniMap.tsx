"use client";

type BboxMiniMapProps = {
  bbox?: unknown;
  frameWidth?: number | null;
  frameHeight?: number | null;
  compact?: boolean;
  className?: string;
};

type ParsedBbox = {
  left: number;
  top: number;
  width: number;
  height: number;
};

function finiteNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numbersFromBbox(bbox: unknown): number[] | null {
  if (Array.isArray(bbox)) {
    const values = bbox.slice(0, 4).map(finiteNumber);
    return values.every((value) => value !== null) ? (values as number[]) : null;
  }

  if (!bbox || typeof bbox !== "object") return null;
  const item = bbox as Record<string, unknown>;

  const x1 = finiteNumber(item.x1 ?? item.left);
  const y1 = finiteNumber(item.y1 ?? item.top);
  const x2 = finiteNumber(item.x2 ?? item.right);
  const y2 = finiteNumber(item.y2 ?? item.bottom);
  if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
    return [x1, y1, x2, y2];
  }

  const x = finiteNumber(item.x ?? item.left);
  const y = finiteNumber(item.y ?? item.top);
  const width = finiteNumber(item.width ?? item.w);
  const height = finiteNumber(item.height ?? item.h);
  if (x !== null && y !== null && width !== null && height !== null) {
    return [x, y, x + width, y + height];
  }

  return null;
}

function parseBbox(bbox: unknown, frameWidth?: number | null, frameHeight?: number | null): ParsedBbox | null {
  const values = numbersFromBbox(bbox);
  if (!values) return null;

  let [x1, y1, x2, y2] = values;
  if (x2 < x1) [x1, x2] = [x2, x1];
  if (y2 < y1) [y1, y2] = [y2, y1];

  const boxWidth = Math.max(x2 - x1, 0);
  const boxHeight = Math.max(y2 - y1, 0);
  if (!boxWidth || !boxHeight) return null;

  const allNormalized = values.every((value) => value >= 0 && value <= 1);
  const viewportWidth = allNormalized ? 1 : frameWidth && frameWidth > 0 ? frameWidth : Math.max(x2, boxWidth) * 1.08;
  const viewportHeight = allNormalized ? 1 : frameHeight && frameHeight > 0 ? frameHeight : Math.max(y2, boxHeight) * 1.08;
  if (!viewportWidth || !viewportHeight) return null;

  const left = Math.max(0, Math.min(96, (x1 / viewportWidth) * 100));
  const top = Math.max(0, Math.min(96, (y1 / viewportHeight) * 100));
  const width = Math.max(4, Math.min(100 - left, (boxWidth / viewportWidth) * 100));
  const height = Math.max(4, Math.min(100 - top, (boxHeight / viewportHeight) * 100));

  return { left, top, width, height };
}

export default function BboxMiniMap({ bbox, frameWidth, frameHeight, compact = false, className = "" }: BboxMiniMapProps) {
  const parsed = parseBbox(bbox, frameWidth, frameHeight);
  if (!parsed) return null;
  const sizeClass = compact ? "h-14 w-20" : "h-16 w-24";

  return (
    <div
      className={`relative ${sizeClass} shrink-0 overflow-hidden rounded border border-dashed border-gray-300 bg-white dark:border-gray-700 dark:bg-gray-950 ${className}`}
      title="bbox示意"
      aria-label="bbox示意"
    >
      <div className="absolute inset-1 rounded border border-gray-200 dark:border-gray-800" />
      <div
        className="absolute rounded-sm border border-blue-600 bg-blue-500/20 shadow-sm dark:border-blue-300 dark:bg-blue-300/20"
        style={{
          left: `${parsed.left}%`,
          top: `${parsed.top}%`,
          width: `${parsed.width}%`,
          height: `${parsed.height}%`,
        }}
      />
      <div className="absolute bottom-0 left-0 right-0 bg-white/80 px-1 py-0.5 text-[9px] leading-none text-gray-500 dark:bg-gray-950/80 dark:text-gray-400">
        bbox示意
      </div>
    </div>
  );
}
