# Defect Finding Process

This is the simple picture of how the project finds possible missing or broken
struts.

## Data Roles

```text
STL = what the design intended
registered JSON = where each expected strut should be inside the CT scan
TIFF = what material was physically scanned
```

Bright CT voxels usually mean titanium alloy material. Dark CT voxels usually
mean air, void, or missing material.

## Step 1 - Build The Canonical Graph

The raw JSON has repeated junction aliases. Phase 0 merges those aliases into
real physical nodes and creates stable canonical edge IDs.

Current graph size:

```text
canonical physical nodes = 3,430
canonical physical struts/edges = 18,468
```

## Step 2 - Separate Designed Removals From Unintended Defects

The STL files tell which struts were intentionally removed in the design.

This matters because a missing strut is not automatically a manufacturing
defect. If the design intentionally removed it, it should not be counted as an
unintended CT defect.

## Step 3 - Register Expected Struts To The CT Scan

The registered JSON gives the expected strut coordinates in CT voxel space.

Important axis rule:

```text
registered JSON coordinates = [x, y, z]
TIFF array indexing = [z, y, x]
```

## Step 4 - Sample CT Evidence Around Each Strut

The sampler follows each expected strut body in 3D. It excludes node/junction
zones near the ends because bright node blobs can make an absent strut look
present if we are not careful.

For each strut, it measures:

- core intensity;
- local background intensity;
- core-minus-background contrast;
- material area along the strut;
- occupied axial fraction;
- longest low-area gap;
- bridge connectivity;
- threshold stability;
- local registration stability.

## Step 5 - Create Guarded Labels

Phase 2B.3 created cautious labels for all `18,468` struts.

It separated:

- present-like struts;
- designed-removed struts;
- possible unintended missing struts;
- possible unintended disconnected struts;
- uncertain review-required struts.

## Step 6 - Strict Automated Review

Phase 2B.4 applied stricter rules and produced the current conservative report
baseline:

```text
auto-supported possible unintended missing = 202
auto-supported possible unintended disconnected = 12
combined = 214
```

The user reviewed ranks `001-040` from this set:

```text
36 defect-like
4 ambiguous
0 present-like contradictions
```

That supports the `214` count as a spot-check-supported automated estimate.

## Step 7 - Phase 2C Second-Pass Triage

Phase 2C looked again at blocked rows using existing all-edge CT features.

It promoted only very clear rows where the strut body was essentially empty or
clearly broken under bounded uncertainty.

Phase 2C result:

```text
possible unintended missing = 215
possible unintended disconnected = 13
combined = 228
newly promoted from Phase 2B.4 blocked rows = 14
still review-required = 677
low-priority uncertain = 2,654
```

The `228` result is the newest automatic triage result, but it is not yet the
spot-check-supported final baseline. Review the `14` newly promoted rows first.

