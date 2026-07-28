# Segmentation Evaluation Rubric

Evaluate the two attached images as follows:

- The first attached image is the ground-truth segmentation.
- The second attached image is the Task 6 result.
- Compare segmentation content only. Ignore titles, axes, colorbars, canvas size, and all other presentation differences.

## Evaluation Criteria

1. **Structural integrity:** Does the result preserve lattice-strut connectivity?
2. **False positives and negatives:** Is there extra foreground noise or missing lattice material?
3. **Topology:** Are nodes, junctions, and strut connections preserved?
4. **Noise and artifacts:** Are there artifacts not present in the ground truth?

## Scoring Scale

- **5:** Identical or efctively equivalent to ground truth, with no meaningful missing structures or false positives.
- **4:** Excellent, with only minor differences.
- **3:** Main topology is correct, but noticeable noise or thin/missing struts exist.
- **2:** Significant differences or large missing/extra regions.
- **1:** Major structural failure or excessive noise.
- **0:** Blank, unrelated, or unusable output.

## Required Output

Return only valid JSON in exactly this structure:

    {
      "reasoning": "Concise evidence-based comparison",
      "score": 0
    }

The `score` must be an integer from 0 through 5. Do not use Markdown fences or include any additional text before or after the JSON object.
