import type { SourceLocatorSummary } from "@/types/api"

export function formatSourceLocatorSummary(locator?: SourceLocatorSummary | null) {
  if (!locator || !locator.anchor_count) {
    return ""
  }

  const bits: string[] = []
  if (typeof locator.page_start === "number" && typeof locator.page_end === "number" && locator.page_end !== locator.page_start) {
    bits.push(`第 ${locator.page_start}-${locator.page_end} 页`)
  } else if (typeof locator.page_start === "number") {
    bits.push(`第 ${locator.page_start} 页`)
  }
  if (typeof locator.char_start === "number" && typeof locator.char_end === "number") {
    bits.push(`字符 ${locator.char_start}-${locator.char_end}`)
  }
  if (locator.has_table_source) {
    bits.push("表格来源")
  }
  if (locator.has_image_source) {
    bits.push("图片来源")
  }
  if (locator.has_bbox) {
    bits.push("bbox")
  }
  bits.push(`${locator.anchor_count} anchors`)
  return bits.join(" · ")
}
