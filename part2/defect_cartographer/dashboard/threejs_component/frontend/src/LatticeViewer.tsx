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
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";


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
  analyzedLabelCodes: number[];
  analyzedRawLabelCodes: number[];
  labelNames: string[];
  rawLabelNames: string[];
  xrayVerticesZyx: number[];
  xrayFaces: number[];
  xrayVertexTexture: number[];
  selectedStrutId?: number | null;
  sliceEvidence?: SliceEvidenceData | null;
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
  uncertain: "Uncertain",
};

type CandidateOption = {
  id: number;
  label: string;
  rawLabel: string;
  display: string;
};

const SELECTOR_ROW_HEIGHT = 36;
const SELECTOR_VIEWPORT_HEIGHT = 216;
const SELECTOR_OVERSCAN = 4;

type SceneHandles = {
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  sceneCenter: THREE.Vector3;
  nominal: THREE.Object3D;
  nodes: THREE.Object3D | null;
  focusNodes: THREE.InstancedMesh;
  overlays: Map<string, THREE.Object3D>;
  contextMesh: THREE.Mesh | null;
  axesHelper: THREE.AxesHelper;
  selectedHalo: THREE.Mesh;
  selectedMesh: THREE.Mesh;
  reset: () => void;
  focus: (strutId: number) => void;
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
  strutIds: number[] = [],
  width = 3,
): LineSegments2 {
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions(zyxToXyz(positionsZyx));
  const material = new LineMaterial({
    color,
    linewidth: width,
    worldUnits: false,
    transparent: opacity < 1,
    opacity,
    alphaToCoverage: true,
  });
  const lines = new LineSegments2(geometry, material);
  lines.computeLineDistances();
  lines.userData.strutIds = strutIds;
  return lines;
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

function segmentForStrut(
  data: LatticeViewerData,
  strutId: number,
): number[] | null {
  const index = data.nominalStrutIds.indexOf(strutId);
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
  if (strutIndex < 0) {
    mesh.count = 0;
    return;
  }
  const segment = data.nominalPositionsZyx.slice(
    strutIndex * 6,
    strutIndex * 6 + 6,
  );
  const endpointsXyz = zyxToXyz(segment);
  for (let instance = 0; instance < 2; instance += 1) {
    const matrix = new THREE.Matrix4().compose(
      new THREE.Vector3(
        endpointsXyz[instance * 3],
        endpointsXyz[instance * 3 + 1],
        endpointsXyz[instance * 3 + 2],
      ),
      new THREE.Quaternion(),
      new THREE.Vector3(radius, radius, radius),
    );
    mesh.setMatrixAt(instance, matrix);
  }
  mesh.count = 2;
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
  const presentLabels = useMemo(
    () =>
      data.labelNames.filter((_, code) =>
        data.analyzedLabelCodes.some((value) => value === code),
      ),
    [data.analyzedLabelCodes, data.labelNames],
  );
  const initialCandidateFilter = useMemo(() => {
    try {
      const stored = window.sessionStorage.getItem(
        `lattice-candidate-filter:${data.sceneRevision}`,
      );
      return stored && (stored === "all" || presentLabels.includes(stored))
        ? stored
        : "all";
    } catch {
      return "all";
    }
  }, [data.sceneRevision, presentLabels]);
  const [showNominal, setShowNominal] = useState(true);
  const [showNodes, setShowNodes] = useState(true);
  const [showContext, setShowContext] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [contextOpacity, setContextOpacity] = useState(0.1);
  const [evidenceOpen, setEvidenceOpen] = useState(Boolean(data.sliceEvidence));
  const [candidateFilter, setCandidateFilter] = useState(initialCandidateFilter);
  const [visibleLabels, setVisibleLabels] = useState<Set<string>>(() =>
    initialCandidateFilter === "all"
      ? new Set(presentLabels)
      : new Set([initialCandidateFilter]),
  );
  const [selectedStrutId, setSelectedStrutId] = useState<number | null>(
    data.selectedStrutId ?? null,
  );
  const [selectionSource, setSelectionSource] = useState<
    "canvas" | "search" | "external" | null
  >(null);
  const [selectorQuery, setSelectorQuery] = useState("");
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [selectorScrollTop, setSelectorScrollTop] = useState(0);
  const [searchValue, setSearchValue] = useState("");
  const [searchError, setSearchError] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fallbackExpanded, setFallbackExpanded] = useState(false);
  const [sceneReady, setSceneReady] = useState(false);
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
    try {
      window.sessionStorage.setItem(
        `lattice-candidate-filter:${data.sceneRevision}`,
        candidateFilter,
      );
    } catch {
      // Session persistence is optional; filtering still works in-memory.
    }
  }, [candidateFilter, data.sceneRevision]);

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

  const candidateOptions = useMemo<CandidateOption[]>(() => {
    const query = selectorQuery.trim().toLowerCase();
    const options: CandidateOption[] = [];
    data.analyzedStrutIds.forEach((id, index) => {
      const label = data.labelNames[data.analyzedLabelCodes[index]] ?? "uncertain";
      if (candidateFilter !== "all" && label !== candidateFilter) {
        return;
      }
      const rawLabel =
        data.rawLabelNames[data.analyzedRawLabelCodes[index]] ?? label;
      const display = `${id} · ${rawLabel}`;
      if (query && !display.toLowerCase().includes(query)) {
        return;
      }
      options.push({ id, label, rawLabel, display });
    });
    return options;
  }, [
    candidateFilter,
    data.analyzedLabelCodes,
    data.analyzedRawLabelCodes,
    data.analyzedStrutIds,
    data.labelNames,
    data.rawLabelNames,
    selectorQuery,
  ]);

  const selectorStart = Math.max(
    0,
    Math.floor(selectorScrollTop / SELECTOR_ROW_HEIGHT) - SELECTOR_OVERSCAN,
  );
  const selectorEnd = Math.min(
    candidateOptions.length,
    selectorStart +
      Math.ceil(SELECTOR_VIEWPORT_HEIGHT / SELECTOR_ROW_HEIGHT) +
      SELECTOR_OVERSCAN * 2,
  );
  const visibleCandidateOptions = candidateOptions.slice(selectorStart, selectorEnd);

  const selectStrut = useCallback(
    (
      strutId: number,
      source: "canvas" | "search" | "external",
    ): void => {
      if (!analyzedIdsRef.current.includes(strutId)) {
        setSearchError(`Strut ${strutId} is not in the classified full-lattice result.`);
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
    setSelectedStrutId(null);
    selectedStrutRef.current = null;
    setSelectionSource(null);
    setSearchError("");
    setStateValueRef.current("selected_strut_id", null);
    lastFocusedStrutRef.current = null;
  }, []);

  useEffect(() => {
    const next = data.selectedStrutId ?? null;
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
  }, [data.selectedStrutId]);

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
    if (handles.nodes) {
      handles.nodes.visible = showNodes;
    }
    handles.focusNodes.visible = showNodes;
    handles.axesHelper.visible = showAxes;
    handles.overlays.forEach((overlay, label) => {
      overlay.visible =
        visibleLabels.has(label) && (label !== "intact" || showNominal);
    });
    if (handles.contextMesh) {
      handles.contextMesh.visible = showContext;
      const material = handles.contextMesh.material as THREE.MeshStandardMaterial;
      material.opacity = contextOpacity;
      material.needsUpdate = true;
    }
  }, [
    contextOpacity,
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
      positionCylinder(handles.selectedHalo, segment, 3.2);
      colorSelectedCylinder(handles.selectedMesh, selectedLabel, data.palette);
      positionCylinder(handles.selectedMesh, segment, 2.65);
      updateFocusedNodes(
        handles.focusNodes,
        data,
        selectedStrutId,
        3.2,
      );
    }
  }, [
    data,
    selectedLabel,
    selectedStrutId,
  ]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    setSceneReady(false);
    const validSchema =
      data.coordinateOrder === "zyx" && data.schemaVersion === 3;
    if (!validSchema) {
      container.textContent = "Unsupported lattice scene schema.";
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);
    const camera = new THREE.PerspectiveCamera(
      42,
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
    const latticeGeometry = new THREE.Group();
    latticeGeometry.name = "Classified lattice line buffers";
    scene.add(latticeGeometry);
    const nominalIndexById = new Map(
      data.nominalStrutIds.map((strutId, index) => [strutId, index]),
    );
    data.labelNames.forEach((label, code) => {
      const positions: number[] = [];
      const strutIds: number[] = [];
      data.analyzedLabelCodes.forEach((value, index) => {
        if (value === code) {
          const strutId = data.analyzedStrutIds[index];
          const nominalIndex = nominalIndexById.get(strutId);
          if (nominalIndex !== undefined) {
            positions.push(
              ...data.nominalPositionsZyx.slice(
                nominalIndex * 6,
                nominalIndex * 6 + 6,
              ),
            );
            strutIds.push(strutId);
          }
        }
      });
      if (positions.length) {
        const overlay = lineSegments(
          positions,
          colorNumber(data.palette.candidates[label], nominalColor),
          1,
          strutIds,
          label === "intact" ? 1.6 : label === "uncertain" ? 2.8 : 4,
        );
        overlay.name = `${label} classified struts`;
        overlay.visible =
          visibleLabels.has(label) && (label !== "intact" || showNominal);
        overlays.set(label, overlay);
        latticeGeometry.add(overlay);
      }
    });
    const nominal = overlays.get("intact") ?? latticeGeometry;

    let contextMesh: THREE.Mesh | null = null;
    if (data.xrayVerticesZyx.length && data.xrayFaces.length) {
      const geometry = new THREE.BufferGeometry();
      const contextPositions = zyxToXyz(data.xrayVerticesZyx);
      geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(contextPositions, 3),
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
          const color = lowColor
            .clone()
            .lerp(highColor, Math.min(Math.max(value, 0), 1));
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
        positionCylinder(selectedHalo, segment, 3.2);
        colorSelectedCylinder(selectedMesh, selectedLabel, data.palette);
        positionCylinder(selectedMesh, segment, 2.65);
        updateFocusedNodes(
          focusNodes,
          data,
          selectedStrutId,
          3.2,
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

    const bounds = new THREE.Box3().setFromObject(latticeGeometry);
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
        start.distanceTo(end) * 3.5,
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
      sceneCenter: center,
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
    };
    if (nodes) {
      nodes.visible = showNodes;
    }
    focusNodes.visible = showNodes;
    axesHelper.visible = showAxes;
    if (contextMesh) {
      contextMesh.visible = showContext;
      (contextMesh.material as THREE.MeshStandardMaterial).opacity = contextOpacity;
    }

    const raycaster = new THREE.Raycaster();
    raycaster.params.Line.threshold = 3.0;
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
      const segmentIndex = hit.faceIndex ?? 0;
      const strutId = ids[segmentIndex];
      if (strutId !== undefined) {
        selectStrut(strutId, "canvas");
      }
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);

    let animationFrame = 0;
    let firstFrame = true;
    const animate = (): void => {
      controls.update();
      renderer.render(scene, camera);
      if (firstFrame) {
        firstFrame = false;
        setSceneReady(true);
      }
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
  }, [data.sceneRevision, selectStrut]);

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
            {` · ${data.analyzedStrutIds.length.toLocaleString()} classified overlays`}
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
          Yellow intact / nominal
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
      </div>
      <div className="viewer-settings">
        <label>
          Candidate class
          <select
            aria-label="Candidate class"
            value={candidateFilter}
            onChange={(event) => {
              const nextFilter = event.target.value;
              setCandidateFilter(nextFilter);
              setSelectorQuery("");
              setSelectorScrollTop(0);
              setSelectorOpen(false);
              setVisibleLabels(
                nextFilter === "all"
                  ? new Set(presentLabels)
                  : new Set([nextFilter]),
              );
              if (
                selectedStrutId !== null &&
                nextFilter !== "all" &&
                selectedLabel !== nextFilter
              ) {
                closeEvidence();
              }
            }}
          >
            <option value="all">All classified</option>
            {presentLabels.map((label) => (
              <option key={label} value={label}>
                {LABEL_TITLES[label] ?? label}
              </option>
            ))}
          </select>
        </label>
        <div
          className="candidate-combobox"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setSelectorOpen(false);
            }
          }}
        >
          <label htmlFor="candidate-strut-selector">Strut number</label>
          <input
            id="candidate-strut-selector"
            type="search"
            role="combobox"
            aria-autocomplete="list"
            aria-controls="candidate-strut-options"
            aria-expanded={selectorOpen}
            value={selectorQuery}
            placeholder="Type or browse IDs"
            onFocus={() => setSelectorOpen(true)}
            onChange={(event) => {
              setSelectorQuery(event.target.value);
              setSelectorScrollTop(0);
              setSelectorOpen(true);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && candidateOptions.length === 1) {
                event.preventDefault();
                const option = candidateOptions[0];
                setSelectorQuery(option.display);
                setSelectorOpen(false);
                selectStrut(option.id, "search");
              } else if (event.key === "Escape") {
                setSelectorOpen(false);
              }
            }}
          />
          {selectorOpen && (
            <div className="candidate-options-shell">
              <div className="candidate-options-count">
                {candidateOptions.length.toLocaleString()} matching struts
              </div>
              <div
                id="candidate-strut-options"
                className="candidate-options"
                role="listbox"
                style={{ height: SELECTOR_VIEWPORT_HEIGHT }}
                onScroll={(event) =>
                  setSelectorScrollTop(event.currentTarget.scrollTop)
                }
              >
                <div
                  className="candidate-options-spacer"
                  style={{ height: candidateOptions.length * SELECTOR_ROW_HEIGHT }}
                >
                  {visibleCandidateOptions.map((option, visibleIndex) => {
                    const absoluteIndex = selectorStart + visibleIndex;
                    return (
                      <button
                        type="button"
                        role="option"
                        aria-selected={selectedStrutId === option.id}
                        className="candidate-option"
                        key={option.id}
                        style={{
                          height: SELECTOR_ROW_HEIGHT,
                          transform: `translateY(${absoluteIndex * SELECTOR_ROW_HEIGHT}px)`,
                        }}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          setSelectorQuery(option.display);
                          setSelectorOpen(false);
                          selectStrut(option.id, "search");
                        }}
                      >
                        <strong>{option.id}</strong>
                        <span>{option.rawLabel}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
        <label className="strut-search">
          Find classified ID
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
                lastFocusedStrutRef.current = selectedStrutId;
              }
            }}
          >
            Recenter selected strut
          </button>
          {!evidenceOpen && data.sliceEvidence && (
            <button type="button" onClick={() => setEvidenceOpen(true)}>
              Show CT evidence
            </button>
          )}
        </div>
      </div>
      {searchError && <div className="search-error">{searchError}</div>}
      <div
        className={`viewer-body ${
          !evidenceOpen || !data.sliceEvidence ? "viewer-body-no-evidence" : ""
        }`}
      >
        {!sceneReady && (
          <div className="viewer-loading" role="status" aria-live="polite">
            <span />
            Loading registered 3D evidence…
          </div>
        )}
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
