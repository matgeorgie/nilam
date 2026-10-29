# Assignment 2 remaining-work plan

This planning note is documentation-only. It does not change the NILAM application runtime.

## Kanban items
- **To Do** - Capture repository and README evidence (#3)
- **In Progress** - Add and verify safe unit-test CI workflow (#1)
- **Done** - Document remaining work schedule and risk controls (#2)

## Gantt schedule

| Task | Days | Dependency |
| --- | ---: | --- |
| Confirm test scope | 1-2 | - |
| Add CI workflow | 3-4 | Test scope |
| Verify CI run | 5 | CI workflow |
| Collect evidence screenshots | 6 | CI run |
| Peer review pull request | 7 | CI run |
| Final PDF and submission check | 8 | Evidence and review |

## Risk list

| Risk | Type | Mitigation |
| --- | --- | --- |
| A test accidentally depends on external data or credentials | Technical | CI runs only the eight deterministic unit tests listed in the workflow. |
| A dependency upgrade breaks the test runner | Technical | Pin the Python major/minor version and constrain pytest. |
| Assignment evidence is incomplete | Project | Verify each required GitHub page before final PDF export. |
| Parallel edits create merge conflicts | Operational | Use a feature branch, small commits and a reviewed pull request. |

## Test evidence

The workflow executes eight existing unit tests:
- 3 tests in `tests/test_weak_labels.py`
- 5 tests in `tests/test_preference_learning.py`

The selected tests exercise pure scoring and preference-learning logic. They do not start the NILAM server, call external APIs, or load model weights.
