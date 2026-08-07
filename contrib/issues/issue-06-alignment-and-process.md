# Alignment & process: US Core note, release cadence, EMS-Overall transaction bindings

Three smaller items, offered as discussion-starters. (The third belongs on
the EMS-Overall repo — filed here only if the editors prefer one venue.)

**1. US Core alignment note (US realm).** The IG carries race/ethnicity via
the universal `pcc-uv-race` / `pcc-uv-ethnicity` extensions only. US-realm
implementers are contractually pulled toward US Core (`us-core-race`/
`us-core-ethnicity`, birthsex, profile expectations). Proposal: a short
note in Volume IV (National Extensions, IHE USA) blessing a dual-carry —
both extension families on the same Patient — so US implementations don't
fork. We dual-carry in production mappings today; both validators accept it.

**2. Release cadence / branch drift.** The published build and the master
branch differ materially (e.g. a MedicationAdministration profile and
Patient changes exist on master only). For implementers this is a moving
target — pinning "the IG version" is currently pinning a CI snapshot.
Request: periodic tagged snapshots (even draft-labeled) so downstream
conformance claims can name a version.

**3. EMS-Overall: explicit ITI transaction bindings.** EMS-Overall describes
document sharing between the EMS actors but names no ITI transaction
numbers, leaving the transport binding loose. Request: name the intended
bindings (we implement **ITI-65** MHD Provide Document Bundle as the
default, with XDR/XDM as alternates behind a transport interface — that
choice being blessed or corrected upstream would settle it for everyone).

Reference implementation for all three:
<https://github.com/FHIRmedicConsulting/emsInterop>.
