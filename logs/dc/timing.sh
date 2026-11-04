#!/bin/bash
# DC cost check: tier3 vs tier3 with bigger discard settings, back to back (arms alternate), locks off.
# One exclusive laptop-lock hold for all runs, taken behind the turnstile (so shared evals cannot starve it).
cd "$(dirname "$0")/../.."
exec flock /tmp/pokerbot_turnstile.lock flock -x /tmp/pokerbot_laptop.lock logs/dc/timing_body.sh
