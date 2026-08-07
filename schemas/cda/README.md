# CDA R2 core XML schema (normative)

The HL7 Clinical Document Architecture R2 core schema, vendored for the
env-gated C-CDA schema-validation test tier (`NEMSIS2FHIR_CCDA_SCHEMA=1`,
`tests/test_ccda_schema.py`). Entry point:
`infrastructure/cda/CDA.xsd` (which includes `POCD_MT000040.xsd` and the
`processable/coreschemas/` datatype/vocabulary schemas — the full include
closure, byte-identical to upstream, directory layout preserved so the
relative `schemaLocation` paths resolve).

- **Source:** https://github.com/HL7/CDA-core-2.0, `schema/normative/`,
  fetched 2026-08-07 at commit `e922fc35586fd2629f0c8a021080bca9ab424e18`.
- **License:** the schema files carry HL7's BSD-style license header
  ("Copyright (c) 2002..2005 Health Level Seven. All rights reserved.
  Redistribution and use in source and binary forms, with or without
  modification, are permitted provided that..." — notice retention,
  notice reproduction, and an acknowledgement clause). Redistribution is
  expressly permitted; the copyright headers are retained unmodified in
  every file. This product includes software developed by Health Level
  Seven.
- These files are the base CDA R2 schema only (C-CDA is templates over
  this schema — template conformance is the schematron tier's job, not
  XSD's). Do not edit them; refresh by re-fetching from upstream.
