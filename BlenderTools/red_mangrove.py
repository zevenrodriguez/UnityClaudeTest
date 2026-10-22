# Red mangrove (Rhizophora mangle) generator for Blender 5.x
# Run from Blender's Scripting tab, or via Blender MCP.
# Change SEED / NAME (and the shape options) to make variants. Units: meters, Z up, ground at z=0.

import bpy, bmesh, math, random
from mathutils import Vector, noise

SEED = 7
NAME = "RedMangrove_01"
MUD_Z = -0.3             # roots sink this far below the ground plane
CROWN_Z = 1.55           # where the root thicket gathers into stems (or the trunk begins)
TRUNK_HEIGHT = 0.0       # > 0 gives a tall single trunk rising out of the root mat
TRUNK_LEAN = 0.1         # sideways lean of the trunk (0 = straight up)
STEM_SCALE = 1.0         # length multiplier for stems and sub-branches
CANOPY_RADIUS = 2.5
CANOPY_TOP = 3.1
CANOPY_EDGE = 1.7        # canopy droops down to this height at its rim
N_STEMS = 7
N_ROOTS = 80
ROOT_SPREAD = 1.0        # how far roots reach out from the plant
ROOT_ARCH = 0.0          # 0 = steep thicket, ~0.5 = classic high arches
ROOT_THICK = 1.0         # root/stem thickness multiplier
DROP_ROOTS = 0           # long thin aerial roots hanging from high branches
ROSETTES = 300           # leaf rosettes at twig tips
N_PNEUMATOPHORES = 220   # mud spikes; separate object, delete if unwanted
BARK_COLOR = None        # linear RGB; None = random mix of dark weathered and reddish-tan
LICHEN = 0.7             # grey patchiness on the bark, 0..1
WET_TOP = 0.25           # height of the dark wet band at the base
WET_COLOR = (0.07, 0.055, 0.04)
PREVIEW_GROUND = True    # sand plane in its own collection, not part of the tree
OFFSET = (0, 0, 0)       # where the tree sits in the Blender scene (reset to 0 before export)

# a caller can exec this file with OVERRIDES = {"SEED": 21, "NAME": "...", ...} to make variants
globals().update(globals().get("OVERRIDES", {}))

rng = random.Random(SEED)
UP = Vector((0, 0, 1))


# ---------- helpers ----------
def bez(p0, p1, p2, p3, t):
    u = 1 - t
    return p0*u*u*u + p1*3*u*u*t + p2*3*u*t*t + p3*t*t*t

def bez_pts(p0, p1, p2, p3, n):
    return [bez(p0, p1, p2, p3, i/n) for i in range(n+1)]

def lerp_r(n, r0, r1):
    return [r0 + (r1-r0)*i/n for i in range(n+1)]

def rand_vec(s=1.0):
    return Vector((rng.uniform(-s, s), rng.uniform(-s, s), rng.uniform(-s, s)))

def kink(pts, amp, freq=2.2):
    # irregular bends, strongest mid-span so both ends stay anchored
    ofs = rand_vec(100)
    out, n = [], len(pts) - 1
    for i, p in enumerate(pts):
        w = math.sin(math.pi * i / n)
        out.append(p + noise.noise_vector(p*freq + ofs) * amp * w)
    return out

def grow(start, d, length, nseg, r0, r1, up_bias, wobble):
    pts, d, p = [start.copy()], d.normalized(), start.copy()
    step = length/nseg
    for _ in range(nseg):
        d = (d + rand_vec(wobble) + UP*up_bias).normalized()
        p = p + d*step
        pts.append(p.copy())
    return pts, lerp_r(nseg, r0, r1)

def dir_from(az, el):
    return Vector((math.cos(el)*math.cos(az), math.cos(el)*math.sin(az), math.sin(el)))

def flat(az):
    return Vector((math.cos(az), math.sin(az), 0))

def to_srgb(c):
    # bmesh byte-color layers take sRGB values; the mesh attribute API takes linear
    return tuple(x*12.92 if x <= 0.0031308 else 1.055*x**(1/2.4) - 0.055 for x in c[:3]) + (1.0,)

def tubes_to_mesh(name, splines, bevel_res, coll):
    cu = bpy.data.curves.new(name + "_crv", 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_mode = 'ROUND'
    cu.bevel_depth = 1.0
    cu.bevel_resolution = bevel_res
    cu.use_fill_caps = True
    for pts, rads in splines:
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts)-1)
        for pt, p, r in zip(sp.points, pts, rads):
            pt.co = (p.x, p.y, p.z, 1.0)
            pt.radius = r
    ob = bpy.data.objects.new(name + "_crv", cu)
    coll.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me

def color_wood(me, base, lichen, mud, wet_top, lichen_amt):
    # linear vertex colors: bark tone, grey lichen patches, wet muddy base
    col = me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
    ofs = rand_vec(50)
    for loop in me.loops:
        v = me.vertices[loop.vertex_index].co
        n = noise.noise(v*3.0 + ofs)*0.5 + 0.5
        c = base*(0.75 + 0.5*n)
        patch = noise.noise(v*6.0 + ofs*1.7)
        c = c.lerp(lichen, min(1.0, max(0.0, (patch - 0.15)*2.5)) * lichen_amt)
        c = c.lerp(mud, min(1.0, max(0.0, (wet_top - v.z)/0.2)))
        col.data[loop.index].color = (c.x, c.y, c.z, 1.0)
    for p in me.polygons:
        p.use_smooth = True

def make_mat(name, base, rough, use_vcol, spec=0.5):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type not in ('BSDF_PRINCIPLED', 'OUTPUT_MATERIAL'):
            nt.nodes.remove(n)
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs["Base Color"].default_value = (*base, 1)  # what FBX/Unity picks up
    bsdf.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    if use_vcol:
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        vc.location = (-300, 200)
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    m.diffuse_color = (*base, 1)
    m.use_backface_culling = False
    return m


# ---------- collection (cleared on re-run) ----------
coll = bpy.data.collections.get(NAME)
if coll is None:
    coll = bpy.data.collections.new(NAME)
    bpy.context.scene.collection.children.link(coll)
for ob in list(coll.objects):
    data = ob.data
    bpy.data.objects.remove(ob)
    if isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)

wood_thick, wood_roots, twigs = [], [], []
stems, branch_pts = [], []
canopy_center = Vector((0, 0, 0))

# ---------- optional tall trunk ----------
trunk_pts = None
if TRUNK_HEIGHT > 0:
    lean_az = rng.uniform(0, 2*math.pi)
    tdir = flat(lean_az)*TRUNK_LEAN + UP
    trunk_pts, trunk_r = grow(Vector((0, 0, CROWN_Z - 0.4)), tdir, TRUNK_HEIGHT, 12,
                              0.15*ROOT_THICK, 0.06*ROOT_THICK, 0.0, 0.04)
    wood_thick.append((trunk_pts, trunk_r))
    canopy_center = Vector((trunk_pts[-1].x, trunk_pts[-1].y, 0))

# ---------- stems: several leaning stems (from the crown, or from the top of the trunk) ----------
for i in range(N_STEMS):
    az = i * 2*math.pi/N_STEMS + rng.uniform(-0.3, 0.3)
    if trunk_pts:
        k = rng.randint(len(trunk_pts) - 5, len(trunk_pts) - 1)
        base, r0, el = trunk_pts[k], trunk_r[k]*0.7, rng.uniform(30, 60)
    else:
        base = Vector((math.cos(az)*0.15, math.sin(az)*0.12, CROWN_Z + rng.uniform(-0.15, 0.25)))
        r0, el = 0.05*ROOT_THICK, rng.uniform(22, 50)
    pts, rads = grow(base, dir_from(az, math.radians(el)), rng.uniform(1.4, 2.2)*STEM_SCALE, 7,
                     r0, 0.018, -0.015, 0.15)
    wood_thick.append((pts, rads))
    stems.append((pts, rads, az))
    branch_pts += pts[2:]
    for _ in range(3):
        kk = rng.randint(2, 5)
        saz = az + rng.choice((-1, 1)) * math.radians(rng.uniform(25, 60))
        sp, sr = grow(pts[kk], dir_from(saz, math.radians(rng.uniform(5, 35))),
                      rng.uniform(0.7, 1.3)*STEM_SCALE, 5, rads[kk]*0.7, 0.01, -0.01, 0.18)
        wood_thick.append((sp, sr))
        branch_pts += sp[1:]

# ---------- root sources ----------
def root_source():
    # returns (start point, outward azimuth)
    if trunk_pts:
        az = rng.uniform(0, 2*math.pi)
        low = [p for p in trunk_pts if p.z <= CROWN_Z + 0.6] or trunk_pts[:2]
        return rng.choice(low) + flat(az)*0.12 + UP*rng.uniform(-0.2, 0.4), az
    spts, _, saz = rng.choice(stems)
    return spts[rng.randint(0, 2)], saz + rng.uniform(-0.9, 0.9)

if trunk_pts:  # thick flaring roots where the trunk meets the root mat
    for i in range(6):
        az = i*math.pi/3 + rng.uniform(-0.3, 0.3)
        s = trunk_pts[1]
        g = Vector((s.x, s.y, MUD_Z)) + flat(az)*rng.uniform(0.5, 1.1)
        p1 = s + flat(az)*0.3 + UP*0.1
        wood_roots.append((kink(bez_pts(s, p1, g + UP*0.6, g, 8), 0.05), lerp_r(8, 0.07*ROOT_THICK, 0.04*ROOT_THICK)))
else:  # one sturdy core root under each stem
    for pts, rads, az in stems:
        s = pts[0]
        g = Vector((s.x, s.y, MUD_Z)) + flat(az)*rng.uniform(0.15, 0.5)
        wood_roots.append((kink(bez_pts(s, s - UP*0.4, g + UP*0.5, g, 8), 0.05),
                           lerp_r(8, 0.04*ROOT_THICK, 0.035*ROOT_THICK)))

# ---------- prop roots: thicket or arches, often forking ----------
for i in range(N_ROOTS):
    s, az = root_source()
    out = flat(az)
    reach = rng.uniform(0.35, 1.0) * (0.6 + s.z*0.6) * ROOT_SPREAD
    if rng.random() < 0.07:
        reach *= rng.uniform(1.6, 2.2)   # occasional long, low diagonal root
    g = Vector((s.x, s.y, MUD_Z)) + out*reach
    p1 = s + out*reach*rng.uniform(0.15, 0.4)*(1 + ROOT_ARCH) + UP*(rng.uniform(-0.05, 0.15) + ROOT_ARCH*rng.uniform(0.1, 0.4))
    p2 = g + UP*(s.z*rng.uniform(0.35, 0.7) + ROOT_ARCH*0.3) - out*reach*rng.uniform(0, 0.15)
    pts = kink(bez_pts(s, p1, p2, g, 10), rng.uniform(0.04, 0.1))
    rr = rng.uniform(0.013, 0.024)*ROOT_THICK
    wood_roots.append((pts, lerp_r(10, rr*1.1, rr*0.95)))
    if rng.random() < 0.55:
        q = pts[rng.randint(3, 6)]
        out2 = flat(az + rng.choice((-1, 1))*math.radians(rng.uniform(10, 35)))
        g2 = Vector((s.x, s.y, MUD_Z)) + out2*(reach + rng.uniform(-0.2, 0.6))
        q1 = q + out2*0.15 + UP*ROOT_ARCH*0.15
        q2 = g2 + UP*(q.z*0.5)
        wood_roots.append((kink(bez_pts(q, q1, q2, g2, 8), 0.06), lerp_r(8, rr*0.85, rr*0.8)))

# ---------- twigs out to a flattened, drooping canopy dome ----------
tips = []
for i in range(ROSETTES):
    a = rng.uniform(0, 2*math.pi)
    f = math.sqrt(rng.random())
    rr = CANOPY_RADIUS * f
    z = CANOPY_EDGE + (CANOPY_TOP - CANOPY_EDGE)*math.sqrt(max(0.0, 1 - f*f)) + rng.uniform(-0.2, 0.15)
    tip = canopy_center + Vector((math.cos(a)*rr, math.sin(a)*rr*0.8, z))
    cands = [p for p in branch_pts if p.z < tip.z + 0.2] or branch_pts
    bp = min(cands, key=lambda p: (p - tip).length)
    d = tip - bp
    p1 = bp + d*0.35 + UP*0.1
    p2 = tip - d.normalized()*min(0.12, d.length*0.3)
    twigs.append((bez_pts(bp, p1, p2, tip, 4), lerp_r(4, 0.011, 0.005)))
    tips.append((tip, (tip - p2).normalized()))

# ---------- drop roots: long thin aerial roots hanging from high branches ----------
high = [p for p in branch_pts if p.z > CANOPY_EDGE*0.75] or branch_pts
for i in range(DROP_ROOTS):
    p = rng.choice(high)
    for _ in range(rng.choice((1, 1, 2, 3))):     # often in small bundles
        p0 = p + Vector((rng.uniform(-.08, .08), rng.uniform(-.08, .08), 0))
        reaches = rng.random() < 0.65
        z_end = MUD_Z if reaches else rng.uniform(max(0.4, p0.z*0.3), p0.z - 0.8)
        nseg = max(4, int((p0.z - z_end)/0.5))
        pts = kink([p0 - UP*((p0.z - z_end)*k/nseg) for k in range(nseg+1)], 0.1, 0.8)
        r = rng.uniform(0.008, 0.016)*ROOT_THICK
        twigs.append((pts, lerp_r(nseg, r, r*0.7)))
        if reaches:  # splays into a few small roots just above the mud
            q = pts[-3]
            for _ in range(rng.randint(2, 3)):
                g = Vector((q.x, q.y, MUD_Z)) + flat(rng.uniform(0, 2*math.pi))*rng.uniform(0.15, 0.4)
                twigs.append((bez_pts(q, q + (g - q)*0.3 + UP*0.05, g + UP*0.2, g, 4), lerp_r(4, r*0.8, r*0.6)))

# ---------- wood mesh ----------
bm = bmesh.new()
for splines, res, nm in ((wood_thick, 1, "thick"), (wood_roots, 1, "roots"), (twigs, 0, "twigs")):
    if not splines:
        continue
    me = tubes_to_mesh("tmp_" + nm, splines, res, coll)
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
wood_me = bpy.data.meshes.new(NAME + "_Wood")
bm.to_mesh(wood_me)
bm.free()
BARK_DARK = Vector((0.04, 0.032, 0.027))   # weathered grey-black roots
BARK_WARM = Vector((0.20, 0.11, 0.06))     # fresh reddish-tan roots
bark = Vector(BARK_COLOR) if BARK_COLOR else BARK_DARK.lerp(BARK_WARM, rng.uniform(0.35, 0.65))
color_wood(wood_me, bark, Vector((0.13, 0.125, 0.11)), Vector(WET_COLOR), WET_TOP, LICHEN)

# ---------- leaves: upright rosettes at each twig tip ----------
bm = bmesh.new()
uv = bm.loops.layers.uv.new("UVMap")
lc = bm.loops.layers.color.new("Col")
LEAF_GREEN = Vector((0.17, 0.38, 0.035))
LEAF_DARK = Vector((0.05, 0.14, 0.02))
LEAF_YELLOW = (0.65, 0.48, 0.04, 1)
LEAF_ORANGE = (0.75, 0.25, 0.03, 1)
UVS = [(0.5, 0.0), (0.05, 0.28), (0.08, 0.68), (0.5, 1.0), (0.92, 0.68), (0.95, 0.28)]
FAN = ((0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5))
leaf_count = 0
for tip, axis in tips:
    e1 = axis.cross(UP)
    e1 = e1.normalized() if e1.length > 1e-4 else Vector((1, 0, 0))
    e2 = axis.cross(e1)
    n = rng.randint(8, 14)
    for j in range(n):
        phi = j*2*math.pi/n + rng.uniform(-0.3, 0.3)
        radial = e1*math.cos(phi) + e2*math.sin(phi)
        ldir = (axis*rng.uniform(0.5, 1.0) + radial*rng.uniform(0.6, 1.0) + UP*0.3).normalized()
        nrm = UP - ldir*ldir.dot(UP)
        nrm = nrm.normalized() if nrm.length > 1e-4 else e1
        side = ldir.cross(nrm)
        nrm = (nrm + side*rng.uniform(-0.3, 0.3)).normalized()
        side = ldir.cross(nrm).normalized()
        L = rng.uniform(0.14, 0.22); W = L*0.45
        b = tip + ldir*0.015
        fold = nrm*0.008
        vs = [bm.verts.new(b),
              bm.verts.new(b + ldir*L*0.28 + side*W*0.45 - fold),
              bm.verts.new(b + ldir*L*0.68 + side*W*0.42 - fold),
              bm.verts.new(b + ldir*L - nrm*0.01),
              bm.verts.new(b + ldir*L*0.68 - side*W*0.42 - fold),
              bm.verts.new(b + ldir*L*0.28 - side*W*0.45 - fold)]
        roll = rng.random()
        if roll < 0.035:
            lcol = to_srgb(LEAF_YELLOW)
        elif roll < 0.05:
            lcol = to_srgb(LEAF_ORANGE)
        else:
            c = (LEAF_GREEN*rng.uniform(0.6, 1.1)).lerp(LEAF_DARK, rng.random()*0.5)
            lcol = to_srgb((c.x, c.y, c.z))
        for tri in FAN:
            f = bm.faces.new([vs[i] for i in tri])
            f.smooth = True
            for loop, i in zip(f.loops, tri):
                loop[uv].uv = UVS[i]
                loop[lc] = lcol
        leaf_count += 1
leaf_me = bpy.data.meshes.new(NAME + "_Leaves")
bm.to_mesh(leaf_me)
bm.free()

# ---------- pneumatophores: thin spikes poking out of the mud ----------
spike_me = None
if N_PNEUMATOPHORES > 0:
    spikes = []
    for _ in range(N_PNEUMATOPHORES):
        a = rng.uniform(0, 2*math.pi)
        rr = rng.uniform(1.0, 4.5)
        p = Vector((math.cos(a)*rr, math.sin(a)*rr*0.9, -0.1))
        h = rng.uniform(0.08, 0.3)
        lean = Vector((rng.uniform(-.03, .03), rng.uniform(-.03, .03), 0))
        spikes.append(([p, p + UP*h*0.5 + lean, p + UP*h + lean*1.6], [0.007, 0.006, 0.003]))
    spike_me = tubes_to_mesh(NAME + "_Pneumatophores", spikes, 0, coll)
    spike_me.name = NAME + "_Pneumatophores"
    color_wood(spike_me, Vector((0.14, 0.12, 0.095)), Vector((0.2, 0.19, 0.16)), Vector((0.08, 0.062, 0.04)), 0.0, 0.7)

# ---------- materials ----------
# keep an existing bark material (mangrove_bark.py builds the detailed procedural version)
m_bark = bpy.data.materials.get("M_RedMangrove_Bark") or make_mat("M_RedMangrove_Bark", (0.04, 0.034, 0.029), 0.8, True, 0.3)
m_leaf = make_mat("M_RedMangrove_Leaf", (0.13, 0.30, 0.03), 0.4, True, 0.45)

# ---------- objects ----------
root = bpy.data.objects.new(NAME, None)
root.empty_display_type = 'PLAIN_AXES'
root.location = OFFSET
root["canopy_offset"] = (canopy_center.x, canopy_center.y)   # lets placement turn the crown to face a spot
coll.objects.link(root)
objs = {}
parts = [("_Wood", wood_me, m_bark), ("_Leaves", leaf_me, m_leaf)]
if spike_me:
    parts.append(("_Pneumatophores", spike_me, m_bark))
for suffix, me, mat in parts:
    me.materials.clear()
    me.materials.append(mat)
    ob = bpy.data.objects.new(NAME + suffix, me)
    coll.objects.link(ob)
    ob.parent = root
    objs[NAME + suffix] = ob

# ---------- preview ground (separate collection, not exported with the tree) ----------
if PREVIEW_GROUND and "Preview_Ground" not in bpy.data.objects:
    gcoll = bpy.data.collections.get("Preview_Ground") or bpy.data.collections.new("Preview_Ground")
    if gcoll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(gcoll)
    gme = bpy.data.meshes.new("Preview_Ground")
    gme.from_pydata([(-7, -6, 0), (7, -6, 0), (7, 6, 0), (-7, 6, 0)], [], [(0, 1, 2, 3)])
    gme.materials.append(make_mat("M_Preview_Sand", (0.30, 0.24, 0.15), 0.9, False, 0.2))
    gcoll.objects.link(bpy.data.objects.new("Preview_Ground", gme))

result = {"leaves": leaf_count,
          "tris": {k: sum(len(p.vertices) - 2 for p in o.data.polygons) for k, o in objs.items()}}
