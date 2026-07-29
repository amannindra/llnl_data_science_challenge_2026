import { FrontendRendererArgs } from "@streamlit/component-v2-lib";
import {
  CSSProperties,
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

type PaletteData = {
  nominal: string;
  nodes: string;
  ctContext: string;
  segmentation: string;
  expectedCenterline: string;
  observedCenterline: string;
  candidates: Record<string, string>;
};

type SliceModeData = {
  rawDataUrl: string;
  segmentationBoundaryDataUrl: string;
  observedCenterlineDataUrl: string;
};

type SliceFrameData = {
  globalIndex: number;
  indexLabel: string;
  offsetVox: number;
  modes: {
    exact: SliceModeData;
    slab: SliceModeData;
  };
  slabBoundsGlobal: number[];
};

type SliceViewData = {
  axis: string;
  title: string;
  xAxis: string;
  yAxis: string;
  frames: SliceFrameData[];
  expectedLine: number[];
  focusPoint: number[];
};

type SliceEvidenceData = {
  schemaVersion: number;
  strutId: number;
  candidateLabel: string;
  candidateColor: string;
  classificationStatus: string;
  focusMethod: string;
  focusZyx: number[];
  preferredView: string;
  slabThicknessVox: number;
  positionOffsetsVox: number[];
  cropSizeVox: number;
  contrast: Record<string, string>;
  observedCenterlineScope: string;
  measurements: Record<string, number | string | null>;
  views: SliceViewData[];
  rawCtVolumeEmbedded: boolean;
};

export type LatticeViewerData = {
  schemaVersion: number;
  sceneRevision: string;
  sceneKind: "lattice" | "unit_cell";
  viewerTitle: string;
  coordinateOrder: string;
  selectedMapping: string;
  palette: PaletteData;
  nominalStrutIds: number[];
  nominalPositionsZyx: number[];
  junctionIds: number[];
  junctionPositionsZyx: number[];
  nominalJunctionIds: number[];
  analyzedStrutIds: number[];
  analyzedPositionsZyx: number[];
  analyzedLabelCodes: number[];
  labelNames: string[];
  xrayVerticesZyx: number[];
  xrayFaces: number[];
  xrayVertexTexture: number[];
  selectedStrutId?: number | null;
  sliceEvidence?: SliceEvidenceData | null;
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
  nodes: THREE.Points | null;
  focusNodes: THREE.InstancedMesh;
  overlays: Map<string, THREE.Object3D>;
  contextMesh: THREE.Mesh | null;
  axesHelper: THREE.AxesHelper;
  selectedHalo: THREE.Mesh;
  selectedMesh: THREE.Mesh;
  reset: () => void;
  focus: (strutId: number) => void;
  setView: (preset: "front" | "side" | "top") => void;
  setContextClip: (fraction: number) => void;
  setNominalIsolated: (isolated: boolean) => void;
  setLightingIntensity: (intensity: number) => void;
};

function colorNumber(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number.parseInt(value.replace("#", ""), 16);
  return Number.isFinite(parsed) ? parsed : fallback;
}

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

function roundPointTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const context = canvas.getContext("2d");
  if (context) {
    const gradient = context.createRadialGradient(24, 20, 4, 32, 32, 30);
    gradient.addColorStop(0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.28, "rgba(255,255,255,0.95)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 64, 64);
  }
  return new THREE.CanvasTexture(canvas);
}

function junctionPoints(
  positionsZyx: number[],
  color: number,
): THREE.Points | null {
  if (!positionsZyx.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.BufferAttribute(zyxToXyz(positionsZyx), 3),
  );
  const material = new THREE.PointsMaterial({
    color,
    map: roundPointTexture(),
    size: 6.0,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.9,
    alphaTest: 0.05,
    depthWrite: false,
  });
  return new THREE.Points(geometry, material);
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

function selectedCylinder(
  color = 0x0066cc,
  opacity = 0.98,
  renderOrder = 8,
): THREE.Mesh {
  const geometry = new THREE.CylinderGeometry(1, 1, 1, 16);
  const material = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.5,
    transparent: true,
    opacity,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.visible = false;
  mesh.renderOrder = renderOrder;
  return mesh;
}

function selectedHaloCylinder(): THREE.Mesh {
  const geometry = new THREE.CylinderGeometry(1, 1, 1, 16);
  const material = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    depthWrite: false,
    opacity: 0.82,
    side: THREE.BackSide,
    transparent: true,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.visible = false;
  mesh.renderOrder = 7;
  return mesh;
}

function focusedNodeMesh(color: number): THREE.InstancedMesh {
  const geometry = new THREE.SphereGeometry(1, 12, 8);
  const material = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.16,
    roughness: 0.46,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, 64);
  mesh.count = 0;
  mesh.renderOrder = 9;
  return mesh;
}

function updateFocusedNodes(
  mesh: THREE.InstancedMesh,
  data: LatticeViewerData,
  strutId: number | null,
  radius: number,
): void {
  if (strutId === null) {
    mesh.count = 0;
    return;
  }
  const strutIndex = data.nominalStrutIds.indexOf(strutId);
  if (
    strutIndex < 0 ||
    data.nominalJunctionIds.length !== data.nominalStrutIds.length * 2
  ) {
    mesh.count = 0;
    return;
  }
  const first = data.nominalJunctionIds[strutIndex * 2];
  const second = data.nominalJunctionIds[strutIndex * 2 + 1];
  const selectedEndpoints = [first, second];
  const positionById = new Map<number, number>();
  data.junctionIds.forEach((id, index) => positionById.set(id, index));
  let instance = 0;
  selectedEndpoints.forEach((junctionId) => {
    const positionIndex = positionById.get(junctionId);
    if (positionIndex === undefined || instance >= 64) {
      return;
    }
    const xyz = zyxToXyz(
      data.junctionPositionsZyx.slice(positionIndex * 3, positionIndex * 3 + 3),
    );
    const matrix = new THREE.Matrix4().compose(
      new THREE.Vector3(xyz[0], xyz[1], xyz[2]),
      new THREE.Quaternion(),
      new THREE.Vector3(radius, radius, radius),
    );
    mesh.setMatrixAt(instance, matrix);
    instance += 1;
  });
  mesh.count = instance;
  mesh.instanceMatrix.needsUpdate = true;
}

function colorSelectedCylinder(
  mesh: THREE.Mesh,
  label: string | null,
  palette: PaletteData,
): void {
  const color = colorNumber(
    palette.candidates[label ?? ""],
    colorNumber(palette.nominal, 0x215290),
  );
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
    materials.forEach((material) => {
      const pointMaterial = material as THREE.PointsMaterial;
      pointMaterial.map?.dispose();
      material.dispose();
    });
  });
}

function formatMetric(value: number | string | null | undefined, digits = 3): string {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  return typeof value === "number" ? value.toFixed(digits) : String(value);
}

type StoredCameraPose = {
  selectedStrutId: number | null;
  position: number[];
  quaternion: number[];
  target: number[];
};

function cameraStorageKey(sceneRevision: string): string {
  return `lattice-camera:${sceneRevision}`;
}

function saveCameraPose(
  sceneRevision: string,
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  selectedStrutId: number | null,
): void {
  const pose: StoredCameraPose = {
    selectedStrutId,
    position: camera.position.toArray(),
    quaternion: camera.quaternion.toArray(),
    target: controls.target.toArray(),
  };
  try {
    window.sessionStorage.setItem(
      cameraStorageKey(sceneRevision),
      JSON.stringify(pose),
    );
  } catch {
    // Browser privacy settings may disable session storage.
  }
}

function restoreCameraPose(
  sceneRevision: string,
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  selectedStrutId: number | null,
): boolean {
  try {
    const serialized = window.sessionStorage.getItem(
      cameraStorageKey(sceneRevision),
    );
    if (!serialized) {
      return false;
    }
    const pose = JSON.parse(serialized) as StoredCameraPose;
    if (
      pose.selectedStrutId !== selectedStrutId ||
      pose.position.length !== 3 ||
      pose.quaternion.length !== 4 ||
      pose.target.length !== 3
    ) {
      return false;
    }
    camera.position.fromArray(pose.position);
    camera.quaternion.fromArray(pose.quaternion);
    controls.target.fromArray(pose.target);
    controls.update();
    return true;
  } catch {
    return false;
  }
}

const SliceEvidencePanel: FC<{
  evidence: SliceEvidenceData | null | undefined;
  palette: PaletteData;
  onClose: () => void;
}> = ({ evidence, palette, onClose }): ReactElement => {
  const [showSegmentation, setShowSegmentation] = useState(true);
  const [showExpected, setShowExpected] = useState(true);
  const [showObservedCenterline, setShowObservedCenterline] = useState(false);
  const [activeAxis, setActiveAxis] = useState("z");
  const [viewMode, setViewMode] = useState<"exact" | "slab">("slab");
  const [brightness, setBrightness] = useState(1);
  const [contrast, setContrast] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [frameIndex, setFrameIndex] = useState(2);

  useEffect(() => {
    if (!evidence) {
      return;
    }
    setActiveAxis(evidence.preferredView);
    setViewMode("slab");
    setShowObservedCenterline(false);
    setBrightness(1);
    setContrast(1);
    setZoom(1);
    setFrameIndex(Math.floor(evidence.positionOffsetsVox.length / 2));
  }, [evidence?.preferredView, evidence?.strutId]);

  if (!evidence) {
    return (
      <aside className="evidence-panel evidence-empty">
        <strong>Linked CT slices</strong>
        <p>
          Select one of the 60 analyzed struts to load registered axial,
          coronal, and sagittal evidence.
        </p>
      </aside>
    );
  }

  const measurements = evidence.measurements;
  const activeView =
    evidence.views.find((view) => view.axis === activeAxis) ?? evidence.views[0];
  const boundedFrameIndex = Math.min(
    Math.max(frameIndex, 0),
    Math.max(activeView.frames.length - 1, 0),
  );
  const activeFrame = activeView.frames[boundedFrameIndex];
  const activeLayers = activeFrame.modes[viewMode];
  const alignment = measurements.alignment_error_vox;
  return (
    <aside className="evidence-panel">
      <div className="evidence-heading">
        <div>
          <span>Exploratory candidate</span>
          <strong>Strut {evidence.strutId}</strong>
        </div>
        <div className="evidence-heading-actions">
          <span
            className={`candidate-pill candidate-${evidence.candidateLabel}`}
            style={{ backgroundColor: evidence.candidateColor }}
          >
            {LABEL_TITLES[evidence.candidateLabel] ?? evidence.candidateLabel}
          </span>
          <button type="button" className="close-evidence" onClick={onClose}>
            Close evidence
          </button>
        </div>
      </div>
      <div className="evidence-metrics">
        <div><span>Material coverage</span><strong>{formatMetric(measurements.occupancy)}</strong></div>
        <div><span>Longest gap</span><strong>{formatMetric(measurements.gap_fraction)}</strong></div>
        <div><span>Alignment</span><strong>{alignment == null ? "Not available" : `${formatMetric(alignment, 2)} vox`}</strong></div>
        <div><span>Diameter</span><strong>{measurements.diameter_median_um == null ? "Not eligible" : `${formatMetric(measurements.diameter_median_um, 1)} µm`}</strong></div>
      </div>
      <div className="slice-orientation-tabs" aria-label="CT slice orientation">
        {evidence.views.map((view) => (
          <button
            type="button"
            key={view.axis}
            className={activeView.axis === view.axis ? "active" : ""}
            aria-pressed={activeView.axis === view.axis}
            onClick={() => {
              setActiveAxis(view.axis);
              setFrameIndex(Math.floor(view.frames.length / 2));
            }}
          >
            {view.title}
          </button>
        ))}
      </div>
      <div className="view-mode-tabs" aria-label="CT rendering mode">
        <button
          type="button"
          className={viewMode === "slab" ? "active" : ""}
          aria-pressed={viewMode === "slab"}
          onClick={() => setViewMode("slab")}
        >
          Enhanced {evidence.slabThicknessVox}-voxel slab
        </button>
        <button
          type="button"
          className={viewMode === "exact" ? "active" : ""}
          aria-pressed={viewMode === "exact"}
          onClick={() => setViewMode("exact")}
        >
          Exact slice
        </button>
      </div>
      <div className="layer-toggles" aria-label="CT evidence layers">
        <label>
          <input type="checkbox" checked={showSegmentation} onChange={(event) => setShowSegmentation(event.target.checked)} />
          <span style={{ backgroundColor: palette.segmentation }} /> Material boundary
        </label>
        <label>
          <input type="checkbox" checked={showExpected} onChange={(event) => setShowExpected(event.target.checked)} />
          <span style={{ backgroundColor: palette.expectedCenterline }} /> Expected strut
        </label>
        <label title="Medial axis of thresholded material near the expected strut; supporting evidence only.">
          <input
            type="checkbox"
            checked={showObservedCenterline}
            onChange={(event) => setShowObservedCenterline(event.target.checked)}
          />
          <span style={{ backgroundColor: palette.observedCenterline }} />
          Observed centerline
        </label>
      </div>
      <div className="image-adjustments" aria-label="CT image adjustments">
        <label className="slice-position-control">
          Slice position
          <input
            type="range"
            min="0"
            max={Math.max(activeView.frames.length - 1, 0)}
            step="1"
            value={boundedFrameIndex}
            onChange={(event) => setFrameIndex(Number(event.target.value))}
          />
          <span>{activeFrame.indexLabel}</span>
        </label>
        <label>
          Brightness
          <input
            type="range"
            min="0.65"
            max="1.65"
            step="0.05"
            value={brightness}
            onChange={(event) => setBrightness(Number(event.target.value))}
          />
        </label>
        <label>
          Contrast
          <input
            type="range"
            min="0.65"
            max="1.8"
            step="0.05"
            value={contrast}
            onChange={(event) => setContrast(Number(event.target.value))}
          />
        </label>
        <label>
          Context zoom
          <input
            type="range"
            min="1"
            max="2.4"
            step="0.1"
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
          />
        </label>
      </div>
      <figure className="slice-card slice-card-primary">
        <div className="slice-title">
          <strong>{activeView.title}</strong>
          <span>
            {activeFrame.indexLabel}
            {viewMode === "slab" && activeView.axis !== "longitudinal"
              ? ` · slab ${activeFrame.slabBoundsGlobal[0]}–${activeFrame.slabBoundsGlobal[1] - 1}`
              : ""}
          </span>
        </div>
        <div className="slice-stack" style={{ "--slice-zoom": zoom } as CSSProperties}>
          <img
            className="slice-raw"
            src={activeLayers.rawDataUrl}
            alt={`${activeView.title} ${viewMode} CT crop`}
            style={{
              filter: `brightness(${brightness}) contrast(${contrast})`,
            }}
          />
          {showSegmentation && (
            <img src={activeLayers.segmentationBoundaryDataUrl} alt="" />
          )}
          {showObservedCenterline && (
            <img src={activeLayers.observedCenterlineDataUrl} alt="" />
          )}
          {showExpected && (
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <line
                x1={activeView.expectedLine[0] * 100}
                y1={activeView.expectedLine[1] * 100}
                x2={activeView.expectedLine[2] * 100}
                y2={activeView.expectedLine[3] * 100}
                stroke={palette.expectedCenterline}
                strokeWidth="2.4"
                strokeDasharray="5 3"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={activeView.expectedLine[0] * 100}
                cy={activeView.expectedLine[1] * 100}
                r="1.6"
                fill={palette.expectedCenterline}
                stroke="#1D1D1F"
                strokeWidth="0.6"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={activeView.expectedLine[2] * 100}
                cy={activeView.expectedLine[3] * 100}
                r="1.6"
                fill={palette.expectedCenterline}
                stroke="#1D1D1F"
                strokeWidth="0.6"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
          )}
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <circle
              cx={activeView.focusPoint[0] * 100}
              cy={activeView.focusPoint[1] * 100}
              r="2.2"
              fill={evidence.candidateColor}
              stroke="#FFFFFF"
              strokeWidth="1.2"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        </div>
        <figcaption>{activeView.xAxis} · {activeView.yAxis}</figcaption>
      </figure>
      <p className="slice-mode-note">
        {viewMode === "slab"
          ? `${evidence.slabThicknessVox}-voxel maximum projection with enhanced local contrast.`
          : "Single-voxel plane with linear local contrast."}
      </p>
      <p className="evidence-reason">{String(measurements.prediction_reason)}</p>
      <p className="evidence-scope">
        Focus: {evidence.focusMethod}. The material boundary and observed
        centerline are supporting visual evidence, not ground-truth validation.
      </p>
    </aside>
  );
};

export const LatticeViewer: FC<ViewerProps> = ({
  data,
  setStateValue,
}): ReactElement => {
  const shellRef = useRef<HTMLDivElement>(null);
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
  const [showNodes, setShowNodes] = useState(true);
  const [showContext, setShowContext] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [contextOpacity, setContextOpacity] = useState(isUnitCell ? 0.82 : 0.1);
  const [contextClip, setContextClip] = useState(0);
  const [lightingIntensity, setLightingIntensity] = useState(1);
  const [isolateTarget, setIsolateTarget] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(Boolean(data.sliceEvidence));
  const [visibleLabels, setVisibleLabels] = useState<Set<string>>(
    () =>
      new Set(
        isUnitCell
          ? presentLabels
          : presentLabels.filter((label) => label !== "intact"),
      ),
  );
  const [selectedStrutId, setSelectedStrutId] = useState<number | null>(
    data.selectedStrutId ?? data.targetStrutId ?? null,
  );
  const [selectionSource, setSelectionSource] = useState<
    "canvas" | "dropdown" | "search" | "external" | null
  >(null);
  const [candidateFilter, setCandidateFilter] = useState("all");
  const [searchValue, setSearchValue] = useState("");
  const [searchError, setSearchError] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fallbackExpanded, setFallbackExpanded] = useState(false);
  const analyzedIdsRef = useRef(data.analyzedStrutIds);
  const selectedStrutRef = useRef<number | null>(selectedStrutId);
  const setStateValueRef = useRef(setStateValue);
  const lastFocusedStrutRef = useRef<number | null>(null);
  const visibleLabelsRef = useRef(visibleLabels);
  const scrollPositionRef = useRef(0);
  analyzedIdsRef.current = data.analyzedStrutIds;
  selectedStrutRef.current = selectedStrutId;
  setStateValueRef.current = setStateValue;
  visibleLabelsRef.current = visibleLabels;

  useEffect(() => {
    if (data.sliceEvidence) {
      setEvidenceOpen(true);
    }
  }, [data.sliceEvidence?.strutId]);

  const selectedLabel = useMemo(() => {
    if (selectedStrutId === null) {
      return null;
    }
    const index = data.analyzedStrutIds.indexOf(selectedStrutId);
    return index < 0
      ? null
      : data.labelNames[data.analyzedLabelCodes[index]] ?? null;
  }, [data.analyzedLabelCodes, data.analyzedStrutIds, data.labelNames, selectedStrutId]);

  const filteredStruts = useMemo(
    () =>
      data.analyzedStrutIds.filter((_, index) => {
        const label = data.labelNames[data.analyzedLabelCodes[index]];
        return candidateFilter === "all" || candidateFilter === label;
      }),
    [
      candidateFilter,
      data.analyzedLabelCodes,
      data.analyzedStrutIds,
      data.labelNames,
    ],
  );

  const selectStrut = useCallback(
    (
      strutId: number,
      source: "canvas" | "dropdown" | "search" | "external",
    ): void => {
      if (!analyzedIdsRef.current.includes(strutId)) {
        setSearchError(`Strut ${strutId} is not in the analyzed 60.`);
        return;
      }
      setSearchError("");
      setSelectedStrutId(strutId);
      setEvidenceOpen(true);
      selectedStrutRef.current = strutId;
      setSelectionSource(source);
      setStateValueRef.current("selected_strut_id", strutId);
      sceneHandles.current?.focus(strutId);
      lastFocusedStrutRef.current = strutId;
    },
    [],
  );

  const closeEvidence = useCallback((): void => {
    setEvidenceOpen(false);
    if (isUnitCell) {
      return;
    }
    setSelectedStrutId(null);
    selectedStrutRef.current = null;
    setSelectionSource(null);
    setSearchError("");
    setStateValueRef.current("selected_strut_id", null);
    lastFocusedStrutRef.current = null;
  }, [isUnitCell]);

  useEffect(() => {
    const next = data.selectedStrutId ?? data.targetStrutId ?? null;
    const previous = selectedStrutRef.current;
    setSelectedStrutId(next);
    selectedStrutRef.current = next;
    if (next !== previous) {
      setStateValueRef.current("selected_strut_id", next);
    }
    if (next !== null && lastFocusedStrutRef.current !== next) {
      setSelectionSource("external");
      setEvidenceOpen(true);
      sceneHandles.current?.focus(next);
      lastFocusedStrutRef.current = next;
    }
  }, [data.selectedStrutId, data.targetStrutId]);

  useEffect(() => {
    const onFullscreenChange = (): void => {
      const active = document.fullscreenElement === shellRef.current;
      setIsFullscreen(active);
      if (active) {
        setFallbackExpanded(false);
      } else if (!fallbackExpanded) {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
      }
      window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [fallbackExpanded]);

  useEffect(() => {
    const handles = sceneHandles.current;
    if (!handles) {
      return;
    }
    handles.nominal.visible = showNominal;
    if (handles.nodes) {
      handles.nodes.visible = showNodes;
    }
    handles.focusNodes.visible = showNodes;
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
    handles.setContextClip(contextClip);
    handles.setNominalIsolated(isolateTarget);
    handles.setLightingIntensity(lightingIntensity);
  }, [
    contextClip,
    contextOpacity,
    isolateTarget,
    lightingIntensity,
    showAxes,
    showContext,
    showNodes,
    showNominal,
    visibleLabels,
  ]);

  useEffect(() => {
    const handles = sceneHandles.current;
    if (!handles) {
      return;
    }
    if (selectedStrutId === null) {
      handles.selectedHalo.visible = false;
      handles.selectedMesh.visible = false;
      updateFocusedNodes(handles.focusNodes, data, null, 0);
      return;
    }
    const segment = segmentForStrut(data, selectedStrutId);
    if (segment) {
      positionCylinder(handles.selectedHalo, segment, isUnitCell ? 2.55 : 3.2);
      colorSelectedCylinder(handles.selectedMesh, selectedLabel, data.palette);
      positionCylinder(handles.selectedMesh, segment, isUnitCell ? 2.15 : 2.65);
      updateFocusedNodes(
        handles.focusNodes,
        data,
        selectedStrutId,
        isUnitCell ? 2.5 : 3.2,
      );
    }
  }, [
    data,
    isUnitCell,
    selectedLabel,
    selectedStrutId,
  ]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const validSchema =
      data.coordinateOrder === "zyx" &&
      ((isUnitCell && data.schemaVersion === 2) ||
        (!isUnitCell && data.schemaVersion === 2));
    if (!validSchema) {
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
    renderer.localClippingEnabled = true;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.replaceChildren(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    const nominalColor = colorNumber(data.palette.nominal, 0x215290);
    const nominal = isUnitCell
      ? cylinderSegments(
          data.nominalPositionsZyx,
          data.nominalStrutIds,
          nominalColor,
          1.0,
          0.94,
        )
      : lineSegments(data.nominalPositionsZyx, nominalColor, 0.8);
    nominal.name = "Nominal lattice";
    scene.add(nominal);

    const nodes = junctionPoints(
      data.junctionPositionsZyx,
      colorNumber(data.palette.nodes, 0x8fb9e3),
    );
    if (nodes) {
      nodes.name = "Registered junction nodes";
      scene.add(nodes);
    }
    const focusNodes = focusedNodeMesh(
      colorNumber(data.palette.nodes, 0x8fb9e3),
    );
    scene.add(focusNodes);

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
          colorNumber(data.palette.candidates[label], nominalColor),
          isUnitCell ? 1.85 : label === "intact" ? 1.3 : 2.1,
          label === "intact" ? 0.75 : 1,
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
      const hasTexture =
        data.xrayVertexTexture.length === data.xrayVerticesZyx.length / 3;
      if (hasTexture) {
        const lowColor = new THREE.Color(0x29445f);
        const highColor = new THREE.Color(0xdce6ef);
        const colors = new Float32Array(data.xrayVertexTexture.length * 3);
        data.xrayVertexTexture.forEach((value, index) => {
          const color = lowColor.clone().lerp(highColor, Math.min(Math.max(value, 0), 1));
          colors[index * 3] = color.r;
          colors[index * 3 + 1] = color.g;
          colors[index * 3 + 2] = color.b;
        });
        geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      }
      const material = new THREE.MeshStandardMaterial({
        color: hasTexture
          ? 0xffffff
          : colorNumber(data.palette.ctContext, 0xb8c0c8),
        vertexColors: hasTexture,
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

    const selectedHalo = selectedHaloCylinder();
    const selectedMesh = selectedCylinder();
    scene.add(selectedHalo);
    scene.add(selectedMesh);
    if (selectedStrutId !== null) {
      const segment = segmentForStrut(data, selectedStrutId);
      if (segment) {
        positionCylinder(selectedHalo, segment, isUnitCell ? 2.55 : 3.2);
        colorSelectedCylinder(selectedMesh, selectedLabel, data.palette);
        positionCylinder(selectedMesh, segment, isUnitCell ? 2.15 : 2.65);
        updateFocusedNodes(
          focusNodes,
          data,
          selectedStrutId,
          isUnitCell ? 2.5 : 3.2,
        );
      }
    }

    const hemisphereLight = new THREE.HemisphereLight(0xffffff, 0x6b7785, 1.9);
    scene.add(hemisphereLight);
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
      if (sceneHandles.current) {
        saveCameraPose(
          data.sceneRevision,
          camera,
          controls,
          selectedStrutRef.current,
        );
      }
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
      const distance = Math.max(
        start.distanceTo(end) * (isUnitCell ? 2.2 : 3.5),
        75,
      );
      controls.target.copy(midpoint);
      camera.position
        .copy(midpoint)
        .add(new THREE.Vector3(distance, distance, distance));
      controls.update();
      saveCameraPose(
        data.sceneRevision,
        camera,
        controls,
        selectedStrutRef.current,
      );
    };
    const setView = (preset: "front" | "side" | "top"): void => {
      const distance = radius * 1.9;
      controls.target.copy(center);
      if (preset === "front") {
        camera.up.set(0, 1, 0);
        camera.position.set(center.x, center.y, center.z + distance);
      } else if (preset === "side") {
        camera.up.set(0, 1, 0);
        camera.position.set(center.x + distance, center.y, center.z);
      } else {
        camera.up.set(0, 0, -1);
        camera.position.set(center.x, center.y + distance, center.z);
      }
      camera.lookAt(center);
      controls.update();
      saveCameraPose(
        data.sceneRevision,
        camera,
        controls,
        selectedStrutRef.current,
      );
    };
    const setContextClip = (fraction: number): void => {
      if (!contextMesh) {
        return;
      }
      const material = contextMesh.material as THREE.MeshStandardMaterial;
      const normalized = Math.min(Math.max(fraction, 0), 1);
      material.clippingPlanes =
        normalized <= 0
          ? []
          : [
              new THREE.Plane(
                new THREE.Vector3(-1, 0, 0),
                bounds.max.x - size.x * normalized,
              ),
            ];
      material.needsUpdate = true;
    };
    const setNominalIsolated = (isolated: boolean): void => {
      const material = (nominal as THREE.Mesh | THREE.LineSegments)
        .material as THREE.Material & { opacity: number };
      material.transparent = true;
      material.opacity = isolated ? 0.14 : isUnitCell ? 0.94 : 0.8;
      material.depthWrite = !isolated;
      material.needsUpdate = true;
    };
    const setLightingLevel = (intensity: number): void => {
      const normalized = Math.min(Math.max(intensity, 0.35), 1.8);
      hemisphereLight.intensity = 1.9 * normalized;
      keyLight.intensity = 2.2 * normalized;
      fillLight.intensity = 1.0 * normalized;
    };
    reset();
    const restoredPose = restoreCameraPose(
      data.sceneRevision,
      camera,
      controls,
      selectedStrutRef.current,
    );
    if (!restoredPose && selectedStrutRef.current !== null) {
      focus(selectedStrutRef.current);
      lastFocusedStrutRef.current = selectedStrutRef.current;
    } else if (restoredPose) {
      lastFocusedStrutRef.current = selectedStrutRef.current;
    }

    sceneHandles.current = {
      camera,
      controls,
      nominal,
      nodes,
      focusNodes,
      overlays,
      contextMesh,
      axesHelper,
      selectedHalo,
      selectedMesh,
      reset,
      focus,
      setView,
      setContextClip,
      setNominalIsolated,
      setLightingIntensity: setLightingLevel,
    };
    nominal.visible = showNominal;
    if (nodes) {
      nodes.visible = showNodes;
    }
    focusNodes.visible = showNodes;
    axesHelper.visible = showAxes;
    if (contextMesh) {
      contextMesh.visible = showContext;
      (contextMesh.material as THREE.MeshStandardMaterial).opacity = contextOpacity;
    }
    setContextClip(contextClip);
    setNominalIsolated(isolateTarget);
    setLightingLevel(lightingIntensity);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerStart: { x: number; y: number } | null = null;
    let controlsMoved = false;
    const onControlsStart = (): void => {
      controlsMoved = false;
    };
    const onControlsChange = (): void => {
      if (pointerStart) {
        controlsMoved = true;
      }
    };
    const onControlsEnd = (): void => {
      saveCameraPose(
        data.sceneRevision,
        camera,
        controls,
        selectedStrutRef.current,
      );
    };
    controls.addEventListener("start", onControlsStart);
    controls.addEventListener("change", onControlsChange);
    controls.addEventListener("end", onControlsEnd);
    const onPointerDown = (event: PointerEvent): void => {
      pointerStart = { x: event.clientX, y: event.clientY };
      controlsMoved = false;
    };
    const onPointerUp = (event: PointerEvent): void => {
      if (
        !pointerStart ||
        controlsMoved ||
        Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 8
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
        .filter(
          ([label, overlay]) =>
            visibleLabelsRef.current.has(label) && overlay.visible,
        )
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
      controls.removeEventListener("start", onControlsStart);
      controls.removeEventListener("change", onControlsChange);
      controls.removeEventListener("end", onControlsEnd);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      controls.dispose();
      disposeObject(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [data.sceneRevision, isUnitCell, selectStrut]);

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

  const runSearch = (): void => {
    const parsed = Number.parseInt(searchValue.trim(), 10);
    if (!Number.isInteger(parsed)) {
      setSearchError("Enter a numeric analyzed strut ID.");
      return;
    }
    selectStrut(parsed, "search");
  };

  const exitExpandedView = useCallback(async (): Promise<void> => {
    setIsFullscreen(false);
    setFallbackExpanded(false);
    document.documentElement.style.overflow = "";
    document.body.style.overflow = "";
    window.scrollTo({ top: scrollPositionRef.current, behavior: "auto" });
    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen();
      } catch {
        // State is already cleared; native fullscreen may have ended independently.
      }
    }
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (
        event.key === "Escape" &&
        (fallbackExpanded ||
          isFullscreen ||
          document.fullscreenElement)
      ) {
        event.preventDefault();
        void exitExpandedView();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [exitExpandedView, fallbackExpanded, isFullscreen]);

  const toggleFullscreen = async (): Promise<void> => {
    const shell = shellRef.current;
    if (!shell) {
      return;
    }
    if (document.fullscreenElement || fallbackExpanded || isFullscreen) {
      await exitExpandedView();
      return;
    }
    scrollPositionRef.current = window.scrollY;
    try {
      await shell.requestFullscreen();
      const enteredFullscreen = document.fullscreenElement === shell;
      setIsFullscreen(enteredFullscreen);
      setFallbackExpanded(!enteredFullscreen);
      if (!enteredFullscreen) {
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
      }
    } catch {
      setFallbackExpanded(true);
      document.documentElement.style.overflow = "hidden";
      document.body.style.overflow = "hidden";
    }
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  };

  return (
    <div
      ref={shellRef}
      className={`viewer-shell ${fallbackExpanded ? "viewer-expanded" : ""}`}
    >
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
        <div className="header-actions">
          <span className="mapping">{data.selectedMapping}</span>
          <button
            type="button"
            className={
              isFullscreen || fallbackExpanded ? "fullscreen-exit" : ""
            }
            onClick={(event) => {
              event.stopPropagation();
              void toggleFullscreen();
            }}
          >
            {isFullscreen
              ? "Exit full screen (Esc)"
              : fallbackExpanded
                ? "Exit expanded view (Esc)"
                : "Full screen"}
          </button>
        </div>
      </div>
      <div className="viewer-toolbar" aria-label="Lattice display controls">
        <label>
          <input
            type="checkbox"
            checked={showNominal}
            onChange={(event) => setShowNominal(event.target.checked)}
          />
          Blue nominal lattice
        </label>
        <label>
          <input
            type="checkbox"
            checked={showNodes}
            onChange={(event) => setShowNodes(event.target.checked)}
          />
          Junction nodes
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
              style={{ backgroundColor: data.palette.candidates[label] }}
            />
            {LABEL_TITLES[label] ?? label}
          </label>
        ))}
        {isUnitCell && (
          <label>
            <input
              type="checkbox"
              checked={isolateTarget}
              onChange={(event) => setIsolateTarget(event.target.checked)}
            />
            Fade neighboring struts
          </label>
        )}
      </div>
      <div className="viewer-settings">
        {!isUnitCell && (
          <>
            <label>
              Candidate class
              <select
                aria-label="Candidate class"
                value={candidateFilter}
                onChange={(event) => {
                  const nextFilter = event.target.value;
                  setCandidateFilter(nextFilter);
                  if (
                    selectedStrutId !== null &&
                    nextFilter !== "all" &&
                    selectedLabel !== nextFilter
                  ) {
                    closeEvidence();
                  }
                }}
              >
                <option value="all">All analyzed</option>
                {presentLabels.map((label) => (
                  <option key={label} value={label}>
                    {LABEL_TITLES[label] ?? label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Strut number
              <select
                aria-label="Analyzed strut"
                value={
                  selectedStrutId !== null && filteredStruts.includes(selectedStrutId)
                    ? selectedStrutId
                    : ""
                }
                onChange={(event) => {
                  if (event.target.value) {
                    selectStrut(Number(event.target.value), "dropdown");
                  }
                }}
              >
                <option value="">Select a strut</option>
                {filteredStruts.map((strutId) => {
                  const index = data.analyzedStrutIds.indexOf(strutId);
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
            <label className="strut-search">
              Find analyzed ID
              <input
                type="search"
                inputMode="numeric"
                value={searchValue}
                placeholder="e.g. 16082"
                onChange={(event) => setSearchValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    runSearch();
                  }
                }}
              />
              <button type="button" onClick={runSearch}>Go</button>
            </label>
          </>
        )}
        <label>
          CT opacity
          <input
            type="range"
            min="0"
            max={isUnitCell ? "1" : "0.45"}
            step="0.01"
            value={contextOpacity}
            disabled={!showContext}
            onChange={(event) => setContextOpacity(Number(event.target.value))}
          />
          <span>{Math.round(contextOpacity * 100)}%</span>
        </label>
        {isUnitCell && (
          <>
            <label>
              CT cutaway
              <input
                type="range"
                min="0"
                max="0.8"
                step="0.05"
                value={contextClip}
                disabled={!showContext}
                onChange={(event) => setContextClip(Number(event.target.value))}
              />
              <span>{Math.round(contextClip * 100)}%</span>
            </label>
            <label>
              Surface lighting
              <input
                type="range"
                min="0.35"
                max="1.8"
                step="0.05"
                value={lightingIntensity}
                onChange={(event) => setLightingIntensity(Number(event.target.value))}
              />
              <span>{lightingIntensity.toFixed(2)}×</span>
            </label>
          </>
        )}
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
                lastFocusedStrutRef.current = selectedStrutId;
              }
            }}
          >
            Recenter selected strut
          </button>
          {isUnitCell && (
            <>
              <button type="button" onClick={() => sceneHandles.current?.setView("front")}>
                Front
              </button>
              <button type="button" onClick={() => sceneHandles.current?.setView("side")}>
                Side
              </button>
              <button type="button" onClick={() => sceneHandles.current?.setView("top")}>
                Top
              </button>
            </>
          )}
          {!evidenceOpen && data.sliceEvidence && (
            <button type="button" onClick={() => setEvidenceOpen(true)}>
              Show CT evidence
            </button>
          )}
        </div>
      </div>
      {isUnitCell && (
        <div className="surface-scope">
          CT-derived surface texture — qualitative visualization, not calibrated
          roughness measurement.
        </div>
      )}
      {searchError && <div className="search-error">{searchError}</div>}
      <div
        className={`viewer-body ${
          !evidenceOpen || !data.sliceEvidence ? "viewer-body-no-evidence" : ""
        }`}
      >
        <div
          ref={containerRef}
          className="viewer-canvas"
          role="img"
          aria-label="Interactive registered three-dimensional lattice geometry"
        />
        {evidenceOpen && data.sliceEvidence && (
          <SliceEvidencePanel
            evidence={data.sliceEvidence}
            palette={data.palette}
            onClose={closeEvidence}
          />
        )}
      </div>
      <div className="viewer-footer">
        <span>
          Drag to rotate · Scroll to zoom · Right-drag to pan · Click an analyzed strut
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
