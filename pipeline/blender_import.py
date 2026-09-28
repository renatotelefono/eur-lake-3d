"""
blender_import.py
------------------
Script Blender (bpy) che legge i GeoJSON prodotti da fetch_osm.py
(coordinate locali in metri, vedi coords.py) e genera la geometria 3D del
mondo di gioco: edifici estrusi, strade e sentieri come ribbon, superficie
del laghetto, aree verdi come poligoni piani.

La vegetazione vera e propria (alberi/cespugli) NON viene generata qui: per
seguire la spec del progetto ("MultiMesh in Godot"), qui esportiamo solo i
contorni delle aree verdi; lo scatter degli alberi avviene a runtime in
Godot (vedi scripts/systems/vegetation_scatter.gd).

Uso (da terminale, con Blender 4.x installato):

    blender --background --python pipeline/blender_import.py -- \\
        --data-dir data/osm \\
        --out assets/generated/eur_world.glb

Convenzione assi (IMPORTANTE):
i GeoJSON contengono coppie [x, z] in metri secondo la convenzione Godot
(x = est, z = -nord; vedi coords.py). L'esportatore glTF di Blender, con le
impostazioni di default, converte le coordinate Blender (Z-up) in glTF
(Y-up) cosi': gltf_x = blender_x, gltf_y = blender_z, gltf_z = -blender_y.
Godot usa esattamente la convenzione glTF (Y-up, -Z avanti), quindi per
ottenere gltf_z = z(geojson) dobbiamo impostare blender_y = -z(geojson).
Se in futuro cambi le impostazioni di export glTF (asse "Up"/"Forward"),
aggiorna la funzione `to_blender_xy` di conseguenza e verifica in Godot che
il nord del mondo corrisponda a -Z.
"""

import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def to_blender_xy(x: float, z: float) -> tuple[float, float]:
    return x, -z


def safe_normalized(v: Vector, fallback=Vector((1.0, 0.0, 0.0))) -> Vector:
    if v.length < 1e-9:
        return fallback
    return v.normalized()


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/osm")
    parser.add_argument("--out", default="assets/generated/eur_world.glb")
    return parser.parse_args(argv)


def load_layer(data_dir: Path, name: str) -> dict:
    path = data_dir / f"{name}.geojson"
    if not path.exists():
        print(f"[blender_import] Attenzione: {path} non trovato, layer '{name}' saltato.")
        return {"type": "FeatureCollection", "features": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block_type in (bpy.data.meshes, bpy.data.materials):
        for block in list(block_type):
            if block.users == 0:
                block_type.remove(block)


def get_or_create_collection(name: str) -> bpy.types.Collection:
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def make_material(name: str, color, alpha: float = 1.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, alpha)
        if alpha < 1.0:
            mat.blend_method = "BLEND"
    return mat


def build_polygon_mesh(name, ring_xz, collection, material, extrude_height=0.0, base_z=0.0):
    """Crea una mesh da un anello (poligono chiuso) di coordinate [x, z].
    Se extrude_height > 0 genera un solido estruso (edificio), altrimenti
    una superficie piana (acqua/aree verdi) a quota base_z."""
    ring = ring_xz[:-1] if ring_xz[0] == ring_xz[-1] else ring_xz
    if len(ring) < 3:
        return None

    bm = bmesh.new()
    bottom_verts = [bm.verts.new((*to_blender_xy(x, z), base_z)) for x, z in ring]
    bm.verts.ensure_lookup_table()

    try:
        bottom_face = bm.faces.new(bottom_verts)
    except ValueError:
        # Poligono degenere/self-intersecting: lo saltiamo (limite noto,
        # capita raramente con geometrie OSM imperfette).
        bm.free()
        return None

    if extrude_height > 0:
        ret = bmesh.ops.extrude_face_region(bm, geom=[bottom_face])
        extruded_verts = [v for v in ret["geom"] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=(0, 0, extrude_height), verts=extruded_verts)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    return obj


def build_line_ribbon(
    name, line_xz, width_m, collection, material,
    z_offset=0.0, centerline_offset=0.0, extrude_height=0.0,
):
    """Crea una ribbon mesh (nastro) lungo una linea, larga width_m, per
    rappresentare strade/sentieri. Giunzioni semplici (nessun miter
    elaborato agli angoli): sufficiente per l'MVP, migliorabile in seguito.

    centerline_offset sposta lateralmente il nastro rispetto alla linea
    originale (positivo = a sinistra rispetto alla direzione di percorrenza):
    usato per generare i cordoli (vedi build_road_curbs), che sono nastri
    sottili "agganciati" al bordo della strada invece che centrati sulla
    linea originale.

    extrude_height, se > 0, trasforma il nastro piatto in un muretto solido
    (estruso verso l'alto di quella altezza) invece di una semplice striscia
    dipinta sul terreno: usato per i cordoli quando devono essere un vero
    ostacolo fisico da scavalcare con un salto, non solo un segnale visivo."""
    if len(line_xz) < 2:
        return None

    points = [Vector((*to_blender_xy(x, z), z_offset)) for x, z in line_xz]
    half_w = width_m / 2.0

    left_pts, right_pts = [], []
    for i, p in enumerate(points):
        if i == 0:
            direction = safe_normalized(points[1] - points[0])
        elif i == len(points) - 1:
            direction = safe_normalized(points[-1] - points[-2])
        else:
            direction = safe_normalized((points[i + 1] - points[i]) + (points[i] - points[i - 1]))
        normal = safe_normalized(Vector((-direction.y, direction.x, 0.0)))
        center = p + normal * centerline_offset
        left_pts.append(center + normal * half_w)
        right_pts.append(center - normal * half_w)

    bm = bmesh.new()
    left_verts = [bm.verts.new(p) for p in left_pts]
    right_verts = [bm.verts.new(p) for p in right_pts]
    bm.verts.ensure_lookup_table()

    faces = []
    for i in range(len(points) - 1):
        try:
            face = bm.faces.new((left_verts[i], left_verts[i + 1], right_verts[i + 1], right_verts[i]))
            faces.append(face)
        except ValueError:
            continue

    if extrude_height > 0 and faces:
        # Estrudendo l'intera striscia di facce verso l'alto si ottengono
        # automaticamente anche le pareti laterali lungo tutto il bordo
        # (stesso meccanismo usato per estrudere gli edifici in
        # build_polygon_mesh), quindi il nastro piatto diventa un muretto
        # solido con collisione, non solo una "scatola" superiore.
        ret = bmesh.ops.extrude_face_region(bm, geom=faces)
        extruded_verts = [v for v in ret["geom"] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=(0, 0, extrude_height), verts=extruded_verts)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    return obj


def process_buildings(data_dir, materials):
    coll = get_or_create_collection("Buildings")
    fc = load_layer(data_dir, "buildings")
    count = 0
    for i, feature in enumerate(fc["features"]):
        geom = feature["geometry"]
        if geom["type"] != "Polygon":
            continue
        ring = geom["coordinates"][0]
        height = feature["properties"].get("height_m", 9.0)
        obj = build_polygon_mesh(f"building_{feature.get('id', i)}", ring, coll, materials["building"], extrude_height=height)
        if obj:
            count += 1
    print(f"[blender_import] Edifici generati: {count}")


def process_lines(data_dir, layer_name, collection_name, material, default_width, z_offset):
    coll = get_or_create_collection(collection_name)
    fc = load_layer(data_dir, layer_name)
    count = 0
    for i, feature in enumerate(fc["features"]):
        geom = feature["geometry"]
        if geom["type"] != "LineString":
            continue
        width = feature["properties"].get("width_m") or default_width
        obj = build_line_ribbon(f"{layer_name}_{feature.get('id', i)}", geom["coordinates"], width, coll, material, z_offset=z_offset)
        if obj:
            count += 1
    print(f"[blender_import] {collection_name} generati: {count}")


def process_areas(data_dir, layer_name, collection_name, material, z_offset):
    coll = get_or_create_collection(collection_name)
    fc = load_layer(data_dir, layer_name)
    count = 0
    for i, feature in enumerate(fc["features"]):
        geom = feature["geometry"]
        if geom["type"] != "Polygon":
            continue
        ring = geom["coordinates"][0]
        obj = build_polygon_mesh(f"{layer_name}_{feature.get('id', i)}", ring, coll, material, extrude_height=0.0, base_z=z_offset)
        if obj:
            count += 1
    print(f"[blender_import] {collection_name} generati: {count}")


def build_road_curbs(
    data_dir, layer_name, material, road_z_offset,
    curb_width=0.3, curb_height=0.35,
):
    """Genera due muretti bassi (cordoli) lungo entrambi i bordi di ogni
    strada del layer, a cavallo del bordo stesso (meta' sopra l'asfalto,
    meta' sul terreno esterno).

    Non sono solo un segnale visivo di dove finisce la carreggiata: sono
    muretti solidi con collisione (vedi COLLIDABLE_PREFIXES in world.gd,
    che include "curb_"), alti curb_height - abbastanza bassi da poterli
    scavalcare con un salto normale, ma abbastanza alti da bloccare
    camminando: per passare da strada a marciapiede (o viceversa) bisogna
    saltare, come un vero cordolo."""
    coll = get_or_create_collection(f"{layer_name}Curbs")
    fc = load_layer(data_dir, layer_name)
    count = 0
    for i, feature in enumerate(fc["features"]):
        geom = feature["geometry"]
        if geom["type"] != "LineString":
            continue
        width = feature["properties"].get("width_m") or 6.0
        half_w = width / 2.0
        for side, sign in (("l", 1.0), ("r", -1.0)):
            name = f"curb_{layer_name}_{feature.get('id', i)}_{side}"
            obj = build_line_ribbon(
                name, geom["coordinates"], curb_width, coll, material,
                z_offset=road_z_offset,
                centerline_offset=sign * half_w,
                extrude_height=curb_height,
            )
            if obj:
                count += 1
    print(f"[blender_import] Cordoli generati: {count}")


def collect_vertices(data_dir, layer_name, is_road, default_width):
    """Ritorna TUTTI i punti (non solo gli estremi) di ogni LineString del
    layer, con la relativa larghezza e l'id della strada di provenienza.

    Serve controllare ogni vertice, non solo primo/ultimo: in OpenStreetMap
    una strada spesso attraversa un incrocio senza essere divisa in due
    tronconi separati, quindi il nodo condiviso con un'altra via puo'
    trovarsi a meta' della lista di coordinate (es. un vicolo che finisce a
    "T" dentro una strada principale continua)."""
    fc = load_layer(data_dir, layer_name)
    vertices = []
    for feature in fc["features"]:
        geom = feature["geometry"]
        if geom["type"] != "LineString":
            continue
        coords = geom["coordinates"]
        if len(coords) < 2:
            continue
        width = feature["properties"].get("width_m") or default_width
        way_id = feature.get("id")
        for pt in coords:
            vertices.append((tuple(pt), width, is_road, way_id))
    return vertices


def build_junctions(data_dir, materials, z_offset=0.035, round_to=0.05, min_ways=2):
    """Genera un piccolo disco piatto in ogni punto dove 2+ strade/sentieri
    DIVERSI condividono un nodo, per coprire visivamente la giunzione: le
    ribbon (vedi build_line_ribbon) finiscono con un taglio netto, quindi
    agli incroci ad angolo lasciano una fessura a cuneo. Un disco delle
    dimensioni adeguate centrato sul nodo copre la fessura senza dover
    calcolare raccordi (miter) geometricamente esatti - approccio semplice
    ma efficace, comune nei generatori di strade procedurali "leggeri".

    Soglia di raggruppamento molto stretta (5 cm di default): due strade che
    si toccano davvero in OSM condividono lo stesso nodo, quindi le stesse
    identiche coordinate dopo la conversione in metri locali (stesso
    lat/lon, stessa trasformazione deterministica). Non serve una tolleranza
    larga - anzi andrebbe a creare incroci "falsi" tra strade semplicemente
    vicine ma non collegate topologicamente (es. un marciapiede parallelo a
    una strada, a un paio di metri di distanza)."""
    coll = get_or_create_collection("Junctions")

    vertices = []
    vertices.extend(collect_vertices(data_dir, "roads", True, 6.0))
    vertices.extend(collect_vertices(data_dir, "paths", False, 2.0))

    groups = {}
    for (x, z), width, is_road, way_id in vertices:
        key = (round(x / round_to) * round_to, round(z / round_to) * round_to)
        groups.setdefault(key, []).append((width, is_road, way_id))

    count = 0
    for (x, z), entries in groups.items():
        # Richiede almeno min_ways vie DIVERSE nello stesso punto: una
        # singola via con due vertici ravvicinati (curva stretta) non deve
        # generare un incrocio.
        distinct_ways = {way_id for _, _, way_id in entries}
        if len(distinct_ways) < min_ways:
            continue
        max_width = max(w for w, _, _ in entries)
        any_road = any(is_road for _, is_road, _ in entries)
        radius = max_width / 2.0 + 0.3
        material = materials["road"] if any_road else materials["path"]
        _build_circle_patch(f"junction_{count}", x, z, radius, z_offset, coll, material)
        count += 1

    print(f"[blender_import] Incroci generati: {count}")


def _build_circle_patch(name, x, z, radius, z_offset, collection, material, segments=12):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=radius, segments=segments)
    # create_circle genera il cerchio piatto sul piano XY di Blender
    # (normale lungo Z) attorno all'origine locale: lo spostiamo nel punto
    # giusto usando la stessa convenzione assi di to_blender_xy (vedi in
    # cima al file).
    bx, by = to_blender_xy(x, z)
    bmesh.ops.translate(bm, vec=(bx, by, z_offset), verts=bm.verts[:])

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    return obj


def build_ground_plane(size_m, material):
    coll = get_or_create_collection("Terrain")
    bpy.ops.mesh.primitive_plane_add(size=size_m, location=(0, 0, -0.05))
    obj = bpy.context.active_object
    obj.name = "ground"
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def main():
    args = parse_args()
    data_dir = Path(args.data_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    clear_scene()

    materials = {
        "building": make_material("mat_building", (0.72, 0.70, 0.66)),
        "road": make_material("mat_road", (0.08, 0.08, 0.09)),
        "path": make_material("mat_path", (0.62, 0.46, 0.28)),
        "curb": make_material("mat_curb", (0.92, 0.92, 0.86)),
        "water": make_material("mat_water", (0.10, 0.35, 0.55), alpha=0.75),
        "green": make_material("mat_green", (0.20, 0.45, 0.18)),
        "ground": make_material("mat_ground", (0.46, 0.42, 0.30)),
    }

    build_ground_plane(2200, materials["ground"])
    process_buildings(data_dir, materials)
    process_lines(data_dir, "roads", "Roads", materials["road"], default_width=6.0, z_offset=0.02)
    process_lines(data_dir, "paths", "Paths", materials["path"], default_width=2.0, z_offset=0.03)
    build_road_curbs(data_dir, "roads", materials["curb"], road_z_offset=0.02)
    build_junctions(data_dir, materials)
    process_areas(data_dir, "water", "Water", materials["water"], z_offset=0.05)
    process_areas(data_dir, "green", "Green", materials["green"], z_offset=0.01)

    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=False,
        export_yup=True,
    )
    print(f"[blender_import] Esportato: {out_path}")


if __name__ == "__main__":
    main()