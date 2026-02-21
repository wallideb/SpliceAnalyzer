# rMATS-Viz

<p align="center">
  <img src="assets/svg/DNA.svg" alt="DNA icon" width="48"/>
  &nbsp;&nbsp;&nbsp;
  <img src="assets/svg/CONNECT.svg" alt="Connect icon" width="48"/>
</p>

A web application for visualizing and exploring RNA alternative splicing events produced by [rMATS](https://rnaseq-mats.sourceforge.io/). Upload your rMATS output files, create analyses, filter events, and curate gene lists through a basket system.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API](#api)
- [Assets](#assets)

---

## Overview

rMATS-Viz provides a browser-based interface on top of rMATS junction-count output files (e.g. `SE.MATS.JC.txt`). Core features:

- **File upload** — drag-and-drop rMATS `.txt` files with automatic sample-group mapping
- **Analysis management** — create, list, and navigate named analyses
- **Event browser** — sortable/filterable table of splicing events (SE, A5SS, A3SS, MXE, RI)
- **Top-10 view** — ranked events by statistical significance or inclusion level difference
- **Basket** — collect and export genes of interest across analyses
- **Dark mode** — toggle-able theme with persistent preference

---

## Architecture

```
┌─────────────────────────────────────────┐
│              Browser (port 3000)         │
│           Next.js 14 / React 18         │
│     TypeScript · Tailwind CSS · TanStack│
└───────────────────┬─────────────────────┘
                    │ REST (JSON)
┌───────────────────▼─────────────────────┐
│              API (port 8000)             │
│           FastAPI 0.111 / Python         │
│        SQLAlchemy async · Pydantic v2    │
└───────────────────┬─────────────────────┘
                    │ asyncpg
┌───────────────────▼─────────────────────┐
│           PostgreSQL 16 (port 5432)      │
│              Docker volume               │
└─────────────────────────────────────────┘
```

All three services are orchestrated with **Docker Compose**.

---

## Project Structure

```
Test_1/
├── assets/
│   └── svg/
│       ├── CONNECT.svg          # Network/connection diagram asset
│       └── DNA.svg              # DNA helix icon asset
├── rmats-viz/
│   ├── backend/                 # FastAPI application
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   └── versions/
│   │   │       ├── 0001_initial_schema.py
│   │   │       └── 0002_add_mutated_genes.py
│   │   └── app/
│   │       ├── main.py          # FastAPI entry point
│   │       ├── config.py
│   │       ├── database.py
│   │       ├── models/          # SQLAlchemy ORM models
│   │       ├── routers/         # API route handlers
│   │       ├── schemas/         # Pydantic request/response schemas
│   │       ├── services/        # Business logic (parser, event selector)
│   │       └── utils/
│   ├── frontend/                # Next.js application
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   ├── tailwind.config.ts
│   │   └── src/
│   │       ├── app/             # Next.js App Router pages
│   │       │   ├── analyses/    # Analysis list, create, detail, top-10
│   │       │   └── layout.tsx
│   │       ├── components/      # React components
│   │       │   ├── basket/
│   │       │   ├── events/
│   │       │   ├── layout/
│   │       │   └── upload/
│   │       ├── contexts/        # React Context (basket, theme)
│   │       ├── lib/             # API client, utilities
│   │       └── types/           # TypeScript type definitions
│   ├── data/                    # Sample rMATS output files
│   │   └── SE.MATS.JC.PUROMOINS.sig.txt
│   └── docker-compose.yml
├── docker-compose.yml           # Root-level compose file (references rmats-viz/)
├── .env.example                 # Environment variable template
└── SE.MATS.JC.PUROMOINS.sig.txt # Sample data (mirrored at root for convenience)
```

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/)

### 1. Clone and configure

```bash
git clone <repo-url>
cd Test_1
cp .env.example .env          # edit credentials if needed
```

### 2. Start all services

```bash
docker compose up --build
```

This will:
1. Start PostgreSQL and wait until healthy
2. Build and start the FastAPI backend — runs Alembic migrations then starts Uvicorn
3. Build and start the Next.js frontend

### 3. Open the app

| Service  | URL                        |
|----------|----------------------------|
| Frontend | http://localhost:3000      |
| API docs | http://localhost:8000/docs |
| Health   | http://localhost:8000/api/v1/health |

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```env
POSTGRES_USER=rmats
POSTGRES_PASSWORD=rmats
POSTGRES_DB=rmatsdb
DATABASE_URL=postgresql+asyncpg://rmats:rmats@db:5432/rmatsdb
CORS_ORIGINS=["http://localhost:3000"]
```

The `docker-compose.yml` at the root uses these variables and falls back to the defaults shown above.

---

## API

The backend exposes a versioned REST API under `/api/v1`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check (DB ping) |
| GET | `/api/v1/analyses` | List all analyses |
| POST | `/api/v1/analyses` | Create a new analysis (file upload) |
| GET | `/api/v1/analyses/{id}` | Get analysis details |
| GET | `/api/v1/analyses/{id}/events` | List events for an analysis |
| GET | `/api/v1/analyses/{id}/top10` | Top-10 events |

Full interactive documentation is available at **http://localhost:8000/docs** (Swagger UI) when the backend is running.

---

## Assets

Visual assets are stored in `assets/svg/`:

| File | Description |
|------|-------------|
| `assets/svg/DNA.svg` | DNA helix icon (36×36, Twemoji-style) used in the loading animation |
| `assets/svg/CONNECT.svg` | Network connection diagram (512×512) representing data connectivity |

The frontend application logo is located at `rmats-viz/frontend/public/logo.svg`.
