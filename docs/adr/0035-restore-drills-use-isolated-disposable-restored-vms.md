# Restore drills use isolated disposable restored VMs

Restore Drills prove recovery from PBS backup reality, not creation from declared intent, so they are distinct from Acceptance Tests even though they may reuse disposable VM lifecycle machinery. A Restore Drill creates a Restored Drill VM on operator-selected placement, attaches it to a Drill Network by default, and must avoid production VM identity collisions and production NAS-backed Dataset mutation. The Restored Drill VM may contain restored production secrets, so it is operator-only and is destroyed by default after the drill, with an explicit keep-on-fail escape hatch for diagnosis.

