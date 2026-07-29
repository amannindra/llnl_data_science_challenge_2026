import { FrontendRendererArgs } from "@streamlit/component-v2-lib";
import {
  FC,
  ReactElement,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";


export type LatticeViewerState = {
  selected_strut_id: number | null;
};

export type LatticeViewerData = {
  schemaVersion: number;
  sceneKind: "lattice" | "unit_cell";
  viewerTitle: string;
  coordinateOrder: string;
  selectedMapping: string;
  nominalStrutIds: number[];
  nominalPositionsZyx: number[];
  analyzedStrutIds: number[];
  analyzedPositionsZyx: number[];
  analyzedLabelCodes: number[];
  labelNames: string[];
  xrayVerticesZyx: number[];
  xrayFaces: number[];
  selectedStrutId?: number | null;
  cellId?: number;
  targetStrutId?: number;
  targetLabel?: string;
  focusZyx?: number[];
};

type ViewerProps = {
  data: LatticeViewerData;
  setStateValue: FrontendRendererArgs<
    LatticeViewerState,
    LatticeViewerData
  >["setStateValue"];
};

const COLORS: Record<string, number> = {
  intact: 0x248a3d,
  missing: 0xd70015,
  broken: 0xc93400,
  thin: 0x8944ab,
  uncertain: 0x0066cc,
};

const LABEL_TITLES: Record<string, string> = {
  intact: "Intact",
  missing: "Missing",
  broken: "Broken",
  thin: "Thin",
  uncertain: "Uncertain",
};

type SceneHandles = {
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  nominal: THREE.Object3D;
  overlays: Map<string, THREE.Object3D>;
  contextMesh: THREE.Mesh | null;
  axesHelper: THREE.AxesHelper;
  selectedMesh: THREE.Mesh;
  reset: () => void;
  focus: (strutId: number) => void;
};

function zyxToXyz(values: number[]): Float32Array {
  const converted = new Float32Array(values.length);
  for (let index = 0; index < values.length; index += 3) {
    converted[index] = values[index + 2];
    converted[index + 1] = values[index + 1];
    converted[index + 2] = values[index];
  }
  return converted;
}

function lineSegments(
  positionsZyx: number[],
  color: number,
  opacity: number,
): THREE.LineSegments {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.BufferAttribute(zyxToXyz(positionsZyx), 3),
  );
  const material = new THREE.LineBasicMaterial({
    color,
    transparent: opacity < 1,
    opacity,
  });
  return new THREE.LineSegments(geometry, material);
}

function segmentMatrix(segmentZyx: number[], radius: number): THREE.Matrix4 {
  const xyz = zyxToXyz(segmentZyx);
  const start = new THREE.Vector3(xyz[0], xyz[1], xyz[2]);
  const end = new THREE.Vector3(xyz[3], xyz[4], xyz[5]);
  const direction = new THREE.Vector3().subVectors(end, start);
  const length = direction.length();
  const midpoint = start.clone().add(end).multiplyScalar(0.5);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    direction.clone().normalize(),
  );
  return new THREE.Matrix4().compose(
    midpoint,
    quaternion,
    new THREE.Vector3(radius, length, radius),
  );
}

function cylinderSegments(
  positionsZyx: number[],
  strutIds: number[],
  color: number,
  radius: number,
  opacity = 1,
): THREE.InstancedMesh {
  const geometry = new THREE.CylinderGeometry(1, 1, 1, 12, 1, false);
  const material = new THREE.MeshStandardMaterial({
    color,
    transparent: opacity < 1,
    opacity,
    roughness: 0.58,
    metalness: 0.08,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, strutIds.length);
  strutIds.forEach((_, index) => {
    mesh.setMatrixAt(
      index,
      segmentMatrix(positionsZyx.slice(index * 6, index * 6 + 6), radius),
    );
  });
  mesh.instanceMatrix.needsUpdate = true;
  mesh.userData.strutIds = strutIds;
  return mesh;
}

function segmentForStrut(
  data: LatticeViewerData,
  strutId: number,
): number[] | null {
  let index = data.analyzedStrutIds.indexOf(strutId);
  if (index >= 0) {
    return data.analyzedPositionsZyx.slice(index * 6, index * 6 + 6);
  }
  index = data.nominalStrutIds.indexOf(strutId);
  return index < 0
    ? null
    : data.nominalPositionsZyx.slice(index * 6, index * 6 + 6);
}

function selectedCylinder(): THREE.Mesh {
  const geometry = new THREE.CylinderGeometry(1, 1, 1, 16);
  const material = new THREE.MeshStandardMaterial({
    color: 0x0066cc,
    emissive: 0x0066cc,
    emissiveIntensity: 0.42,
    transparent: true,
    opacity: 0.96,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.visible = false;
  mesh.renderOrder = 8;
  return mesh;
}

function colorSelectedCylinder(mesh: THREE.Mesh, label: string | null): void {
  const color = COLORS[label ?? ""] ?? 0x0066cc;
  const material = mesh.material as THREE.MeshStandardMaterial;
  material.color.setHex(color);
  material.emissive.setHex(color);
  material.needsUpdate = true;
}

function positionCylinder(
  mesh: THREE.Mesh,
  segmentZyx: number[],
  radius: number,
): void {
  mesh.matrix.copy(segmentMatrix(segmentZyx, radius));
  mesh.matrix.decompose(mesh.position, mesh.quaternion, mesh.scale);
  mesh.visible = true;
}

function disposeObject(object: THREE.Object3D): void {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    mesh.geometry?.dispose();
    const materials = Array.isArray(mesh.material)
      ? mesh.material
      : mesh.material
        ? [mesh.material]
        : [];
    materials.forEach((material) => material.dispose());
  });
}

export const LatticeViewer: FC<ViewerProps> = ({
  data,
  setStateValue,
}): ReactElement => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneHandles = useRef<SceneHandles | null>(null);
  const isUnitCell = data.sceneKind === "unit_cell";
  const presentLabels = useMemo(
    () =>
      data.labelNames.filter((_, code) =>
        data.analyzedLabelCodes.some((value) => value === code),
      ),
    [data.analyzedLabelCodes, data.labelNames],
  );
  const [showNominal, setShowNominal] = useState(true);
  const [showContext, setShowContext] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [contextOpacity, setContextOpacity] = useState(isUnitCell ? 0.2 : 0.1);
  const [visibleLabels, setVisibleLabels] = useState<Set<string>>(
    () => new Set(presentLabels.filter((label) => label !== "intact")),
  );
  const [selectedStrutId, setSelectedStrutId] = useState<number | null>(
    data.selectedStrutId ?? data.targetStrutId ?? null,
  );
  const [selectionSource, setSelectionSource] = useState<
    "canvas" | "dropdown" | null
  >(null);

  const selectedLabel = useMemo(() => {
    if (selectedStrutId === null) {
      return null;
    }
    const index = data.analyzedStrutIds.indexOf(selectedStrutId);
    return index < 0
      ? null
      : data.labelNames[data.analyzedLabelCodes[index]] ?? null;
  }, [data, selectedStrutId]);

  const selectStrut = useCallback(
    (strutId: number, source: "canvas" | "dropdown"): void => {
      setSelectedStrutId(strutId);
      setSelectionSource(source);
      setStateValue("selected_strut_id", strutId);
    },
    [setStateValue],
  );

  useEffect(() => {
    setVisibleLabels(new Set(presentLabels.filter((label) => label !== "intact")));
    setContextOpacity(isUnitCell ? 0.2 : 0.1);
    setSelectedStrutId(data.selectedStrutId ?? data.targetStrutId ?? null);
  }, [data.sceneKind, data.targetStrutId, data.selectedStrutId, isUnitCell, presentLabels]);

  useEffect(() => {
    const handles = sceneHandles.current;
    if (!handles) {
      return;
    }
    handles.nominal.visible = showNominal;
    handles.axesHelper.visible = showAxes;
    handles.overlays.forEach((overlay, label) => {
      overlay.visible = visibleLabels.has(label);
    });
    if (handles.contextMesh) {
      handles.contextMesh.visible = showContext;
      const material = handles.contextMesh.material as THREE.MeshStandardMaterial;
      material.opacity = contextOpacity;
      material.needsUpdate = true;
    }
  }, [contextOpacity, showAxes, showContext, showNominal, visibleLabels]);

  useEffect(() => {
    const handles = sceneHandles.current;
    if (!handles) {
      return;
    }
    if (selectedStrutId === null) {
      handles.selectedMesh.visible = false;
      return;
    }
    const segment = segmentForStrut(data, selectedStrutId);
    if (segment) {
      colorSelectedCylinder(handles.selectedMesh, selectedLabel);
      positionCylinder(handles.selectedMesh, segment, isUnitCell ? 2.15 : 2.6);
    }
  }, [data, isUnitCell, selectedLabel, selectedStrutId]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    if (data.schemaVersion !== 1 || data.coordinateOrder !== "zyx") {
      container.textContent = "Unsupported lattice scene schema.";
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f7fa);
    const camera = new THREE.PerspectiveCamera(
      isUnitCell ? 36 : 42,
      Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1),
      0.1,
      5000,
    );
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.replaceChildren(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    const nominal = isUnitCell
      ? cylinderSegments(
          data.nominalPositionsZyx,
          data.nominalStrutIds,
          0x687786,
          1.0,
          0.92,
        )
      : lineSegments(data.nominalPositionsZyx, 0x687786, 0.42);
    nominal.name = "Nominal lattice";
    scene.add(nominal);

    const overlays = new Map<string, THREE.Object3D>();
    data.labelNames.forEach((label, code) => {
      const positions: number[] = [];
      const strutIds: number[] = [];
      data.analyzedLabelCodes.forEach((value, index) => {
        if (value === code) {
          positions.push(
            ...data.analyzedPositionsZyx.slice(index * 6, index * 6 + 6),
          );
          strutIds.push(data.analyzedStrutIds[index]);
        }
      });
      if (positions.length) {
        const overlay = cylinderSegments(
          positions,
          strutIds,
          COLORS[label] ?? 0x687786,
          isUnitCell ? 1.85 : label === "intact" ? 1.25 : 2.05,
          label === "intact" ? 0.72 : 1,
        );
        overlay.name = `${label} analyzed struts`;
        overlay.visible = visibleLabels.has(label);
        overlays.set(label, overlay);
        scene.add(overlay);
      }
    });

    let contextMesh: THREE.Mesh | null = null;
    if (data.xrayVerticesZyx.length && data.xrayFaces.length) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(zyxToXyz(data.xrayVerticesZyx), 3),
      );
      geometry.setIndex(data.xrayFaces);
      geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({
        color: 0xb8c0c8,
        transparent: true,
        opacity: contextOpacity,
        depthWrite: false,
        side: THREE.DoubleSide,
        roughness: 0.78,
        metalness: 0.04,
      });
      contextMesh = new THREE.Mesh(geometry, material);
      contextMesh.name = "Derived CT material context";
      contextMesh.renderOrder = 1;
      scene.add(contextMesh);
    }

    const selectedMesh = selectedCylinder();
    scene.add(selectedMesh);
    if (selectedStrutId !== null) {
      const segment = segmentForStrut(data, selectedStrutId);
      if (segment) {
        const selectedIndex = data.analyzedStrutIds.indexOf(selectedStrutId);
        const selectedCode = data.analyzedLabelCodes[selectedIndex];
        colorSelectedCylinder(
          selectedMesh,
          selectedIndex < 0 ? null : data.labelNames[selectedCode] ?? null,
        );
        positionCylinder(selectedMesh, segment, isUnitCell ? 2.15 : 2.6);
      }
    }

    scene.add(new THREE.HemisphereLight(0xffffff, 0x6b7785, 1.9));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
    keyLight.position.set(1, 2, 3);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xaed8ff, 1.0);
    fillLight.position.set(-2, -1, 1);
    scene.add(fillLight);

    const bounds = new THREE.Box3().setFromObject(nominal);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 1);
    const axesHelper = new THREE.AxesHelper(Math.max(radius * 0.18, 18));
    axesHelper.position.copy(bounds.min);
    scene.add(axesHelper);

    const initialPosition = new THREE.Vector3(
      center.x + radius * 1.15,
      center.y + radius * 0.75,
      center.z + radius * 1.15,
    );
    const reset = (): void => {
      controls.target.copy(center);
      camera.position.copy(initialPosition);
      camera.near = Math.max(radius / 1000, 0.1);
      camera.far = Math.max(radius * 10, 5000);
      camera.updateProjectionMatrix();
      controls.update();
    };
    const focus = (strutId: number): void => {
      const segment = segmentForStrut(data, strutId);
      if (!segment) {
        return;
      }
      const xyz = zyxToXyz(segment);
      const start = new THREE.Vector3(xyz[0], xyz[1], xyz[2]);
      const end = new THREE.Vector3(xyz[3], xyz[4], xyz[5]);
      const midpoint = start.clone().add(end).multiplyScalar(0.5);
      const distance = Math.max(start.distanceTo(end) * (isUnitCell ? 2.2 : 3.5), 75);
      controls.target.copy(midpoint);
      camera.position.copy(midpoint).add(new THREE.Vector3(distance, distance, distance));
      controls.update();
    };
    reset();

    sceneHandles.current = {
      camera,
      controls,
      nominal,
      overlays,
      contextMesh,
      axesHelper,
      selectedMesh,
      reset,
      focus,
    };

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerStart: { x: number; y: number } | null = null;
    const onPointerDown = (event: PointerEvent): void => {
      pointerStart = { x: event.clientX, y: event.clientY };
    };
    const onPointerUp = (event: PointerEvent): void => {
      if (
        !pointerStart ||
        Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 5
      ) {
        pointerStart = null;
        return;
      }
      pointerStart = null;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const candidates = Array.from(overlays.entries())
        .filter(([label, overlay]) => visibleLabels.has(label) && overlay.visible)
        .map(([, overlay]) => overlay);
      const hit = raycaster.intersectObjects(candidates, false)[0];
      if (!hit) {
        return;
      }
      const ids = hit.object.userData.strutIds as number[];
      const strutId = ids[hit.instanceId ?? 0];
      if (strutId !== undefined) {
        selectStrut(strutId, "canvas");
      }
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);

    let animationFrame = 0;
    const animate = (): void => {
      controls.update();
      renderer.render(scene, camera);
      animationFrame = requestAnimationFrame(animate);
    };
    animate();

    const resizeObserver = new ResizeObserver(() => {
      const width = Math.max(container.clientWidth, 1);
      const height = Math.max(container.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    });
    resizeObserver.observe(container);

    return () => {
      sceneHandles.current = null;
      cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      controls.dispose();
      disposeObject(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [data, isUnitCell, selectStrut]);

  const toggleLabel = (label: string): void => {
    setVisibleLabels((current) => {
      const next = new Set(current);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  return (
    <div className="viewer-shell">
      <div className="viewer-header">
        <div>
          <strong>{data.viewerTitle}</strong>
          <span>
            {data.nominalStrutIds.length.toLocaleString()} nominal struts
            {isUnitCell
              ? ` · unit cell ${data.cellId} · target ${data.targetStrutId}`
              : ` · ${data.analyzedStrutIds.length} analyzed overlays`}
          </span>
        </div>
        <span className="mapping">{data.selectedMapping}</span>
      </div>
      <div className="viewer-toolbar" aria-label="Lattice display controls">
        <label>
          <input
            type="checkbox"
            checked={showNominal}
            onChange={(event) => setShowNominal(event.target.checked)}
          />
          Nominal lattice
        </label>
        <label>
          <input
            type="checkbox"
            checked={showContext}
            onChange={(event) => setShowContext(event.target.checked)}
          />
          Derived CT surface
        </label>
        <label>
          <input
            type="checkbox"
            checked={showAxes}
            onChange={(event) => setShowAxes(event.target.checked)}
          />
          Orientation axes
        </label>
        {presentLabels.map((label) => (
          <label key={label}>
            <input
              type="checkbox"
              checked={visibleLabels.has(label)}
              onChange={() => toggleLabel(label)}
            />
            <span
              className="legend-dot"
              style={{ backgroundColor: `#${(COLORS[label] ?? 0x687786)
                .toString(16)
                .padStart(6, "0")}` }}
            />
            {LABEL_TITLES[label] ?? label}
          </label>
        ))}
      </div>
      <div className="viewer-settings">
        <label>
          Analyzed strut
          <select
            aria-label="Analyzed strut"
            value={selectedStrutId ?? ""}
            onChange={(event) => {
              if (event.target.value) {
                selectStrut(Number(event.target.value), "dropdown");
              }
            }}
          >
            <option value="">Select a strut</option>
            {data.analyzedStrutIds.map((strutId, index) => {
              const label =
                data.labelNames[data.analyzedLabelCodes[index]] ?? "unknown";
              return (
                <option key={strutId} value={strutId}>
                  {strutId} · {LABEL_TITLES[label] ?? label}
                </option>
              );
            })}
          </select>
        </label>
        <label>
          CT opacity
          <input
            type="range"
            min="0"
            max="0.45"
            step="0.01"
            value={contextOpacity}
            disabled={!showContext}
            onChange={(event) => setContextOpacity(Number(event.target.value))}
          />
          <span>{Math.round(contextOpacity * 100)}%</span>
        </label>
        <div className="viewer-actions">
          <button type="button" onClick={() => sceneHandles.current?.reset()}>
            Reset view
          </button>
          <button
            type="button"
            disabled={selectedStrutId === null}
            onClick={() => {
              if (selectedStrutId !== null) {
                sceneHandles.current?.focus(selectedStrutId);
              }
            }}
          >
            Focus selected
          </button>
        </div>
      </div>
      <div
        ref={containerRef}
        className="viewer-canvas"
        role="img"
        aria-label="Interactive registered three-dimensional lattice geometry"
      />
      <div className="viewer-footer">
        <span>
          Drag to rotate · Scroll to zoom · Right-drag to pan · Click a colored strut
        </span>
        <strong>
          {selectedStrutId === null
            ? "No strut selected"
            : `Strut ${selectedStrutId} · ${
                LABEL_TITLES[selectedLabel ?? ""] ?? selectedLabel
              }${selectionSource ? ` · selected via ${selectionSource}` : ""}`}
        </strong>
      </div>
    </div>
  );
};
