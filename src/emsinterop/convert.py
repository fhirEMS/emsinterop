"""Top-level convenience API: NEMSIS XML in, FHIR bundles out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .assemble import build_composition, document_bundle
from .ingest import parse, to_operation_outcome, validate
from .log import event, get_logger
from .mapping import MappingContext, map_pcr
from .submit import transaction_bundle

logger = get_logger("convert")


@dataclass
class ConversionResult:
    context: MappingContext
    composition: dict
    transaction: dict
    document: dict

    @property
    def resources(self) -> list[dict]:
        return self.context.resources

    @property
    def issues(self):
        return self.context.issues


def convert(
    source: str | Path | bytes,
    xsd_validate: bool = True,
    document_variant: str = "CR",
    agency_names: dict[str, str] | None = None,
    personnel_names: dict[str, dict[str, str]] | None = None,
    agency_contact: dict[str, str] | None = None,
    city_gazetteer: dict[str, str] | None = None,
) -> list[ConversionResult]:
    """Convert an EMSDataSet document; one result per PatientCareReport.

    XSD-invalid documents raise ValueError carrying the OperationOutcome
    (quarantine, don't crash — the caller owns the quarantine store).
    """
    if xsd_validate:
        errors = validate(source)
        if errors:
            event(logger, "xsd.rejected", level=logging.WARNING, count=len(errors))
            exc = ValueError(f"NEMSIS XSD validation failed with {len(errors)} error(s)")
            exc.operation_outcome = to_operation_outcome(errors)  # type: ignore[attr-defined]
            raise exc

    dataset = parse(source)
    results: list[ConversionResult] = []
    for pcr in dataset.reports:
        ctx = map_pcr(dataset, pcr, agency_names=agency_names,
                      personnel_names=personnel_names,
                      agency_contact=agency_contact,
                      city_gazetteer=city_gazetteer)
        composition = build_composition(ctx, variant=document_variant)
        transaction = transaction_bundle(ctx.resources, bundle_identifier=ctx.pcr_number)
        document = document_bundle(ctx, composition)
        event(logger, "pcr.converted", pcr_number=ctx.pcr_number,
              variant=document_variant, resources=len(ctx.resources),
              issues=len(ctx.issues))
        results.append(ConversionResult(ctx, composition, transaction, document))
    return results
