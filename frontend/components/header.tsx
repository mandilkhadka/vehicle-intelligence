"use client"

import Link from "next/link"
import { Activity, History as HistoryIcon, LayoutDashboard, Menu, Upload as UploadIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ThemeToggle } from "@/components/theme-toggle"

export function Header() {
  return (
    <header className="sticky top-0 z-50 flex h-14 items-center justify-between border-b border-border bg-background/90 px-4 backdrop-blur-md sm:px-6">
      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden">
              <Menu className="h-5 w-5" />
              <span className="sr-only">Open menu</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem asChild>
              <Link href="/" className="flex items-center gap-2">
                <LayoutDashboard className="h-4 w-4" /> Dashboard
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/inspect" className="flex items-center gap-2">
                <UploadIcon className="h-4 w-4" /> New Inspection
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/history" className="flex items-center gap-2">
                <HistoryIcon className="h-4 w-4" /> History
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary shadow-sm">
            <span className="font-mono text-xs font-bold text-primary-foreground">V</span>
          </div>
          <span className="text-base font-semibold tracking-tight">Vehicle IQ</span>
          <span className="hidden text-sm text-muted-foreground lg:inline">
            Vehicle Intelligence Platform
          </span>
        </Link>
      </div>

      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground sm:flex">
          <Activity className="h-3.5 w-3.5 text-emerald-500" />
          Live console
        </div>
        <ThemeToggle />
      </div>
    </header>
  )
}
