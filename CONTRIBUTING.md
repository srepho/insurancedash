# Contributing

- Public data only. Never add employer-internal or non-public data.
- New series need a `registry/series.yaml` entry (unique `series_id`, units, frequency, adjustment, definition, basis, breaks).
- Check URLs, IDs and codes against the live source before hardcoding them. Parse by header name and fail clearly if a layout changes.
- Before opening a PR: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- Check the browser-side baseline calculations with `npm test --prefix site`.
