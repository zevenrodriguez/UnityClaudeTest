# Procedural red mangrove bark for Blender 5.x
# Rebuilds the node tree of M_RedMangrove_Bark (shared by every tree variant).
# Keeps the per-tree vertex colors ("Col") as the base tint and layers on detail.
# Works off Object coordinates, so detail stays put on collection instances; z = height above the tree's ground.

import bpy

MAT = "M_RedMangrove_Bark"

m = bpy.data.materials.get(MAT) or bpy.data.materials.new(MAT)
nt = m.node_tree
nt.nodes.clear()
N, L = nt.nodes, nt.links


def node(kind, loc, **inputs):
    n = N.new(kind)
    n.location = loc
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n

def sock(sockets, ident):
    return next(s for s in sockets if s.identifier == ident)

def mix(kind, fac, a, b, loc, blend='MIX'):
    n = N.new("ShaderNodeMix"); n.location = loc
    n.data_type = kind
    if kind == 'RGBA':
        n.blend_type = blend
    suffix = "_Color" if kind == 'RGBA' else "_Float"
    for ident, val in (("Factor_Float", fac), ("A" + suffix, a), ("B" + suffix, b)):
        s = sock(n.inputs, ident)
        if isinstance(val, bpy.types.NodeSocket):
            L.new(val, s)
        else:
            s.default_value = val
    return sock(n.outputs, "Result" + suffix)

def map_range(src, fmin, fmax, tmin, tmax, loc, smooth=True):
    n = node("ShaderNodeMapRange", loc)
    if smooth:
        n.interpolation_type = 'SMOOTHSTEP'
    n.inputs["From Min"].default_value = fmin
    n.inputs["From Max"].default_value = fmax
    n.inputs["To Min"].default_value = tmin
    n.inputs["To Max"].default_value = tmax
    L.new(src, n.inputs["Value"])
    return n.outputs["Result"]

def math_op(op, a, b, loc):
    n = node("ShaderNodeMath", loc)
    n.operation = op
    for i, v in enumerate((a, b)):
        if isinstance(v, bpy.types.NodeSocket):
            L.new(v, n.inputs[i])
        else:
            n.inputs[i].default_value = v
    return n.outputs[0]

def noise(vec, scale, detail, loc, rough=0.55):
    n = node("ShaderNodeTexNoise", loc, Scale=scale, Detail=detail, Roughness=rough)
    L.new(vec, n.inputs["Vector"])
    return n

def voronoi(vec, scale, loc):
    n = node("ShaderNodeTexVoronoi", loc, Scale=scale)
    L.new(vec, n.inputs["Vector"])
    return n


out = node("ShaderNodeOutputMaterial", (1800, 0))
bsdf = node("ShaderNodeBsdfPrincipled", (1500, 0))
tc = node("ShaderNodeTexCoord", (-1600, 0))
obj = tc.outputs["Object"]
sep = node("ShaderNodeSeparateXYZ", (-1400, -600))
L.new(obj, sep.inputs["Vector"])
z = sep.outputs["Z"]
vc = node("ShaderNodeVertexColor", (-600, 600))
vc.layer_name = "Col"

# height bands above the tree's ground (z = 0)
wet_band = map_range(z, 0.45, 0.1, 0, 1, (-1200, -600))       # 1 at the mud, fading by 0.45 m
tide_band = mix('FLOAT', map_range(z, 0.05, 0.2, 0, 1, (-1200, -750)),
                0.0, map_range(z, 0.55, 0.35, 0, 1, (-1200, -900)), (-1000, -800))  # 0.05..0.55 m
dry_band = map_range(z, 0.4, 0.9, 0, 1, (-1200, -1050))

# 1. fissured bark: noise stretched along the length of trunks and roots
mp = node("ShaderNodeMapping", (-1400, 300))
mp.inputs["Scale"].default_value = (14.0, 14.0, 2.2)
L.new(obj, mp.inputs["Vector"])
fis = noise(mp.outputs["Vector"], 1.0, 10.0, (-1200, 300), 0.6)
ridge = map_range(fis.outputs["Fac"], 0.38, 0.55, 0, 1, (-1000, 300))
shade = map_range(ridge, 0, 1, 0.55, 1.15, (-800, 300), smooth=False)
base = mix('RGBA', 1.0, vc.outputs["Color"], (1, 1, 1, 1), (-400, 500), 'MULTIPLY')
shade_rgb = node("ShaderNodeCombineColor", (-600, 300))
for ch in ("Red", "Green", "Blue"):
    L.new(shade, shade_rgb.inputs[ch])
base = mix('RGBA', 1.0, base, shade_rgb.outputs["Color"], (-200, 500), 'MULTIPLY')
fis_inv = math_op('SUBTRACT', 1.0, ridge, (-800, 150))
base = mix('RGBA', math_op('MULTIPLY', fis_inv, 0.45, (-600, 150)), base, (0.10, 0.035, 0.018, 1), (0, 500))  # reddish inner bark

# broad colour variation so no two stretches look identical
var = noise(obj, 0.8, 3.0, (-600, 800))
var_col = map_range(var.outputs["Fac"], 0.3, 0.7, 0.8, 1.15, (-400, 800))
var_rgb = node("ShaderNodeCombineColor", (-200, 800))
for ch in ("Red", "Green", "Blue"):
    L.new(var_col, var_rgb.inputs[ch])
base = mix('RGBA', 1.0, base, var_rgb.outputs["Color"], (200, 500), 'MULTIPLY')

# 2. lenticels: small pale breathing pores
len_v = voronoi(obj, 55.0, (-600, 1000))
len_m = map_range(len_v.outputs["Distance"], 0.1, 0.06, 0, 1, (-400, 1000))
base = mix('RGBA', math_op('MULTIPLY', len_m, 0.55, (-200, 1000)), base, (0.32, 0.28, 0.22, 1), (400, 500))

# 3. crusty lichen patches (grey-green and chalky white), only on drier bark
lich_n = noise(obj, 4.0, 6.0, (-600, 1250))
lich_m = map_range(lich_n.outputs["Fac"], 0.55, 0.63, 0, 1, (-400, 1250))
lich_m = math_op('MULTIPLY', lich_m, dry_band, (-200, 1250))
lich_c = noise(obj, 12.0, 4.0, (-600, 1450))
lich_col = mix('RGBA', lich_c.outputs["Fac"], (0.26, 0.28, 0.2, 1), (0.42, 0.42, 0.37, 1), (-200, 1450))
base = mix('RGBA', math_op('MULTIPLY', lich_m, 0.8, (0, 1250)), base, lich_col, (600, 500))

# 4. tide line: green-brown algae slime and barnacle clusters
base = mix('RGBA', math_op('MULTIPLY', tide_band, 0.55, (200, -800)), base, (0.035, 0.05, 0.018, 1), (800, 500))
bar_v = voronoi(obj, 70.0, (-600, -1300))
bar_dots = map_range(bar_v.outputs["Distance"], 0.2, 0.12, 0, 1, (-400, -1300))
bar_patch = map_range(noise(obj, 3.0, 2.0, (-600, -1500)).outputs["Fac"], 0.45, 0.6, 0, 1, (-400, -1500))
bar_m = math_op('MULTIPLY', math_op('MULTIPLY', bar_dots, bar_patch, (-200, -1350)), tide_band, (0, -1350))
base = mix('RGBA', bar_m, base, (0.5, 0.47, 0.4, 1), (1000, 500))

# 5. mud splash darkening right at the base
base = mix('RGBA', math_op('MULTIPLY', wet_band, 0.6, (800, -600)), base, (0.03, 0.022, 0.015, 1), (1200, 500))

# roughness: dry bark matte, glossy where wet, lichen chalky
rough = mix('FLOAT', wet_band, 0.82, 0.28, (1000, -200))
rough = mix('FLOAT', lich_m, rough, 0.95, (1200, -200))

# bump: fissures + lenticels + barnacles
h = math_op('ADD', math_op('MULTIPLY', ridge, 0.6, (800, -300)), math_op('MULTIPLY', len_m, 0.2, (800, -400)), (1000, -400))
h = math_op('ADD', h, math_op('MULTIPLY', bar_m, 0.8, (1000, -550)), (1150, -450))
bump = node("ShaderNodeBump", (1300, -400), Strength=0.55, Distance=0.02)
L.new(h, bump.inputs["Height"])

L.new(base, bsdf.inputs["Base Color"])
L.new(rough, bsdf.inputs["Roughness"])
L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
L.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
m.use_backface_culling = False
m.diffuse_color = (0.12, 0.09, 0.07, 1)
result = {"nodes": len(N)}
