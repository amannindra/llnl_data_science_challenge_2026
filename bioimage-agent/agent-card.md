---
language:
  - en
tags:
  - project:genesis
  - team:LLNL
  - type:agent
  - science:bio-imaging
  - science:biology
  - risk:general
license: BSD-3-Clause-Commercial
license_name: BSD-3-Clause-Commercial
license_link: LICENSE

base_model: N/A
datasets:
  - eval/data # Evaluation datasets for testing MCP tools with napari
metrics:
  - task_success_rate # Per-skill task completion
  - tool_call_correctness # Correct tool invocation and parameters

agent_card:
  name: "BioImage-Agent"
  description: "A lightweight napari plugin that exposes the viewer over MCP (Message-Control Protocol) via a Python socket server, enabling AI agents to control napari remotely for bioimage analysis tasks."
  provider:
    organization: "Lawrence Livermore National Laboratory"
    url: "https://github.com/LLNL/bioimage-agent"
  version: "1.0.0"
  documentation_url: "https://github.com/LLNL/bioimage-agent/blob/main/README.md"
  protocol_version: "0.3.0"
  preferred_transport: "MCP"
  capabilities:
    streaming: false
    push_notifications: false
    state_transition_history: false

authentication:
  schemes:
    - "None"
  credentials: ""

  default_input_modes:
    - "text/plain"
    - "application/json"
  default_output_modes:
    - "text/plain"
    - "application/json"
    - "image/jpeg"

  skills:
    - id: "file_operations"
      name: "File Operations"
      description: "Load image files (TIFF, PNG, ND2, NPZ, etc.) into napari and save layer data to disk"
      tags: ["io", "file", "load", "save"]
      examples: ["Load my_image.tif", "Save layer as output.tiff"]
      input_modes: ["text/plain"]
      output_modes: ["text/plain"]

    - id: "layer_management"
      name: "Layer Management"
      description: "List, remove, show/hide, and manage layers in the napari viewer"
      tags: ["layers", "visibility", "management"]
      examples: ["List all layers", "Remove layer 'segmentation'", "Hide the labels layer"]
      input_modes: ["text/plain"]
      output_modes: ["application/json", "text/plain"]

    - id: "visualization_controls"
      name: "Visualization Controls"
      description: "Control colormap, opacity, blending, contrast, gamma, interpolation, and view modes (2D/3D)"
      tags: ["visualization", "rendering", "display"]
      examples: ["Set colormap to viridis", "Auto-adjust contrast", "Switch to 3D view"]
      input_modes: ["text/plain"]
      output_modes: ["text/plain"]

    - id: "camera_controls"
      name: "Camera Controls"
      description: "Adjust camera position, zoom, rotation angles, and reset to default view"
      tags: ["camera", "navigation", "zoom"]
      examples: ["Zoom in", "Reset camera", "Rotate to angle 45"]
      input_modes: ["application/json"]
      output_modes: ["application/json"]

    - id: "annotations"
      name: "Annotations and Overlays"
      description: "Add points, shapes, labels, surfaces, and vector fields to the viewer"
      tags: ["annotation", "points", "shapes", "labels", "3d"]
      examples: ["Add point markers at coordinates", "Draw rectangle overlay", "Add segmentation mask"]
      input_modes: ["application/json"]
      output_modes: ["text/plain"]

    - id: "measurements"
      name: "Measurement and Analysis"
      description: "Measure distances, get layer statistics (min, max, mean, std), and crop layer data"
      tags: ["measurement", "analysis", "statistics"]
      examples: ["Measure distance between two points", "Get statistics for layer 'image'"]
      input_modes: ["application/json"]
      output_modes: ["application/json"]

    - id: "multidimensional_navigation"
      name: "Multi-dimensional Navigation"
      description: "Navigate time series, z-stacks, and channel dimensions; play animations"
      tags: ["time", "z-stack", "channels", "animation"]
      examples: ["Go to timestep 10", "Set z-slice to 50", "Switch to channel 2"]
      input_modes: ["text/plain"]
      output_modes: ["text/plain"]

    - id: "channel_management"
      name: "Channel Management"
      description: "Get channel info, split multi-channel layers, and merge layers into multi-channel datasets"
      tags: ["channels", "split", "merge"]
      examples: ["Split RGB into separate channels", "Merge channels into composite"]
      input_modes: ["application/json"]
      output_modes: ["application/json", "text/plain"]

    - id: "screenshot"
      name: "Screenshot Capture"
      description: "Capture the current viewport as a JPG image"
      tags: ["screenshot", "capture", "image"]
      examples: ["Take a screenshot", "Capture current view"]
      input_modes: ["text/plain"]
      output_modes: ["image/jpeg"]

extensions:
  agent_runtime:
    framework: "FastMCP"
    service_endpoint: "tcp://127.0.0.1:64908"
    rate_limits: ""
    logging: "File logging to ~/napari_logs/bioimage_agent_socket.log"
    memory: "Stateless - communicates with napari via TCP socket"

---

# BioImage-Agent

A lightweight napari plugin that exposes the viewer over **MCP (Message-Control Protocol)** via a Python socket server. Built on top of **FastMCP**, it enables external MCP-speaking clients—such as autonomous AI agents running on Claude or OpenAI—to **call napari's public API remotely** for bioimage analysis and visualization tasks.

*Last Updated*: **2026-02-09**

## Developed by

- Haichao Miao (miao1@llnl.gov) - Lawrence Livermore National Laboratory
- Shusen Liu (liu42@llnl.gov) - Lawrence Livermore National Laboratory

## Contributed by

Lawrence Livermore National Laboratory (LLNL)

## Agent Changelog

+ **2026-02-09** Initial public version with full MCP tool suite for napari control

## Agent short description

MCP-based agent that enables AI systems to remotely control napari viewers for bioimage visualization, analysis, and annotation tasks via a socket interface.

## Agent description

BioImage-Agent provides a bridge between AI agents and the napari bioimage visualization platform:

1. The agent runs as an MCP server that receives requests from AI clients (Claude Desktop, OpenAI, etc.)
2. Requests are forwarded to a live napari GUI session over a TCP socket connection
3. The agent supports 37+ tools for complete control over image loading, visualization, annotation, measurement, and multi-dimensional data navigation
4. Results and screenshots are returned to the AI agent for analysis and decision-making

## Underlying model(s)

- Primary model(s): N/A (This is an agent that can be controlled by any LLM)
- The agent works with Claude, GPT-4, and other LLM providers via MCP protocol

## Inputs and outputs

### Default interaction modes

- defaultInputModes: `["text/plain", "application/json"]`
- defaultOutputModes: `["text/plain", "application/json", "image/jpeg"]`

### Skills

**File Operations**
- **Skill ID**: file_operations
- **Tools**: `open_file`, `save_layers`, `get_layer_data`
- **Description**: Load image files (TIFF, PNG, ND2, NPZ) and save layer data

**Layer Management**
- **Skill ID**: layer_management
- **Tools**: `list_layers`, `remove_layer`, `set_layer_visibility`
- **Description**: Manage layers in the napari viewer

**Visualization Controls**
- **Skill ID**: visualization_controls
- **Tools**: `set_colormap`, `set_opacity`, `set_blending`, `set_contrast_limits`, `auto_contrast`, `set_gamma`, `set_interpolation`, `toggle_view`, `iso_contour`, `set_view_mode`, `set_scale_bar`, `set_axis_labels`
- **Description**: Control all aspects of image visualization

**Camera Controls**
- **Skill ID**: camera_controls
- **Tools**: `set_camera`, `get_camera`, `reset_camera`
- **Description**: Navigate the viewport

**Annotations**
- **Skill ID**: annotations
- **Tools**: `add_points`, `add_shapes`, `add_labels`, `add_surface`, `add_vectors`
- **Description**: Add overlays and annotations

**Measurements**
- **Skill ID**: measurements
- **Tools**: `measure_distance`, `get_layer_statistics`, `crop_layer`
- **Description**: Analyze and measure image data

**Multi-dimensional Navigation**
- **Skill ID**: multidimensional_navigation
- **Tools**: `set_timestep`, `set_channel`, `set_z_slice`, `play_animation`, `get_dims_info`
- **Description**: Navigate time series, z-stacks, and channels

**Channel Management**
- **Skill ID**: channel_management
- **Tools**: `get_channel_info`, `split_channels`, `merge_channels`
- **Description**: Manage multi-channel image data

**Screenshot**
- **Skill ID**: screenshot
- **Tools**: `screenshot`
- **Description**: Capture viewport images

### Tools and permissions

| Tool | Purpose | Side Effects | Permissions |
|------|---------|--------------|-------------|
| `open_file` | Load image files into napari | Reads files from disk | File read access |
| `remove_layer` | Remove a layer from viewer | Modifies viewer state | None |
| `toggle_view` | Switch between 2D/3D view | Modifies viewer state | None |
| `iso_contour` | Enable iso-surface rendering | Modifies layer properties | None |
| `screenshot` | Capture current viewport | Writes temp file | Temp file write |
| `list_layers` | Get layer information | None (read-only) | None |
| `set_colormap` | Change layer colormap | Modifies layer properties | None |
| `set_opacity` | Adjust layer transparency | Modifies layer properties | None |
| `set_blending` | Set layer blend mode | Modifies layer properties | None |
| `set_contrast_limits` | Adjust contrast range | Modifies layer properties | None |
| `auto_contrast` | Auto-adjust contrast | Modifies layer properties | None |
| `set_gamma` | Adjust gamma correction | Modifies layer properties | None |
| `set_interpolation` | Set zoom interpolation | Modifies layer properties | None |
| `set_timestep` | Navigate to time point | Modifies viewer state | None |
| `get_dims_info` | Get dimension information | None (read-only) | None |
| `set_camera` | Adjust camera view | Modifies viewer state | None |
| `get_camera` | Get camera settings | None (read-only) | None |
| `reset_camera` | Reset to default view | Modifies viewer state | None |
| `add_points` | Add point markers | Creates new layer | None |
| `add_shapes` | Add shape overlays | Creates new layer | None |
| `add_labels` | Add segmentation masks | Creates new layer | None |
| `add_surface` | Add 3D mesh surface | Creates new layer | None |
| `add_vectors` | Add vector field | Creates new layer | None |
| `save_layers` | Save layers to file | Writes files to disk | File write access |
| `get_layer_data` | Extract layer data | None (read-only) | None |
| `set_scale_bar` | Show/hide scale bar | Modifies viewer state | None |
| `set_axis_labels` | Set axis labels | Modifies viewer state | None |
| `set_view_mode` | Switch 2D/3D mode | Modifies viewer state | None |
| `set_layer_visibility` | Show/hide layer | Modifies layer properties | None |
| `measure_distance` | Calculate distance | None (read-only) | None |
| `get_layer_statistics` | Get layer stats | None (read-only) | None |
| `crop_layer` | Crop layer data | Creates new layer | None |
| `set_channel` | Switch channel | Modifies viewer state | None |
| `set_z_slice` | Navigate z-slice | Modifies viewer state | None |
| `play_animation` | Animate time series | Modifies viewer state | None |
| `get_channel_info` | Get channel info | None (read-only) | None |
| `split_channels` | Split multi-channel layer | Creates new layers | None |
| `merge_channels` | Merge layers | Creates new layer | None |

### Service endpoint and discovery

- Base URL: `tcp://127.0.0.1:64908`
- MCP Server Script: `src/mcp_server/mcp_server.py`
- napari Socket Plugin: `src/napari_socket/`

## Runtime Infrastructure

This agent runs as a local MCP server process that communicates with a napari viewer instance via TCP socket.

### Hardware

No special hardware required. Runs on standard desktop/laptop systems that can run napari.

### Software

**Requirements:**
| Package | Version |
|---------|---------|
| Python | ≥ 3.9 |
| napari | ≥ 0.5 |
| fastmcp | ≥ 0.3 |
| Qt/PyQt5 | Installed with napari |

**Installation:**
```bash
# Install napari
python -m pip install "napari[all]"

# Install socket server plugin
cd bioimage-agent/src/napari_socket
pip install -e .
```

## Papers and Scientific Outputs

N/A - Initial release

## Agent License

BSD 3-Clause with Commercial License alternative. See [LICENSE](LICENSE) for details.

LLNL-CODE-2011142

## Contact Info and Card Authors

- Haichao Miao - miao1@llnl.gov
- Shusen Liu - liu42@llnl.gov

# Intended Uses

## Intended Use

This agent is designed for:

1. **AI-assisted bioimage analysis**: Enabling LLMs to load, visualize, and analyze microscopy data
2. **Automated visualization workflows**: Creating reproducible visualization pipelines controlled by AI
3. **Interactive research assistant**: Helping scientists explore and annotate bioimage data through natural language
4. **Multi-dimensional data navigation**: AI-guided exploration of time series, z-stacks, and multi-channel data

### Primary Intended Users

- Bioimage researchers and scientists working with microscopy data
- AI/ML developers building bioimage analysis pipelines
- Research teams integrating AI assistants into visualization workflows

### Mission Relevance

This work supports DOE scientific computing and data visualization workflows, particularly in biological sciences and light source research facilities.

## Out-of-Scope Use Cases

- Real-time clinical diagnostics (not validated for medical use)
- Autonomous decision-making without human oversight
- Processing of classified or sensitive data
- High-throughput production pipelines requiring guaranteed response times

# How to use

## Install Instructions

1. **Install napari:**
   ```bash
   python -m pip install "napari[all]"
   ```

2. **Install Socket Server Plugin:**
   ```bash
   cd bioimage-agent/src/napari_socket
   pip install -e .
   ```

3. **Install MCP tools in your MCP Client** (e.g., Claude Desktop):
   Add to your Claude Desktop config (`Developer → Open App Config File`):
   ```json
   "Napari": {
     "command": ".../python.exe",
     "args": [".../bioimage-agent/src/mcp_server/mcp_server.py"],
     "env": {}
   }
   ```

## Agent configuration

- **System prompt**: Embedded in `mcp_server.py` via FastMCP `instructions` parameter
- **Socket configuration**: Host/port configurable via command-line arguments
- **Logging**: Logs written to `~/napari_logs/bioimage_agent_socket.log`

## Invocation / integration

1. **Launch napari:**
   ```bash
   napari
   ```

2. **Start the socket server:**
   Choose **Plugins → Socket Server → Start Server** in napari

3. **Use via MCP client:**
   The agent will be available through your configured MCP client (Claude Desktop, etc.)

# Code snippets of how to use the agent

**Example: Load and visualize a TIFF file**
```
User: Load the file microscopy_data.tif and show me a screenshot

Agent: [Calls open_file("microscopy_data.tif")]
Agent: [Calls screenshot()]
Agent: Here's the loaded image...
```

**Example: Adjust visualization**
```
User: Make the image more visible with auto-contrast and use the viridis colormap

Agent: [Calls auto_contrast("microscopy_data")]
Agent: [Calls set_colormap("microscopy_data", "viridis")]
Agent: Done! The contrast has been auto-adjusted and colormap changed to viridis.
```

**Example: 3D visualization**
```
User: Show this as a 3D volume with iso-surface rendering

Agent: [Calls toggle_view()]
Agent: [Calls iso_contour()]
Agent: [Calls screenshot()]
Agent: Here's the 3D iso-surface view...
```

# Limitations

## Risks

### Agent-specific risk notes (tool use)

1. **File system access**: The `open_file` and `save_layers` tools can read/write files. Ensure file paths are validated and restricted to appropriate directories.

2. **No authentication**: The socket server runs without authentication by default. It should only be exposed on localhost.

3. **Resource consumption**: Loading very large files could consume significant memory in the napari viewer.

4. **Prompt injection**: Tool descriptions are passed to the LLM. Ensure tool outputs are sanitized to prevent injection attacks.

## Limitations

- **Local only**: Currently only supports local napari instances via TCP socket
- **Single session**: One MCP server connects to one napari viewer at a time
- **No undo**: Layer modifications cannot be automatically undone
- **Limited file formats**: Relies on napari's built-in readers for file format support
- **Animation**: The `play_animation` tool has limited functionality (sets range but doesn't play continuously)

# Agent evaluation details

The `eval/` directory contains evaluation tools:

- **MCP Client** (`general_mcp_client.py`): Supports Claude, OpenAI, and LiteLLM endpoints
- **Promptfoo Config** (`test_general.yaml`): Automated evaluation of core functionality

**Evaluation metrics:**
- Task success criteria per skill
- Tool-call correctness
- Screenshot accuracy using LLM rubric scoring

```bash
cd eval
promptfoo eval -c test_general.yaml
```

# More Information

- **Demo Video**: [Watch on YouTube](https://youtu.be/WM3gkBIt6A8)
- **GitHub Repository**: https://github.com/LLNL/bioimage-agent
- **Interactive Testing**: Use `tests/test_napari_manager_socket.ipynb` for exploration
