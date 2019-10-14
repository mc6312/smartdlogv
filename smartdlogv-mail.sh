#!/bin/bash

MAILTO=""
LOGTAG="`basename $0`"

if [ -z "$MAILTO" ]
then
    EM="$0 is not configured: no mail address."
    echo "$EM"
    logger -t "$LOGTAG" "$EM"
    exit 1
fi

logger -t "$LOGTAG" "parsing smartd log(s)..."
if ! ./smartdlogv.py -r 2>&1 |mail "$MAILTO" -s "smartdlogv"
then
    EC=$?
    logger -t "$LOGTAG" "error $EC parsing smartd log(s)"
fi
