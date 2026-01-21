"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Car, Gauge, Fuel, Cog, Tag } from "lucide-react"

interface VehicleInfoProps {
  vehicle: {
    brand: string
    model: string
    year: number
    type: string
    odometer: string
    fuelType: string
    transmission: string
    vin: string
    confidence: number
    image?: string
  }
}

export function VehicleInfo({ vehicle }: VehicleInfoProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Car className="h-5 w-5 text-primary" />
            Vehicle Identification
          </CardTitle>
          <Badge variant="outline" className="text-emerald-500 border-emerald-500/30">
            {vehicle.confidence}% confidence
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-4">
          <h3 className="text-2xl font-bold">
            {vehicle.year} {vehicle.brand} {vehicle.model}
          </h3>
          <p className="text-muted-foreground">{vehicle.type}</p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex items-center gap-3 rounded-lg bg-secondary/50 p-3">
            <Gauge className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm text-muted-foreground">Odometer</p>
              <p className="font-semibold">{vehicle.odometer}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg bg-secondary/50 p-3">
            <Fuel className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm text-muted-foreground">Fuel Type</p>
              <p className="font-semibold">{vehicle.fuelType}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg bg-secondary/50 p-3">
            <Cog className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm text-muted-foreground">Transmission</p>
              <p className="font-semibold">{vehicle.transmission}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg bg-secondary/50 p-3">
            <Tag className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm text-muted-foreground">VIN</p>
              <p className="font-mono text-sm font-semibold">{vehicle.vin}</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
