#!/usr/bin/env python3
"""Adversarial checks for XYZ/ZYX semantics and transform mathematics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

import numpy as np


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from Aman_Scripts.Components.coordinates import (  # noqa: E402
    apply_transform,
    compose_transforms,
    homogeneous_matrix,
    invert_transform,
    rotation_matrix_xyz,
    xyz_to_zyx,
    zyx_to_xyz,
)


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.results: list[dict[str, object]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}: {detail}")
        self.results.append({"name": name, "passed": bool(condition), "detail": detail})

    def raises(self, name: str, error: type[BaseException], operation: Callable[[], object]) -> None:
        try:
            operation()
        except error:
            self.check(name, True)
        except Exception as exc:  # pragma: no cover - diagnostic branch
            self.check(name, False, f"raised {type(exc).__name__}, expected {error.__name__}")
        else:
            self.check(name, False, f"did not raise {error.__name__}")


def main() -> int:
    checks = Checks()

    point = np.array([11, 22, 33], dtype=np.int16)
    reordered = xyz_to_zyx(point)
    checks.check("single XYZ point converts to ZYX", np.array_equal(reordered, [33, 22, 11]))
    checks.check("coordinate conversion preserves dtype", reordered.dtype == point.dtype)
    checks.check("coordinate conversion returns a copy", not np.shares_memory(point, reordered))

    batch = np.array([[[1.0, 2.0, 3.0]], [[4.0, 5.0, 6.0]]])
    batch_zyx = xyz_to_zyx(batch)
    checks.check("batched coordinate shape preserved", batch_zyx.shape == batch.shape)
    checks.check("batched coordinate values reverse last axis", np.array_equal(batch_zyx[..., 0], batch[..., 2]))
    checks.check("XYZ-ZYX round trip exact", np.array_equal(zyx_to_xyz(batch_zyx), batch))
    checks.raises("scalar coordinate rejected", ValueError, lambda: xyz_to_zyx(4))
    checks.raises("wrong final dimension rejected", ValueError, lambda: zyx_to_xyz([[1, 2]]))

    identity_rotation = rotation_matrix_xyz([0, 0, 0])
    checks.check("zero Euler angles produce identity", np.allclose(identity_rotation, np.eye(3)))
    rotate_z = rotation_matrix_xyz([0, 0, 90], degrees=True)
    checks.check("positive Z rotation maps X to Y", np.allclose(rotate_z @ [1, 0, 0], [0, 1, 0]))
    checks.check(
        "degree and radian rotations agree",
        np.allclose(rotate_z, rotation_matrix_xyz([0, 0, np.pi / 2])),
    )
    checks.check("rotation matrix is orthonormal", np.allclose(rotate_z.T @ rotate_z, np.eye(3)))
    checks.raises("wrong Euler angle count rejected", ValueError, lambda: rotation_matrix_xyz([0, 1]))
    checks.raises("nonfinite Euler angle rejected", ValueError, lambda: rotation_matrix_xyz([0, np.nan, 0]))

    identity = homogeneous_matrix()
    checks.check("default homogeneous transform is identity", np.array_equal(identity, np.eye(4)))
    translation = homogeneous_matrix(translation=[10, -2, 5])
    checks.check(
        "translation applies in XYZ order",
        np.allclose(apply_transform([1, 2, 3], translation), [11, 0, 8]),
    )
    uniform = homogeneous_matrix(scale=2)
    checks.check("uniform scale applies", np.allclose(apply_transform([1, 2, 3], uniform), [2, 4, 6]))
    anisotropic = homogeneous_matrix(rotation=rotate_z, scale=[2, 3, 4])
    checks.check(
        "anisotropic scale precedes rotation",
        np.allclose(apply_transform([1, 1, 1], anisotropic), [-3, 2, 4]),
    )
    checks.raises("zero scale rejected", ValueError, lambda: homogeneous_matrix(scale=0))
    checks.raises("wrong scale length rejected", ValueError, lambda: homogeneous_matrix(scale=[1, 2]))
    checks.raises("wrong rotation shape rejected", ValueError, lambda: homogeneous_matrix(rotation=np.eye(4)))
    checks.raises("wrong translation shape rejected", ValueError, lambda: homogeneous_matrix(translation=[1, 2]))

    transformed_batch = apply_transform(batch, translation)
    checks.check("transform preserves arbitrary leading dimensions", transformed_batch.shape == batch.shape)
    checks.check(
        "inverse transform restores points",
        np.allclose(apply_transform(transformed_batch, invert_transform(translation)), batch),
    )

    first = homogeneous_matrix(scale=2)
    second = homogeneous_matrix(translation=[1, 0, 0])
    composed = compose_transforms(first, second)
    sequential = apply_transform(apply_transform([3, 0, 0], first), second)
    checks.check("composition follows application order", np.allclose(apply_transform([3, 0, 0], composed), sequential))
    checks.check("empty composition is identity", np.array_equal(compose_transforms(), np.eye(4)))
    checks.raises("non-4x4 transform rejected", ValueError, lambda: apply_transform([1, 2, 3], np.eye(3)))
    checks.raises(
        "nonfinite transform rejected",
        ValueError,
        lambda: apply_transform([1, 2, 3], np.full((4, 4), np.nan)),
    )

    zero_weight = np.eye(4)
    zero_weight[3, 3] = 0
    checks.raises("zero homogeneous weight rejected", ValueError, lambda: apply_transform([1, 2, 3], zero_weight))
    singular = np.eye(4)
    singular[2] = 0
    checks.raises("singular transform cannot invert", np.linalg.LinAlgError, lambda: invert_transform(singular))

    projective = np.eye(4)
    projective[3, 0] = 0.5
    checks.check(
        "non-unit homogeneous weight is normalized",
        np.allclose(apply_transform([2, 0, 0], projective), [1, 0, 0]),
    )

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} coordinate checks passed")
    print(json.dumps({"suite": "coordinates", "passed": checks.passed, "failed": checks.failed,
                      "total": total, "minimum_satisfied": total >= 12,
                      "results": checks.results}, sort_keys=True))
    return 0 if checks.failed == 0 and total >= 12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
