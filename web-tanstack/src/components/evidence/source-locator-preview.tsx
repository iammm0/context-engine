import { BboxMiniMap } from "@/components/ui/bbox-mini-map"
import type { ChunkPreviewArtifact, OcrImageRef, SourceLocatorAnchor, SourceLocatorSummary, TableSourceRef } from "@/types/api"

const sourceLocatorAnchorTypeLabel: Record<string, string> = {
  page_range: "页码",
  char_range: "字符",
  table: "表格",
  image: "图片",
  section: "章节",
}

function formatPercent(value?: number | null) {
  if (typeof value !== "number") {
    return ""
  }
  const percent = value <= 1 ? value * 100 : value
  return `${Math.round(percent)}%`
}

function formatLocatorValue(value: unknown) {
  if (value === null || value === undefined) {
    return ""
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(", ")
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function formatSourceLocatorAnchor(anchor: SourceLocatorAnchor, index: number) {
  const bits: string[] = []
  const type = anchor.type ? sourceLocatorAnchorTypeLabel[anchor.type] || anchor.type : `锚点 ${index + 1}`
  bits.push(type)
  if (typeof anchor.page_start === "number" && typeof anchor.page_end === "number" && anchor.page_end !== anchor.page_start) {
    bits.push(`第 ${anchor.page_start}-${anchor.page_end} 页`)
  } else if (typeof anchor.page === "number") {
    bits.push(`第 ${anchor.page} 页`)
  } else if (typeof anchor.page_start === "number") {
    bits.push(`第 ${anchor.page_start} 页`)
  }
  if (typeof anchor.char_start === "number" && typeof anchor.char_end === "number") {
    bits.push(`字符 ${anchor.char_start}-${anchor.char_end}`)
  }
  if (typeof anchor.table_index === "number") {
    bits.push(`表格 ${anchor.table_index}`)
  }
  if (typeof anchor.image_index === "number") {
    bits.push(`图片 ${anchor.image_index}`)
  }
  if (typeof anchor.confidence === "number") {
    bits.push(`置信度 ${formatPercent(anchor.confidence)}`)
  }
  if (anchor.low_confidence) {
    bits.push("低置信")
  }
  if (anchor.caption) {
    bits.push(anchor.caption)
  } else if (anchor.title) {
    bits.push(anchor.title)
  }
  if (anchor.source) {
    bits.push(anchor.source)
  }
  if (anchor.target) {
    bits.push(anchor.target)
  }
  if (anchor.text_preview) {
    bits.push(anchor.text_preview)
  }
  return bits.filter(Boolean).join(" · ")
}

function formatTableSourceRef(source: TableSourceRef, index: number) {
  const bits: string[] = []
  if (typeof source.page === "number" && typeof source.page_end === "number" && source.page_end !== source.page) {
    bits.push(`第 ${source.page}-${source.page_end} 页`)
  } else if (typeof source.page === "number") {
    bits.push(`第 ${source.page} 页`)
  }
  if (typeof source.table_index === "number") {
    bits.push(`表格 ${source.table_index}`)
  }
  if (source.caption) {
    bits.push(source.caption)
  } else if (source.title) {
    bits.push(source.title)
  }
  if (source.type) {
    bits.push(source.type)
  }
  if (typeof source.row_count === "number" && typeof source.column_count === "number") {
    bits.push(`${source.row_count}x${source.column_count}`)
  }
  if (source.source) {
    bits.push(source.source)
  }
  if (source.target) {
    bits.push(source.target)
  }
  if (source.bbox) {
    bits.push(`bbox ${formatLocatorValue(source.bbox)}`)
  }
  return bits.join(" · ") || `表格来源 ${index + 1}`
}

function formatOcrImageRef(image: OcrImageRef, index: number) {
  const bits: string[] = []
  if (typeof image.page === "number") {
    bits.push(`第 ${image.page} 页`)
  }
  if (typeof image.image_index === "number") {
    bits.push(`图片 ${image.image_index}`)
  }
  if (typeof image.confidence === "number") {
    bits.push(`置信度 ${formatPercent(image.confidence)}`)
  }
  if (typeof image.line_count === "number") {
    bits.push(`${image.line_count} 行`)
  }
  if (typeof image.width === "number" && typeof image.height === "number") {
    bits.push(`${image.width}x${image.height}`)
  }
  if (typeof image.text_length === "number") {
    bits.push(`${image.text_length} 字`)
  }
  if (image.target) {
    bits.push(image.target)
  }
  if (image.bbox) {
    bits.push(`bbox ${formatLocatorValue(image.bbox)}`)
  }
  if (image.low_confidence) {
    bits.push("低置信")
  }
  if (image.text_preview) {
    bits.push(image.text_preview)
  }
  return bits.join(" · ") || `图片 ${index + 1}`
}

export function SourceLocatorAnchorPreview({
  locator,
  compact = false,
}: {
  locator?: SourceLocatorSummary | null
  compact?: boolean
}) {
  const anchors = (locator?.anchors || []).filter((anchor) => anchor && typeof anchor === "object").slice(0, compact ? 3 : 4)
  if (!anchors.length) {
    return null
  }

  const total = typeof locator?.anchor_count === "number" ? Math.max(locator.anchor_count, anchors.length) : anchors.length
  const remaining = Math.max(total - anchors.length, 0)

  return (
    <div className="mt-2 rounded-lg border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-900">
      <div className="mb-1 font-medium">定位锚点</div>
      <div className="space-y-1">
        {anchors.map((anchor, index) => (
          <div
            className="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1"
            key={`${anchor.type || "anchor"}-${anchor.page ?? anchor.page_start ?? "page"}-${anchor.table_index ?? anchor.image_index ?? index}`}
          >
            <span className="min-w-0 flex-1 break-words">{formatSourceLocatorAnchor(anchor, index)}</span>
            {anchor.bbox ? (
              <BboxMiniMap bbox={anchor.bbox} compact frameHeight={anchor.height} frameWidth={anchor.width} />
            ) : null}
          </div>
        ))}
        {remaining > 0 ? <div className="text-emerald-700">还有 {remaining} 个锚点</div> : null}
      </div>
    </div>
  )
}

function TableSourceLocator({ sources }: { sources: TableSourceRef[] }) {
  if (!sources.length) {
    return null
  }

  return (
    <div className="mt-3 border-t border-sky-100 pt-2 text-xs text-sky-900">
      <div className="mb-1 font-medium">表格来源</div>
      <div className="space-y-1">
        {sources.map((source, index) => (
          <div className="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1" key={`${source.page ?? "page"}-${source.table_index ?? "table"}-${index}`}>
            <span className="shrink-0 rounded bg-white px-1.5 py-0.5 text-sky-700">来源 {index + 1}</span>
            <span className="min-w-0 flex-1 break-words">{formatTableSourceRef(source, index)}</span>
            {source.bbox ? <BboxMiniMap bbox={source.bbox} compact /> : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function OcrSourceLocator({ images }: { images: OcrImageRef[] }) {
  if (!images.length) {
    return null
  }

  return (
    <div className="mt-3 border-t border-amber-100 pt-2 text-xs text-amber-900">
      <div className="mb-1 font-medium">图片来源</div>
      <div className="space-y-1">
        {images.map((image, index) => (
          <div
            className={`flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1 rounded px-2 py-1 ${
              image.low_confidence ? "bg-rose-50 text-rose-800" : "bg-amber-50/70"
            }`}
            key={`${image.page ?? "page"}-${image.image_index ?? "image"}-${index}`}
          >
            <span className="shrink-0 rounded bg-white px-1.5 py-0.5 text-amber-700">
              图片 {typeof image.image_index === "number" ? image.image_index : index + 1}
            </span>
            <span className="min-w-0 flex-1 break-words">{formatOcrImageRef(image, index)}</span>
            {image.bbox ? <BboxMiniMap bbox={image.bbox} compact frameHeight={image.height} frameWidth={image.width} /> : null}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ArtifactSourceLocatorPreview({ artifact }: { artifact?: ChunkPreviewArtifact | null }) {
  if (!artifact) {
    return null
  }

  return (
    <>
      {artifact.sources?.length ? <TableSourceLocator sources={artifact.sources} /> : null}
      {artifact.images?.length ? <OcrSourceLocator images={artifact.images} /> : null}
    </>
  )
}
