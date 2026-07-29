import {
  FrontendRenderer,
  FrontendRendererArgs,
} from "@streamlit/component-v2-lib";
import { StrictMode } from "react";
import { createRoot, Root } from "react-dom/client";

import { LatticeViewer, LatticeViewerData, LatticeViewerState } from "./LatticeViewer";
import "./styles.css";

const roots = new WeakMap<FrontendRendererArgs["parentElement"], Root>();

const renderer: FrontendRenderer<LatticeViewerState, LatticeViewerData> = (args) => {
  const rootElement = args.parentElement.querySelector(".lattice-viewer-root");
  if (!rootElement) {
    throw new Error("Lattice viewer root element was not found");
  }

  let root = roots.get(args.parentElement);
  if (!root) {
    root = createRoot(rootElement);
    roots.set(args.parentElement, root);
  }

  root.render(
    <StrictMode>
      <LatticeViewer data={args.data} setStateValue={args.setStateValue} />
    </StrictMode>,
  );

  return () => {
    const mountedRoot = roots.get(args.parentElement);
    if (mountedRoot) {
      mountedRoot.unmount();
      roots.delete(args.parentElement);
    }
  };
};

export default renderer;
