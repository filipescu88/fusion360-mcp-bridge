"""
BOX-JOINT V4 for Fusion MCP
- laser-cut flat layout in one root sketch
- separate 3D components
- extrusion to material thickness
- assembled 3D box preview

Dimension convention in V4:
    box_width_mm, box_depth_mm, box_height_mm = OUTER dimensions.

Default material: 3 mm plywood.
"""

from __future__ import annotations

import base64
import json
import math
import zlib


def _number(params: dict[str, str], key: str, default: float) -> float:
    raw = params.get(key, str(default)).strip().replace(",", ".")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} musi byc liczba, podano {raw!r}") from exc


def _positive(params: dict[str, str], key: str, default: float) -> float:
    value = _number(params, key, default)
    if value <= 0:
        raise ValueError(f"{key} musi byc > 0")
    return value


def _nonnegative(params: dict[str, str], key: str, default: float) -> float:
    value = _number(params, key, default)
    if value < 0:
        raise ValueError(f"{key} musi byc >= 0")
    return value


def _boolean(params: dict[str, str], key: str, default: bool) -> bool:
    if key not in params:
        return default
    value = params[key].strip().lower()
    if value in {"1", "true", "yes", "y", "tak", "on"}:
        return True
    if value in {"0", "false", "no", "n", "nie", "off"}:
        return False
    raise ValueError(f"{key} musi byc 0/1 albo true/false")


def _nearest_odd_segments(length_mm: float, target_mm: float) -> int:
    approx = max(3, int(round(length_mm / target_mm)))
    candidates = [n for n in range(max(3, approx - 6), approx + 7) if n >= 3 and n % 2 == 1]
    if not candidates:
        return 3
    return min(candidates, key=lambda n: abs(length_mm / n - target_mm))


def _append(points, p):
    if points and abs(points[-1][0]-p[0]) < 1e-9 and abs(points[-1][1]-p[1]) < 1e-9:
        return
    points.append(p)


def _edge_points(p0,p1,outward,nominal_length_mm,polarity,material_mm,finger_target_mm,kerf_mm,clearance_mm,margin_start_mm=0.0,margin_end_mm=0.0):
    x0,y0=p0; x1,y1=p1
    dx,dy=x1-x0,y1-y0
    L=math.hypot(dx,dy)
    ux,uy=dx/L,dy/L
    nx,ny=outward
    result=[p0]
    if polarity==0:
        _append(result,p1); return result
    active_length=nominal_length_mm-margin_start_mm-margin_end_mm
    segments=_nearest_odd_segments(active_length,finger_target_mm)
    pitch=active_length/segments
    active_width=pitch+kerf_mm if polarity>0 else pitch+clearance_mm-kerf_mm
    if active_width<=0:
        raise ValueError("Kerf jest za duzy wzgledem szerokosci zeba.")
    nominal_start=kerf_mm/2.0+margin_start_mm
    depth=material_mm*polarity
    if nominal_start>0:
        _append(result,(x0+ux*nominal_start,y0+uy*nominal_start))
    for cell in range(1,segments-1,2):
        center=nominal_start+(cell+0.5)*pitch
        s1=center-active_width/2.0; s2=center+active_width/2.0
        b1=(x0+ux*s1,y0+uy*s1); b2=(x0+ux*s2,y0+uy*s2)
        _append(result,b1); _append(result,(b1[0]+nx*depth,b1[1]+ny*depth))
        _append(result,(b2[0]+nx*depth,b2[1]+ny*depth)); _append(result,b2)
    active_end=kerf_mm/2.0+nominal_length_mm-margin_end_mm
    _append(result,(x0+ux*active_end,y0+uy*active_end)); _append(result,p1)
    return result


def _panel_outline(width_mm,height_mm,edges,margins,material_mm,finger_mm,kerf_mm,clearance_mm):
    k2=kerf_mm/2.0
    xl,xr=-width_mm/2-k2,width_mm/2+k2
    yb,yt=-height_mm/2-k2,height_mm/2+k2
    defs=[((xl,yb),(xr,yb),(0,-1),width_mm,edges[0],margins[0]),((xr,yb),(xr,yt),(1,0),height_mm,edges[1],margins[1]),((xr,yt),(xl,yt),(0,1),width_mm,edges[2],margins[2]),((xl,yt),(xl,yb),(-1,0),height_mm,edges[3],margins[3])]
    out=[]
    for p0,p1,norm,length,polarity,margin in defs:
        pts=_edge_points(p0,p1,norm,length,polarity,material_mm,finger_mm,kerf_mm,clearance_mm,margin[0],margin[1])
        for p in pts: _append(out,p)
    if out: _append(out,out[0])
    return out


def _bbox(points):
    xs=[p[0] for p in points]; ys=[p[1] for p in points]
    return min(xs),min(ys),max(xs),max(ys)


def build_model(params: dict[str,str]) -> dict:
    W=_positive(params,"box_width_mm",120.0); D=_positive(params,"box_depth_mm",80.0); H=_positive(params,"box_height_mm",60.0)
    t=_positive(params,"material_mm",3.0); finger=_positive(params,"finger_mm",10.0)
    kerf=_nonnegative(params,"kerf_mm",0.0); clearance=_nonnegative(params,"clearance_mm",0.0)
    include_lid=_boolean(params,"include_lid",True); gap=_positive(params,"panel_gap_mm",12.0)
    layout_limit=_positive(params,"layout_width_mm",500.0)
    make_layout=_boolean(params,"make_layout",True); make_assembly=_boolean(params,"make_assembly",True)
    wall_h=H-(2*t if include_lid else t); front_w=W-2*t
    zero=(0.0,0.0); corner=(t,t)
    specs=[
        {"name":"FRONT","width":front_w,"height":wall_h,"edges":(1,1,1 if include_lid else 0,1),"margins":(zero,zero,zero,zero)},
        {"name":"BACK","width":front_w,"height":wall_h,"edges":(1,1,1 if include_lid else 0,1),"margins":(zero,zero,zero,zero)},
        {"name":"LEFT","width":D,"height":wall_h,"edges":(1,-1,1 if include_lid else 0,-1),"margins":(corner,zero,corner,zero)},
        {"name":"RIGHT","width":D,"height":wall_h,"edges":(1,-1,1 if include_lid else 0,-1),"margins":(corner,zero,corner,zero)},
        {"name":"BOTTOM","width":W,"height":D,"edges":(-1,-1,-1,-1),"margins":(corner,corner,corner,corner)},
    ]
    if include_lid:
        specs.append({"name":"LID","width":W,"height":D,"edges":(-1,-1,-1,-1),"margins":(corner,corner,corner,corner)})
    panels=[]
    for s in specs:
        panels.append({"name":s["name"],"width":s["width"],"height":s["height"],"points_mm":_panel_outline(s["width"],s["height"],s["edges"],s["margins"],t,finger,kerf,clearance)})
    cx=cy=rowh=0.0; layout_panels=[]
    for p in panels:
        minx,miny,maxx,maxy=_bbox(p["points_mm"]); pw,ph=maxx-minx,maxy-miny
        if cx>0 and cx+pw>layout_limit: cx=0; cy+=rowh+gap; rowh=0
        layout_panels.append({"name":p["name"],"points_mm":[(x+cx-minx,y+cy-miny) for x,y in p["points_mm"]]})
        cx+=pw+gap; rowh=max(rowh,ph)
    zc=t+wall_h/2
    transforms={
        "BOTTOM":{"x":(1,0,0),"y":(0,1,0),"z":(0,0,1),"origin_mm":(0,0,0)},
        "FRONT":{"x":(-1,0,0),"y":(0,0,1),"z":(0,1,0),"origin_mm":(0,-D/2,zc)},
        "BACK":{"x":(1,0,0),"y":(0,0,1),"z":(0,-1,0),"origin_mm":(0,D/2,zc)},
        "LEFT":{"x":(0,1,0),"y":(0,0,1),"z":(1,0,0),"origin_mm":(-W/2,0,zc)},
        "RIGHT":{"x":(0,-1,0),"y":(0,0,1),"z":(-1,0,0),"origin_mm":(W/2,0,zc)},
    }
    if include_lid: transforms["LID"]={"x":(1,0,0),"y":(0,1,0),"z":(0,0,1),"origin_mm":(0,0,H-t)}
    return {"panels":panels,"layout_panels":layout_panels,"transforms":transforms,"meta":{"W":W,"D":D,"H":H,"t":t,"make_layout":make_layout,"make_assembly":make_assembly}}


def generate(params: dict[str,str]) -> str:
    model=build_model(params)
    layout_name=params.get("layout_sketch_name","BOX_JOINT_CUT_LAYOUT")
    packed=base64.b64encode(zlib.compress(json.dumps(model,separators=(",",":")).encode(),9)).decode()
    return f'''import adsk.core\nimport adsk.fusion\nimport base64,json,zlib\n\ndef _matrix(xa,ya,za,o):\n    m=adsk.core.Matrix3D.create()\n    for c,a in enumerate((xa,ya,za)):\n        m.setCell(0,c,float(a[0])); m.setCell(1,c,float(a[1])); m.setCell(2,c,float(a[2]))\n    m.setCell(0,3,o[0]/10); m.setCell(1,3,o[1]/10); m.setCell(2,3,o[2]/10)\n    return m\n\ndef _draw(sketch,pts):\n    lines=sketch.sketchCurves.sketchLines\n    x0,y0=pts[0]; x1,y1=pts[1]\n    first=lines.addByTwoPoints(adsk.core.Point3D.create(x0/10,y0/10,0),adsk.core.Point3D.create(x1/10,y1/10,0))\n    prev=first\n    for x,y in pts[2:-1]: prev=lines.addByTwoPoints(prev.endSketchPoint,adsk.core.Point3D.create(x/10,y/10,0))\n    lines.addByTwoPoints(prev.endSketchPoint,first.startSketchPoint)\n\ndef run(_context: str):\n    app=adsk.core.Application.get(); design=adsk.fusion.Design.cast(app.activeProduct)\n    if not design: raise RuntimeError("Open a Design document first")\n    data=json.loads(zlib.decompress(base64.b64decode({packed!r})).decode())\n    root=design.rootComponent; meta=data["meta"]; material=meta["t"]/10\n    if meta["make_layout"]:\n        sk=root.sketches.add(root.xYConstructionPlane); sk.name={layout_name!r}; sk.isComputeDeferred=True\n        try:\n            for p in data["layout_panels"]: _draw(sk,p["points_mm"])\n        finally: sk.isComputeDeferred=False\n        sk.isLightBulbOn=False\n    created=0\n    if meta["make_assembly"]:\n        by={{p["name"]:p for p in data["panels"]}}\n        for name in ("BOTTOM","FRONT","BACK","LEFT","RIGHT","LID"):\n            if name not in by: continue\n            td=data["transforms"][name]; occ=root.occurrences.addNewComponent(_matrix(td["x"],td["y"],td["z"],td["origin_mm"]))\n            comp=occ.component; comp.name="BOX_"+name\n            sk=comp.sketches.add(comp.xYConstructionPlane); sk.isComputeDeferred=True\n            try: _draw(sk,by[name]["points_mm"])\n            finally: sk.isComputeDeferred=False\n            if sk.profiles.count<1: raise RuntimeError(name+": no profile")\n            feat=comp.features.extrudeFeatures.addSimple(sk.profiles.item(0),adsk.core.ValueInput.createByReal(material),adsk.fusion.FeatureOperations.NewBodyFeatureOperation)\n            if not feat or feat.bodies.count<1: raise RuntimeError(name+": extrusion failed")\n            sk.isLightBulbOn=False; created+=1\n    app.activeViewport.fit()\n    print("OK: BOX_JOINT_V4 | components="+str(created))\n'''
