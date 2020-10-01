#!/bin/bash

echo "Adding lxc-start profile to Apparmor"
rm /etc/apparmor.d/disable/usr.bin.lxc-start
apparmor_parser --add /etc/apparmor.d/usr.bin.lxc-start

for NIC in br-mgt0 br-wan0 br-wan1 br-wan2 br-wan1-gwa br-wan2-gwb br-lan0-gwa br-lan0-gwb br-lan0-ngwa br-lan0-ngwb
do
	echo "Removing $NIC"
	ip link del dev $NIC 2> /dev/null
done

# Remove static host entries
sed -i '/10.0.0.10/d' /etc/hosts
sed -i '/10.0.0.11/d' /etc/hosts
sed -i '/10.0.0.12/d' /etc/hosts
sed -i '/10.0.0.13/d' /etc/hosts
sed -i '/10.0.0.14/d' /etc/hosts
sed -i '/10.0.0.15/d' /etc/hosts
sed -i '/10.0.0.16/d' /etc/hosts
sed -i '/10.0.0.17/d' /etc/hosts
sed -i '/10.0.0.21/d' /etc/hosts
sed -i '/10.0.0.22/d' /etc/hosts
sed -i '/10.0.0.26/d' /etc/hosts
sed -i '/10.0.0.27/d' /etc/hosts
