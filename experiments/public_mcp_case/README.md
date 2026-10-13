# P0-02 public MCP issue #3644

This opt-in experiment runs official SDK commit
`2118f14f8a19bc158d8a1cf90af58d85d187f849` unchanged. Both `mcp` and
`mcp_types` load from that source tree. Only third-party runtime dependencies
are installed in this directory's separate `.venv`, using its own `uv.lock`.
The parent project's dependency environment is not modified.

Run from the repository root, with Python 3.12 and uv installed:

```sh
python3 -I -B experiments/public_mcp_case/prepare.py
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  experiments/public_mcp_case/.venv/bin/python -I -B experiments/public_mcp_case/probe.py
```

`prepare.py` downloads only the fixed official GitHub archive, verifies its
SHA-256 and the complete extracted file/directory set, then performs a frozen
dependency installation. Extra files (including .pyc), extra directories
(including __pycache__), all symlinks, missing entries and altered content fail.
There is no bytecode-cache whitelist. `-I -B` prevents environment/path injection
and new bytecode caches; the probe also passes these flags to the server.
Download timeout is 180 seconds; each dependency HTTP request has a 20-second
timeout with one retry, and the installation has a 120-second process limit.
Source and run outputs remain in ignored `artifacts/public-mcp-case/`.

The probe uses actual official SDK stdio `initialize`, `list_tools`, and
`call_tool`. Its client deliberately defers the SDK output-validation hook so
an invalid server result can be captured, then independently validates that
result with JSON Schema. The server and its schema generation are not patched.
Probe request work has a 20-second deadline; SDK transport shutdown has its own
bounded cleanup. This is a trusted local experiment, not an untrusted sandbox.

The exported `synthetic-public-case-envelope.json` contains only the issue's
public synthetic minimal values. It is SDK-normalized evidence, with a local
association ID; it does not certify raw wire bytes. `reproduction.json` records
runtime versions, hashes and observed schema violations. Exit 0 means the
historical mismatch was reproduced; it does not mean the tool contract passed.

Before independently reviewing a result, rerun `prepare.py` to verify source
and lock, then run the probe. The main product adapter must independently
connect to `server.py`; this probe alone does not certify the product adapter.

Report and scope: [public-case experiment](../../docs/experiments/P0-02-public-case.md).

Read-only runtime verification, with no downloads, installation or writes:

```sh
python3 -I -B experiments/public_mcp_case/prepare.py --verify-only
python3 -I -B experiments/public_mcp_case/test_prepare.py
```

Successful verification exits 0 and prints one JSON object containing `code` =
`source_verified`, `commit`, `archive_sha256`, `lock_sha256`,
`source_tree_sha256`, `source_files_verified`, and `source_modified` = false.
Failure exits 2 with one fixed `code`, without paths or exception text. The tree
digest is SHA-256 of UTF-8 JSON (`ensure_ascii=False`, compact separators) of
the sorted array of `[relative POSIX file path, file SHA-256]` pairs. Directories
are verified as an exact set; their metadata is not part of the file-tree digest.

Previously polluted artifact trees are rejected, not silently cleaned. To retain
old evidence, move the specific `artifacts/public-mcp-case/python-sdk-<commit>`
directory aside, then explicitly rerun setup to reconstruct from the hash-pinned
archive. Never remove unrelated user paths. This is a point-in-time check within
a trusted local experiment; it does not prevent hostile concurrent mutation.
