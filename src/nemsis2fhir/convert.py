"""Top-level convenience API: NEMSIS XML in, FHIR bundles out."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assemble import build_composition, document_bundle
from .ingest import parse, to_operation_outcome, validate
from .mapping import MappingContext, map_pcr
from .submit import transaction_bundle


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
) -> list[ConversionResult]:
    """Convert an EMSDataSet document; one result per PatientCareReport.

    XSD-invalid documents raise ValueError carrying the OperationOutcome
    (quarantine, don't crash — the caller owns the quarantine store).
    """
    if xsd_validate:
        errors = validate(source)
        if errors:
            exc = ValueError(f"NEMSIS XSD validation failed with {len(errors)} error(s)")
            exc.operation_outcome = to_operation_outcome(errors)  # type: ignore[attr-defined]
            raise exc

    dataset = parse(source)
    results: list[ConversionResult] = []
    for pcr in dataset.reports:
        ctx = map_pcr(dataset, pcr, agency_names=agency_names)
        composition = build_composition(ctx, variant=document_variant)
        transaction = transaction_bundle(ctx.resources, bundle_identifier=ctx.pcr_number)
        document = document_bundle(ctx, composition)
        results.append(ConversionResult(ctx, composition, transaction, document))
    return results
