# Safe initialization

The preview plan is the write boundary. It contains repository realpath, a base fingerprint, per-file before and after digests, exact content, and a plan digest. The digest detects accidental edits; it is not a signature. Apply must also regenerate the current init plan and require an exact match, so a caller cannot recompute a digest for an arbitrary write.

Before apply:

- reject repository or digest mismatch;
- reject stale before-digests;
- reject commands, fields, operations, and paths outside the fixed init surface;
- require an exact match with a freshly generated plan;
- reject absolute paths, `..`, or symlink escape;
- preserve user-owned files and content outside managed blocks;
- validate every operation before the first write.

Apply files atomically and roll back in-process on failure. A second preview against the applied state must contain no operations.
