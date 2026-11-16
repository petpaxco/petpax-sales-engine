# PetPax Sales Engine

AI sales development for PetPax Co.: finds grooming salons, scores them, runs compliant outreach, manages the pipeline, and keeps existing retail partners (Active Accounts, Reorders Due) in the same system.

Plan and architecture: *PetPax AI Sales Development Engine — Architecture & Build Plan* (Claude doc).

## Status

Phase 1 (prospecting, CRM, existing accounts) — **in progress**

| Module | State |
| --- | --- |
| Database schema (`supabase/migrations/0001_init.sql`) | Written, tested on Postgres 16 |
| Dedup (`dedup.py`, `normalize.py`) | Done, tested |
| Lead scoring (`scoring.py`) | Done, tested; weights in `config/settings.yaml` |
| Territories / distance from 90008 (`territory.py`) | Done; real drive times come with the Routes API |
| Reorder estimates (`reorder.py`) | Done, tested |
| Retail tracker import (`tracker_import.py`) | Mapping done, tested; live read needs Sheets API credentials |
| Places discovery (`places.py`) | Client done; needs `GOOGLE_MAPS_API_KEY` |
| Website enrichment, Sheets sync, Cloud Run jobs | Next |

**No email is sent by anything in this repo yet.**

## Safety rules enforced in code

- Suppression list (unsubscribe, bounce, complaint, do-not-contact, existing customer) is permanent and checked before any send.
- Only approved templates send; every draft stores why it was written.
- The retail tracker spreadsheet is read-only to this system.
- Enrichment facts must have a source URL or be labeled `inference`.

## Setup

1. Supabase: open the project's **SQL Editor**, paste `supabase/migrations/0001_init.sql`, click **Run**.
2. Copy `.env.example` to `.env` locally (never commit it). Production secrets live in Google Secret Manager.
3. `pip install -e .[dev]` then `pytest`.

## Layout

```
config/settings.yaml        business rules (weights, caps, cycles) — no secrets
supabase/migrations/        database schema
src/petpax_engine/          engine code
tests/                      unit tests (run in CI on every push)
docs/                       approved claims & pricing (pending sign-off)
```
