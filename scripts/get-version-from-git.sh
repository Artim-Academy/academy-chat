#!/usr/bin/env bash

# Echoes a version based on the git hashes of the element-web & js-sdk checkouts, for the case where
# these dependencies are git checkouts.

set -e

SCRIPT_DIR=$(dirname "$0")

VECTOR_SHA=$(git rev-parse --short=12 HEAD) # use the ACTUAL SHA rather than assume develop

# layered.sh clones matrix-js-sdk directly into <root>/matrix-js-sdk.
# Builds against the released js-sdk from npm have no such checkout.
if [ -d "$SCRIPT_DIR/../matrix-js-sdk" ]; then
    JSSDK_SHA=$(git -C "$SCRIPT_DIR/../matrix-js-sdk" rev-parse --short=12 HEAD)
    echo "$VECTOR_SHA-js-$JSSDK_SHA"
else
    echo "$VECTOR_SHA"
fi
