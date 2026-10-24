# qaswarm_exec — Execution Service host agent

Package skeleton only. The Execution Service (sandbox lifecycle, worker runtime drivers with gVisor,
tool adapters, target manager, bounded result collection) arrives in **slice 1c**. It will import only
`qaswarm.contracts` and never connect to the control-plane database.
