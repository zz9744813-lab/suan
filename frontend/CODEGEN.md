# OpenAPI Codegen for NovelForge

Auto-generates TypeScript types and SDK from the backend OpenAPI schema.

## Prerequisites

- Backend running at `http://localhost:8000` (or a static `openapi.json` file)
- Dependencies installed: `@hey-api/openapi-ts`, `@hey-api/client-fetch`

## Scripts

| Script | Description |
|--------|-------------|
| `npm run codegen` | Generate from running backend (`openapi-codegen.config.ts`) |
| `npm run codegen:file` | Generate from static `../backend/openapi.json` file |

## Usage

### Generate from running backend

Make sure the backend is running, then:

```bash
cd frontend
npm run codegen
```

### Generate from static schema

First export the schema from the backend:

```bash
cd backend
python -c "from app.main import app; import json; print(json.dumps(app.openapi()))" > openapi.json
```

Then generate:

```bash
cd frontend
npm run codegen:file
```

## Output

Generated files are placed in `src/api/generated/`:

- `index.ts` — Main barrel export (auto-generated)
- `types.gen.ts` — TypeScript type definitions
- `sdk.gen.ts` — API client SDK functions
- `client.gen.ts` — Fetch client configuration
- `core/` — Core utilities
- `client/` — Client utilities

## Importing

```typescript
import { createProject, listProjects } from '@/api/generated';
import type { ProjectRead, ProjectCreate } from '@/api/generated';
```

NOTE: `src/api/generated/index.ts` is auto-generated. Do not edit it manually.
