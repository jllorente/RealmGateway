#!/bin/bash

if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo:"
    echo "sudo $0 $*"
    exit 1
fi

# Notes: This hook is called by LXC with the following parameters
# disableOffload_hook.sh $LXC_NAME net up veth $net.i.link $net.i.veth.pair

echo "Executing: $0 $*" >> /var/tmp/lxc_net_hook

ETHTOOL="/sbin/ethtool"
DEV=$6

echo "Disabling offload in $6"
$ETHTOOL -K $DEV rx                      off
$ETHTOOL -K $DEV tx                      off
$ETHTOOL -K $DEV sg                      off
$ETHTOOL -K $DEV tso                     off
$ETHTOOL -K $DEV ufo                     off
$ETHTOOL -K $DEV gso                     off
$ETHTOOL -K $DEV gro                     off
$ETHTOOL -K $DEV lro                     off
$ETHTOOL -K $DEV rxvlan                  off
$ETHTOOL -K $DEV txvlan                  off
$ETHTOOL -K $DEV ntuple                  off
$ETHTOOL -K $DEV rxhash                  off
$ETHTOOL -K $DEV highdma                 off
$ETHTOOL -K $DEV tx-nocache-copy         off
$ETHTOOL -K $DEV tx-vlan-stag-hw-insert  off
$ETHTOOL -K $DEV rx-vlan-stag-hw-parse   off
$ETHTOOL -K $DEV tx-gre-segmentation     off
$ETHTOOL -K $DEV tx-ipip-segmentation    off
$ETHTOOL -K $DEV tx-sit-segmentation     off
$ETHTOOL -K $DEV tx-udp_tnl-segmentation off
exit 0
