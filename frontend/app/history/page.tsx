"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import Image from "next/image"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Search,
  Filter,
  Download,
  Eye,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  Loader2,
} from "lucide-react"
import { useSearchParams } from "next/navigation"
import { Suspense } from "react"
import Loading from "./loading"
import { getInspections, BACKEND_BASE_URL } from "@/lib/api"

function getStatusBadge(status: string) {
  switch (status) {
    case "completed":
      return (
        <Badge className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">
          Completed
        </Badge>
      )
    case "processing":
      return (
        <Badge className="bg-primary/10 text-primary hover:bg-primary/20">
          Processing
        </Badge>
      )
    case "failed":
      return (
        <Badge className="bg-destructive/10 text-destructive hover:bg-destructive/20">
          Failed
        </Badge>
      )
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

function getScoreColor(score: number) {
  if (score >= 80) return "text-emerald-500"
  if (score >= 60) return "text-accent"
  if (score > 0) return "text-destructive"
  return "text-muted-foreground"
}

function HistoryPageContent() {
  const [searchQuery, setSearchQuery] = useState("")
  const [inspections, setInspections] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState("all")
  const searchParams = useSearchParams()

  useEffect(() => {
    const fetchInspections = async () => {
      try {
        const data = await getInspections()
        // Transform API data to match component expectations
        const transformed = data.map((insp: any) => {
          const vehicleInfo =
            typeof insp.vehicle_info === "string"
              ? JSON.parse(insp.vehicle_info)
              : insp.vehicle_info || {}
          
          const damage =
            typeof insp.damage_summary === "string"
              ? JSON.parse(insp.damage_summary)
              : insp.damage_summary || {}
          
          const issues =
            (damage.scratches?.count || 0) +
            (damage.dents?.count || 0) +
            (damage.rust?.count || 0)

          const frames =
            typeof insp.extracted_frames === "string"
              ? JSON.parse(insp.extracted_frames)
              : insp.extracted_frames || []

          return {
            id: insp.id,
            vehicle: `${vehicleInfo.year || ""} ${vehicleInfo.brand || insp.vehicle_brand || "Unknown"} ${vehicleInfo.model || insp.vehicle_model || ""}`.trim(),
            brand: vehicleInfo.brand || insp.vehicle_brand || "Unknown",
            date: insp.created_at ? new Date(insp.created_at).toLocaleDateString() : new Date().toLocaleDateString(),
            status: "completed",
            issues,
            score: Math.round((vehicleInfo.confidence || insp.vehicle_confidence || 0)),
            image: frames.length > 0 ? `${BACKEND_BASE_URL}/uploads/${frames[0]}` : null,
          }
        })
        setInspections(transformed)
      } catch (err) {
        console.error("Failed to fetch inspections:", err)
      } finally {
        setLoading(false)
      }
    }

    fetchInspections()
  }, [])

  const filteredInspections = inspections.filter((insp) => {
    const matchesSearch =
      insp.vehicle.toLowerCase().includes(searchQuery.toLowerCase()) ||
      insp.id.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesFilter = filterStatus === "all" || insp.status === filterStatus
    return matchesSearch && matchesFilter
  })

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="p-6">
            <div className="mb-6">
              <h1 className="text-2xl font-bold tracking-tight">
                Inspection History
              </h1>
              <p className="text-muted-foreground">
                View and manage all past vehicle inspections
              </p>
            </div>

            <Card>
              <CardHeader>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <CardTitle>All Inspections</CardTitle>
                    <CardDescription>
                      {loading ? "Loading..." : `${filteredInspections.length} total inspections`}
                    </CardDescription>
                  </div>
                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          placeholder="Search inspections..."
                          className="w-full bg-secondary pl-10 sm:w-64"
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                        />
                      </div>
                      <Select value={filterStatus} onValueChange={setFilterStatus}>
                        <SelectTrigger className="w-32">
                          <Filter className="mr-2 h-4 w-4" />
                          <SelectValue placeholder="Filter" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All</SelectItem>
                          <SelectItem value="completed">Completed</SelectItem>
                          <SelectItem value="processing">Processing</SelectItem>
                          <SelectItem value="failed">Failed</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button variant="outline" size="icon">
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-40">
                            <Button
                              variant="ghost"
                              className="-ml-4 h-8 gap-1 text-xs"
                            >
                              ID
                              <ArrowUpDown className="h-3 w-3" />
                            </Button>
                          </TableHead>
                          <TableHead>Vehicle</TableHead>
                          <TableHead>Date</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="text-center">Issues</TableHead>
                          <TableHead className="text-center">Score</TableHead>
                          <TableHead className="w-20"></TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {loading ? (
                          <TableRow>
                            <TableCell colSpan={7} className="text-center py-8">
                              <Loader2 className="h-6 w-6 animate-spin mx-auto text-primary mb-2" />
                              <p className="text-muted-foreground">Loading inspections...</p>
                            </TableCell>
                          </TableRow>
                        ) : filteredInspections.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                              No inspections found
                            </TableCell>
                          </TableRow>
                        ) : (
                          filteredInspections.map((inspection) => (
                            <TableRow key={inspection.id}>
                              <TableCell className="font-mono text-sm">
                                {inspection.id}
                              </TableCell>
                              <TableCell>
                                <div className="flex items-center gap-3">
                                  {inspection.image ? (
                                    <div className="relative h-10 w-14 overflow-hidden rounded-lg">
                                      <Image
                                        src={inspection.image || "/placeholder.svg"}
                                        alt={inspection.vehicle}
                                        fill
                                        className="object-cover"
                                      />
                                    </div>
                                  ) : (
                                    <div className="flex h-10 w-14 items-center justify-center rounded-lg bg-secondary text-xs font-medium text-muted-foreground">
                                      {inspection.brand.slice(0, 2).toUpperCase()}
                                    </div>
                                  )}
                                  <span className="font-medium">
                                    {inspection.vehicle}
                                  </span>
                                </div>
                              </TableCell>
                              <TableCell className="text-muted-foreground">
                                {inspection.date}
                              </TableCell>
                              <TableCell>
                                {getStatusBadge(inspection.status)}
                              </TableCell>
                              <TableCell className="text-center">
                                {inspection.issues > 0 ? (
                                  <Badge variant="secondary">
                                    {inspection.issues}
                                  </Badge>
                                ) : (
                                  <span className="text-muted-foreground">-</span>
                                )}
                              </TableCell>
                              <TableCell className="text-center">
                                <span
                                  className={`font-semibold ${getScoreColor(inspection.score)}`}
                                >
                                  {inspection.score > 0 ? inspection.score : "-"}
                                </span>
                              </TableCell>
                              <TableCell>
                                <Button variant="ghost" size="icon" asChild>
                                  <Link href={`/inspect/results?id=${inspection.id}`}>
                                    <Eye className="h-4 w-4" />
                                  </Link>
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </div>

                  <div className="mt-4 flex items-center justify-between">
                    <p className="text-sm text-muted-foreground">
                      Showing {filteredInspections.length > 0 ? 1 : 0}-{Math.min(filteredInspections.length, 8)} of {filteredInspections.length} inspections
                    </p>
                    <div className="flex items-center gap-2">
                      <Button variant="outline" size="sm" disabled>
                        <ChevronLeft className="h-4 w-4" />
                        Previous
                      </Button>
                      <Button variant="outline" size="sm" disabled>
                        Next
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </main>
        </div>
      </div>
  )
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<Loading />}>
      <HistoryPageContent />
    </Suspense>
  )
}
