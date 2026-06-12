"use client";

import Link from "next/link";
import {
  Camera,
  ClipboardCheck,
  History as HistoryIcon,
  Images,
  LayoutDashboard,
  Menu,
  Upload as UploadIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggle } from "@/components/theme-toggle";

export function Header() {
  return (
    <header className="sticky top-0 z-50 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 sm:px-6">
      <div className="flex items-center gap-3">
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
                <UploadIcon className="h-4 w-4" /> New inspection
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/photos" className="flex items-center gap-2">
                <Images className="h-4 w-4" /> Photo inspection
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/capture" className="flex items-center gap-2">
                <Camera className="h-4 w-4" /> Guided capture
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/review" className="flex items-center gap-2">
                <ClipboardCheck className="h-4 w-4" /> Review queue
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/history" className="flex items-center gap-2">
                <HistoryIcon className="h-4 w-4" /> History
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Link
          href="/"
          className="text-sm font-medium tracking-tight text-foreground hover:text-foreground/80"
        >
          Vehicle Intelligence
        </Link>
      </div>

      <ThemeToggle />
    </header>
  );
}
