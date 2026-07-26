# SQLAlchemy → SQLModel Migration Assessment

**Date:** 2026-07-25
**Project:** AutoLaw Phase 1 (Intake + Chronology Builder)
**Assessor:** AO Worker (autolaw-6)

---

## Short Answer

**Feasible but the async question makes the ROI questionable.** You'd get cleaner model definitions but the async plumbing remains nearly identical to what you have now.

| Approach | Effort | Risk | SQLModel benefits realized |
|---|---|---|---|
| Stay async | 8–12 hours | Medium | ~10% (models only; session layer unchanged) |
| Go sync | 6–8 hours | High | ~80% (full SQLModel experience, but changes concurrency model) |
| Hybrid (SQLModel models + keep async session + keep schemas) | 4–6 hours | Low | ~30% (cleaner models, everything else same) |

---

## Current State (Baseline)

The project uses **SQLAlchemy 2.0 async** with:

- **`DeclarativeBase`** — ORM base class
- **`Mapped` / `mapped_column`** — modern 2.0-style column declarations
- **`AsyncSession` / `async_sessionmaker` / `create_async_engine`** — async engine and sessions
- **`select()` / `where()` / `func.count()`** — SQLAlchemy Core-style queries (new 2.0 style)
- **Separate Pydantic schemas** (`schemas/`) for request/response validation — decoupled from models

**10 files** import SQLAlchemy directly:

| File | What it imports | Purpose |
|---|---|---|
| `app/database.py` | `AsyncSession`, `async_sessionmaker`, `create_async_engine`, `DeclarativeBase` | Engine + session + base class |
| `app/models/matter.py` | `DateTime`, `Enum`, `String`, `Text`, `Mapped`, `mapped_column`, `relationship` | Model definition |
| `app/models/document.py` | `DateTime`, `Enum`, `Float`, `ForeignKey`, `Integer`, `String`, `Text`, `Mapped`, `mapped_column`, `relationship` | Model definition |
| `app/models/event.py` | `DateTime`, `Enum`, `Float`, `ForeignKey`, `Integer`, `String`, `Text`, `Mapped`, `mapped_column`, `relationship` | Model definition |
| `app/services/matter.py` | `select`, `func`, `AsyncSession` | Queries |
| `app/services/document.py` | `select`, `func`, `AsyncSession` | Queries |
| `app/services/timeline.py` | `select`, `and_`, `or_`, `func`, `AsyncSession` | Queries |
| `app/routers/matters.py` | `AsyncSession` | Type hint only |
| `app/routers/documents.py` | `AsyncSession` | Type hint only |
| `app/routers/timeline.py` | `AsyncSession` | Type hint only |
| `app/routers/export.py` | `AsyncSession` | Type hint only |

---

## What Would Need to Change

### 1. Models (3 files)

| Aspect | Current (SQLAlchemy) | SQLModel Equivalent | Pain Level |
|---|---|---|---|
| Base class | `DeclarativeBase` | `SQLModel` | Trivial |
| Column types | `Mapped[str] = mapped_column(String(36))` | `str = Field(max_length=36)` | Easy |
| UUID PKs | `default=lambda: str(uuid.uuid4())` | `default_factory=lambda: str(uuid.uuid4())` | Easy |
| ForeignKeys | `ForeignKey("matters.id")` | `foreign_key="matters.id"` | Easy |
| Relationships | `relationship(...)` | `Relationship(...)` | Easy |
| **Enum columns** (3 models, ~6 enums) | `Enum("a","b", name="...")` | **No native SQLModel Enum.** Must use `sa_column=Column(Enum(...))`. | **Medium** — escape hatch needed for every one |
| **`onupdate` on `updated_at`** | `onupdate=lambda: datetime.now(timezone.utc)` | **Not in `Field()`.** Must use `sa_column_kwargs={"onupdate": ...}`. | **Medium** — another escape hatch |
| `index=True` | `index=True` in `mapped_column` | `Field(index=True)` | Easy |
| `default` | `default="active"` | `default="active"` | Easy |

**Net:** Models get slightly cleaner type syntax (`str = Field(...)` instead of `Mapped[str] = mapped_column(...)`), but every `Enum` and `onupdate` requires a raw-SQLAlchemy escape hatch that partly defeats the purpose.

### 2. `database.py` (1 file)

- Replace `DeclarativeBase` with `SQLModel` as base
- Replace `Base.metadata.create_all` with `SQLModel.metadata.create_all`
- All async engine/session setup stays **identical** (SQLModel models are SQLAlchemy models under the hood)

**Effort:** Trivial (10 lines change).

### 3. Schemas (3 files)

**Option A: Delete and merge into models.** SQLModel's headline feature: one class is both ORM model *and* Pydantic schema (`table=True`). You'd eliminate `schemas/matter.py`, `schemas/document.py`, `schemas/event.py`.

**Catch:** You have separate Create/Update/Response schemas with different field subsets. SQLModel handles this via `model_dump(exclude_unset=...)` and techniques like partial model classes, but this requires careful design work — not a mechanical find-and-replace.

**Option B: Keep separate schemas.** You get *zero* benefit from SQLModel's schema merging. The only advantage is slightly prettier model files.

**Effort:** Medium (if merging) or zero (if keeping) — but if you keep them, ask yourself why you're switching.

### 4. Services (3 files) — the async decision

This is the make-or-break question. The answer determines how much service code changes:

| If you... | Query code becomes | Benefit over current |
|---|---|---|
| **Stay async** | `await db.execute(select(Matter).where(...))` + `.scalars().all()` | **None.** You write the exact same queries you do now. SQLModel models are SQLAlchemy models at runtime. |
| **Go sync** | `session.exec(select(Matter).where(...))` + `.all()` | Full SQLModel experience: `session.exec()`, automatic type inference, cleaner iteration |

**Reality check:** If you stay async, SQLModel is **mostly cosmetic** — you get cleaner `Field()` syntax in model files but everything else (queries, sessions, transactions) remains 90% unchanged. The `.scalars()` vs `.all()` pattern difference is a rename, not a simplification.

### 5. Routers (4 files)

Minimal change — update the `AsyncSession` type hint if the session class changes. Routers delegate all DB work to services.

**Effort:** Trivial.

### 6. Tests (1 file)

Change `Base.metadata` → `SQLModel.metadata`. That's it — tests use the HTTP API, never models directly.

**Effort:** 1 line.

### 7. `pyproject.toml`

Add `sqlmodel` dependency. Keep `sqlalchemy` (it's a transitive dependency of sqlmodel anyway). Remove `aiosqlite` if going sync (SQLite's sync driver is built-in).

**Effort:** Trivial.

---

## The Three Migration Paths

### Path A: Stay Async ("Cosmetic Upgrade")

- Convert model files to SQLModel `Field()` syntax
- Keep `AsyncSession`, `create_async_engine`, `async_sessionmaker`
- Keep schemas separate (or optionally merge a few trivial ones)
- Keep all service queries unchanged (`await db.execute(select(...))`)
- Keep routers unchanged

**Files touched:** ~6 (3 models, database.py, pyproject.toml)
**Effort:** 4–6 hours
**Risk:** Low
**What you gain:** Cleaner model definitions (subjective)
**What you lose:** Nothing functional, but you added a dependency for marginal benefit

### Path B: Go Sync ("Full SQLModel")

- Convert models and make them `table=True`
- Replace async engine/session with sync `create_engine` + `Session`
- Rewrite all services to use `session.exec()` and sync patterns
- Rewrite all routers to be sync (or keep async and wrap in `run_in_executor`)
- Merge or restructure schemas
- Remove `aiosqlite`, `greenlet` dependencies

**Files touched:** ~10 (3 models, database.py, 3 services, 3 schema files deleted/merged)
**Effort:** 6–8 hours (spread, not contiguous)
**Risk:** **High** — changing the concurrency model of a working app mid-phase. You lose the benefits of `asyncio` for I/O-bound routes (file uploads, LLM calls, OCR). You'd be trading `async def` for `def` on every endpoint, or adding `run_in_executor` boilerplate.
**What you gain:** Full SQLModel experience
**What you lose:** Async I/O concurrency, clean `async def` endpoints

### Path C: Hybrid (Models Only)

- Convert model files to SQLModel `Field()` syntax with `table=True`
- Keep *everything else* exactly as-is: async sessions, raw SQLAlchemy queries, separate schemas
- Accept that you're using SQLModel as "SQLAlchemy with different model syntax"

**Files touched:** ~4 (3 models, database.py)
**Effort:** 3–5 hours
**Risk:** Very low
**What you gain:** Nicer-looking model files
**What you lose:** Nothing — but you're using SQLModel at its shallowest

---

## Risk Areas

| Risk | Severity | Mitigation |
|---|---|---|
| **Async + SQLModel session incompatibility** | Medium | SQLModel's `Session` is sync. If you accidentally use `session.exec()` in an async handler, it blocks the event loop. Solution: don't use `session.exec()`, keep `await db.execute()`. |
| **Enum breakage on DB migration** | Medium | Changing from `Enum("a","b")` to Python `enum.Enum` with `sa_column` changes the schema. Existing databases with the old Enum type will need a migration. |
| **Time estimate inflation** | Medium | First-time SQLModel migration always hits surprises (nested models, JSON columns, `onupdate`, relationship back-references). Add 50% buffer. |
| **Dependency version conflicts** | Low | SQLModel lags behind SQLAlchemy releases. Check that the latest SQLModel supports your SQLAlchemy version. |
| **Team learning curve** | Low | If only one person knows SQLModel, future contributors need ramp-up. SQLAlchemy is far more widely known. |

---

## Recommendation

**Don't do it right now.** Three reasons:

1. **The async gap is real.** SQLModel was designed for sync. The current codebase correctly uses SQLAlchemy async — the standard pattern for FastAPI. Forcing SQLModel into an async pipeline gives ~10% of the benefit for 80% of the effort.

2. **The current code is already clean.** You're using modern SQLAlchemy 2.0 patterns (`Mapped`, `mapped_column`, `select()`). The Pydantic schemas are decoupled from the DB layer — which is an architectural benefit, not a deficit. Separate schemas make it easy to evolve the API without touching the DB layer, and vice versa.

3. **Enum handling is a downgrade.** You have 6+ Enum columns across 3 models. Your current `Enum("a","b", name="...")` is clean and correct. SQLModel requires a Python `enum.Enum` subclass plus a `sa_column` escape hatch for each one. That's not progress.

**If you still want to explore it**, Path C (Hybrid — models only) is the least risky. It avoids the async decision, keeps your working service code untouched, and gives you a feel for SQLModel's model syntax. You can always deepen the integration later. That path touches ~4 files and takes an afternoon.

---

## Files Referenced in This Assessment

| File | Role in migration |
|---|---|
| `backend/app/database.py` | Engine/session setup — small change |
| `backend/app/models/matter.py` | Model — medium change (Field syntax, Enum workaround) |
| `backend/app/models/document.py` | Model — medium change |
| `backend/app/models/event.py` | Model — medium change |
| `backend/app/schemas/matter.py` | Optional deletion if merging |
| `backend/app/schemas/document.py` | Optional deletion if merging |
| `backend/app/schemas/event.py` | Optional deletion if merging |
| `backend/app/services/matter.py` | Depends on async/sync decision |
| `backend/app/services/document.py` | Depends on async/sync decision |
| `backend/app/services/timeline.py` | Depends on async/sync decision |
| `backend/app/routers/matters.py` | Trivial (type hint) |
| `backend/app/routers/documents.py` | Trivial (type hint) |
| `backend/app/routers/timeline.py` | Trivial (type hint) |
| `backend/app/routers/export.py` | Trivial (type hint) |
| `backend/tests/test_api.py` | Trivial (1 line: `Base` → `SQLModel`) |
| `backend/pyproject.toml` | Add `sqlmodel` dep |
