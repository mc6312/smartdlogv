#!/bin/bash

MAILTO=""
MAILSUBJ="`hostname`: smartdlogv"

LOGTAG="`basename $0`"

function logmsg(){
    echo "$*" 1>&2
    logger -t "$LOGTAG" "$*"
}

if [ -z "$MAILTO" ]
then
    logmsg "$0 is not configured: no mail address."
    exit 1
fi

logmsg "$LOGTAG" "parsing smartd log(s)..."
if ! "`dirname $0`/smartdlogv.py" -r 2>&1 |mail "$MAILTO" -s "$MAILSUBJ"
then
    EC=$?
    logmsg "error $EC parsing smartd log(s)"
fi
