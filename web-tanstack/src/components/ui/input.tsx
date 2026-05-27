import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(({ className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      className={cn(
        "flex h-11 w-full rounded-xl border border-[var(--blue-line)] bg-white px-4 py-2 text-sm text-slate-950 outline-none transition-all",
        "placeholder:text-slate-400 focus-visible:border-sky-400 focus-visible:ring-4 focus-visible:ring-sky-100",
        className,
      )}
      {...props}
    />
  )
})

Input.displayName = "Input"

export { Input }
