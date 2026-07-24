---
name: manage-notion-project-records
description: Set up, migrate, and maintain structured Notion project journals using a lightweight index page, one work-record database, an architectural-decision page, and a preserved archive. Use when a project needs durable implementation and validation records, an oversized Notion work log needs restructuring, or repository instructions require significant completed work to be recorded in Notion.
---

# Manage Notion Project Records

Keep project records useful without turning one Notion page into an ever-growing log.

## Resolve the target

1. Read the closest repository instructions before using Notion.
2. Use exact page, database, and data-source IDs when the repository provides them.
3. Verify the target page title and parent before any mutation.
4. Never infer a target from a similar page name.
5. If no project journal is bound, ask before initializing one.
6. Let repository-specific instructions override personal global defaults.

## Choose the operation

- **Record completed work:** Add one structured database item after a significant diagnosis, decision, implementation, validation, environment change, documentation update, or release.
- **Initialize a journal:** Create a lightweight index, work-record database, and architectural-decision page.
- **Migrate a large page:** Preserve the original as an archive and replace it with the structured journal.
- **Record a decision:** Add or update an ADR when a choice will affect future implementation or operation.
- **Inspect:** Read or summarize records without writing.

Read [references/notion-schema.md](references/notion-schema.md) before initializing, migrating, or changing the database schema.

## Record completed work

1. Fetch the current database schema immediately before writing.
2. Query recent records to prevent accidental duplicates.
3. Create one item with an honest status and concise searchable properties.
4. Put detail in the page body using the callout and toggle structure in the reference.
5. Record only material outcomes. Skip simple questions, lookups, and intermediate progress.
6. Verify the created record by reading it back.
7. Update the decision page only for durable architectural or operational decisions.

## Initialize or migrate

1. Fetch the target page and its parent immediately before changes.
2. When migrating, rename the existing large page to `<title> Archive · <cutoff> 이전`.
3. Preserve the archive in place; do not copy, delete, or reconstruct its contents.
4. Create a new page with the original title under the confirmed parent.
5. Add a concise purpose, navigation, operating rules, and links.
6. Create one inline work-record database using the reference schema.
7. Add views for recent work, follow-up work, area grouping, and monthly history.
8. Create an `중요 설계 결정` page and seed `ADR-001` with the journal-structure decision.
9. Store exact Notion identifiers in the repository instructions or designated project config.
10. Verify the new index, database, views, decision page, archive, and stored bindings.

## Safety and failure handling

- Never record API keys, tokens, personal data, or secret environment values.
- Preserve unrelated content and edits.
- Fetch immediately before updates to reduce stale edits.
- Do not delete legacy pages during migration.
- If Notion access or writing fails, report the failure and provide the sanitized pending record so the user can preserve it.
