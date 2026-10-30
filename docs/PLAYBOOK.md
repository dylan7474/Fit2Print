# The Fit2Print playbook: a repeatable way to go from an idea to a print with an AI colleague

Written 2026-10-30 from the Phonosphere radio and the Pi Zero sample. It is the model made explicit, so a new project (or a new session, or a new AI) follows the same way without anyone remembering this conversation.

## 1. The principle: files are the memory, the AI is the worker
A long chat is a poor place to keep a project. When a conversation is summarised, details are lost (this happened: the meter fit answers). So:
* **The project's files hold all state:** `fit2print.toml` (what it is), `NEXT.md` (what is next, what needs the person), `brief.md` (what and why), `records/` (every check, print and photo), the model source. Nothing important lives only in a chat.
* **A session is short and bounded.** It starts by reading the state and ends by writing it. Any session, today's or in six months, can pick up.
* **The dashboard is the front page:** `fit2print dashboard` shows state worked out from the records, never typed in.

### Session start (the AI does this first, every time)
1. Read `fit2print.toml`, `NEXT.md`, `brief.md`, and the project's own `CLAUDE.md` (its rules).
2. Run `fit2print dashboard` and read "What I need from you" and the last prints.
3. Say in one or two plain sentences where the project stands and what the next step is. Then wait for the person's go-ahead before doing anything new.
### Session end (the AI does this last)
1. Record what happened (print log entries, photos, check runs).
2. Rewrite `NEXT.md`: done, next, blocked, needs-you.
3. Commit and push if the person has asked for that on this project.

## 2. The stages and who does what
| Stage | The AI | The person | Gate to leave |
|---|---|---|---|
| 0 Scope | asks the questions it needs, reads the hardware library, writes `brief.md`, lists assumptions and unknowns | answers, measures anything unknown | brief approved |
| 1 Concept | makes concept pictures, one at a time | approves or redirects | picture approved |
| 2 Model | writes the parametric model; every dimension a named parameter; marks unverified dimensions | | model builds, parameters exported |
| 3 Checks | runs fit, printability, assembly, fixings; shows every finding as a picture and a plain sentence; fixes the model and re-runs | looks at the pictures | all checks pass, **a CHECK is shown and decided by the person, a BLOCK is never waived** |
| 4 Plate | slices, judges the toolpaths, refuses stale files | looks at the plate | person says print |
| 5 Coupon | for anything untested and expensive, a small test piece first | prints it, sends a photo | coupon result logged |
| 6 Print | gives ONE file at a time, with what to look for | prints, sends a photo | photo logged |
| 7 Verify | compares the photo with what the checks said, logs it honestly | | outcome logged |
| 8 Assemble | tells the build order, checks it fits | tries it, reports | fit notes logged |
| 9 Learn | turns each failure into a check with a negative control | approves the rule | the control fails first, then passes after the fix |

## 3. The standing rules (each came from a real failure; see LESSONS.md)
1. **Never waive a check.** Show every BLOCK; show every CHECK and let the person decide.
2. **Look before printing:** pictures and overlap checks with the real hardware in place, before a file is handed over.
3. **Coupons before big prints.** A small test piece of the risky feature first.
4. **Print time and filament are a cost.** Test only where there is a real, named concern.
5. **Every fixing must be reachable** by a straight driver, and every bolt hole must pass through plastic.
6. **A file is only the current design if it is newer than its model.** Stale files are refused.
7. **Never invent a dimension.** Unknown numbers are marked, and the person measures.
8. **Projects are kept apart:** their own folder, marker, records and output folder. Samples are marked as samples.
9. **A question is not a go-ahead.** Answer, give the plan, wait.
10. **One picture at a time, in plain words.** The person is not an engineer; do not bury them.
11. **Report outcomes faithfully:** failures with the output, skipped steps said to be skipped, and the AI never marks its own work as passed.
12. **No secrets in output or in files that are backed up.** Print only the fields you mean.
13. **Name the person's pronouns as given; never guess.**

Rules that can be code are code (the stale-file refusal, the marker check, the negative controls). Rules that cannot are in the project's `CLAUDE.md`, which the AI reads at the start of every session.

## 4. What the AI may and may not do
| May | May not |
|---|---|
| propose designs and changes (as a diff with before/after pictures) | mark a check as passed (only the tools do) |
| write models, run checks, slice, explain | invent a dimension, or call a guess a measurement |
| draft a new check from a failure | decide how it should look |
| keep the records and the dashboard up to date | approve its own print |
| say "I don't know" and ask | start new work on a question |

## 5. How Claude is wired in, and the concerns, honestly
Level 1 works today. Levels 2 to 4 are later and only if they earn it.
1. **Claude Code in the project folder, with Fit2Print as its tools.** The project's `CLAUDE.md` carries the rules, `NEXT.md` carries the state, and the CLI runs the checks. This is how the whole of today went.
2. **Stage commands and gates.** Slash commands/skills per stage (scope, check, plate, log), and hooks that enforce a gate (for example, refuse to hand over a print file unless a check record exists for that exact file).
3. **An MCP server** that exposes the checks as tools, so any agent can use them with the same rules.
4. **An app that calls a model through an API,** with the provider as a setting (Claude, another cloud model, a local one).

| Concern | Why it is real | What the model does about it |
|---|---|---|
| The AI forgets over a long chat | summaries lose detail | state lives in files; short sessions; session start and end protocols |
| It states a number it does not know | models fill gaps | unknown dimensions are marked; the person measures; checks use the model's exported parameters, never numbers from memory |
| It grades its own work | a model can be over-confident | only tools mark pass; negative controls prove the tools can fail |
| It prints from a stale file | happened on 29 Oct | the tool refuses stale input |
| Cost | long sessions are expensive | short bounded sessions, checks run as ordinary programs not model calls, and the container does the heavy work |
| Privacy | models, photos and notes are personal | local by default; the person chooses what is sent to which model; secrets never in files |
| Drift and vendor | the model, the slicer and the profiles change | versions are pinned (container); the playbook and checks are plain text a different AI can follow |
| The person cannot see what the AI did | trust | the event log and the dashboard show every check, print and decision |

## 6. Definition of done for a project
Every part has a PASS (or a person-decided CHECK) on the current design; every risky feature has a coupon result; every real print has a photo and an outcome in the log; the build order passes; and `NEXT.md` says "finished" or what is left.
