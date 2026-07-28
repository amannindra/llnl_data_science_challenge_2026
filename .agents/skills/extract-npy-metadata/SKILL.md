---
name: extract-npy-metadata
description: Inspect one or more NumPy .npy files and print array metadata and basic statistics without modifying data. Use for requests to inspect NPY metadata; show shape, dtype, element count, file size, minimum, maximum, mean, or nonzero count; or explicitly use extract-npy-metadata on provided .npy paths.
---

# Extract NPY Metadata

Require the user to provide one or more input paths explicitly. Do not discover or infer dataset paths.

Run the bundled script from the repository root and pass every requested path:

```bash
/opt/miniconda3/envs/dssi_env/bin/python \
  .agents/skills/extract-npy-metadata/scripts/extract_metadata.py \
  <input.npy> [<input.npy> ...]
```

Treat all input arrays as read-only. Do not generate, modify, or overwrite dataset or report files. Do not invoke MCP tools; metadata extraction requires only the bundled script.

Print the script results to the terminal. If a path is missing, invalid, not a `.npy` file, or cannot be loaded safely, report the clear error and nonzero exit status to the user.
