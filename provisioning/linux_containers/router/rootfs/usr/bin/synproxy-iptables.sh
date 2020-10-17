#!/bin/bash

if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo:"
    echo "sudo $0 $*"
    exit 1
fi

# Configure iptables for SYNPROXY - Protect wanX interfaces from incoming TCP SYNs from wan0
/sbin/sysctl -w net.ipv4.tcp_syncookies=1
/sbin/sysctl -w net.ipv4.tcp_timestamps=1
/sbin/sysctl -w net.netfilter.nf_conntrack_tcp_loose=0

/usr/bin/flushIptables

/sbin/iptables -t raw    -N SYNPROXY_RULES
/sbin/iptables -t raw    -A PREROUTING     -i wan0 -j SYNPROXY_RULES
/sbin/iptables -t raw    -A SYNPROXY_RULES -i wan0 -p tcp -m tcp --syn -j CT --notrack
/sbin/iptables -t raw    -A SYNPROXY_RULES -j ACCEPT

/sbin/iptables -t filter -N SYNPROXY_RULES
/sbin/iptables -t filter -A FORWARD        -i wan0 -o wan+ -j SYNPROXY_RULES
/sbin/iptables -t filter -A SYNPROXY_RULES -i wan0 -o wan+ -p tcp -m tcp -m conntrack --ctstate INVALID,UNTRACKED -j SYNPROXY --sack-perm --timestamp --wscale 7 --mss 1460
/sbin/iptables -t filter -A SYNPROXY_RULES -p tcp -m conntrack --ctstate INVALID -j DROP
