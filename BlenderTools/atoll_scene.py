# Mangrove atoll scene for Blender 5.x
# Builds terrain, water, sky/sun and rocks, then places the RedMangrove_* variants
# (made by red_mangrove.py) as collection instances by tidal zone.
# Re-running rebuilds everything; change SEED for a new layout. Units: meters, Z up, sea level z=0.

import bpy, bmesh, math, random
from mathutils import Vector, Euler, noise

SEED = 3
ISLAND_A = 38.0          # island half-length (x)
ISLAND_B = 26.0          # island half-width (y)
GRID_X, GRID_Y = 170.0, 130.0
CELL = 0.5               # terrain resolution in meters
WATER_Z = 0.0
BEACH_ANGLE = 3.6        # direction (radians) of the sandy beach with no mangroves
BEACH_WIDTH = 0.45
MAX_TREES = 750
SPACING = 0.5            # < 1 lets neighbouring canopies overlap
N_CREEKS = 4
CREEK_WIDTH = (7.0, 3.5) # half-width falloff at the mouth, and where it reaches the pond
POND = (-4.0, 3.0, 9.0)  # x, y, radius of the central tidal pond
CLEAR_CREEK = 0          # which creek the dome clearing sits beside
CLEAR_RADIUS = 4.5       # tree-free circle for the dome camera
CLEAR_H = 0.3            # firm mud just above sea level
CAMERA_HEIGHT = 1.6
VIEW_CORRIDOR = (30.0, 25)   # tree-free wedge from the clearing: length (m), half-angle (degrees)
CANOPY_RING = 9              # leaning tall trees whose crowns hang over the clearing
MUCK_RANGE = (1.0, 0.7)      # island_r where muck starts fading in, and where it is full strength
LITTER_GROUND = 40000        # dead leaves on the mud
LITTER_FLOAT = 6000          # leaves floating on the interior water
STICKS = 1800                # twigs on the mud and in the water
FLOAT_PROPAGULES = 300       # pencil-shaped seedlings drifting in the water
DOME_TILT = 30           # degrees the dome camera leans from straight up toward the view

globals().update(globals().get("OVERRIDES", {}))
rng = random.Random(SEED)
UP = Vector((0, 0, 1))


# ---------- helpers ----------
def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0)/(e1 - e0)))
    return t*t*(3 - 2*t)

def lerp(a, b, t):
    return a + (b - a)*t

def fbm(p, octaves=4):
    s, a = 0.0, 0.5
    for _ in range(octaves):
        s += a*noise.noise(p)
        p = p*2.0
        a *= 0.5
    return s

def get_coll(name, parent=None, clear=True):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    if clear:
        for ob in list(c.objects):
            d = ob.data
            bpy.data.objects.remove(ob)
            if isinstance(d, bpy.types.Mesh) and d.users == 0:
                bpy.data.meshes.remove(d)
    return c

def layer_coll(name, lc=None):
    lc = lc or bpy.context.view_layer.layer_collection
    if lc.name == name:
        return lc
    for ch in lc.children:
        r = layer_coll(name, ch)
        if r:
            return r


# ---------- island shape ----------
def angdiff(a, b):
    return abs((a - b + math.pi) % (2*math.pi) - math.pi)

def beach_weight(x, y):
    return smoothstep(BEACH_WIDTH, BEACH_WIDTH*0.4, angdiff(math.atan2(y/ISLAND_B, x/ISLAND_A), BEACH_ANGLE))

def island_r(x, y):
    w = Vector((x*0.02, y*0.02, 0.3 + SEED))
    wx = x + 10*noise.noise(w)
    wy = y + 10*noise.noise(w + Vector((5.2, 1.3, 0)))
    return math.sqrt((wx/ISLAND_A)**2 + (wy/ISLAND_B)**2)

def make_creek(theta, phase):
    # winds from the open water at the rim into the central pond
    mouth = Vector((ISLAND_A*1.25*math.cos(theta), ISLAND_B*1.25*math.sin(theta), 0))
    pond = Vector((POND[0], POND[1], 0))
    side = (pond - mouth).cross(UP).normalized()
    pts = []
    for k in range(13):
        t = k/12
        p = mouth.lerp(pond, t) + side*4.0*math.sin(math.pi*t)*math.sin(k*0.9 + phase)
        pts.append((p.x, p.y, lerp(CREEK_WIDTH[0], CREEK_WIDTH[1], t)))
    return pts

# spread creeks evenly around the island, skipping the beach side
CREEKS = [make_creek(BEACH_ANGLE + (i + 1)*2*math.pi/(N_CREEKS + 1), i*1.7) for i in range(N_CREEKS)]

# dome clearing: on the bank of one creek, near its mouth, looking across the water and out to sea
cp = CREEKS[CLEAR_CREEK]
_a, _b = Vector(cp[5][:2] + (0,)), Vector(cp[6][:2] + (0,))
_tan = (_b - _a).normalized()
_nrm = _tan.cross(UP)
_center = _a.lerp(_b, 0.5)
_w = cp[5][2]
_cands = [_center + _nrm*s*(_w*0.8 + CLEAR_RADIUS*0.6) for s in (1, -1)]
_inland = [math.hypot(c.x/ISLAND_A, c.y/ISLAND_B) for c in _cands]
CLEARING = _cands[0] if _inland[0] < _inland[1] else _cands[1]   # pick the bank deeper inside the forest
VIEW_DIR = ((_center - CLEARING).normalized() - _tan*0.7).normalized()  # across the creek, toward its mouth

def muck_weight(x, y):
    return smoothstep(MUCK_RANGE[0], MUCK_RANGE[1], island_r(x, y)) * (1 - beach_weight(x, y))

def creek_falloff(x, y):
    best = 0.0
    for pts in CREEKS:
        for (ax, ay, aw), (bx, by, bw) in zip(pts, pts[1:]):
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax)*dx + (y - ay)*dy)/(dx*dx + dy*dy)))
            d = math.hypot(x - (ax + dx*t), y - (ay + dy*t))
            w = lerp(aw, bw, t)
            if d < w:
                best = max(best, min(1.0, (1 - d/w)*1.6))
    return best

def height(x, y):
    r = island_r(x, y)
    beach = beach_weight(x, y)
    if r < 1.0:
        land = 1.3 + 0.35*fbm(Vector((x*0.05, y*0.05, 0)))
        h = lerp(land, -0.05, smoothstep(0.55, 1.0, r))
    elif r < 1.5:
        h = lerp(-0.05, -0.9, smoothstep(1.0, 1.5, r))
    else:
        h = lerp(-0.9, -7.0, smoothstep(1.5, 2.1, r))
    h += 0.12*fbm(Vector((x*0.15, y*0.15, 2.0))) * (1.0 if r < 1.6 else 0.5)
    h += beach*0.45*smoothstep(1.15, 0.85, r)             # sand sits higher and steeper
    if r < 1.3 and beach < 0.5:
        h = lerp(h, -0.6, creek_falloff(x, y))            # tidal creeks
    pd = math.hypot(x - POND[0], y - POND[1])
    if pd < POND[2]:
        h = lerp(h, -0.45, smoothstep(POND[2], POND[2]*0.4, pd))
    cd = math.hypot(x - CLEARING.x, y - CLEARING.y)
    if cd < CLEAR_RADIUS + 3:
        # flatten to firm mud, but leave the creek water alone
        f = smoothstep(CLEAR_RADIUS + 3, CLEAR_RADIUS*0.6, cd) * smoothstep(-0.4, 0.0, h)
        h = lerp(h, CLEAR_H + 0.04*noise.noise(Vector((x*0.5, y*0.5, 9.0))), f)
    return h


# ---------- library: tree variants become hidden instance sources ----------
lib = get_coll("Mangrove_Library", clear=False)
variants = {}
for c in list(bpy.data.collections):
    if c.name.startswith("RedMangrove_"):
        root = bpy.data.objects.get(c.name)
        if root:
            c.instance_offset = root.location
        if c.name not in lib.children:
            for parent in [bpy.context.scene.collection] + list(bpy.data.collections):
                if c.name in parent.children and parent != lib:
                    parent.children.unlink(c)
            lib.children.link(c)
        variants[c.name.split("_")[1]] = c
lc = layer_coll("Mangrove_Library")
if lc:
    lc.exclude = True
lc = layer_coll("Preview_Ground")
if lc:
    lc.exclude = True


# ---------- terrain ----------
tcoll = get_coll("Atoll_Terrain")
nx, ny = int(GRID_X/CELL) + 1, int(GRID_Y/CELL) + 1
verts, heights = [], []
for j in range(ny):
    y = -GRID_Y/2 + j*CELL
    for i in range(nx):
        x = -GRID_X/2 + i*CELL
        h = height(x, y)
        verts.append((x, y, h))
        heights.append(h)
faces = [(j*nx + i, j*nx + i + 1, (j+1)*nx + i + 1, (j+1)*nx + i) for j in range(ny-1) for i in range(nx-1)]
tme = bpy.data.meshes.new("Atoll_Terrain")
tme.from_pydata(verts, [], faces)
for p in tme.polygons:
    p.use_smooth = True

DEEP = Vector((0.03, 0.06, 0.07))
REEF_SAND = Vector((0.42, 0.38, 0.28))
SEAGRASS = Vector((0.05, 0.07, 0.035))
WET_MUD = Vector((0.06, 0.048, 0.035))
WET_SAND = Vector((0.33, 0.28, 0.2))
DRY_SAND = Vector((0.55, 0.47, 0.33))
LITTER = Vector((0.07, 0.05, 0.032))
MOSS = Vector((0.05, 0.065, 0.03))

col = tme.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
wet = tme.attributes.new("wet", 'FLOAT', 'POINT')
muck = tme.attributes.new("muck", 'FLOAT', 'POINT')
for idx, (x, y, h) in enumerate(verts):
    muck.data[idx].value = muck_weight(x, y) * smoothstep(-1.2, -0.4, h) if h > -1.2 else 0.0
    n = noise.noise(Vector((x*0.3, y*0.3, 7.0)))
    beach = beach_weight(x, y)
    if h < -0.9:
        c = (REEF_SAND*0.7).lerp(DEEP, smoothstep(-0.9, -5.0, h))
    elif h < -0.25:
        c = REEF_SAND.lerp(SEAGRASS, smoothstep(0.0, 0.3, fbm(Vector((x*0.06, y*0.06, 3.0)))))
    elif h < 0.5:
        mud = WET_MUD.lerp(WET_SAND, beach)
        c = mud.lerp(DRY_SAND, beach*smoothstep(0.1, 0.35, h))
    else:
        soil = LITTER.lerp(MOSS, smoothstep(-0.1, 0.4, n))
        c = soil.lerp(DRY_SAND, beach*smoothstep(1.3, 0.9, h))
        c = WET_MUD.lerp(c, smoothstep(0.5, 0.75, h))
    c = c*(0.85 + 0.3*(n*0.5 + 0.5))
    col.data[idx].color = (c.x, c.y, c.z, 1.0)
    wet.data[idx].value = smoothstep(0.7, 0.3, h) * (1 - 0.6*beach*smoothstep(0.0, 0.3, h))

def sock(sockets, ident):
    return next(s for s in sockets if s.identifier == ident)

def mix(nt, kind, fac, a, b, loc):
    # ShaderNodeMix in FLOAT or RGBA mode; a/b/fac are sockets or constants
    n = nt.nodes.new("ShaderNodeMix"); n.location = loc
    n.data_type = kind
    suffix = "_Color" if kind == 'RGBA' else "_Float"
    for ident, val in (("Factor_Float", fac), ("A" + suffix, a), ("B" + suffix, b)):
        s = sock(n.inputs, ident)
        if isinstance(val, bpy.types.NodeSocket):
            nt.links.new(val, s)
        else:
            s.default_value = val
    return sock(n.outputs, "Result" + suffix)

def ramp(nt, src, stops, loc, interp='LINEAR'):
    r = nt.nodes.new("ShaderNodeValToRGB"); r.location = loc
    r.color_ramp.interpolation = interp
    els = r.color_ramp.elements
    els[0].position, els[0].color = stops[0]
    els[1].position, els[1].color = stops[-1]
    for pos, c in stops[1:-1]:
        e = els.new(pos); e.color = c
    nt.links.new(src, r.inputs["Fac"])
    return r.outputs["Color"]

def noise_tex(nt, scale, detail, loc, vec=None, speed=0.0):
    # speed > 0 makes it a 4D noise that evolves over time (driven by the frame number)
    t = nt.nodes.new("ShaderNodeTexNoise"); t.location = loc
    t.inputs["Scale"].default_value = scale
    t.inputs["Detail"].default_value = detail
    if vec is not None:
        nt.links.new(vec, t.inputs["Vector"])
    if speed:
        t.noise_dimensions = '4D'
        drv = t.inputs["W"].driver_add("default_value").driver
        drv.type = 'SCRIPTED'
        drv.expression = f"frame*{speed}"
    return t

def terrain_material():
    m = bpy.data.materials.get("M_Atoll_Terrain") or bpy.data.materials.new("M_Atoll_Terrain")
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (600, 0)
    vc = nt.nodes.new("ShaderNodeVertexColor"); vc.layer_name = "Col"; vc.location = (-300, 300)
    at = nt.nodes.new("ShaderNodeAttribute"); at.attribute_name = "wet"; at.location = (-700, -50)
    mk = nt.nodes.new("ShaderNodeAttribute"); mk.attribute_name = "muck"; mk.location = (-700, 150)
    muckf = mk.outputs["Fac"]
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.location = (-500, -50)
    mr.inputs["To Min"].default_value = 0.92
    mr.inputs["To Max"].default_value = 0.3
    nt.links.new(at.outputs["Fac"], mr.inputs["Value"])

    # muck: dark organic mud with lighter silty streaks and specks of broken-down leaves
    n1 = noise_tex(nt, 1.5, 10.0, (-700, 500))
    mud = ramp(nt, n1.outputs["Fac"], [(0.3, (0.012, 0.009, 0.006, 1)), (0.55, (0.035, 0.026, 0.016, 1)),
                                       (0.75, (0.07, 0.05, 0.028, 1))], (-500, 500))
    vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.location = (-700, 750)
    vor.inputs["Scale"].default_value = 22.0
    specks = ramp(nt, vor.outputs["Distance"], [(0.12, (1, 1, 1, 1)), (0.2, (0, 0, 0, 1))], (-500, 750), 'CONSTANT')
    mud = mix(nt, 'RGBA', specks, mud, (0.16, 0.10, 0.045, 1), (-200, 600))
    base = mix(nt, 'RGBA', muckf, vc.outputs["Color"], mud, (100, 300))

    # wet sheen: puddly glossy patches in the muck
    n2 = noise_tex(nt, 4.0, 4.0, (-700, -250))
    sheen = nt.nodes.new("ShaderNodeMapRange"); sheen.location = (-500, -250)
    sheen.inputs["From Min"].default_value = 0.45
    sheen.inputs["From Max"].default_value = 0.6
    sheen.inputs["To Min"].default_value = 0.65
    sheen.inputs["To Max"].default_value = 0.3
    nt.links.new(n2.outputs["Fac"], sheen.inputs["Value"])
    rough = mix(nt, 'FLOAT', muckf, mr.outputs["Result"], sheen.outputs["Result"], (100, -100))

    # lumpy bump, stronger where it's mucky
    tex = noise_tex(nt, 45.0, 6.0, (-700, -500))
    lump = noise_tex(nt, 3.0, 6.0, (-700, -700))
    hgt = mix(nt, 'FLOAT', muckf, tex.outputs["Fac"], lump.outputs["Fac"], (-400, -550))
    strength = mix(nt, 'FLOAT', muckf, 0.25, 0.6, (-400, -750))
    bump = nt.nodes.new("ShaderNodeBump"); bump.location = (300, -400)
    nt.links.new(hgt, bump.inputs["Height"])
    nt.links.new(strength, bump.inputs["Strength"])

    nt.links.new(base, bsdf.inputs["Base Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = (0.1, 0.08, 0.06, 1)
    return m

m_terrain = terrain_material()
tme.materials.append(m_terrain)
tcoll.objects.link(bpy.data.objects.new("Atoll_Terrain", tme))


# ---------- water ----------
wme = bpy.data.meshes.new("Atoll_Water")
S = 3000
wme.from_pydata([(-S, -S, 0), (S, -S, 0), (S, S, 0), (-S, S, 0)], [], [(0, 1, 2, 3)])
mw = bpy.data.materials.get("M_Atoll_Water") or bpy.data.materials.new("M_Atoll_Water")
nt = mw.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (400, 0)
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (100, 0)
bsdf.inputs["IOR"].default_value = 1.33
tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-1300, 0)
obj = tc.outputs["Object"]

# murk mask: an ellipse matching the island, warped by noise, full strength in the interior
sep = nt.nodes.new("ShaderNodeSeparateXYZ"); sep.location = (-1100, 300)
nt.links.new(obj, sep.inputs["Vector"])
comb = nt.nodes.new("ShaderNodeCombineXYZ"); comb.location = (-750, 300)
for axis, half in (("X", ISLAND_A), ("Y", ISLAND_B)):
    dv = nt.nodes.new("ShaderNodeMath"); dv.operation = 'DIVIDE'; dv.location = (-930, 380 if axis == "X" else 250)
    nt.links.new(sep.outputs[axis], dv.inputs[0])
    dv.inputs[1].default_value = half
    nt.links.new(dv.outputs[0], comb.inputs[axis])
ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = 'LENGTH'; ln.location = (-580, 300)
nt.links.new(comb.outputs["Vector"], ln.inputs[0])
warp = noise_tex(nt, 0.03, 2.0, (-750, 100), obj)
wsub = nt.nodes.new("ShaderNodeMath"); wsub.operation = 'MULTIPLY_ADD'; wsub.location = (-580, 100)
nt.links.new(warp.outputs["Fac"], wsub.inputs[0])
wsub.inputs[1].default_value = 0.35
wsub.inputs[2].default_value = -0.175
radd = nt.nodes.new("ShaderNodeMath"); radd.operation = 'ADD'; radd.location = (-420, 250)
nt.links.new(ln.outputs["Value"], radd.inputs[0])
nt.links.new(wsub.outputs[0], radd.inputs[1])
murk = nt.nodes.new("ShaderNodeMapRange"); murk.location = (-260, 250)
murk.interpolation_type = 'SMOOTHSTEP'
murk.inputs["From Min"].default_value = MUCK_RANGE[0] + 0.05
murk.inputs["From Max"].default_value = MUCK_RANGE[1]
nt.links.new(radd.outputs[0], murk.inputs["Value"])
murkf = murk.outputs["Result"]

# floating scum patches in the murky water
sc_n = noise_tex(nt, 0.6, 6.0, (-750, -150), obj, speed=0.002)   # scum slowly drifts and reshapes
scum = nt.nodes.new("ShaderNodeMapRange"); scum.location = (-420, -150)
scum.inputs["From Min"].default_value = 0.6
scum.inputs["From Max"].default_value = 0.68
nt.links.new(sc_n.outputs["Fac"], scum.inputs["Value"])
scm = nt.nodes.new("ShaderNodeMath"); scm.operation = 'MULTIPLY'; scm.location = (-260, -150)
nt.links.new(scum.outputs["Result"], scm.inputs[0])
nt.links.new(murkf, scm.inputs[1])
scumf = scm.outputs[0]

water_col = mix(nt, 'RGBA', murkf, (0.035, 0.11, 0.09, 1), (0.035, 0.026, 0.008, 1), (-50, 300))
water_col = mix(nt, 'RGBA', scumf, water_col, (0.10, 0.085, 0.035, 1), (150, 300))
alpha = mix(nt, 'FLOAT', murkf, 0.6, 0.92, (-50, 100))
alpha = mix(nt, 'FLOAT', scumf, alpha, 1.0, (150, 100))
rough = mix(nt, 'FLOAT', murkf, 0.04, 0.12, (-50, -50))   # duller, less mirror-like murky water
rough = mix(nt, 'FLOAT', scumf, rough, 0.6, (150, -50))

tex = noise_tex(nt, 0.35, 8.0, (-250, -350), obj, speed=0.02)    # rolling ripples
fine = noise_tex(nt, 3.0, 4.0, (-250, -450), obj, speed=0.05)    # quick small wavelets
ripple = mix(nt, 'FLOAT', 0.3, tex.outputs["Fac"], fine.outputs["Fac"], (-120, -400))
bump = nt.nodes.new("ShaderNodeBump"); bump.location = (-50, -350)
strength = mix(nt, 'FLOAT', murkf, 0.12, 0.04, (-250, -550))   # stiller water inland
nt.links.new(ripple, bump.inputs["Height"])
nt.links.new(strength, bump.inputs["Strength"])
nt.links.new(water_col, bsdf.inputs["Base Color"])
nt.links.new(alpha, bsdf.inputs["Alpha"])
nt.links.new(rough, bsdf.inputs["Roughness"])
nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
try:
    mw.surface_render_method = 'BLENDED'
except Exception:
    pass
mw.diffuse_color = (0.04, 0.12, 0.1, 0.6)
wme.materials.append(mw)
wob = bpy.data.objects.new("Atoll_Water", wme)
wob.location.z = WATER_Z
tcoll.objects.link(wob)


# ---------- limestone rocks, mostly along the beach ----------
bm = bmesh.new()
rock_n = 0
for _ in range(4000):
    if rock_n >= 40:
        break
    x, y = rng.uniform(-ISLAND_A*1.3, ISLAND_A*1.3), rng.uniform(-ISLAND_B*1.3, ISLAND_B*1.3)
    h = height(x, y)
    if not (-0.45 < h < 0.6) or math.hypot(x - CLEARING.x, y - CLEARING.y) < CLEAR_RADIUS + 2:
        continue
    if beach_weight(x, y) < 0.3 and rng.random() > 0.15:
        continue
    rb = bmesh.new()
    bmesh.ops.create_icosphere(rb, subdivisions=2, radius=1.0)
    ofs = Vector((rng.uniform(0, 99), rng.uniform(0, 99), 0))
    sx, sy, sz = rng.uniform(0.5, 1.6), rng.uniform(0.4, 1.2), rng.uniform(0.25, 0.6)
    rot = Euler((0, 0, rng.uniform(0, 6.28))).to_matrix()
    for v in rb.verts:
        d = v.co + ofs
        v.co = v.co*(1 + 0.35*noise.noise(d*1.3) + 0.12*noise.noise(d*4.0))
        v.co = rot @ Vector((v.co.x*sx, v.co.y*sy, v.co.z*sz)) + Vector((x, y, h - sz*0.25))
    tmp = bpy.data.meshes.new("tmp_rock")
    rb.to_mesh(tmp)
    rb.free()
    bm.from_mesh(tmp)
    bpy.data.meshes.remove(tmp)
    rock_n += 1
rme = bpy.data.meshes.new("Atoll_Rocks")
bm.to_mesh(rme)
bm.free()
rcol = rme.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
rwet = rme.attributes.new("wet", 'FLOAT', 'POINT')
for v in rme.vertices:
    n = noise.noise(v.co*2.0)*0.5 + 0.5
    c = Vector((0.30, 0.28, 0.24))*(0.6 + 0.6*n)
    c = c.lerp(Vector((0.08, 0.07, 0.05)), smoothstep(0.25, -0.1, v.co.z))
    rcol.data[v.index].color = (c.x, c.y, c.z, 1.0)
    rwet.data[v.index].value = smoothstep(0.3, 0.0, v.co.z)
for p in rme.polygons:
    p.use_smooth = True
rme.materials.append(m_terrain)
tcoll.objects.link(bpy.data.objects.new("Atoll_Rocks", rme))


# ---------- sky + sun ----------
world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
wnt = world.node_tree
bg = next((n for n in wnt.nodes if n.type == 'BACKGROUND'), None)
if bg:
    # physical sky; the sun disc comes from the sun lamp instead
    sky = next((n for n in wnt.nodes if n.type == 'TEX_SKY'), None) or wnt.nodes.new("ShaderNodeTexSky")
    sky.location = (-300, 300)
    sky.sky_type = 'MULTIPLE_SCATTERING'
    sky.sun_disc = False
    sky.sun_elevation = math.radians(45)
    sky.sun_rotation = math.radians(125)
    sky.air_density = 1.0
    sky.aerosol_density = 1.5
    wnt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.25
sun = bpy.data.objects.get("Atoll_Sun")
if sun is None:
    sun = bpy.data.objects.new("Atoll_Sun", bpy.data.lights.new("Atoll_Sun", 'SUN'))
    tcoll.objects.link(sun)
sun.data.energy = 4.0
sun.data.color = (1.0, 0.95, 0.87)
sun.data.angle = math.radians(1.5)
sun.rotation_euler = Euler((math.radians(45), 0, math.radians(35)))


# ---------- place mangroves by tidal zone ----------
RADIUS = {"01": 2.4, "02": 1.6, "03": 3.0, "04": 2.8, "05": 3.0, "06": 2.6, "07": 2.3, "08": 1.6, "09": 0.5,
          "10": 1.8, "11": 1.8,   # 10/11 lean their crowns, so only the root footprint counts
          "12": 2.8, "13": 3.0, "14": 2.5}
ZONES = [  # (min h, max h, max trees, [(variant, weight)]) — filled in this order
    (0.45, 2.5, 280, [("05", 0.2), ("06", 0.15), ("03", 0.15), ("04", 0.1),
                      ("12", 0.2), ("13", 0.2)]),                                                 # landward forest
    (-0.12, 0.45, 300, [("01", 0.2), ("04", 0.15), ("07", 0.15), ("08", 0.08), ("02", 0.1), ("03", 0.07),
                        ("13", 0.1), ("14", 0.15)]),                                              # intertidal
    (-0.55, -0.12, 170, [("09", 0.45), ("08", 0.3), ("02", 0.25)]),                          # seaward fringe
]
mcoll = get_coll("Atoll_Mangroves")
placed, grid = [], {}
GCELL = 6.0

def fits(x, y, r):
    dx, dy = x - CLEARING.x, y - CLEARING.y
    dist = math.hypot(dx, dy)
    if dist < CLEAR_RADIUS + r*0.35:
        return False
    # keep a view corridor from the clearing out across the water
    if dist < VIEW_CORRIDOR[0] and (dx*VIEW_DIR.x + dy*VIEW_DIR.y) > dist*math.cos(math.radians(VIEW_CORRIDOR[1])):
        return False
    gx, gy = int(x // GCELL), int(y // GCELL)
    for i in range(gx - 1, gx + 2):
        for j in range(gy - 1, gy + 2):
            for (px, py, pr) in grid.get((i, j), ()):
                if math.hypot(x - px, y - py) < (r + pr)*SPACING:
                    return False
    return True

counts = {}

def place(v, x, y, h, s, rot=None):
    r = RADIUS[v]*s
    ob = bpy.data.objects.new(f"MG_{v}_{len(placed):03d}", None)
    ob.instance_type = 'COLLECTION'
    ob.instance_collection = variants[v]
    ob.location = (x, y, h - 0.05)
    ob.rotation_euler = (0, 0, rng.uniform(0, 2*math.pi) if rot is None else rot)
    ob.scale = (s, s, s)
    ob.empty_display_size = 0.05
    mcoll.objects.link(ob)
    placed.append((x, y, r))
    grid.setdefault((int(x // GCELL), int(y // GCELL)), []).append((x, y, r))
    counts[v] = counts.get(v, 0) + 1

view_az = math.atan2(VIEW_DIR.y, VIEW_DIR.x)

# canopy over the clearing: leaning tall trees turned so their crowns hang over the camera
lean_vs = [v for v in ("10", "11") if v in variants]
for k in range(CANOPY_RING if lean_vs else 0):
    az = view_az + math.radians(55 + k*250/max(1, CANOPY_RING - 1) + rng.uniform(-6, 6))   # 55°..305°
    d = CLEAR_RADIUS + rng.uniform(1.2, 2.5)
    x, y = CLEARING.x + math.cos(az)*d, CLEARING.y + math.sin(az)*d
    h = height(x, y)
    if h < -0.4:
        continue
    v = rng.choice(lean_vs)
    s = rng.uniform(0.95, 1.1)
    if not fits(x, y, RADIUS[v]*s):
        continue
    ox, oy = bpy.data.objects[variants[v].name]["canopy_offset"]
    rot = math.atan2(CLEARING.y - y, CLEARING.x - x) - math.atan2(oy, ox)
    place(v, x, y, h, s, rot)

# frame the clearing: tall trees around the back and sides, leaving the water view open
for k in range(14):
    az = view_az + math.radians(40 + k*21 + rng.uniform(-5, 5))   # sweeps 40°..320° away from the view
    d = CLEAR_RADIUS + rng.uniform(1.0, 3.0)
    x, y = CLEARING.x + math.cos(az)*d, CLEARING.y + math.sin(az)*d
    h = height(x, y)
    if h < -0.55:
        continue
    if h > 0.2:
        pool = ("05", "06", "03", "12", "13")
    elif h > -0.15:
        pool = ("03", "04", "01", "07", "14")
    else:
        pool = ("07", "08", "02")       # red mangroves standing in the shallows
    pool = [v for v in pool if v in variants]
    v = rng.choice(pool)
    s = rng.uniform(0.95, 1.2)
    if fits(x, y, RADIUS[v]*s*0.6):
        place(v, x, y, h, s)

for zmin, zmax, budget, mix in ZONES:
    names = [v for v, _ in mix if v in variants]
    weights = [w for v, w in mix if v in variants]
    if not names:
        continue
    n = 0
    for _ in range(90000):
        if n >= budget or len(placed) >= MAX_TREES:
            break
        x, y = rng.uniform(-ISLAND_A*1.4, ISLAND_A*1.4), rng.uniform(-ISLAND_B*1.4, ISLAND_B*1.4)
        h = height(x, y)
        if not (zmin <= h < zmax) or (beach_weight(x, y) > 0.4 and h > -0.3):
            continue
        v = rng.choices(names, weights)[0]
        s = rng.uniform(0.8, 1.25)
        if not fits(x, y, RADIUS[v]*s):
            continue
        place(v, x, y, h, s)
        n += 1


# ---------- leaf litter, twigs and floating debris in the mucky interior ----------
def to_srgb(c):
    return tuple(v*12.92 if v <= 0.0031308 else 1.055*v**(1/2.4) - 0.055 for v in c[:3]) + (1.0,)

def pick(palette):
    c = rng.choices([p for p, _ in palette], [w for _, w in palette])[0]
    k = rng.uniform(0.75, 1.2)
    return (c[0]*k, c[1]*k, c[2]*k)

GROUND_LEAF = [((0.10, 0.055, 0.025), 0.3), ((0.2, 0.12, 0.05), 0.2), ((0.05, 0.035, 0.02), 0.2),
               ((0.4, 0.3, 0.05), 0.12), ((0.35, 0.12, 0.03), 0.1), ((0.07, 0.13, 0.025), 0.08)]
FLOAT_LEAF = [((0.45, 0.34, 0.05), 0.3), ((0.4, 0.14, 0.03), 0.2), ((0.15, 0.09, 0.04), 0.25),
              ((0.09, 0.17, 0.03), 0.25)]
LEAF_UVS = [(0.5, 0.0), (0.05, 0.28), (0.08, 0.68), (0.5, 1.0), (0.92, 0.68), (0.95, 0.28)]
LEAF_FAN = ((0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5))

bm = bmesh.new()
luv = bm.loops.layers.uv.new("UVMap")
lcl = bm.loops.layers.color.new("Col")

def add_leaf(pos, tilt, curl, color):
    yaw = rng.uniform(0, 2*math.pi)
    d = Vector((math.cos(yaw), math.sin(yaw), 0))
    nrm = (UP + rand_vec(tilt)).normalized()
    d = (d - nrm*d.dot(nrm)).normalized()
    s = d.cross(nrm)
    L = rng.uniform(0.08, 0.14); W = L*0.45
    b = pos - d*L*0.5
    lift = nrm*curl
    vs = [bm.verts.new(b),
          bm.verts.new(b + d*L*0.28 + s*W*0.45 + lift),
          bm.verts.new(b + d*L*0.68 + s*W*0.42 + lift),
          bm.verts.new(b + d*L + lift*0.5),
          bm.verts.new(b + d*L*0.68 - s*W*0.42 + lift),
          bm.verts.new(b + d*L*0.28 - s*W*0.45 + lift)]
    c = to_srgb(color)
    for tri in LEAF_FAN:
        f = bm.faces.new([vs[i] for i in tri])
        for loop, i in zip(f.loops, tri):
            loop[luv].uv = LEAF_UVS[i]
            loop[lcl] = c

def rand_vec(s):
    return Vector((rng.uniform(-s, s), rng.uniform(-s, s), rng.uniform(-s, s)))

def sample_interior():
    return rng.uniform(-ISLAND_A, ISLAND_A), rng.uniform(-ISLAND_B, ISLAND_B)

n_ground = n_float = 0
for _ in range(LITTER_GROUND*6):
    if n_ground >= LITTER_GROUND:
        break
    x, y = sample_interior()
    if rng.random() > muck_weight(x, y):
        continue
    h = height(x, y)
    if h < WATER_Z - 0.02:
        continue
    add_leaf(Vector((x, y, h + 0.02)), 0.15, rng.uniform(0.0, 0.015), pick(GROUND_LEAF))
    n_ground += 1

for _ in range(LITTER_FLOAT*20):
    if n_float >= LITTER_FLOAT:
        break
    x, y = sample_interior()
    w = muck_weight(x, y)
    h = height(x, y)
    # debris drifts into the edges of the channels
    if h > WATER_Z - 0.05 or rng.random() > w*(0.35 + 0.65*smoothstep(-0.6, -0.05, h)):
        continue
    add_leaf(Vector((x, y, WATER_Z + 0.004)), 0.03, 0.004, pick(FLOAT_LEAF))
    n_float += 1

litter_me = bpy.data.meshes.new("Atoll_LeafLitter")
bm.to_mesh(litter_me)
bm.free()
m_litter = bpy.data.materials.get("M_Atoll_LeafLitter") or bpy.data.materials.new("M_Atoll_LeafLitter")
nt = m_litter.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
vc = nt.nodes.new("ShaderNodeVertexColor"); vc.layer_name = "Col"; vc.location = (-300, 100)
bsdf.inputs["Roughness"].default_value = 0.45
nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
m_litter.use_backface_culling = False
m_litter.diffuse_color = (0.12, 0.07, 0.03, 1)
litter_me.materials.append(m_litter)
tcoll.objects.link(bpy.data.objects.new("Atoll_LeafLitter", litter_me))

# twigs (on the mud and floating) and drifting propagules, built as thin tubes
cu = bpy.data.curves.new("tmp_debris", 'CURVE')
cu.dimensions = '3D'
cu.bevel_mode = 'ROUND'
cu.bevel_depth = 1.0
cu.bevel_resolution = 0
cu.use_fill_caps = True
debris_cols = []

def add_tube(pts, radii, color):
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for pt, p, r in zip(sp.points, pts, radii):
        pt.co = (p.x, p.y, p.z, 1.0)
        pt.radius = r
    debris_cols.append(color)

n_sticks = n_props = 0
for _ in range(STICKS*20):
    if n_sticks >= STICKS:
        break
    x, y = sample_interior()
    if rng.random() > muck_weight(x, y):
        continue
    h = height(x, y)
    a = rng.uniform(0, 2*math.pi)
    L = rng.uniform(0.2, 0.8)
    r = rng.uniform(0.006, 0.015)
    p0 = Vector((x, y, 0))
    p2 = p0 + Vector((math.cos(a), math.sin(a), 0))*L
    p1 = p0.lerp(p2, 0.5) + Vector((rng.uniform(-.05, .05), rng.uniform(-.05, .05), 0))
    pts = [p0, p1, p2]
    if h < WATER_Z - 0.05:
        for p in pts:
            p.z = WATER_Z + r*0.3
    else:
        for p in pts:
            p.z = max(height(p.x, p.y), WATER_Z - 0.05) + r
        pts[1].z += 0.02
    add_tube(pts, [r, r*0.9, r*0.6], pick([((0.06, 0.045, 0.03), 0.6), ((0.12, 0.1, 0.08), 0.4)]))
    n_sticks += 1

for _ in range(FLOAT_PROPAGULES*30):
    if n_props >= FLOAT_PROPAGULES:
        break
    x, y = sample_interior()
    if height(x, y) > WATER_Z - 0.05 or rng.random() > muck_weight(x, y):
        continue
    a = rng.uniform(0, 2*math.pi)
    d = Vector((math.cos(a), math.sin(a), 0))
    L = rng.uniform(0.18, 0.28)
    p0 = Vector((x, y, WATER_Z + 0.004))
    add_tube([p0, p0 + d*L*0.5, p0 + d*L], [0.008, 0.009, 0.004], pick([((0.1, 0.14, 0.035), 0.7), ((0.12, 0.07, 0.03), 0.3)]))
    n_props += 1

dob = bpy.data.objects.new("tmp_debris", cu)
tcoll.objects.link(dob)
dg = bpy.context.evaluated_depsgraph_get()
debris_me = bpy.data.meshes.new_from_object(dob.evaluated_get(dg))
bpy.data.objects.remove(dob)
bpy.data.curves.remove(cu)
debris_me.name = "Atoll_Debris"
# each tube becomes 4 sides x segments + caps; color faces by their tube via mesh islands
dcol = debris_me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
bmd = bmesh.new()
bmd.from_mesh(debris_me)
bmd.faces.ensure_lookup_table()
seen, island = set(), 0
face_col = {}
for f in bmd.faces:
    if f.index in seen:
        continue
    stack = [f]
    seen.add(f.index)
    c = debris_cols[min(island, len(debris_cols) - 1)]
    while stack:
        g = stack.pop()
        face_col[g.index] = c
        for e in g.edges:
            for h2 in e.link_faces:
                if h2.index not in seen:
                    seen.add(h2.index)
                    stack.append(h2)
    island += 1
bmd.free()
for poly in debris_me.polygons:
    c = face_col.get(poly.index, (0.06, 0.045, 0.03))
    for li in poly.loop_indices:
        dcol.data[li].color = (c[0], c[1], c[2], 1.0)
debris_me.materials.append(m_litter)
tcoll.objects.link(bpy.data.objects.new("Atoll_Debris", debris_me))


# ---------- dome camera at the clearing ----------
eye = Vector((CLEARING.x, CLEARING.y, height(CLEARING.x, CLEARING.y) + CAMERA_HEIGHT))
cam = bpy.data.objects.get("Dome_Camera")
if cam is None:
    cam = bpy.data.objects.new("Dome_Camera", bpy.data.cameras.new("Dome_Camera"))
    tcoll.objects.link(cam)
cam.location = eye
# 90° on X looks along +Y; add elevation to tip it up toward the zenith, then turn to face the view
cam.rotation_euler = Euler((math.radians(180 - DOME_TILT), 0, view_az - math.pi/2))
try:
    cam.data.type = 'PANO'
    cam.data.panorama_type = 'FISHEYE_EQUIDISTANT'
    cam.data.fisheye_fov = math.radians(180)
except Exception:
    pass
cam.data.clip_end = 2000

# plain marker that survives FBX export, so the Unity camera can be dropped on the same spot
mk = bpy.data.objects.get("Dome_Camera_Marker")
if mk is None:
    mk = bpy.data.objects.new("Dome_Camera_Marker", None)
    mk.empty_display_type = 'SINGLE_ARROW'
    tcoll.objects.link(mk)
mk.location = eye
mk.rotation_euler = Euler((math.radians(-90), 0, view_az - math.pi/2))   # arrow (+Z) = horizontal view direction
mk.empty_display_size = 1.5

result = {"terrain_verts": len(verts), "rocks": rock_n, "trees": len(placed), "by_variant": counts,
          "clearing": [round(CLEARING.x, 1), round(CLEARING.y, 1)], "eye": [round(c, 2) for c in eye],
          "view_az_deg": round(math.degrees(view_az)),
          "litter": {"ground": n_ground, "floating": n_float, "sticks": n_sticks, "propagules": n_props},
          "h_range": [round(min(heights), 2), round(max(heights), 2)]}
