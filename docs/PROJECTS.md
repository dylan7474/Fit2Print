# Keeping projects apart

One project = one folder = one git repo = one deliverables folder. Fit2Print (the tool), Phonosphere (the radio) and the Pi Zero case are three
different things and must never share files.

1. **A marker file.** Every project has `fit2print.toml` with a unique `id`. Every command takes the project folder explicitly and reads the marker first; the folder the shell happens to be in is never used to guess. A folder without a marker is refused.
2. **Records carry the project id.** Print log lines, check results and photos belong to the project whose folder they are in; the dashboard's title and the log's header show the id, so a wrong page is obvious at a glance.
3. **Deliverables go in `~/Downloads/<project>/`**, one folder per project (renders, plates, photos). The tool never writes into another project's folder.
4. **Memory is per project:** one notes file per project, indexed separately, so a session about one does not read the other's state as its own.
5. **The tool repo holds no real project's data.** Fit2Print contains code, profiles, docs and tests. Real projects (the Phonosphere radio) live in their own repos, and tests that need their files skip when they are absent. The one exception is **samples** under `samples/`: small made-up projects built only to test the tool, marked `kind = "sample"`, each in its own folder with its own marker and its own output folder.
6. **Naming:** parts, plates and files that could collide are prefixed or live in the project's own folder (the radio's `back_lower_R` and the case's `base` can both exist).


## The 3D model view ([[model3d]], added 2026-10-31)

The page shows the project's model as a mesh you can turn (drag), zoom (scroll or pinch), hide part by part (tick boxes) and switch between "Assembled" and
"Pulled apart". Each piece of the model is a `[[model3d]]` table in the marker; `fit2print render PROJECT` (and the page's "Draw again") draws them with OpenSCAD
into `renders/3d/` as raw float32 triangles plus a `meta.json`; the browser draws them with WebGL, no library.

    [[model3d]]
    name = "display"            # letters, digits, - and _
    label = "LED display"       # what the person sees
    part = "display"            # the model's `part` value that draws just this piece IN PLACE (not laid flat like an [[export]])
    colour = "#3A7BD5"
    scene = "assembled"         # or "exploded"

With no `[[model3d]]` tables the view is the model's `part = "assembly"` and `part = "exploded"`, each in one colour. A piece OpenSCAD cannot draw is left out and
reported (the others still show). Z is up. The "Components it uses" card lists the library parts in `components = ["id", ...]`.

### Using library parts in a model (hardware.scad)

When the marker lists `components`, `fit2print render` (and the 3D build and `export`) write `hardware.scad` into the project from the component library: each part's dimensions as variables (the person's measurement where there is one, otherwise the published figure, each tagged MEASURED or UNVERIFIED) and a module per piece plus `<id_with_underscores>_shape()` for the whole part, in the part's own frame, z up. A model does `include <hardware.scad>` and draws `translate([...]) esp32_devkitc_v4_shape();`. The file is regenerated every time, so measuring a size in the library changes the model; do not edit it.
