"""
Parametric 2D laser/CNC plate generator for fusion_bridge.py.

Creates one sketch in the active Fusion Design:
- rectangular outer cut path,
- four circular mounting holes,
- optional centered rectangular cutout,
- optional geometric kerf compensation.

Generator contract:
    generate(params: dict[str, str]) -> str
"""

from __future__ import annotations


def _float(params: dict[str, str], key: str, default: float) -> float:
    raw = params.get(key, str(default)).strip().replace(",", ".")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} musi byc liczba, podano: {raw!r}") from exc


def _positive(params: dict[str, str], key: str, default: float) -> float:
    value = _float(params, key, default)
    if value <= 0:
        raise ValueError(f"{key} musi byc > 0")
    return value


def _nonnegative(params: dict[str, str], key: str, default: float) -> float:
    value = _float(params, key, default)
    if value < 0:
        raise ValueError(f"{key} musi byc >= 0")
    return value


def generate(params: dict[str, str]) -> str:
    width_mm = _positive(params, "width_mm", 120.0)
    height_mm = _positive(params, "height_mm", 80.0)
    hole_diameter_mm = _nonnegative(params, "hole_diameter_mm", 5.0)
    hole_edge_mm = _nonnegative(params, "hole_edge_mm", 10.0)
    slot_width_mm = _nonnegative(params, "slot_width_mm", 40.0)
    slot_height_mm = _nonnegative(params, "slot_height_mm", 12.0)
    kerf_mm = _nonnegative(params, "kerf_mm", 0.0)
    sketch_name = (
        params.get("sketch_name", "LASER_PLATE")
        .strip().replace('"', "").replace("\n", " ") or "LASER_PLATE"
    )

    if hole_diameter_mm > 0:
        if hole_edge_mm <= hole_diameter_mm / 2:
            raise ValueError("hole_edge_mm musi byc wieksze od polowy hole_diameter_mm")
        if 2 * hole_edge_mm >= width_mm or 2 * hole_edge_mm >= height_mm:
            raise ValueError("hole_edge_mm jest za duze dla podanych wymiarow plyty.")

    if slot_width_mm > 0 or slot_height_mm > 0:
        if not (slot_width_mm > 0 and slot_height_mm > 0):
            raise ValueError("Podaj oba wymiary centralnego wyciecia albo ustaw oba na 0.")
        if slot_width_mm >= width_mm or slot_height_mm >= height_mm:
            raise ValueError("Centralne wyciecie musi miescic sie wewnatrz plyty.")

    outer_w_mm = width_mm + kerf_mm
    outer_h_mm = height_mm + kerf_mm
    cut_hole_d_mm = hole_diameter_mm - kerf_mm if hole_diameter_mm > 0 else 0.0
    cut_slot_w_mm = slot_width_mm - kerf_mm if slot_width_mm > 0 else 0.0
    cut_slot_h_mm = slot_height_mm - kerf_mm if slot_height_mm > 0 else 0.0

    if hole_diameter_mm > 0 and cut_hole_d_mm <= 0:
        raise ValueError("kerf_mm jest za duzy wzgledem hole_diameter_mm.")
    if slot_width_mm > 0 and (cut_slot_w_mm <= 0 or cut_slot_h_mm <= 0):
        raise ValueError("kerf_mm jest za duzy wzgledem wymiarow centralnego wyciecia.")

    outer_half_w_cm = outer_w_mm / 20.0
    outer_half_h_cm = outer_h_mm / 20.0
    hole_radius_cm = cut_hole_d_mm / 20.0
    hole_x_cm = (width_mm / 2.0 - hole_edge_mm) / 10.0
    hole_y_cm = (height_mm / 2.0 - hole_edge_mm) / 10.0
    slot_half_w_cm = cut_slot_w_mm / 20.0
    slot_half_h_cm = cut_slot_h_mm / 20.0

    return f"""
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("Otworz dokument typu Design w Fusion.")

    root = design.rootComponent
    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.name = {sketch_name!r}
    lines = sketch.sketchCurves.sketchLines
    circles = sketch.sketchCurves.sketchCircles

    p1 = adsk.core.Point3D.create({-outer_half_w_cm!r}, {-outer_half_h_cm!r}, 0)
    p2 = adsk.core.Point3D.create({outer_half_w_cm!r}, {outer_half_h_cm!r}, 0)
    lines.addTwoPointRectangle(p1, p2)

    hole_radius_cm = {hole_radius_cm!r}
    if hole_radius_cm > 0:
        for x in ({-hole_x_cm!r}, {hole_x_cm!r}):
            for y in ({-hole_y_cm!r}, {hole_y_cm!r}):
                circles.addByCenterRadius(adsk.core.Point3D.create(x, y, 0), hole_radius_cm)

    slot_half_w_cm = {slot_half_w_cm!r}
    slot_half_h_cm = {slot_half_h_cm!r}
    if slot_half_w_cm > 0 and slot_half_h_cm > 0:
        s1 = adsk.core.Point3D.create(-slot_half_w_cm, -slot_half_h_cm, 0)
        s2 = adsk.core.Point3D.create(slot_half_w_cm, slot_half_h_cm, 0)
        lines.addTwoPointRectangle(s1, s2)

    print("OK: laser sketch " + sketch.name + " | nominal {width_mm:g} x {height_mm:g} mm")
""".lstrip()
