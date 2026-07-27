# Phase 1 — CreateMatter Simplify: Remove File Upload

**Status:** Done
**Depends on:** Nothing (self-contained frontend change)

---

## Why

The `CreateMatter` page currently includes a `DropZone` + file upload flow, but documents are uploaded separately on the `MatterDetail` page (via the same `DropZone`). This duplication confuses users and adds unnecessary complexity to the creation flow. Keeping creation fast (metadata only) is better UX.

## What

Remove all file-upload related code from `frontend/src/pages/CreateMatter.tsx`:

- Remove `DropZone` import, `FileEntry` type, `UploadProgressBar` import
- Remove `useUpload` import and its usage
- Remove `files` state (`useState<FileEntry[]>`)
- Remove `handleFilesSelected` and `handleRemoveFile` callbacks
- Simplify `handleSubmit` to only create matter and navigate (no `uploadFiles` call)
- Remove the Documents section (the `<DropZone>` and `<UploadProgressBar>` JSX)
- Update `CardDescription` text to remove document mention

Also update `docs/workflows.md` to reflect that CreateMatter is metadata-only.

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/pages/CreateMatter.tsx` | Remove upload logic |
| `docs/workflows.md` | Update CreateMatter description |

## Not Changing

- `MatterDetail.tsx` — still has upload via DropZone (that's the correct place)
- `DropZone.tsx`, `useUpload.ts`, `UploadProgressBar` — still used by MatterDetail
- Backend — no API changes
