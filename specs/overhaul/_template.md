# Phase X — <Title>

```yaml
phase_id: phase_X
status: pending          # pending | in_progress | done | blocked
depends_on: []           # list of phase_ids that must be done first
blocks: []               # list of phase_ids that wait on this
estimated_effort: <e.g. "3 days">
test_framework: pytest + streamlit.testing.v1.AppTest
```

## Goal

<1-paragraph plain-language description of what this phase delivers and why.>

## Acceptance criteria

- [ ] <criterion 1>
- [ ] <criterion 2>
- [ ] All tests in `tests/<phase_folder>/` green
- [ ] Manual verification checklist (below) green

## Prerequisites

- <file or function that must already exist>
- <phase_id> done

## Task list

### TASK-X.1 — <imperative title>

```yaml
parallelizable: no            # yes | no
parallel_group: null          # group id if parallelizable
reason: <why this can/can't run in parallel>
estimated_effort: <e.g. "2h">
```

**Test first** (TDD):
```python
# tests/<file>.py
def test_<scenario>():
    ...
```

**Files to modify**:
- `path/to/file.py:start-end` — <what changes>

**Implementation steps**:
1. Step 1
2. Step 2

**Acceptance**:
- [ ] Failing test now passes
- [ ] `pytest tests/<file>.py::test_<scenario>` green

---

### TASK-X.2 — <next task>

(same shape)

## Streamlit considerations (if applicable)

- **Components touched**: `st.dataframe`, `st.metric`, ...
- **AppTest pattern**:
  ```python
  from streamlit.testing.v1 import AppTest
  at = AppTest.from_file("src/dashboard.py")
  at.run()
  ...
  ```
- **Session state keys**: <list>

## Verification

End-to-end check:

1. Run `<command>`
2. Expect `<observation>`

## Done definition

- [ ] All tasks marked complete in this doc
- [ ] All tests green (`pytest tests/<phase_folder>/`)
- [ ] Manual verification passed
- [ ] Phase status updated to `done` in `README.md`

## References

- Plan: `/Users/leander/.claude/plans/first-the-scale-you-hazy-naur.md`
- Code anchors: <file:line list>
- Other phase docs: <links>
