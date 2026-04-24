# Memory Schema (LLM-Wiki Pattern)

## Overview

This is a **personal knowledge base** maintained by the AI assistant for the user.
The bot reads/writes markdown files in `workspace/memory/` to persist knowledge across Discord sessions.

## Three Layers

1. **Raw Sources** (read-only)
   - `workspace/sessions/<session_name>/log.txt` — conversation logs
   - User attachments saved in `workspace/files/<session_name>/`

2. **The Wiki** (LLM-managed)
   - `workspace/memory/entities/` — pages about people, projects, tools, servers, etc.
   - `workspace/memory/topics/` — pages about concepts, technologies, themes, workflows
   - `workspace/memory/sources/` — summaries of ingested documents, articles, files
   - Cross-linked with `[[WikiLinks]]` style

3. **The Schema** (this file)
   - Rules and conventions for maintaining the wiki

## Page Format

Every wiki page MUST have YAML frontmatter:

```yaml
---
title: "Page Title"
type: entity | topic | source | overview
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [tag1, tag2]
sources: 0  # number of raw sources that contributed to this page
---
```

Body uses Markdown with `[[WikiLinks]]` for cross-references.

Use lowercase with hyphens for filenames: `my-topic.md`.

## Operations

### Ingest

When the user shares new information, files, or significant context:
1. Discuss key takeaways with the user (if appropriate)
2. Write/update relevant wiki pages under `entities/`, `topics/`, or `sources/`
3. Update cross-references (`[[WikiLinks]]`) between related pages
4. Update `workspace/memory/index.md`
5. Append an entry to `workspace/memory/log.md`

A single conversation might touch 3–10 wiki pages. Prefer updating existing pages over creating duplicates.

### Query

When the user asks a question:
1. Read `workspace/memory/index.md` first to find relevant pages
2. Read relevant pages
3. Synthesize an answer with citations to wiki pages
4. If the answer reveals new insights or connections, file them back into the wiki as new or updated pages

### Lint

Periodically (or when the user asks "記憶を整理して"):
1. Check for contradictions between pages
2. Look for orphan pages with no inbound links
3. Find important concepts mentioned but lacking their own page
4. Note stale claims that newer sources have superseded
5. Suggest missing cross-references
6. Update `index.md` and append to `log.md`

## Special Files

### index.md

Content-oriented catalog. Organized by category. Each entry has a link and one-line summary.

### log.md

Append-only chronological log. Each entry starts with a consistent prefix for parseability.

Format:
```markdown
## [YYYY-MM-DD] ingest | Brief description
What was ingested and what pages were updated.
```

## Conventions

- **Language**: Default to Japanese. Use English only for proper nouns, code, or when the user explicitly switches.
- **One concept per page**: Keep pages focused. Split if a page grows too large.
- **Contradictions**: When new data contradicts old claims, note the contradiction explicitly and update the page. Do not silently overwrite.
- **Citations**: When answering from memory, cite wiki pages like `（参照: [[page-name]]）`.
- **User-centric**: The wiki is about the user's world. Prioritize information relevant to the user's goals, projects, and preferences.
