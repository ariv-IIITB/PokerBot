"""Stand-in river solver (BUILDMAP §7 Phase 7): always defers to the blueprint.

botsrc/river_api.decide() calls decide() here. Phase 10 replaces this module with your friend's river
solver (same signature: decide(ctx: RiverContext) -> list | None).
"""


def decide(ctx):
    return None
