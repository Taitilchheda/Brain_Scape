# BrainScape Next.js Frontend

This is a Next.js wrapper around the existing Brain_Scape clinical console UI.

## Why this exists

- Keeps the current UI and behavior intact (same HTML/CSS/JS logic)
- Moves delivery to Next.js for easier frontend iteration and scaling
- Lets us gradually refactor legacy module code into React components over time

## Run

```bash
cd frontend-next
npm install
npm run dev
```

Open: `http://127.0.0.1:3000`

## Backend API base

By default, the UI calls:

- `http://127.0.0.1:8000`

Override with environment variable:

```bash
# PowerShell
$env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000"
npm run dev
```

## Notes

- Legacy UI assets are in `public/legacy/`:
  - `brainscape.css`
  - `brainscape-body.html`
  - `three-importmap.json`
  - `brainscape-app.js`
- Page wiring is in `app/page.tsx`
- This is a compatibility layer; behavior should match the current static UI.
