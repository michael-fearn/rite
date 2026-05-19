"""Compatibility Adapter for Service Runtime Intent.

Service Runtime Intent is Inventory-derived meaning. Import it from
``fortress_inventory.service_runtime_intent`` in new code.
"""

from fortress_inventory.service_runtime_intent import (  # noqa: F401
    BackendRuntimeFact,
    NativeEnvironmentSecretRuntimeFact,
    PublishedPortRuntimeFact,
    RuntimeDiagnostic,
    ServiceDataDirectoryRuntimeFact,
    ServiceOwnedVolumeRuntimeFact,
    ServiceRuntimeIntent,
    ServiceSecretRuntimeFact,
    ShareBackedVolumeRuntimeFact,
    TelemetryTargetRuntimeFact,
    analyze_service_runtime_intent,
    service_runtime_intent_for_service,
)
