# Subcontractor Pipeline Checkpoint

Generated: 2026-07-17T01:27:41-07:00

## Python Modules

- `scripts/subcontractor/__init__.py`
- `scripts/subcontractor/config.py`
- `scripts/subcontractor/database.py`
- `scripts/subcontractor/logging_utils.py`
- `scripts/subcontractor/pdf_cache.py`
- `scripts/subcontractor/run_pipeline.py`
- `scripts/subcontractor/stages/__init__.py`
- `scripts/subcontractor/stages/audit_bidder_context.py`
- `scripts/subcontractor/stages/audit_quarantine_context.py`
- `scripts/subcontractor/stages/audit_quarantined_contracts.py`
- `scripts/subcontractor/stages/build_identity_overlay.py`
- `scripts/subcontractor/stages/certify_alternate_stage2.py`
- `scripts/subcontractor/stages/group_alternate_layout.py`
- `scripts/subcontractor/stages/parse_alternate_layout.py`
- `scripts/subcontractor/stages/promote_alternate_disclosures.py`
- `scripts/subcontractor/stages/reconcile_alternate_blocks.py`
- `scripts/subcontractor/stages/stage2_alternate_parser.py`
- `scripts/subcontractor/stages/validate_stage1.py`
- `scripts/subcontractor/tests/__init__.py`
- `scripts/subcontractor/validation.py`
- `scripts/subcontractor/verify_framework.py`

## Configuration

- `config/subcontractor/settings.json`

## Current Promoted Output

- Table: `bid_tab_subcontractor_disclosure_2025_alt_promoted_v1`
- Contracts: 3
- Ranked bidder blocks: 22
- Disclosure rows: 470
- Fully identity-resolved rows: 415
- Explicit identity-gap rows: 55

## Remaining Quarantine

- `07-0Y2004`: EXTRA_1
- `07-375304`: EXTRA_1
- `08-1P6104`: MISSING_1
- `11-2N1764`: MISSING_2
- `11-430314`: EXTRA_1
