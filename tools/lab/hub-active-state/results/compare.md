| case | role | t | ask | cgm-remote-monitor | Nocturne GetActiveAt | Nocturne list read | agree (GetActiveAt / list) | note |
|---|---|---|---|---|---|---|---|---|
| c1-tt-cancel | case | T0+10 | tt | `c1-tt` | `c1-tt` | `c1-tt` | yes / yes |  |
| c1-tt-cancel | case | T0+30 | tt | `none` | `none` | `c1-cancel+c1-tt` | yes / **no** | GetActiveAt(state "Active") = `c1-tt` |
| c1-tt-cancel | case | T0+70 | tt | `none` | `none` | `c1-cancel` | yes / **no** |  |
| c1-ctl | control | T0+10 | tt | `c1-tt` | `c1-tt` | `c1-tt` | yes / yes |  |
| c1-ctl | control | T0+30 | tt | `c1-tt` | `c1-tt` | `c1-tt` | yes / yes |  |
| c1-ctl | control | T0+70 | tt | `none` | `none` | `none` | yes / yes |  |
| c1-perturb | perturbation | T0+10 | tt | `c1-tt` | `c1-tt` | `c1-tt` | yes / yes |  |
| c1-perturb | perturbation | T0+30 | tt | `c1-tt` | `c1-tt` | `c1-tt` | yes / yes |  |
| c1-perturb | perturbation | T0+70 | tt | `none` | `none` | `c1-cancel` | yes / **no** |  |
| c2-ov-cancel | case | T0+10 | override_tx | `c2-ov` | `c2-ov` | `c2-ov` | yes / yes |  |
| c2-ov-cancel | case | T0+30 | override_tx | `c2-ov` | `c2-ov` | `c2-ov` | yes / yes |  |
| c2-ov-cancel | case | T0+70 | override_tx | `none` | `none` | `none` | yes / yes |  |
| c2-ctl | control | T0+10 | override_tx | `c2-ov` | `c2-ov` | `c2-ov` | yes / yes |  |
| c2-ctl | control | T0+30 | override_tx | `none` | `none` | `none` | yes / yes |  |
| c2-ctl | control | T0+70 | override_tx | `none` | `none` | `none` | yes / yes |  |
| c2-perturb | perturbation | T0+10 | override_tx | `c2-ov` | `c2-ov` | `c2-ov` | yes / yes |  |
| c2-perturb | perturbation | T0+30 | override_tx | `none` | `none` | `none` | yes / yes |  |
| c2-perturb | perturbation | T0+70 | override_tx | `none` | `none` | `none` | yes / yes |  |
| c3-loop-ds-override | case | T0+12 | override_ds | `active` | `active` | — | yes |  |
| c3-loop-ds-override | case | T0+40 | override_ds | `none` | `active` | — | **no** |  |
| c3-loop-ds-override | case | T0+120 | override_ds | `none` | `active` | — | **no** |  |
| c3-ctl | control | T0+12 | override_ds | `active` | `active` | — | yes |  |
| c3-ctl | control | T0+27 | override_ds | `active` | `active` | — | yes |  |
| c3-ctl | control | T0+120 | override_ds | `active` | `active` | — | yes |  |
| c3-perturb | perturbation | T0+12 | override_ds | `active` | `active` | — | yes |  |
| c3-perturb | perturbation | T0+40 | override_ds | `active` | `active` | — | yes |  |
| c3-perturb | perturbation | T0+120 | override_ds | `none` | `active` | — | **no** |  |
| c3-perturb-short | perturbation | T0+12 | override_ds | `none` | `active` | — | **no** |  |
| c3-perturb-short | perturbation | T0+40 | override_ds | `none` | `active` | — | **no** |  |
| c3-perturb-short | perturbation | T0+120 | override_ds | `none` | `none` | — | yes |  |
| c4-ps-timed-after-permanent | case | T0+30 | profile | `Weekend basal=0.800` | `Weekend basal=0.800` | — | yes |  |
| c4-ps-timed-after-permanent | case | T0+90 | profile | `Exercise basal=0.500` | `Exercise basal=0.500` | — | yes |  |
| c4-ps-timed-after-permanent | case | T0+150 | profile | `Weekend basal=0.800` | `Default basal=1.100` | — | **no** |  |
| c4-ctl | control | T0+30 | profile | `Weekend basal=0.800` | `Weekend basal=0.800` | — | yes |  |
| c4-ctl | control | T0+90 | profile | `Weekend basal=0.800` | `Weekend basal=0.800` | — | yes |  |
| c4-ctl | control | T0+150 | profile | `Weekend basal=0.800` | `Weekend basal=0.800` | — | yes |  |
| c4-perturb | perturbation | T0+30 | profile | `Weekend basal=0.800` | `Weekend basal=0.800` | — | yes |  |
| c4-perturb | perturbation | T0+90 | profile | `Exercise basal=0.500` | `Exercise basal=0.500` | — | yes |  |
| c4-perturb | perturbation | T0+150 | profile | `Exercise basal=0.500` | `Exercise basal=0.500` | — | yes |  |
| c5-aaps-timeshift-ms | case | T0+300 | profile | `Default basal=1.150` | `Default basal=1.250` | — | **no** |  |
| c5-aaps-timeshift-ms | case | T0+600 | profile | `Default basal=1.400` | `Default basal=1.500` | — | **no** |  |
| c5-ctl | control | T0+300 | profile | `Default basal=1.250` | `Default basal=1.250` | — | yes |  |
| c5-ctl | control | T0+600 | profile | `Default basal=1.500` | `Default basal=1.500` | — | yes |  |
| c5-perturb | perturbation | T0+300 | profile | `Default basal=2.500` | `Default basal=2.500` | — | yes |  |
| c5-perturb | perturbation | T0+600 | profile | `Default basal=3.000` | `Default basal=3.000` | — | yes |  |
| c5-perturb-hours | perturbation | T0+300 | profile | `Default basal=1.250` | `Default basal=1.350` | — | **no** |  |
| c5-perturb-hours | perturbation | T0+600 | profile | `Default basal=1.500` | `Default basal=1.600` | — | **no** |  |
| c6-tt-same-ms | case | T0+10 | tt | `c6-tt-a` | `c6-tt-a` | `c6-tt-a` | yes / yes | list read with dedup mocked = `c6-tt-a+c6-tt-b` |
| c6-tt-same-ms | case | T0+45 | tt | `c6-tt-a` | `c6-tt-a` | `c6-tt-a` | yes / yes |  |
| c6-ctl | control | T0+10 | tt | `c6-tt-a` | `c6-tt-a` | `c6-tt-a` | yes / yes |  |
| c6-ctl | control | T0+45 | tt | `c6-tt-a` | `c6-tt-a` | `c6-tt-a` | yes / yes |  |
| c6-ctl | control | T0+100 | tt | `c6-tt-b` | `c6-tt-b` | `c6-tt-b` | yes / yes |  |
| c6-perturb | perturbation | T0+10 | tt | `c6-tt-b` | `c6-tt-b` | `c6-tt-b` | yes / yes | list read with dedup mocked = `c6-tt-a+c6-tt-b` |
| c6-perturb | perturbation | T0+45 | tt | `none` | `c6-tt-a` | `none` | **no** / yes | list read with dedup mocked = `c6-tt-a` |
| c7-ov-backfill | case | T0+30 | override_tx | `c7-ov-earlier` | `c7-ov-earlier` | `c7-ov-earlier` | yes / yes |  |
| c7-ov-backfill | case | T0+90 | override_tx | `c7-ov-earlier+c7-ov-later` | `c7-ov-later` | `c7-ov-earlier+c7-ov-later` | **no** / yes |  |
| c7-ctl | control | T0+15 | override_tx | `c7-ov-earlier` | `c7-ov-earlier` | `c7-ov-earlier` | yes / yes |  |
| c7-ctl | control | T0+45 | override_tx | `none` | `none` | `none` | yes / yes |  |
| c7-ctl | control | T0+75 | override_tx | `c7-ov-later` | `c7-ov-later` | `c7-ov-later` | yes / yes |  |
| c7-perturb | perturbation | T0+30 | override_tx | `c7-ov-earlier` | `c7-ov-earlier` | `c7-ov-earlier` | yes / yes |  |
| c7-perturb | perturbation | T0+90 | override_tx | `c7-ov-earlier+c7-ov-later` | `c7-ov-later` | `c7-ov-later` | **no** / **no** |  |

rows: 61; cases rows agreeing on GetActiveAt: 12/18; control rows agreeing on every reading: 20/20
