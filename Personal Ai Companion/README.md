# Personal AI Companion

A local-first, privacy-conscious personal companion designed around the architecture specification. It keeps memory in a Markdown vault, routes messages by mode, logs predictions, and supports a Claude-ready response path when an Anthropic API key is configured.

## Features

- Obsidian-friendly vault scaffold
- Daily and person-note memory writes
- Heuristic conversation interpretation with mode routing
- Retrieval logic that ranks by similarity, recency, and entity relevance
- Prediction logging and memory-turn processing
- Optional Claude integration via `ANTHROPIC_API_KEY`
- Local CLI and lightweight HTTP API
- Test coverage for the core workflow

## Quick start

```bash
python -m pip install -e .
personal-ai-companion scaffold --vault ./vault
personal-ai-companion chat --vault ./vault
```

## Browser UI

Start the local server:

```bash
personal-ai-companion serve --vault ./vault --host 0.0.0.0 --port 8000
```

Then open this in Chrome:

```text
http://localhost:8000/
```

The page is a dark, active, local-first companion interface that sends messages to the same companion engine and memory stack described in the architecture document.

## Claude mode

Set an API key and the companion will prefer Anthropic for replies:

```bash
export ANTHROPIC_API_KEY="your-key"
personal-ai-companion chat --vault ./vault
```

If no API key is configured, the app uses a local fallback reply engine so it remains operational offline.

## Commands

- `personal-ai-companion scaffold --vault ./vault`
- `personal-ai-companion chat --vault ./vault`
- `personal-ai-companion recall "what did I say about my sister" --vault ./vault`
- `personal-ai-companion serve --vault ./vault --host 0.0.0.0 --port 8000`

## Package structure

- `src/personal_ai_companion/` — library code
- `tests/` — validation tests

## Notes

This is a working v1 implementation of the architecture direction: it is local-first, privacy-aware, and ready for a Claude-powered back end without depending on the cloud for the memory system itself.
