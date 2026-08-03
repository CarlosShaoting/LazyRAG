# Decision policy v1

1. Missing preparation inputs: ask for or bind inputs; do not start.
2. Stopped session with user resume intent: call `resume_workflow`.
3. Failed/interrupted ready target: call the profile's permitted advance tool.
4. Succeeded target explicitly changed: advance the target; Runtime resolves rewind.
5. Multiple independent ready steps: parallelize only when the profile allows it.
6. No ready step and active Attempt: observe; do not manufacture a transition.
7. Required Artifact absent at terminal callback: fail the Attempt structurally.

