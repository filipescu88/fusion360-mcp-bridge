# Fusion 360 MCP Bridge

Python bridge for Autodesk Fusion's **official local MCP server**, plus example parametric generators for Fusion API.

> Verified with Fusion MCP at `http://127.0.0.1:27182/mcp`.

Flow:

**external Python generator → `fusion_bridge.py` → Fusion MCP → Fusion API → geometry in Fusion**

## Features

- dynamic MCP tool discovery,
- support for current `fusion_mcp_execute` dispatcher,
- execution of generated Fusion API scripts with `run(_context)`,
- offline generator workflow,
- laser-cut plate generator,
- box-joint / finger-joint 2D generator,
- verified box-joint 3D assembly generator,
- offline tests and GitHub Actions CI.

## Requirements

- Autodesk Fusion desktop,
- `Fusion MCP Server` enabled in Fusion,
- Python 3.10+,
- Python package `mcp>=2,<3`.

Default endpoint:

```text
http://127.0.0.1:27182/mcp
```

## Installation

```powershell
git clone https://github.com/filipescu88/fusion360-mcp-bridge.git
cd fusion360-mcp-bridge

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Or run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

## Enable Fusion MCP

In Fusion:

`Preferences → General → API → Fusion MCP Server`

Then test the bridge:

```powershell
python fusion_bridge.py doctor
```

The current official dispatcher is detected as:

```text
fusion_mcp_execute
featureType="script", object.script
```

List all discovered tools:

```powershell
python fusion_bridge.py tools -v
```

## Generator contract

A generator is a normal external Python module:

```python
def generate(params: dict[str, str]) -> str:
    ...
```

It returns a complete Fusion-side script containing:

```python
def run(_context: str):
    ...
```

Run any generator with:

```powershell
python fusion_bridge.py run path/to/generator.py
```

## Included generators

### Test block

```powershell
python fusion_bridge.py run generators/generator_test_block.py
```

Creates a simple 40 × 30 × 10 mm body by default.

### Laser plate

```powershell
python fusion_bridge.py run generators/generator_laser_plate.py
```

Default geometry:

- 120 × 80 mm plate,
- 4 × Ø5 mm mounting holes,
- 40 × 12 mm center cutout,
- optional geometric kerf compensation.

Example:

```powershell
python fusion_bridge.py run generators/generator_laser_plate.py `
  --param width_mm=200 `
  --param height_mm=120 `
  --param hole_diameter_mm=6 `
  --param kerf_mm=0.15
```

Export from Fusion with `Sketch → Export DXF`.

### Box Joint V3 — 2D cut layout

```powershell
python fusion_bridge.py run generators/generator_box_joint_3mm_v3.py
```

V3 generates six closed panel profiles and uses actual Fusion `SketchPoint` connections when chaining line segments. This avoids the topological closure problem that can occur when consecutive segments only share identical numeric coordinates.

The default 120 × 80 × 60 mm / 3 mm plywood test produced:

```text
OK: BOX_JOINT_V3 | panels=6 | lines=440 | profiles=6
```

Example:

```powershell
python fusion_bridge.py run generators/generator_box_joint_3mm_v3.py `
  --param box_width_mm=200 `
  --param box_depth_mm=120 `
  --param box_height_mm=80 `
  --param material_mm=3 `
  --param kerf_mm=0.15 `
  --param clearance_mm=0.05
```

### Box Joint V4 — 2D layout + assembled 3D

```powershell
python fusion_bridge.py run generators/generator_box_joint_3d_v4.py
```

V4 creates:

- flat cut layout for DXF,
- separate Fusion components,
- one extrusion per panel,
- assembled 3D box preview.

V4 was verified on a real Fusion MCP session with the default box:

```text
OK: BOX_JOINT_V4 | outer=120.0x80.0x60.0 mm | material=3.0 mm | components=6 | bodies=6 | layout_lines=368
```

The `box_width_mm`, `box_depth_mm`, and `box_height_mm` parameters in V4 represent **outer box dimensions**.

## Emit without Fusion

To inspect the generated Fusion-side Python without executing it:

```powershell
python fusion_bridge.py emit generators/generator_laser_plate.py generated.py
```

## Tests

Offline tests do not require Fusion:

```powershell
python -m unittest discover -s tests -v
```

The repository includes GitHub Actions checks for Python 3.10–3.13.

## Important Fusion API lesson

For large sketches:

```python
sketch.isComputeDeferred = True
```

can significantly reduce repeated sketch recomputation. Always restore it to `False` after bulk geometry creation.

For closed polygonal profiles, prefer chaining real `SketchPoint` objects such as `previous.endSketchPoint` rather than relying only on separate `Point3D` values with equal coordinates.

## Kerf

Measure kerf on your own machine and material. If your CAM/controller already performs kerf compensation, keep generator-side compensation disabled to avoid applying it twice.

## Official references

- Autodesk Fusion MCP overview: https://help.autodesk.com/view/fusion360/ENU/?guid=FMCP-OVERVIEW
- Fusion MCP connection: https://help.autodesk.com/view/ADSKMCP/ENU/?guid=ADSKMCP_FusionDesktopMcp_connecting_to_the_fusion_mcp_server_html
- Fusion API `SketchLines.addByTwoPoints`: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SketchLines_addByTwoPoints.htm
- Fusion API `Sketch.isComputeDeferred`: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Sketch_isComputeDeferred.htm
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Autodesk Fusion MCP sample: https://github.com/AutodeskFusion360/FusionMCPSample

## Security

The bridge executes generated Python **inside the active Fusion session**. Only run generators you trust.

## License

MIT
