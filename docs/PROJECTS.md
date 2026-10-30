# Keeping projects apart

One project = one folder = one git repo = one deliverables folder. Fit2Print (the tool), Phonosphere (the radio) and the Pi Zero case are three
different things and must never share files.

1. **A marker file.** Every project has `fit2print.toml` with a unique `id`. Every command takes the project folder explicitly and reads the marker first; the folder the shell happens to be in is never used to guess. A folder without a marker is refused.
2. **Records carry the project id.** Print log lines, check results and photos belong to the project whose folder they are in; the dashboard's title and the log's header show the id, so a wrong page is obvious at a glance.
3. **Deliverables go in `~/Downloads/<project>/`**, one folder per project (renders, plates, photos). The tool never writes into another project's folder.
4. **Memory is per project:** one notes file per project, indexed separately, so a session about one does not read the other's state as its own.
5. **The tool repo holds no project data.** Fit2Print contains code, profiles, docs and tests; example data lives in the project repos, and tests that need real project files skip when they are absent.
6. **Naming:** parts, plates and files that could collide are prefixed or live in the project's own folder (the radio's `back_lower_R` and the case's `base` can both exist).
