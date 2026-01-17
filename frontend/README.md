# Frontend Application

Next.js frontend for Vehicle Intelligence Platform.

## Setup

```bash
npm install
npm run dev
```

## Environment Variables

Create `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:3001/api
```

## Pages

- `/` - Home page
- `/upload` - Video upload page
- `/job/[id]` - Job status page
- `/inspection/[id]` - Inspection results page

## Components

- `VideoUpload` - Video upload with drag-and-drop
- `JobStatus` - Job processing status display
- `VehicleInfo` - Vehicle information display
- `OdometerInfo` - Odometer reading display
- `DamageInfo` - Damage assessment display
- `ExhaustInfo` - Exhaust classification display

## Features

- Drag-and-drop file upload
- Real-time job status polling
- Responsive design with Tailwind CSS
- JSON report download
