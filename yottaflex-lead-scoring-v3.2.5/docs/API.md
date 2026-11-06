# API Documentation

Base URL: `http://127.0.0.1:8000/api/v1`  
Interactive docs: `/docs` (OpenAPI/Swagger)  
Auth: none (local MVP — see KNOWN_LIMITATIONS).

## Health & meta

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/meta/seed` | seed, counts, scoring weights, thresholds |

## Pipeline

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/pipeline/run-all` | `{"inject_anomalies": bool, "mini": bool}` | Run full A→L pipeline |

## Resources

| Method | Path | Query params |
|--------|------|--------------|
| GET | `/leads` | category, status, territory, score_min, limit, offset |
| GET | `/leads/{id}` | — (includes score explanation) |
| GET | `/opportunities` | stage, salesrep_id, limit, offset |
| GET | `/opportunities/{id}/history` | — (append-only StageHistory) |
| GET | `/tasks` | status, salesrep_id, limit, offset |
| GET | `/sales-reps` | — |
| GET | `/exceptions` | issue_type, severity, resolution_status, limit, offset |
| PATCH | `/exceptions/{id}` | `{"resolution_status": "open\|investigating\|resolved\|false_positive\|wont_fix"}` |
| GET | `/metrics/summary` | all core KPIs + funnel + exception evaluation |
| GET | `/metrics/funnel` | conversion funnel series |
| GET | `/score-rules` | active scoring rules |

## Conventions

- JSON only; timestamps ISO-8601 naive UTC.
- Pagination via `limit` (max 500) and `offset`.
- Errors: FastAPI default `{"detail": "..."}` with 404/422.

## Example

```bash
curl http://127.0.0.1:8000/api/v1/metrics/summary
curl "http://127.0.0.1:8000/api/v1/leads?category=hot&score_min=80&limit=10"
curl -X PATCH http://127.0.0.1:8000/api/v1/exceptions/1 \
  -H "Content-Type: application/json" \
  -d '{"resolution_status":"resolved"}'
```
