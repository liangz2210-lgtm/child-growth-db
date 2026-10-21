# Child Growth Database

> Turn "a child is growing up" from **a diary** into **an analyzable matrix** — where every judgement you make can be falsified by your own data.

A local-first framework for building a longitudinal, multi-dimensional database about one person's development. Markdown + JSONL + Python. No dependencies, no cloud, no app. `git`-versionable.

**This is not a parenting app. It is a data-engineering method** for anyone who wants to record a person's long-term development seriously.

[中文版 / Chinese version → README.md](README.md)

---

## Why

Ordinary growth records fail in three ways:

| Problem | What it looks like |
|---|---|
| **Recorded, then forgotten** | 3,000 photos, and you can't recall how much he slept at 18 months |
| **Recorded, but useless** | You have height and weight, and no idea what to change next |
| **Recorded, but wrong** | Self-reported screen time is typically 30–50% below actual; nobody logs which caregiver was on duty |

One root cause: **we ask humans to compute while they record**.

Humans can't. So they record only the easy things and drop everything complex — and end up with a "multi-dimensional" spreadsheet that contains nothing but sleep.

This framework's answer: **the human writes one sentence; the machine computes every indicator.**

---

## Three core designs

### 1. A matrix, not a diary

**13 core dimensions + 7 meta-capabilities**, sampled at different resolutions:

```
T0 daily    → only 2 (sleep, emotion)
T1 weekly   → language, self-care, interaction, screen, safety…
T2 monthly  → all 13 core dimensions          ← hard constraint
T3 quarterly→ trajectories, change points, hypothesis re-testing
```

Sampling everything daily → the matrix is 97% empty and the habit dies.
**Daily can be sparse. Monthly must be complete.**

### 2. An event stream, not a form

| You say | The system gets |
|---|---|
| "He asked me 'why' three times" | language dim + questioning dim + frequency + traceable verbatim quote |
| "Didn't fall asleep until ten" | sleep dim + lights-out time + comparison against history |

**Why this matters most:** make people compute and the habit breaks. Make them only record and it survives three years.

### 3. Hypothesis-driven, not passive

What the system maintains is not "data" but **falsifiable hypotheses**, each with a deadline:

> *"If we cap the afternoon nap at 2 hours, his sleepiness signals will arrive earlier within a week.*
> *If they don't, sleep onset is driven by environmental cues, not sleep pressure — change the intervention point."*

A falsified hypothesis is as valuable as a confirmed one. That line is what separates this from a diary.

---

## Quick start

```bash
git clone https://github.com/liangz2210-lgtm/child-growth-db.git
cd child-growth-db

# One command: create profile, self-test, tell you what to do next
python3 scripts/init.py
```

`init.py` does three things: creates `profile/child-profile.md` from the template, runs validate/derive/view once, and prints which dimensions to fill first, ranked by gap severity.

**Then fill in one date** — line 3 of `profile/child-profile.md`:

```yaml
birthday: 2024-01-01   # ← set a real birthday; every age is derived from it
```

Until you do, `age_days` stays empty — **this repo never guesses.**

<details>
<summary>Kick the tires without initializing</summary>

```bash
python3 scripts/validate.py --fixtures   # see the 14 error classes the validator catches
python3 scripts/validate.py              # validate the example event stream
python3 scripts/derive.py                # L0 → L2 derivation
python3 scripts/view.py                  # heatmap / status / gap report
cat derived/gaps.md
```
</details>

**Zero third-party dependencies.** Python 3.9+. No `pip install`.

### If everything reads "overdue", that's not a bug

`events/2026-01-example.jsonl` is **synthetic** data dated January 2026. Run `gaps.md` today and it will correctly report that every dimension has been silent for 200+ days.

That is the system being honest: **these cells have been empty for a long time.** Delete the example, add your own events, and the status normalizes.

### Where to start reading

| If you are | Start with |
|---|---|
| Trying to understand the design | [`CRITIQUE.md`](CRITIQUE.md) — five rounds of self-critique |
| Just want to use it | `python3 scripts/init.py` |
| Handing it to an AI agent | [`AGENTS.md`](AGENTS.md) |
| Want to change the structure | [`MATRIX.md`](MATRIX.md) + [`schema/dimension-tree.json`](schema/dimension-tree.json) |

*(Note: `CRITIQUE.md`, `AGENTS.md` and `MATRIX.md` are currently Chinese-only. The schema, scripts and dimension tree are language-neutral.)*

---

## Data flow

```
① One sentence from everyday conversation
        ↓ extracted into a structured event (verbatim text, observer, confidence)
② events/YYYY-MM.jsonl         ← append-only, never edited (single source of truth)
        ↓ code validates: fields, ranges, duplicates, contradictions
③ derived/events.csv
        ↓ code aggregates
④ derived/daily.csv / weekly.csv   ← always recomputable
        ↓ machine interprets
⑤ judgement and advice
```

**Why so many layers:** raw observations are kept forever, so if an indicator definition changes you can recompute all history. Write numbers straight into a table and you can never answer "where did this 9.5 hours come from?"

---

## Three iron rules

| ID | Rule | Why |
|---|---|---|
| **R-03** | **No imputation** | Missing means missing. Forward-fill, mean-fill, trend estimation — all fabrication |
| **R-04** | **Bottom-up aggregation only** | indicator → dimension → domain is computable; the reverse is fiction |
| **R-05** | **Every number traceable to the original words** | If you can't trace it, it's an impression, not data |

Full spec: [`MATRIX.md`](MATRIX.md) — 20 rules, each annotated with *who enforces it*.

---

## Key design decisions

### LLM and code must do different jobs

| Who | Does what |
|---|---|
| **LLM** | Parses language, extracts events, assigns dimensions, explains, generates questions |
| **Code** | Validates, aggregates, **computes every number**, detects anomalies |

**Iron rule: any number derived from other numbers must be computed by code.**
LLM arithmetic is probabilistic — and it doesn't raise an error when it's wrong.

### Every rule must name its enforcer

`code` (script-enforced) / `prompt` (honor system) / `human` (a person decides).

Honest finding: **only 5 of the 20 rules have real technical enforcement.** The rest run on discipline.
The next thing to build is not more rules — it's pushing `prompt`-class rules down into `code`.

### Monthly upgrades, default-deny

Once a month, do an external literature scan, then ask: **is there a real pain point in the database right now?**

No → write "no upgrade proposal this month" and stop.

Yes → the proposal must answer: who did we learn from (with source), which specific problem does it solve (with data), what happens if we don't upgrade, what's the cost, is it reversible.

Plus a hard constraint: **at most 2 structural changes per year.**

> Three consecutive months with no proposal = the system is stable. That's success, not failure.
> This rule exists to prevent upgrading for the sake of upgrading — a system that keeps changing never accumulates data.

---

## What this deliberately does not do

1. **No medical diagnosis.** Anything abnormal → refer to a doctor, with a pre-visit checklist
2. **No standardized developmental score.** Formal assessment belongs to clinical tools and professionals
3. **No substitute for professional evaluation.** WHO's own GSED states it is *not intended for individual screening or diagnosis*
4. **Not trying to fill the matrix.** It tries to keep the *important* cells non-empty
5. **No promise of efficacy.** It's an observation instrument, not an intervention

---

## References

- **WHO GSED** (Global Scales for Early Development, 2023) — four-domain structure, D-score method
- **WHO/UNICEF Nurturing Care Framework** (2018) — five-domain environment model, incl. *security & safety*
- **CDC Learn the Signs. Act Early** (2022 revision) — milestones at the 75th percentile
- **Harvard Center on the Developing Child** — Serve and Return, five steps
- **Sameroff's developmental cascades, Bronfenbrenner's ecological systems, Skinner's operant conditioning** — the three explanatory layers

Details in [`knowledge/benchmarks.md`](knowledge/benchmarks.md).

---

## License

MIT. Fork it, change the dimension tree, wire up your own frontend.

Keep one rule: **never treat a number the LLM computed as data.**
