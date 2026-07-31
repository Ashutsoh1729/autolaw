# Phase 2 — Group C: Research UI

**Status:** Planned
**Depends on:** Group B's Research API contract (endpoint paths, request/response shapes); does NOT need Group B's code.
**Parallel groups:** Modifies `MatterDetail.tsx` and `App.tsx` (no conflict with Group D, which does not modify these files). Group D later modifies `TimelineView.tsx` (different file).
**Parallelization contract:** Group C depends on the API endpoints defined by Group B. Both groups can work simultaneously if Group C uses the agreed endpoint/response shapes from the Group B plan. Any changes to the API contract after merge must be synced.

---

## Description

Build the frontend research UI: a research tab on the Matter Detail page with a search input (query + filters), a research brief display with expandable citations and source links, status indicators, and regenerate controls. Communicates with Group B's Research API.

## Goals

- Add a "Research" tab to the matter detail page.
- Implement search input with filter controls (court, jurisdiction, year range).
- Display research brief with sections, inline expandable citations, and source links.
- Show relevance scores and confidence indicators on search results.
- Add "Generate Brief" and "Regenerate" buttons.
- Handle all states: loading, empty (no results), generating, complete, error.
- Write component tests for the research UI.

## Workflow

```
User navigates to Matter Detail → clicks "Research" tab
  → [ResearchSearch component] — search input + filters
  → User types query, clicks search
  → GET /api/matters/{id}/research/search returns results preview
  → User clicks "Generate Brief"
  → POST /api/matters/{id}/research/brief → brief status polling
  → [ResearchBrief component] — displays structured brief
  → User expands citations → shows source passage + score
  → User clicks "Regenerate" → new brief generation
```

## Implementation Steps

### Step 1: Create research API hooks

- [ ] Create `frontend/src/hooks/useResearch.ts` with custom hooks:
  - `useResearchSearch(matterId)` — manages search state
    - `search(query, filters?)` → calls `POST /api/matters/{id}/research/search`
    - Returns: `{ results, totalResults, loading, error }`
    - `results` is `SearchResultItem[]` with fields: `chunk_id`, `corpus_document_id`, `text`, `case_name`, `citation`, `court`, `year`, `relevance_score`
  - `useResearchBrief(matterId)` — manages brief state
    - `fetchStatus()` → calls `GET /api/matters/{id}/research/status`
    - `generateBrief(query?)` → calls `POST /api/matters/{id}/research/brief` (optionally with query body)
    - `regenerateBrief(query?)` → calls `POST /api/matters/{id}/research/brief/regenerate`
    - Returns: `{ brief, status, loading, error, generateBrief, regenerateBrief }`
    - `status` is one of: `"not_generated"`, `"generating"`, `"complete"`, `"partial"`, `"no_results"`, `"error"`
  - `searchResultItem` TypeScript interface (shared type):
    ```typescript
    interface SearchResultItem {
      chunk_id: string
      corpus_document_id: string
      text: string
      case_name: string
      citation: string
      court: string
      year: number
      relevance_score: number
    }
    ```
  - `ResearchBrief` TypeScript interface:
    ```typescript
    interface BriefCitation {
      citation: string
      passage: string
      relevance_score: number
      corpus_document_id: string
    }
    interface BriefSection {
      title: string
      content: string
      citations: BriefCitation[]
    }
    interface ResearchBrief {
      id: string
      matter_id: string
      query: string
      created_at: string
      summary: string
      sections: BriefSection[]
      status: "complete" | "partial" | "no_results" | "generating"
    }
    ```
- [ ] Use `apiFetch` from `@/lib/api` for all calls (already handles auth, base URL, error parsing).
- [ ] Add polling: when `status === "generating"`, poll `GET /research/status` every 2s until status changes to `"complete"`, `"partial"`, or `"no_results"`.
- [ ] Write unit tests for the hooks:
  - Mock `apiFetch` with test data
  - Test `search()` returns expected results
  - Test `generateBrief()` transitions through states
  - Test polling loop stops on terminal status
  - Test error handling (API returns 4xx/5xx)

### Step 2: Create ResearchSearch component

- [ ] Create `frontend/src/components/ResearchSearch.tsx`:
  - Search input (text field with search icon, from `lucide-react`)
  - Filter controls (collapsible):
    - Court: dropdown/select (Supreme Court, Circuit Court, District Court, etc.)
    - Jurisdiction: text input or dropdown
    - Year range: two number inputs (from/to)
  - Search button: "Search" with search icon
  - Results area:
    - If loading: spinner (`Loader2`)
    - If error: error card with retry button
    - If empty: "No results found" with suggestion to modify filters
    - If results: list of result cards, each showing:
      - Case name (bold, link-like)
      - Citation + court + year (subtitle)
      - Text snippet (2–3 lines, truncated)
      - Relevance score bar (colored: green >0.7, yellow 0.4–0.7, red <0.4)
    - Clicking a result card expands it to show full passage text
  - Props:
    ```typescript
    interface ResearchSearchProps {
      matterId: string
      onSearchComplete?: (results: SearchResultItem[]) => void
      onGenerateBrief?: (query: string) => void
    }
    ```
- [ ] Use existing UI components: `Input`, `Button`, `Card`, `CardContent`, `Badge`, `Select` from `@/components/ui/`.
- [ ] Search is debounced (300ms) or triggered by button click (button click preferred for legal research — intentional).
- [ ] Write component tests:
  - Render empty state
  - Render loading state
  - Render results list
  - Render error state
  - Filter controls show/hide correctly
  - Clicking result expands/collapses

### Step 3: Create ResearchBrief component

- [ ] Create `frontend/src/components/ResearchBrief.tsx`:
  - Brief status indicator:
    - `"not_generated"`: "No brief generated yet. Search for relevant cases and generate a brief."
    - `"generating"`: animated generation status with spinner + "Analyzing passages..."
    - `"complete"`: full brief display
    - `"partial"`: brief display with a warning banner "Some sections could not be completed"
    - `"no_results"`: "No relevant precedents found for this matter."
  - Brief display (when `status === "complete"` or `"partial"`):
    - Brief metadata: query used, generated date, status badge
    - Summary section (always first): rendered as a highlighted blockquote
    - Each `BriefSection` rendered as a collapsible card:
      - Section title as card header
      - Content rendered as formatted text (support basic markdown: bold, italic, lists)
      - Citations displayed as inline numbered references `[1]`, `[2]`, etc.
      - Clicking a citation number expands an inline citation card showing:
        - Citation text
        - Source passage (the exact text retrieved)
        - Relevance score (colored bar)
        - "View Source" link (opens corpus_document or external URL if available)
    - Copy brief button (copies formatted text to clipboard)
  - "Regenerate" button (always visible when brief exists):
    - Shows confirmation dialog: "Regenerate brief? This will replace the current brief."
    - On confirm: calls `regenerateBrief(query)` with current query
  - Props:
    ```typescript
    interface ResearchBriefProps {
      matterId: string
      brief: ResearchBrief | null
      status: string
      loading: boolean
      error: string | null
      onRegenerate: (query?: string) => void
    }
    ```
- [ ] Use existing UI components: `Card`, `CardContent`, `Button`, `Badge`, `Dialog` (for confirm), `Progress` (for score bar).
- [ ] Handle long content: truncate passage text at 500 chars with "Show more" toggle.
- [ ] Write component tests:
  - Render each status state correctly
  - Render complete brief with sections + citations
  - Expand citation inline card
  - Regenerate confirmation dialog
  - Copy to clipboard (mock `navigator.clipboard`)
  - Truncation toggle

### Step 4: Add Research tab to MatterDetail

- [ ] Modify `frontend/src/pages/MatterDetail.tsx`:
  - Add a tab bar below the matter header (using `@radix-ui/react-tabs` which is already a dependency):
    - "Documents" tab (existing document list — default active)
    - "Research" tab (new — shows ResearchSearch + ResearchBrief)
  - Tab state management: `const [activeTab, setActiveTab] = useState<"documents" | "research">("documents")`
  - Wrap the existing document section content inside the "Documents" tab panel
  - Add the research content inside the "Research" tab panel:
    ```tsx
    <Tabs.Content value="research">
      <div className="space-y-6">
        <ResearchSearch
          matterId={id!}
          onGenerateBrief={(query) => handleGenerateBrief(query)}
        />
        <ResearchBrief
          matterId={id!}
          brief={brief}
          status={briefStatus}
          loading={briefLoading}
          error={briefError}
          onRegenerate={handleRegenerate}
        />
      </div>
    </Tabs.Content>
    ```
  - Wire up `useResearchBrief` hook at the MatterDetail level (or inside the tab content)
- [ ] Add `@radix-ui/react-tabs` if not already imported (it's in `package.json` already as a dependency).
- [ ] Style the tab bar to match the existing design (shadcn/ui pattern — use `TabsList`, `TabsTrigger`, `TabsContent` from a new `@/components/ui/tabs.tsx` if not already created, or inline).
- [ ] Update imports: add `Tabs` components, `ResearchSearch`, `ResearchBrief`, `useResearchBrief`.
- [ ] Ensure the research tab is only shown when the matter has been processed (documents exist and are extracted). Show a disabled Research tab with tooltip if no documents processed.

### Step 5: Add Research route to App.tsx (optional — keep as tab)

- [ ] The research UI lives inside MatterDetail as a tab, so no new route is needed. However, if a standalone research page is desired:
  - Add route: `<Route path="/matters/:id/research" element={<ResearchPage />} />` in `App.tsx`
  - Create `frontend/src/pages/ResearchPage.tsx` as a standalone page with the full research UI (ResearchSearch + ResearchBrief)
  - This is optional — recommend keeping research as a tab for Phase 2 v1
- [ ] **No route change needed for v1** — skip unless explicitly required.

### Step 6: Component tests

- [ ] Create `frontend/src/__tests__/ResearchSearch.test.tsx`:
  - Test renders with matterId prop
  - Test search input updates on typing
  - Test filter controls show/hide
  - Test search results display
  - Test loading spinner appears during search
  - Test error state with retry button
- [ ] Create `frontend/src/__tests__/ResearchBrief.test.tsx`:
  - Test all status states render correctly
  - Test expand/collapse citations
  - Test regenerate button flow
- [ ] Set up test runner if not already present (check if `vitest` or `jest` is configured; the project uses `oxlint` for linting but no test runner visible in `package.json` — add `vitest` as dev dep if needed).
- [ ] Add `vitest` config and run with `npx vitest run`.

---

## Files to Modify

| Action | File | Notes |
|--------|------|-------|
| **Create** | `frontend/src/hooks/useResearch.ts` | Research API hooks (search, brief, status) |
| **Create** | `frontend/src/components/ResearchSearch.tsx` | Search input + filters + results list |
| **Create** | `frontend/src/components/ResearchBrief.tsx` | Brief display with citations |
| **Create** | `frontend/src/__tests__/ResearchSearch.test.tsx` | Component test for ResearchSearch |
| **Create** | `frontend/src/__tests__/ResearchBrief.test.tsx` | Component test for ResearchBrief |
| **Modify** | `frontend/src/pages/MatterDetail.tsx` | Add tab bar with Documents + Research tabs |
| **Modify** | `frontend/src/App.tsx` | Only if adding standalone research route (optional) |

**Consumed from Group B (agreed API contract):**
| Endpoint | Method | Request Body | Response Type |
|----------|--------|-------------|--------------|
| `/api/matters/{id}/research/search` | POST | `{ query, filters?, top_k? }` | `{ results: SearchResultItem[], total_results, query_used }` |
| `/api/matters/{id}/research/brief` | GET | — | `ResearchStatusResponse` |
| `/api/matters/{id}/research/brief` | POST | `{ query? }` | `ResearchBriefResponse` |
| `/api/matters/{id}/research/brief/regenerate` | POST | `{ query? }` | `ResearchBriefResponse` |
| `/api/matters/{id}/research/status` | GET | — | `ResearchStatusResponse` |

## Functional Components

| Component | File | Role |
|-----------|------|------|
| `useResearchSearch` hook | `frontend/src/hooks/useResearch.ts` | Manages search state, calls search API |
| `useResearchBrief` hook | `frontend/src/hooks/useResearch.ts` | Manages brief state, calls brief APIs |
| `ResearchSearch` | `frontend/src/components/ResearchSearch.tsx` | Search input, filters, results display |
| `ResearchBrief` | `frontend/src/components/ResearchBrief.tsx` | Brief display with expandable citations |
| MatterDetail (modified) | `frontend/src/pages/MatterDetail.tsx` | Tab bar with Documents + Research sections |

## Data Model

### TypeScript interfaces (in `useResearch.ts`)

```typescript
interface SearchResultItem {
  chunk_id: string
  corpus_document_id: string
  text: string
  case_name: string
  citation: string
  court: string
  year: number
  relevance_score: number
}

interface BriefCitation {
  citation: string
  passage: string
  relevance_score: number
  corpus_document_id: string
}

interface BriefSection {
  title: string
  content: string
  citations: BriefCitation[]
}

interface ResearchBrief {
  id: string
  matter_id: string
  query: string
  created_at: string
  summary: string
  sections: BriefSection[]
  status: "complete" | "partial" | "no_results" | "generating"
}

interface ResearchStatusResponse {
  brief_id: string | null
  status: "not_generated" | "generating" | "complete" | "partial" | "no_results" | "error"
  brief?: ResearchBrief
}
```

### Component state shapes

```typescript
// ResearchSearch internal state
{
  query: string,
  filters: { court?: string, jurisdiction?: string, yearFrom?: number, yearTo?: number },
  results: SearchResultItem[],
  totalResults: number,
  loading: boolean,
  error: string | null,
  expandedResultId: string | null
}

// ResearchBrief internal state (via useResearchBrief hook)
{
  brief: ResearchBrief | null,
  status: string,
  loading: boolean,
  error: string | null
}
```

## Boundaries

| Boundary | Input | Output |
|----------|-------|--------|
| **useResearchSearch.search()** | `query, filters` | `SearchResultItem[]` from Group B API |
| **useResearchBrief.generateBrief()** | `(optional query)` | `ResearchBrief` from Group B API |
| **useResearchBrief.regenerateBrief()** | `(optional query)` | `ResearchBrief` from Group B API |
| **ResearchSearch → ResearchBrief** | `onGenerateBrief(query)` callback | Triggers brief generation in parent |
| **Brief display → User** | `ResearchBrief` data | Rendering with inline citations, scores |

## Considerations

- **API readiness**: Group C will test against mock API responses first, then switch to real Group B endpoints when Group B merges. Provide a mock mode for standalone development.
- **Tab persistence**: Switching tabs should not reset search/brief state. Keep state in the MatterDetail parent or use a context.
- **Responsive design**: The research tab should work on mobile (stack search + brief vertically).
- **Long passages**: Citation passages can be long. Truncate at 500 chars with "Show more" toggle. Full text is available on expand.
- **Disabled state**: If the matter has no extracted documents yet, show the Research tab as disabled with a tooltip: "Process documents first to enable legal research."
- **No backend changes**: Group C touches zero backend files. All communication is via the REST API contract with Group B.
- **File conflict note**: Group C modifies `MatterDetail.tsx` and `App.tsx`. Group D does not modify these files — D modifies `TimelineView.tsx` (for export checkbox). No file conflicts between C and D.
- **After merge**: Verify all endpoint paths and response shapes match Group B's actual implementation. Run frontend integration tests against real API.
