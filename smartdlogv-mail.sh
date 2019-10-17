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

BUF="`mktemp`"
trap 'rm -rf "$BUF"' EXIT

logmsg "parsing smartd log(s)..."
"`dirname $0`"/smartdlogv.py -r 2>&1 >"$BUF"
EC=$?
if [[ $EC != 0 ]]
then
    logmsg "error parsing smartd log(s) - exit code is $EC"
    exit $EC
fi

logmsg "sending mail..."
cat "$BUF" |mail -s "$MAILSUBJ" "$MAILTO"
logmsg "result is $?"
