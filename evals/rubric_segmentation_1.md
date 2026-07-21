---
name: rubric-segmentation-1
description: Evaluate a lattice-structure segmentation slice against its ground-truth image using structural integrity, pixel-classification errors, topology, and artifacts.
---

# Lattice Segmentation Evaluation Rubric

## Inputs

- The first attached image is the ground-truth segmentation.
- The second attached image is the segmentation result being evaluated.

Compare only the segmentation content visible in these two images. Do not infer quality from filenames, reports, or other external information.

## Evaluation Criteria

### 1. Structural Integrity

Compare the overall lattice geometry and connectivity. Determine whether the result preserves the same struts, their approximate thicknesses, and their connections as the ground truth. Penalize broken, merged, displaced, or missing structures.

### 2. False Positives and False Negatives

- **False positives / over-segmentation:** Foreground pixels, blobs, or structures appear in the result but not in the ground truth.
- **False negatives / under-segmentation:** Ground-truth struts, junctions, or portions of structures are missing from the result.

Consider both the severity and spatial extent of these errors.

### 3. Topology

Determine whether the result preserves the lattice network's nodes, junctions, branches, and connected paths. Give greater weight to topology-changing errors than to small boundary differences.

### 4. Noise and Artifacts

Identify isolated pixels, speckle, holes, jagged boundaries, disconnected fragments, or other artifacts absent from the ground truth. Distinguish minor edge roughness from artifacts that obscure or alter the structure.

## Overall Scoring (0–5)

Assign one integer score based on all four criteria:

- **5 — Near-perfect:** The result matches the ground truth almost exactly. Connectivity and junctions are preserved, with no meaningful missing structure, extra structure, noise, or artifacts.
- **4 — Excellent:** The full lattice topology is preserved. Only minor boundary, thickness, or isolated-pixel differences are visible and do not affect connectivity.
- **3 — Acceptable:** The main lattice and topology are recognizable and mostly correct, but there is noticeable noise, boundary error, or loss/addition of some thin strut regions. Most important connections remain intact.
- **2 — Poor:** Significant portions are missing or added, multiple struts or junctions are incorrect, or artifacts substantially reduce agreement. Some lattice structure remains recognizable.
- **1 — Major failure:** Most structural connectivity is wrong or missing, false foreground dominates, or severe artifacts make the segmentation barely useful.
- **0 — No valid segmentation:** The result is blank, unrelated, unreadable, or does not represent the ground-truth lattice.

When a result lies between two scores, choose the lower score if an error changes lattice connectivity or destroys a junction. Otherwise, choose the score that best represents the overall visible agreement.

## Required Output

Return only one valid JSON object. Do not include Markdown fences or text before or after it.

Use exactly this schema:

```json
{
  "reasoning": "Briefly discuss structural integrity, false positives/negatives, topology, and noise/artifacts, then justify the overall score.",
  "score": 0
}
```

The `score` must be an integer from `0` through `5`. The `reasoning` must be concise and evidence-based.
