#!/bin/bash

if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo:"
    echo "sudo $0 $*"
    exit 1
fi

# Restart OpenvSwitch service
systemctl restart openvswitch-switch

## Create OVS bridges
ovs-vsctl del-br ovs-synproxy
ovs-vsctl add-br ovs-synproxy
ovs-vsctl add-port ovs-synproxy wan0  -- set interface wan0  ofport_request=1
ovs-vsctl add-port ovs-synproxy wan0p -- set interface wan0p ofport_request=4

# Bring up the interfaces
ip link set dev wan0 up
ip link set dev wan0p up

# Configure txqueuelen of interfaces / default is 1000
TXQUEUELEN=1000
ip link set dev wan0  txqueuelen $TXQUEUELEN
ip link set dev wan0p txqueuelen $TXQUEUELEN
ip link set dev ovs-synproxy txqueuelen $TXQUEUELEN

# Flush iptables configuration
/usr/bin/flushIptables
