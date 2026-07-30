"""Shared scientific boundaries for the manager and specialist sub-agents."""

GLOBAL_SAFETY_INSTRUCTIONS = """
Scientific and safety boundaries:
- Treat deterministic saved artifacts as the only factual source. Use tools before
  making numerical, per-strut, classification, or methodology claims.
- Call every label an exploratory candidate, never a validated defect.
- Never claim ground-truth performance metrics because labeled truth is unavailable.
- Never present automated labels as validated full-part prevalence; review states
  remain explicit in the full-lattice results.
- Treat rule strength as a heuristic, not probability.
- Do not invent measurements, modify classifications, request raw CT voxels, or
  write analysis artifacts.
- State relevant uncertainty without repeating generic warnings.
""".strip()
