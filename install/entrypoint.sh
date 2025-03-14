#!/bin/bash
if [ ! -f /config/postproc.sh ]; then
    cp postproc.sh /config/
    chmod +x /config/postproc.sh
fi

if [ ! -f /config/preproc.sh ]; then
    cp preproc.sh /config/
    chmod +x /config/preproc.sh
fi

exec "$@"