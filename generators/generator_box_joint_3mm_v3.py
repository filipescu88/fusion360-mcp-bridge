"""Stable laser-cut box-joint generator for fusion_bridge.py."""
from __future__ import annotations

import base64
import json
import math
import zlib


def _num(params, key, default):
    return float(params.get(key, str(default)).replace(",", "."))


def _bool(params, key, default=True):
    if key not in params:
        return default
    return params[key].strip().lower() not in {"0", "false", "no", "off", "nie"}


def _odd_segments(length, target):
    n = max(3, round(length / target))
    if n % 2 == 0:
        n += 1
    return int(n)


def _edge(p0, p1, outward, length, polarity, material, finger, kerf, clearance):
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    nx, ny = outward
    pts = [p0]
    if polarity == 0:
        return [p0, p1]

    segs = _odd_segments(length, finger)
    pitch = length / segs
    width = pitch + kerf if polarity > 0 else pitch + clearance - kerf
    if width <= 0:
        raise ValueError("kerf/clearance invalid for finger size")
    depth = material * polarity

    for cell in range(1, segs - 1, 2):
        c = (cell + 0.5) * pitch + kerf / 2
        s1, s2 = c - width / 2, c + width / 2
        b1 = (x0 + ux * s1, y0 + uy * s1)
        b2 = (x0 + ux * s2, y0 + uy * s2)
        pts += [b1, (b1[0] + nx * depth, b1[1] + ny * depth),
                (b2[0] + nx * depth, b2[1] + ny * depth), b2]
    pts.append(p1)
    return pts


def _outline(w, h, edges, material, finger, kerf, clearance):
    k = kerf / 2
    xl, xr, yb, yt = -w/2-k, w/2+k, -h/2-k, h/2+k
    defs = [
        ((xl,yb),(xr,yb),(0,-1),w,edges[0]),
        ((xr,yb),(xr,yt),(1,0),h,edges[1]),
        ((xr,yt),(xl,yt),(0,1),w,edges[2]),
        ((xl,yt),(xl,yb),(-1,0),h,edges[3]),
    ]
    out=[]
    for args in defs:
        part=_edge(*args, material, finger, kerf, clearance)
        if out and part and out[-1] == part[0]:
            part=part[1:]
        out.extend(part)
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def build_layout(params: dict[str,str]) -> dict:
    W=_num(params,"box_width_mm",120)
    D=_num(params,"box_depth_mm",80)
    H=_num(params,"box_height_mm",60)
    t=_num(params,"material_mm",3)
    finger=_num(params,"finger_mm",10)
    kerf=_num(params,"kerf_mm",0)
    clearance=_num(params,"clearance_mm",0)
    gap=_num(params,"panel_gap_mm",12)
    maxw=_num(params,"layout_width_mm",500)
    lid=_bool(params,"include_lid",True)

    top=1 if lid else 0
    specs=[
        ("FRONT",W,H,(1,1,top,1)),
        ("BACK",W,H,(1,1,top,1)),
        ("LEFT",D,H,(1,-1,top,-1)),
        ("RIGHT",D,H,(1,-1,top,-1)),
        ("BOTTOM",W,D,(-1,-1,-1,-1)),
    ]
    if lid:
        specs.append(("LID",W,D,(-1,-1,-1,-1)))

    raw=[(name,_outline(w,h,edges,t,finger,kerf,clearance)) for name,w,h,edges in specs]
    panels=[]; cx=cy=rowh=0.0
    for name,pts in raw:
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys)
        pw,ph=maxx-minx,maxy-miny
        if cx>0 and cx+pw>maxw:
            cx=0; cy+=rowh+gap; rowh=0
        shifted=[(x+cx-minx,y+cy-miny) for x,y in pts]
        panels.append({"name":name,"points_mm":shifted})
        cx+=pw+gap; rowh=max(rowh,ph)
    return {"panels":panels}


def generate(params: dict[str,str]) -> str:
    layout=build_layout(params)
    name=params.get("sketch_name","BOX_JOINT_3MM_V3")
    packed=base64.b64encode(zlib.compress(json.dumps(layout,separators=(",",":")).encode(),9)).decode()
    return f'''import adsk.core\nimport adsk.fusion\nimport base64,json,zlib\n\ndef run(_context: str):\n    app=adsk.core.Application.get()\n    design=adsk.fusion.Design.cast(app.activeProduct)\n    if not design:\n        raise RuntimeError("Open a Design document first")\n    data=json.loads(zlib.decompress(base64.b64decode({packed!r})).decode())\n    root=design.rootComponent\n    sketch=root.sketches.add(root.xYConstructionPlane)\n    sketch.name={name!r}\n    lines=sketch.sketchCurves.sketchLines\n    total=0\n    sketch.isComputeDeferred=True\n    try:\n        for panel in data["panels"]:\n            pts=panel["points_mm"]\n            x0,y0=pts[0]; x1,y1=pts[1]\n            first=lines.addByTwoPoints(adsk.core.Point3D.create(x0/10,y0/10,0),adsk.core.Point3D.create(x1/10,y1/10,0))\n            prev=first; total+=1\n            for x,y in pts[2:-1]:\n                prev=lines.addByTwoPoints(prev.endSketchPoint,adsk.core.Point3D.create(x/10,y/10,0))\n                total+=1\n            lines.addByTwoPoints(prev.endSketchPoint,first.startSketchPoint)\n            total+=1\n    finally:\n        sketch.isComputeDeferred=False\n    if lines.count != total:\n        raise RuntimeError("Unexpected line count")\n    profiles=sketch.profiles.count\n    sketch.isLightBulbOn=True\n    app.activeViewport.fit()\n    print("OK: BOX_JOINT_V3 | panels="+str(len(data["panels"]))+" | lines="+str(lines.count)+" | profiles="+str(profiles))\n'''
