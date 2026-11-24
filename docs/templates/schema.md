## How an alignment change is applied

`LandDB.revise(base, new, ...)` adds the revised alignment as a new version, marks the base `superseded`,
recomputes the affected areas and interests, and reconciles them lot by lot:

- **Out of scope** (an interest in the base, none in the new version): the interest becomes `withdrawn`;
  its steps not yet done become `withdrawn`; steps already done are kept and flagged
  `completed before revision: review`.
- **New in scope**: new interests with every step `not_started`.
- **Continuing** (same lot and take type): the area change is logged when it exceeds {{landdb.area_tol_m2:.0f}} square metre or the
  instrument changes; progress already made is carried over to the new interest when the instrument is the
  same, and the old interest becomes `superseded`.
- Every change is written to `change_log` with the version that caused it and the reason.

## Demo in the committed database

The database holds {{landdb.tables.alignment_versions}} alignment versions ({{landdb.tables.interests}} interests,
{{landdb.tables.steps}} steps, {{landdb.tables.documents}} document placeholders). SYNTHETIC progress was recorded on
the baseline {{landdb.update_demo.base_version}}, then the alignment was revised to
{{landdb.update_demo.new_version}} ({{landdb.update_demo.revised_label}}). Result:
{{landdb.update_demo.n_out}} interests moved out of scope, {{landdb.update_demo.n_new}} came into scope,
{{landdb.update_demo.n_changed}} continuing interests changed area or instrument, and
{{landdb.update_demo.n_steps_to_review}} completed steps were flagged for review. The change log has
{{landdb.tables.change_log}} entries. All {{landdb.n_rules}} validation rules pass on the committed file
({{landdb.validation_failures}} failures); `tests/test_landdb.py` plants an error for each rule and checks that it is caught.

Lots that moved out of scope: {{landdb.update_demo.out_lots:join}}.
Lots that came into scope: {{landdb.update_demo.new_lots:join}}.
