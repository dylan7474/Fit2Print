"""A multi-colour plate: several meshes that stay in register, each printed in its own filament, as ONE Bambu Studio (A1) project 3MF.

The slicer will not take the pieces as separate files (a loose set of dots floating in the air stops it: 'ZFiller: encounter idx from clip'), but it slices
them happily as the PARTS of one object, each part assigned a filament. Layout and settings copied from a real Bambu Studio project (the same writer as
~/claude/tools/bambu3mf, tested on the A1 on 2026-10-23); the process settings (layer height, supports) are put in by the slice command, not taken from here.
Do NOT add Application=BambuStudio metadata without the full layout: the slicer segfaults."""
import json, os, uuid, zipfile
from xml.sax.saxutils import quoteattr
import trimesh
from .settings import ROOT

PROFILES = os.path.join(ROOT, "profiles", "bambu_a1")
HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'
NS = ('unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')
DEFAULT_COLOURS = ["#1A1A1A", "#FFFFFF", "#808080", "#D62828"]

def load_mesh(path):
    """An STL (binary or ASCII) as (points, triangles)."""
    m = trimesh.load(path); m.merge_vertices()
    return [tuple(float(c) for c in v) for v in m.vertices], [tuple(int(i) for i in f) for f in m.faces]

def slots(pieces):
    """pieces: [{name, colour or None}] -> ([filament number from 1 for each piece], {number: '#RRGGBB'}). The same colour shares a filament; a piece with
    no colour gets a filament of its own."""
    nums, colours, by_colour = [], {}, {}
    for p in pieces:
        c = (p.get("colour") or "").upper() or None
        if c and c in by_colour:
            nums.append(by_colour[c]); continue
        n = len(colours) + 1
        colours[n] = c or DEFAULT_COLOURS[(n - 1) % len(DEFAULT_COLOURS)]
        if c: by_colour[c] = n
        nums.append(n)
    return nums, colours

def write_3mf(path, name, parts, colours, bed_centre=(128, 128)):
    """parts: [(part_name, (points, triangles), filament number from 1)], already placed relative to each other with z = 0 on the bed.
    colours: {filament number: '#RRGGBB'}. The assembly is centred on the bed in x and y."""
    nfil = max(f for _, _, f in parts)
    xs = [p[0] for _, (pts, _), _ in parts for p in pts]; ys = [p[1] for _, (pts, _), _ in parts for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    objs, comps, cfg_parts, total = [], [], [], 0
    for n, (pname, (pts, tris), fil) in enumerate(parts, start=1):
        total += len(tris)
        v = "".join(f'<vertex x="{x - cx:.5f}" y="{y - cy:.5f}" z="{z:.5f}"/>' for x, y, z in pts)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
        objs.append(f' <object id="{n}" p:UUID="0001{n:04x}-81cb-4c03-9d28-80fed5dfa1dc" type="model"><mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object>')
        comps.append(f'<component p:path="/3D/Objects/object_1.model" objectid="{n}" p:UUID="0001{n:04x}-b206-40ff-9872-83e8017abed1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
        cfg_parts.append(
            f'<part id="{n}" subtype="normal_part" uuid="{uuid.uuid4()}"><metadata key="name" value={quoteattr(pname)}/>'
            '<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
            f'<metadata key="source_file" value={quoteattr(pname + ".step")}/><metadata key="source_object_id" value="0"/><metadata key="source_volume_id" value="0"/>'
            '<metadata key="source_offset_x" value="0"/><metadata key="source_offset_y" value="0"/><metadata key="source_offset_z" value="0"/>'
            f'<metadata key="extruder" value="{fil}"/>'
            f'<mesh_stat face_count="{len(tris)}" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/></part>')
    wid = len(parts) + 1
    obj_model = HEAD + f'<model {NS}>\n <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n' + "\n".join(objs) + '\n </resources>\n <build/>\n</model>\n'
    model = (HEAD + f'<model {NS}>\n <metadata name="Application">BambuStudio-02.08.02.61</metadata>\n <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
             f'  <object id="{wid}" p:UUID="00000001-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n   <components>\n' + "\n".join(comps) + '\n   </components>\n  </object>\n </resources>\n'
             f' <build p:UUID="{uuid.uuid4()}">\n  <item objectid="{wid}" p:UUID="00000003-b1ec-4553-aec9-835e5b724bb4" '
             f'transform="1 0 0 0 1 0 0 0 1 {bed_centre[0]} {bed_centre[1]} 0" printable="1"/>\n </build>\n</model>\n')
    cfg = (HEAD + f'<config>\n <object id="{wid}">\n  <metadata key="name" value={quoteattr(name)}/>\n  <metadata face_count="{total}"/>\n  ' + "\n  ".join(cfg_parts) + '\n </object>\n <plate>\n'
           '  <metadata key="plater_id" value="1"/>\n  <metadata key="plater_name" value=""/>\n  <metadata key="locked" value="false"/>\n'
           '  <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
           f'  <metadata key="filament_maps" value="{" ".join(["1"] * nfil)}"/>\n  <metadata key="filament_volume_maps" value="{" ".join(["0"] * nfil)}"/>\n'
           f'  <model_instance>\n   <metadata key="object_id" value="{wid}"/>\n   <metadata key="instance_id" value="0"/>\n   <metadata key="identify_id" value="74"/>\n'
           '  </model_instance>\n </plate>\n <assemble>\n </assemble>\n</config>\n')
    ps = json.load(open(os.path.join(PROFILES, "multicolour_project_settings.json")))
    for key, val in list(ps.items()):                          # the template has two filaments: size every per-filament list to the number used
        if isinstance(val, list) and len(val) == 2 and not key.startswith("machine_") and key != "start_end_points":
            ps[key] = (val * nfil)[:nfil]
    ps["filament_self_index"] = [str(i) for i in range(1, nfil + 1)]
    ps["flush_volumes_matrix"] = [str(0 if i == j else 300) for i in range(nfil) for j in range(nfil)]
    ps["flush_volumes_vector"] = ["140"] * (4 * nfil)
    ps["filament_colour"] = [colours.get(i, DEFAULT_COLOURS[(i - 1) % len(DEFAULT_COLOURS)]) for i in range(1, nfil + 1)]
    rel = lambda target: (HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                          f' <Relationship Target="{target}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", open(os.path.join(PROFILES, "multicolour_content_types.xml")).read())
        z.writestr("_rels/.rels", rel("/3D/3dmodel.model"))
        z.writestr("3D/3dmodel.model", model)
        z.writestr("3D/_rels/3dmodel.model.rels", rel("/3D/Objects/object_1.model"))
        z.writestr("3D/Objects/object_1.model", obj_model)
        z.writestr("Metadata/model_settings.config", cfg)
        z.writestr("Metadata/project_settings.config", json.dumps(ps, indent=4))
