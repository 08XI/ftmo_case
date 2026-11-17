# Demo script

Prereqs: venv active (`source .venv/Scripts/activate`), clean `main`, `FACTORY_USER=<your GitHub login>`.

Live (Claude Code):

    factory new "Cancel remaining quantity of partially filled orders"       --goal "A partially filled order can be cancelled; filled quantity is kept; FILLED stays terminal." --id T-001
    factory run planner
    cat .factory/tasks/T-001/plan.md        # human reads, may edit
    factory approve-plan
    factory run implementer                 # session 1, may stop with status in_progress
    factory run implementer                 # session 2 resumes from handoff-001.json
    factory run reviewer                    # blind: diff + plan + factory test run
    factory status
    factory verify
    factory pr                              # pushes branch, opens PR with provenance body

Fallback (no network/API): `export FACTORY_RUNTIME=fake FACTORY_FAKE_DIR=demo/fake` and run the same commands.

Tamper demo (after `factory verify` passes):

    echo "- extra scope" >> .factory/tasks/T-001/plan.md && git commit -qam "edit plan"
    factory verify                          # FAIL: chain of custody
    git reset -q --hard HEAD~1
