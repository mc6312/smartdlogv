#!/bin/bash

MAILTO=""

if [ -z "$MAILTO" ]
then
    EM="$0 is not configured: no mail address."
    echo "$EM"
    #logger -t $0 "$EM"
    exit 1
fi

smartdlogv.py -r 2>&1 |mail "$MAILTO" -s "smartdlogv"
