"""Compatibility Adapter for Service Runtime Intent.

Service Runtime Intent is Inventory-derived meaning. Import it from
``fortress_inventory.service_runtime_intent`` in new code.
"""

from fortress_inventory.service_runtime_intent import (  # noqa: F401
    BackendRuntimeFact,
    PublishedPortRuntimeFact,
    RuntimeDiagnostic,
    ServiceRuntimeIntent,
    TelemetryTargetRuntimeFact,
    analyze_service_runtime_intent,
)
