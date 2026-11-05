# What-if editor

```bash
firescore whatif --project projects/sevier_47155 --id FS-001234
```

Three actions are applied to an in-memory copy of the scored layer and
rescored through the same code path as the main run:

- **clear_veg** — defensible-space clearing: the fuel hazard within a
  radius of the target drops to the configured cleared value; every
  structure in the radius is treated.
- **add_hydrant** — a hydrant at the target; water distances recomputed.
- **add_road** — a second exit: the target cluster's road node is linked to
  the nearest node outside the cluster, and egress is recomputed for the
  whole county on the modified graph.

Each action reports the target's score before/after, how many structures
improve, the estimated cost (from `whatif.costs_usd`), and the **score drop
per $1,000** — the ranking a marshal spends by. This is the
return-on-effort engine behind the mitigation ranking in the pilot pack.
