# Lessons: each real failure and the check it became

(From Phonosphere, 2026-10-16 onwards. The check column says where it lives or will live.)

| Failure | What it cost | Check |
|---|---|---|
| A line over air judged by length, not by what held it up: a groove broke out of a corner | a print | toolpath check: cantilever depth and sides held, not line length |
| Arches printed on an unsupported lap shelf | a failed print | unsupported-plastic check; never print a flagged plate without looking |
| Supports filled blind pilots and small holes | a failed print | as-built check: supports inside small holes |
| Seam bolts unreachable with a driver (hand tried it: an hour for 4 bolts) | a redesign | fixings check: a 6 mm rod, 100 mm long, straight from outside to the head |
| Bolt holes passing through air, not plastic | a redesign | fixings check: plastic around each hole |
| The file named on the command line was a stale STL from an older design | three "checks" of the wrong part | refuse any STL older than the model; rebuild or stop |
| The as-built check tried only 0/90/180/270 turns; the slicer had turned the plate 45 degrees | false "missing" and "extra" | find the turn angle by chamfer distance |
| A pod lid collided with turned lugs | a part that would not fit | fit check: part against part |
| A lug's wedge was cut short by the pod, leaving a flat 4 mm shelf: ragged print | a coupon | layer slicer: z-step in area; fix by flush lug and 45 degree underside |
| A screw foot with a flat 4 mm underside, spotted by hand in the slicer | a check that missed it | wedge under every protruding boss; the checker now needs a case for it |
| The pod cannot be pushed in or out through the open back (six lugs in the way) | would have been found at assembly | assembly sweeps, in the real order |
| A check test that models the wrong gap (the plates lock a 1.5 mm gap) | a false alarm | model the gaps the real build has |
| `pgrep -f` matches its own command line: false "still running" | hours of stuck waits | wait on a PID with `kill -0` |
| A tool printed a secret into the log while looking something up | a credential exposed | print only the fields you mean; mask by default |
