"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Menu, X, Car } from "lucide-react"

export function Navbar() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-slate-200 bg-white/80 backdrop-blur-xl">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 shadow-sm">
              <Car className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl font-semibold text-foreground">VIP</span>
          </div>

          <div className="hidden md:flex md:items-center md:gap-8">
            <Link href="#features" className="text-sm font-medium text-slate-700 transition-colors hover:text-blue-600">
              Features
            </Link>
            <Link
              href="#how-it-works"
              className="text-sm font-medium text-slate-700 transition-colors hover:text-purple-600"
            >
              How It Works
            </Link>
            <Link href="#detection" className="text-sm font-medium text-slate-700 transition-colors hover:text-pink-600">
              Detection
            </Link>
            <Link href="#tech" className="text-sm font-medium text-slate-700 transition-colors hover:text-indigo-600">
              Technology
            </Link>
          </div>

          <div className="hidden md:flex md:items-center md:gap-4">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/upload">Log in</Link>
            </Button>
            <Button size="sm" asChild>
              <Link href="/upload">Get Started</Link>
            </Button>
          </div>

          <button className="md:hidden" onClick={() => setIsOpen(!isOpen)} aria-label="Toggle menu">
            {isOpen ? <X className="h-6 w-6 text-foreground" /> : <Menu className="h-6 w-6 text-foreground" />}
          </button>
        </div>

        {isOpen && (
          <div className="border-t border-border py-4 md:hidden">
            <div className="flex flex-col gap-4">
              <Link href="#features" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
                Features
              </Link>
              <Link
                href="#how-it-works"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                How It Works
              </Link>
              <Link href="#detection" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
                Detection
              </Link>
              <Link href="#tech" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
                Technology
              </Link>
              <div className="flex flex-col gap-2 pt-4">
                <Button variant="ghost" size="sm" className="justify-start" asChild>
                  <Link href="/upload">Log in</Link>
                </Button>
                <Button size="sm" asChild>
                  <Link href="/upload">Get Started</Link>
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  )
}
