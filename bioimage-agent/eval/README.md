# Napari Agent Benchmark

This repository provides a structured benchmark for evaluating **agentic systems** that interact with [napari](https://napari.org/), a Python-based viewer for multidimensional scientific images.  
The benchmark is designed to test correctness, compositionality, and scientific utility across three levels of increasing complexity.  

---

## Benchmark Levels 

### 1. **Actions**
At this level, the benchmark evaluates whether the agent can correctly call **individual napari functions** with the right parameters.  
- Example tasks:
  - Load image files using `open_file()` with correct file paths
  - Set colormaps using `set_colormap()` with appropriate colormap names (viridis, plasma, hot, cool, etc.)
  - Adjust layer opacity using `set_opacity()` with values between 0.0 and 1.0
  - Change blending modes using `set_blending()` (opaque, translucent, additive, minimum)
  - Auto-adjust contrast using `auto_contrast()` or set specific limits with `set_contrast_limits()`
  - Switch between 2D and 3D views using `toggle_view()`
  - Take screenshots using `screenshot()`
  - Get layer information using `list_layers()` and `get_layer_statistics()`
  - Add point annotations using `add_points()` with coordinate arrays
  - Add shape annotations using `add_shapes()` with geometry data
  - Measure distances using `measure_distance()` between two points
  - Control camera settings using `get_camera()`, `set_camera()`, and `reset_camera()`
  - Manage layer visibility using `set_layer_visibility()`
  - Handle errors gracefully when loading non-existent files or operating on missing layers


---

### 2. **Workflows**
This level tests whether the agent can compose a **sequence of operations** into a coherent workflow.  
- Example tasks:
  - **Multi-dimensional Data Navigation**: Load multi-channel data, navigate through z-stacks using `set_z_slice()`, switch between channels using `set_channel()`, and explore time series using `set_timestep()`
  - **Basic Visualization Techniques**: Create multi-channel overlays with different colormaps, test various blending modes, adjust opacity and contrast, and apply different interpolation methods
  - **Advanced Rendering**: Set up 3D volume rendering, enable iso-surface rendering, create Maximum Intensity Projections (MIPs), and combine different rendering modes
  - **Camera Control**: Perform complex camera navigation sequences including zoom, pan, rotation, and view mode switching with proper state management
  - **Analysis Workflows**: Combine measurement tools, statistical analysis, data export, and annotation creation into coherent analysis pipelines


---

### 3. **Scientific Tasks**
At the highest level, the benchmark evaluates whether the agent can complete **real scientific workflows** that reflect research practices across domains. These tasks combine visualization, annotation, and analysis toward a scientific goal.  


#### **Iso-surface Extraction for Cell Analysis** (`eval_iso_surface_extraction.yaml`)
- Load cell microscopy data and switch to 3D visualization
- Enable iso-surface rendering with iterative threshold adjustment
- Use visual feedback from screenshots to optimize surface extraction parameters
- Test different threshold values (0.1, 0.3, 0.6, 0.8) and select optimal settings
- Apply different colormaps and opacity settings for enhanced visualization
- Perform cell counting and quality assessment of extracted surfaces
- Navigate camera angles to inspect 3D structures from multiple perspectives

#### **Scene Understanding and Cell Counting** (`eval_scene_understanding.yaml`)
- Load multi-channel cell data with green and magenta colormaps
- Count cells by specific colors (green, magenta, yellow/overlapping)
- Analyze cell size distribution, spatial arrangement, and shape characteristics
- Compare color intensities and provide comprehensive scene analysis
- Test consistency across different zoom levels and 2D/3D views
- Generate detailed summaries of visual observations and quantitative measurements

#### **Figure Recreation from Published Papers** (`eval_figure_recreation.yaml`)
- Load BBBC012 C. elegans infection dataset (3-channel microscopy data)
- Apply appropriate colormaps and blending modes to match target figures
- Optimize contrast and gamma settings for scientific visualization
- Compare recreated figures with reference images from assertions folder
- Demonstrate ability to reproduce published scientific visualizations

#### Microscopy & Cell Biology
- Track cell migration across a time-lapse dataset.  
- Perform colocalization analysis of two fluorescent markers.  
- Reconstruct 3D organelle morphology.  
- Annotate cell lineage divisions over time.  

#### Medical Imaging
- Segment a tumor in MRI/CT data and compute volumetrics.  
- Validate AI-predicted lesion detection against ground truth.  
- Align and visualize PET and MRI scans together.  
- Annotate surgical planning structures in 3D.  
- Explore gigapixel histopathology slides and mark regions of interest.  

#### Materials Science & Additive Manufacturing
- Detect and quantify defects in CT-scanned lattice structures.  
- Identify material phases by overlaying SEM + EDS data.  
- Compute porosity from 3D reconstructions.  
- Annotate crack propagation over stress-test datasets.  
- Measure grain size and orientation distributions.  

#### Environmental & Earth Sciences
- Visualize and segment layers in CT-scanned rock cores.  
- Explore hyperspectral signatures and classify vegetation.  
- Compare volumetric flow simulations with experimental PIV data.  
- Annotate plankton organisms in microscopy datasets.  
- Align optical and hyperspectral remote sensing images.  

#### Cross-Domain
- Integrate multi-modal datasets in a single visualization.  
- Generate annotation datasets for ML training.  
- Perform interactive hypothesis testing with thresholds and segmentations.  
- Extract quantitative features (size, shape, intensity).  
- Export and share annotated datasets for collaborative review.  

---

## Usage

### Prerequisites

1. **Install napari and dependencies**:
   ```bash
   pip install napari napari-socket
   ```

2. **Start napari with the socket plugin**:
   ```bash
   python eval/start_napari.py
   ```

3. **Install promptfoo** (for running evaluations):
   ```bash
   npm install -g promptfoo
   ```

### Running Evaluations

The benchmark uses [promptfoo](https://promptfoo.dev/) to run evaluations against different AI models. Each evaluation level can be run independently.

#### **Actions Level (Individual Functions)**
```bash
# Run basic napari function tests
promptfoo eval -c eval_claude.yaml -t tasks/0_actions/eval_basic_napari_functions.yaml
```

#### **Workflows Level (Sequences of Operations)**
```bash
# Run multi-dimensional data navigation tests
promptfoo eval -c eval_claude.yaml -t tasks/1_workflows/eval_multi_dim_viewing.yaml

# Run basic visualization workflow tests
promptfoo eval -c eval_claude.yaml -t tasks/1_workflows/eval_visualization_workflows.yaml

# Run advanced rendering tests
promptfoo eval -c eval_claude.yaml -t tasks/1_workflows/eval_complex_visualization.yaml

# Run camera control tests
promptfoo eval -c eval_claude.yaml -t tasks/1_workflows/eval_camera_control_workflows.yaml

# Run analysis workflow tests
promptfoo eval -c eval_claude.yaml -t tasks/1_workflows/eval_analysis_workflows.yaml
```

#### **Scientific Tasks Level (End-to-End Workflows)**
```bash
# Run iso-surface extraction tests
promptfoo eval -c eval_claude.yaml -t tasks/2_scientific_tasks/eval_iso_surface_extraction.yaml

# Run scene understanding tests
promptfoo eval -c eval_claude.yaml -t tasks/2_scientific_tasks/eval_scene_understanding.yaml

# Run figure recreation tests
promptfoo eval -c eval_claude.yaml -t tasks/2_scientific_tasks/eval_figure_recreation.yaml
```

#### **Running All Evaluations**
```bash
# Run all evaluation levels
promptfoo eval -c eval_claude.yaml -t tasks/
```

### Configuration Files

- **`eval_claude.yaml`**: Configuration for Claude Sonnet 4 evaluations
- **`eval_livai.yaml`**: Configuration for LLNL's LivaAI (GPT-4o) evaluations

### Evaluation Results

Results are saved in the `promptfoo` output directory and include:
- Success/failure rates for each test
- Accuracy of parameters and function calls
- Task completion quality scores
- Screenshot comparisons for visual tasks
- Detailed logs of agent interactions

### Customizing Evaluations

To add new tests or modify existing ones:
1. Create new YAML files in the appropriate `tasks/` subdirectory
2. Follow the existing test format with `vars`, `assert`, and `options` sections
3. Use the provided data in the `data/` directory or add your own datasets

---

## Citation

If you use this benchmark in your work, please cite:

