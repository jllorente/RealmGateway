#!/bin/bash

echo "Adding lxc-start profile to Apparmor"
rm /etc/apparmor.d/disabled/usr.bin.lxc-start
apparmor_parser --add /etc/apparmor.d/usr.bin.lxc-start

for NIC in br-wan0 br-wan1 br-wan2 br-wan1p br-wan2p br-lan0a br-lan0b br-lan1a br-lan1b
do
	echo "Removing $NIC"
	ip link del dev $NIC 2> /dev/null
done


echo "Removing lxcmgt0"
ip link del dev lxcmgt0 2> /dev/null

# Remove static host entries
sed -i '/172.31.255.10/d' /etc/hosts
sed -i '/172.31.255.11/d' /etc/hosts
sed -i '/172.31.255.12/d' /etc/hosts
sed -i '/172.31.255.13/d' /etc/hosts
sed -i '/172.31.255.14/d' /etc/hosts
sed -i '/172.31.255.15/d' /etc/hosts
sed -i '/172.31.255.16/d' /etc/hosts
sed -i '/172.31.255.17/d' /etc/hosts
sed -i '/172.31.255.21/d' /etc/hosts
sed -i '/172.31.255.22/d' /etc/hosts
sed -i '/172.31.255.26/d' /etc/hosts
sed -i '/172.31.255.27/d' /etc/hosts
