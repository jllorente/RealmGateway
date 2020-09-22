#!/bin/bash

# Add this at the beginning of the script to assure you run it with sudo
if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo:"
    echo "sudo $0 $*"
    exit 1
fi


echo "Setting txqueuelen in LXC containers of deployment"
TXQUEUELEN=25000
while read ctname; do
    echo "Analyzing container $ctname..."
    # Get list of all network interfaces
    CT_NICS="$(lxc-attach -n $ctname -- tail -n+3 /proc/net/dev | cut --delimiter=: -f 1 | awk '{ print $1}')"
    for nic in $CT_NICS; do
        echo "    > Setting txqueuelen=$TXQUEUELEN for $nic@$ctname"
        lxc-attach -n $ctname -- /sbin/ip link set dev $nic txqueuelen $TXQUEUELEN
    done
done <CONTAINERS
