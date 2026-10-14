# P0-05b reviewed synthetic analysis cases

These are deliberately constructed contract cases, not historical user incidents.

- `output_mismatch.json`: `lookup` declares integer `count` but returns a string.
- `passing.json`: the identical input and contract return an integer.
- `source/server.py`: exact byte snapshot of `containers/p0_03/server.py`, never executed by the source-reading tool. The model receives only the approved `lookup_result` function slice. Its `wrong_type` branch is the actual serialization fault used by the container fixture; `pass` keeps the integer.
- `manifest.json`: envelope and complete source hashes, plus the approved source slice. Its own digest is pinned in `controlled_tools/resources.py`. Updating a fixture requires explicitly reviewing and updating both the manifest and this pin. No model can edit this registration.

The real T05 reproduction uses the existing offline, non-root, read-only Docker policy. It does not invoke this snapshot on the host. Scenario `wrong_type` is available to the approved analysis case; the four Web reproduction choices are unchanged.

Validation from the project root:

```sh
uv run pytest tests/test_controlled_resources.py tests/test_controlled_runtime.py
uv run python containers/p0_03/prepare.py
AWB_TOOL_DOCKER=1 uv run pytest tests/test_controlled_tools_docker.py
```

The Docker gate is skipped unless explicitly enabled; skipped tests do not establish execution evidence. Both real cases assert actual SDK protocol negotiation, contract findings, persisted report hash/IDs, removal of the container, and request replay without a second dispatch. The test uses a temporary SQLite directory and never the user's existing run database.
