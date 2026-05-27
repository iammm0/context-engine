import type { HTMLAttributes } from "react"

import { cn } from "@/lib/utils"

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[var(--blue-line)] bg-[var(--surface-blue)] px-3 py-1 text-xs font-medium text-sky-900",
        className,
      )}
      {...props}
    />
  )
}
