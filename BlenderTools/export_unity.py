# Exports the mangrove atoll from Blender to this Unity project (Assets/Mangrove).
#  - Models/RedMangrove_XX.fbx: one per tree variant, meshes named _LOD0/_LOD1/_LOD2
#    (Unity turns those into a LOD Group); submesh 0 = bark, 1 = leaves
#  - Models/Atoll_Ground.fbx: terrain, rocks, leaf litter and debris
#  - mangrove_placement.json: every placed tree and the dome camera, already in Unity coordinates
# Run after red_mangrove.py / atoll_scene.py have built the scene. Units: meters.

import bpy, bmesh, json, math, os
from mathutils import Vector

UNITY_DIR = os.path.join(os.path.dirname(os.path.abspath(globals().get("__file__", ""))), "..", "Assets", "Mangrove")
LOD_WOOD_RATIO = (1.0, 0.35, 0.12)   # decimate ratio for trunks and roots per LOD
LOD_LEAF_KEEP = (1, 2, 4)            # keep every Nth leaf per LOD
LOD_LEAF_GROW = (1.0, 1.3, 1.7)      # enlarge the kept leaves so crowns keep their volume

globals().update(globals().get("OVERRIDES", {}))
UNITY_DIR = os.path.normpath(UNITY_DIR)
MODEL_DIR = os.path.join(UNITY_DIR, "Models")
os.makedirs(MODEL_DIR, exist_ok=True)


def to_unity(v):
    # matches the FBX export below (-Z forward, Y up, transform baked); Unity also mirrors X
    return [round(-v[0], 4), round(v[2], 4), round(-v[1], 4)]

def export_coll():
    c = bpy.data.collections.get("UnityExport")
    if c is None:
        c = bpy.data.collections.new("UnityExport")
        bpy.context.scene.collection.children.link(c)
    return c

def clear_coll(c):
    for ob in list(c.objects):
        me = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(me, bpy.types.Mesh) and me.users == 0:
            bpy.data.meshes.remove(me)

def export_fbx(objs, path):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={'MESH'},
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
        axis_forward='-Z', axis_up='Y', bake_space_transform=True,
        use_mesh_modifiers=False, mesh_smooth_type='FACE', use_tspace=False,
        colors_type='SRGB', add_leaf_bones=False, bake_anim=False,
        path_mode='AUTO', embed_textures=False)

def decimated(me, ratio, coll):
    if ratio >= 0.999:
        return me.copy()
    ob = bpy.data.objects.new("tmp_decimate", me)
    coll.objects.link(ob)
    mod = ob.modifiers.new("Decimate", 'DECIMATE')
    mod.ratio = ratio
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    return out

def thinned_leaves(me, keep, grow):
    # leaves were built as 4-triangle fans, one after another, so leaf i = faces 4i..4i+3
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    drop = []
    for i in range(len(bm.faces) // 4):
        group = bm.faces[4*i:4*i + 4]
        if i % keep:
            drop.extend(group)
        elif grow != 1.0:
            verts = {v for f in group for v in f.verts}
            c = sum((v.co for v in verts), Vector()) / len(verts)
            for v in verts:
                v.co = c + (v.co - c)*grow
    bmesh.ops.delete(bm, geom=drop, context='FACES')
    out = bpy.data.meshes.new("tmp_leaves")
    bm.to_mesh(out)
    bm.free()
    return out

def combine(name, parts):
    # parts: [(mesh, material_index)] -> one mesh with bark/leaf submeshes
    bm = bmesh.new()
    for me, mi in parts:
        n0 = len(bm.faces)
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        for f in bm.faces[n0:]:
            f.material_index = mi
    out = bpy.data.meshes.new(name)
    bm.to_mesh(out)
    bm.free()
    return out


# ---------- tree variants ----------
ecoll = export_coll()
clear_coll(ecoll)
m_bark = bpy.data.materials["M_RedMangrove_Bark"]
m_leaf = bpy.data.materials["M_RedMangrove_Leaf"]
lib = bpy.data.collections["Mangrove_Library"]
tree_stats = {}
for coll in lib.children:
    parts = {ob.name[len(coll.name) + 1:]: ob.data for ob in coll.objects if ob.type == 'MESH'}
    wood = parts["Wood"]
    if "Pneumatophores" in parts:
        wood = combine("tmp_wood", [(parts["Wood"], 0), (parts["Pneumatophores"], 0)])
    objs, tris = [], []
    for lod in range(3):
        w = decimated(wood, LOD_WOOD_RATIO[lod], ecoll)
        l = thinned_leaves(parts["Leaves"], LOD_LEAF_KEEP[lod], LOD_LEAF_GROW[lod])
        me = combine(f"{coll.name}_LOD{lod}", [(w, 0), (l, 1)])
        bpy.data.meshes.remove(w)
        bpy.data.meshes.remove(l)
        me.materials.append(m_bark)
        me.materials.append(m_leaf)
        ob = bpy.data.objects.new(f"{coll.name}_LOD{lod}", me)
        ecoll.objects.link(ob)
        objs.append(ob)
        tris.append(sum(len(p.vertices) - 2 for p in me.polygons))
    if wood is not parts["Wood"]:
        bpy.data.meshes.remove(wood)
    export_fbx(objs, os.path.join(MODEL_DIR, coll.name + ".fbx"))
    clear_coll(ecoll)
    tree_stats[coll.name] = tris


# ---------- ground: terrain, rocks, litter, debris ----------
def ground_copy(src_name):
    # pack the float attributes Unity can't read: muck -> vertex color alpha, wet -> uv0.x
    src = bpy.data.objects[src_name]
    src.name = src_name + "__src"   # free the name so the export copy isn't suffixed .001
    me = src.data.copy()
    col = me.color_attributes["Col"]
    muck = me.attributes.get("muck")
    wet = me.attributes.get("wet")
    if col.domain == 'POINT':
        for i, d in enumerate(col.data):
            c = d.color
            d.color = (c[0], c[1], c[2], muck.data[i].value if muck else 0.0)
    if wet:
        for uv in list(me.uv_layers):
            me.uv_layers.remove(uv)
        uvl = me.uv_layers.new(name="Data")
        for loop in me.loops:
            uvl.data[loop.index].uv = (wet.data[loop.vertex_index].value, 0.0)
    for name in ("muck", "wet"):
        a = me.attributes.get(name)
        if a:
            me.attributes.remove(a)
    ob = bpy.data.objects.new(src_name, me)
    ecoll.objects.link(ob)
    return ob

GROUND = ("Atoll_Terrain", "Atoll_Rocks", "Atoll_LeafLitter", "Atoll_Debris")
try:
    ground = [ground_copy(n) for n in GROUND]
    export_fbx(ground, os.path.join(MODEL_DIR, "Atoll_Ground.fbx"))
finally:
    clear_coll(ecoll)
    bpy.data.collections.remove(ecoll)
    for n in GROUND:
        src = bpy.data.objects.get(n + "__src")
        if src:
            src.name = n


# ---------- placement ----------
trees = []
for ob in bpy.data.collections["Atoll_Mangroves"].objects:
    if ob.instance_type != 'COLLECTION' or ob.instance_collection is None:
        continue
    trees.append({"model": ob.instance_collection.name,
                  "position": to_unity(ob.location),
                  "yaw": round(-math.degrees(ob.rotation_euler.z), 3),   # Blender CCW around Z -> Unity around Y
                  "scale": round(ob.scale.x, 4)})

marker = bpy.data.objects["Dome_Camera_Marker"]
fwd = marker.matrix_world.to_3x3() @ Vector((0, 0, 1))        # the marker's arrow
cam = bpy.data.objects["Dome_Camera"]
tilt = 180 - math.degrees(cam.rotation_euler.x)
data = {"seaLevel": 0.0,
        "trees": trees,
        "domeCamera": {"position": to_unity(marker.location), "forward": to_unity(fwd), "tiltDegrees": round(tilt, 2)},
        "murk": {"radii": [38.0, 26.0]}}
with open(os.path.join(UNITY_DIR, "mangrove_placement.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, indent=1)

result = {"variants": tree_stats, "trees": len(trees), "out": UNITY_DIR}
