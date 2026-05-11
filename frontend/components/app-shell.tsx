"use client"

import type { ReactNode } from "react"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { cn } from "@/lib/utils"

interface AppShellProps {
  children: ReactNode
  className?: string
}

export function AppShell({ children, className }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className={cn("min-w-0 flex-1 overflow-auto", className)}>
          {children}
        </main>
      </div>
    </div>
  )
}
