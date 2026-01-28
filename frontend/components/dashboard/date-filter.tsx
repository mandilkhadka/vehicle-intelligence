"use client";

import * as React from "react";
import { format, subDays, startOfDay, endOfDay } from "date-fns";
import { Calendar as CalendarIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

type Preset = "today" | "7days" | "30days" | "all";

interface DateFilterProps {
  startDate: Date;
  endDate: Date;
  onRangeChange: (start: Date, end: Date) => void;
}

const presets: { label: string; value: Preset }[] = [
  { label: "Today", value: "today" },
  { label: "7 Days", value: "7days" },
  { label: "30 Days", value: "30days" },
  { label: "All Time", value: "all" },
];

export function DateFilter({ startDate, endDate, onRangeChange }: DateFilterProps) {
  const [selectedPreset, setSelectedPreset] = React.useState<Preset | null>("30days");
  const [isCalendarOpen, setIsCalendarOpen] = React.useState(false);

  const handlePresetClick = (preset: Preset) => {
    setSelectedPreset(preset);
    const today = new Date();

    switch (preset) {
      case "today":
        onRangeChange(startOfDay(today), endOfDay(today));
        break;
      case "7days":
        onRangeChange(startOfDay(subDays(today, 6)), endOfDay(today));
        break;
      case "30days":
        onRangeChange(startOfDay(subDays(today, 29)), endOfDay(today));
        break;
      case "all":
        // Set to a far past date for "all time"
        onRangeChange(new Date("2020-01-01"), endOfDay(today));
        break;
    }
  };

  const handleDateSelect = (range: { from?: Date; to?: Date } | undefined) => {
    if (range?.from) {
      const from = startOfDay(range.from);
      const to = range.to ? endOfDay(range.to) : endOfDay(range.from);
      setSelectedPreset(null);
      onRangeChange(from, to);
    }
  };

  const formatDateRange = () => {
    if (selectedPreset === "all") {
      return "All Time";
    }
    return `${format(startDate, "MMM d, yyyy")} - ${format(endDate, "MMM d, yyyy")}`;
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Quick preset buttons */}
      <div className="flex gap-1">
        {presets.map((preset) => (
          <Button
            key={preset.value}
            variant={selectedPreset === preset.value ? "default" : "outline"}
            size="sm"
            onClick={() => handlePresetClick(preset.value)}
            className="h-8"
          >
            {preset.label}
          </Button>
        ))}
      </div>

      {/* Custom date picker */}
      <Popover open={isCalendarOpen} onOpenChange={setIsCalendarOpen}>
        <PopoverTrigger asChild>
          <Button
            variant={selectedPreset === null ? "default" : "outline"}
            size="sm"
            className={cn(
              "h-8 justify-start text-left font-normal",
              !selectedPreset && "min-w-[240px]"
            )}
          >
            <CalendarIcon className="mr-2 h-4 w-4" />
            {selectedPreset === null ? formatDateRange() : "Custom"}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="range"
            defaultMonth={startDate}
            selected={{
              from: startDate,
              to: endDate,
            }}
            onSelect={handleDateSelect}
            numberOfMonths={2}
            disabled={(date) => date > new Date()}
          />
        </PopoverContent>
      </Popover>

      {/* Current range display */}
      <span className="text-sm text-muted-foreground hidden sm:inline">
        {formatDateRange()}
      </span>
    </div>
  );
}
