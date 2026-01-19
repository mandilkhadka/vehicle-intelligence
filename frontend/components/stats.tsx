export function Stats() {
  const stats = [
    { value: "<3 min", label: "Processing Time" },
    { value: "94%+", label: "Detection Accuracy" },
    { value: "6", label: "AI Models Working" },
    { value: "360°", label: "Full Coverage" },
  ]

  return (
    <section className="border-y border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 divide-x divide-slate-200 md:grid-cols-4">
          {stats.map((stat, index) => (
            <div key={index} className="px-4 py-8 text-center md:px-8 md:py-12">
              <p className="text-3xl font-bold text-blue-600 md:text-4xl">{stat.value}</p>
              <p className="mt-2 text-sm font-medium text-slate-600">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
