#!/bin/bash

# Define IP:port mappings
PORT_STRING=$(for ip in `prips $IP_FIRST $IP_LAST`; do for port in `seq $PORT_FIRST $PORT_LAST`; do echo "$ip:$port"; done; done | paste -s -d " ")

echo "Starting echoserver @ $PORT_STRING"
/usr/local/bin/echoserver.py --tcp $PORT_STRING --udp $PORT_STRING
