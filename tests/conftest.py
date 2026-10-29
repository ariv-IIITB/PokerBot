"""Suite-wide setup. The product's default wire format is the official one (pokerbots); the
generic tests exercise the neutral layer and other variants through the mock formats, so they
default to the placeholder format unless POKERBOT_PROTOCOL says otherwise. Tests of the official
format name it explicitly (adapter="pokerbots")."""
import os

os.environ.setdefault("POKERBOT_PROTOCOL", "placeholder")
