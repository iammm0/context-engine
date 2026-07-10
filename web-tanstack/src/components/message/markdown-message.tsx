import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type MarkdownMessageProps = {
  content: string
  inverted?: boolean
}

type MarkdownBlock =
  | { type: "paragraph"; text: string }
  | { type: "heading"; depth: number; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; text: string }
  | { type: "code"; language: string; code: string }
  | { type: "table"; headers: string[]; rows: string[][] }

const CODE_FENCE_PATTERN = /^```(\w+)?\s*$/
const HEADING_PATTERN = /^(#{1,4})\s+(.+)$/
const UNORDERED_LIST_PATTERN = /^\s*[-*]\s+(.+)$/
const ORDERED_LIST_PATTERN = /^\s*\d+\.\s+(.+)$/
const QUOTE_PATTERN = /^\s*>\s?(.*)$/
const TABLE_SEPARATOR_PATTERN = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/
const INLINE_PATTERN = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g

function isTableSeparator(line?: string) {
  return Boolean(line && TABLE_SEPARATOR_PATTERN.test(line))
}

function splitTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim())
}

function startsSpecialBlock(line: string, nextLine?: string) {
  return (
    CODE_FENCE_PATTERN.test(line) ||
    HEADING_PATTERN.test(line) ||
    UNORDERED_LIST_PATTERN.test(line) ||
    ORDERED_LIST_PATTERN.test(line) ||
    QUOTE_PATTERN.test(line) ||
    (line.includes("|") && isTableSeparator(nextLine))
  )
}

function parseMarkdownBlocks(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n")
  const blocks: MarkdownBlock[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    const trimmed = line.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    const fence = line.match(CODE_FENCE_PATTERN)
    if (fence) {
      const language = fence[1] || "text"
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !CODE_FENCE_PATTERN.test(lines[index])) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) {
        index += 1
      }
      blocks.push({ type: "code", language, code: codeLines.join("\n") })
      continue
    }

    if (line.includes("|") && isTableSeparator(lines[index + 1])) {
      const headers = splitTableRow(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }
      blocks.push({ type: "table", headers, rows })
      continue
    }

    const heading = line.match(HEADING_PATTERN)
    if (heading) {
      blocks.push({ type: "heading", depth: heading[1].length, text: heading[2].trim() })
      index += 1
      continue
    }

    const unordered = line.match(UNORDERED_LIST_PATTERN)
    const ordered = line.match(ORDERED_LIST_PATTERN)
    if (unordered || ordered) {
      const orderedList = Boolean(ordered)
      const items: string[] = []
      while (index < lines.length) {
        const item = lines[index].match(orderedList ? ORDERED_LIST_PATTERN : UNORDERED_LIST_PATTERN)
        if (!item) {
          break
        }
        items.push(item[1].trim())
        index += 1
      }
      blocks.push({ type: "list", ordered: orderedList, items })
      continue
    }

    const quote = line.match(QUOTE_PATTERN)
    if (quote) {
      const quoteLines: string[] = []
      while (index < lines.length) {
        const quoted = lines[index].match(QUOTE_PATTERN)
        if (!quoted) {
          break
        }
        quoteLines.push(quoted[1])
        index += 1
      }
      blocks.push({ type: "quote", text: quoteLines.join("\n").trim() })
      continue
    }

    const paragraphLines = [line.trim()]
    index += 1
    while (
      index < lines.length &&
      lines[index].trim() &&
      !startsSpecialBlock(lines[index], lines[index + 1])
    ) {
      paragraphLines.push(lines[index].trim())
      index += 1
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join("\n") })
  }

  return blocks.length ? blocks : [{ type: "paragraph", text: content }]
}

function renderInline(text: string, inverted: boolean): ReactNode[] {
  const nodes: ReactNode[] = []
  let lastIndex = 0

  for (const match of text.matchAll(INLINE_PATTERN)) {
    const token = match[0]
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }

    if (token.startsWith("`")) {
      nodes.push(
        <code
          className={cn(
            "rounded px-1.5 py-0.5 font-mono text-[0.85em]",
            inverted ? "bg-white/15 text-white" : "bg-slate-100 text-slate-900",
          )}
          key={`${token}-${match.index}`}
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={`${token}-${match.index}`}>{token.slice(2, -2)}</strong>)
    } else {
      const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/)
      if (link) {
        nodes.push(
          <a
            className={cn("font-medium underline underline-offset-2", inverted ? "text-sky-100" : "text-sky-700")}
            href={link[2]}
            key={`${token}-${match.index}`}
            rel="noreferrer"
            target="_blank"
          >
            {link[1]}
          </a>,
        )
      }
    }

    lastIndex = match.index + token.length
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes
}

export function MarkdownMessage({ content, inverted = false }: MarkdownMessageProps) {
  const blocks = parseMarkdownBlocks(content)

  return (
    <div className={cn("space-y-3 text-sm leading-6", inverted ? "text-white" : "text-slate-800")}>
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const HeadingTag = `h${Math.min(block.depth + 1, 4)}` as "h2" | "h3" | "h4"
          return (
            <HeadingTag className="font-semibold text-current" key={`heading-${index}`}>
              {renderInline(block.text, inverted)}
            </HeadingTag>
          )
        }

        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul"
          return (
            <ListTag
              className={cn("space-y-1 pl-5", block.ordered ? "list-decimal" : "list-disc")}
              key={`list-${index}`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{renderInline(item, inverted)}</li>
              ))}
            </ListTag>
          )
        }

        if (block.type === "quote") {
          return (
            <blockquote
              className={cn(
                "border-l-2 pl-3 italic",
                inverted ? "border-white/40 text-sky-50" : "border-sky-200 text-slate-600",
              )}
              key={`quote-${index}`}
            >
              {block.text.split("\n").map((line, lineIndex) => (
                <p key={`${line}-${lineIndex}`}>{renderInline(line, inverted)}</p>
              ))}
            </blockquote>
          )
        }

        if (block.type === "code") {
          return (
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-950" key={`code-${index}`}>
              <div className="border-b border-white/10 px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] text-slate-400">
                {block.language}
              </div>
              <pre className="overflow-x-auto px-3 py-2 text-xs leading-5 text-slate-100">
                <code>{block.code}</code>
              </pre>
            </div>
          )
        }

        if (block.type === "table") {
          return (
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white" key={`table-${index}`}>
              <table className="min-w-full border-collapse text-xs text-slate-700">
                <thead className="bg-slate-50 text-slate-900">
                  <tr>
                    {block.headers.map((header, headerIndex) => (
                      <th className="border-b border-slate-200 px-3 py-2 text-left font-semibold" key={headerIndex}>
                        {renderInline(header, false)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowIndex) => (
                    <tr className="border-b border-slate-100 last:border-0" key={rowIndex}>
                      {block.headers.map((_, cellIndex) => (
                        <td className="px-3 py-2 align-top" key={cellIndex}>
                          {renderInline(row[cellIndex] || "", false)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }

        return (
          <p className="whitespace-pre-wrap" key={`paragraph-${index}`}>
            {renderInline(block.text, inverted)}
          </p>
        )
      })}
    </div>
  )
}
