"""
Minimalny generator testowy dla fusion_bridge.py.

Tworzy prosty prostopadłościan w AKTYWNYM dokumencie Design w Fusion.
Generator sam nie importuje adsk; zwraca tekst skryptu, który wykona się wewnątrz Fusion.
"""

from __future__ import annotations


def _positive_float(params: dict[str, str], key: str, default: float) -> float:
    raw = params.get(key, str(default)).replace(",", ".")
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{key} musi być > 0")
    return value


def generate(params: dict[str, str]) -> str:
    width_mm = _positive_float(params, "width_mm", 40.0)
    depth_mm = _positive_float(params, "depth_mm", 30.0)
    height_mm = _positive_float(params, "height_mm", 10.0)
    body_name = params.get("body_name", "MCP_TEST_BLOCK").strip() or "MCP_TEST_BLOCK"

    half_w_cm = width_mm / 20.0
    half_d_cm = depth_mm / 20.0

    return f"""
import adsk.core
import adsk.fusion

def run(context):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError(
            "Otworz lub utworz dokument typu Design w Fusion przed uruchomieniem generatora."
        )

    root = design.rootComponent
    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.name = "MCP_TEST_SKETCH"

    p1 = adsk.core.Point3D.create({-half_w_cm!r}, {-half_d_cm!r}, 0)
    p2 = adsk.core.Point3D.create({half_w_cm!r}, {half_d_cm!r}, 0)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1, p2)

    if sketch.profiles.count < 1:
        raise RuntimeError("Nie powstal zamkniety profil szkicu.")

    profile = sketch.profiles.item(0)
    distance = adsk.core.ValueInput.createByString({(str(height_mm) + " mm")!r})
    extrudes = root.features.extrudeFeatures
    feature = extrudes.addSimple(
        profile,
        distance,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )

    if not feature or feature.bodies.count < 1:
        raise RuntimeError("Ekstruzja nie utworzyla bryly.")

    body = feature.bodies.item(0)
    body.name = {body_name!r}

    print(
        "OK: utworzono bryle "
        + body.name
        + " | {width_mm:g} x {depth_mm:g} x {height_mm:g} mm"
    )
""".lstrip()
