#!/bin/bash
echo "Enabling iptables masquerade"
/sbin/iptables -t nat -I POSTROUTING -o $(ip route show | grep default | awk '{ print $5}') -j MASQUERADE
