#!/bin/bash


echo "Enabling necesary kernel modules for CES/RealGateway"
for MODULE in sctp nf_conntrack_proto_sctp xt_sctp xt_MARKDNAT netmap openvswitch
do
	echo "> modprobe $MODULE"
	modprobe $MODULE
done
echo ""

echo "Remove lxc-start profile from Apparmor"
apparmor_parser --remove /etc/apparmor.d/usr.bin.lxc-start
ln -s /etc/apparmor.d/usr.bin.lxc-start /etc/apparmor.d/disabled/

echo ""
for NIC in br-wan0 br-wan1 br-wan2 br-wan1p br-wan2p br-lan0a br-lan0b br-lan1a br-lan1b
do
	echo "Setting up $NIC"
	ip link del dev $NIC 2> /dev/null
	ip link add dev $NIC type bridge forward_delay 0
	ip link set dev $NIC up
done


echo "Setting up lxcmgt0"
ip link del dev lxcmgt0 2> /dev/null
ip link add dev lxcmgt0 type bridge forward_delay 0
ip link set dev lxcmgt0 up
ip address add 172.31.255.1/24 dev lxcmgt0
# Configure br-wan0 with IP address for accessing test public network
ip address flush dev br-wan0
ip address add 100.64.0.254/24 dev br-wan0
## Set default gateway via br-wan0 in host to control NATting
ip route add 100.64.0.0/16 via 100.64.0.1

# Add static host entries
cat <<EOF >> /etc/hosts
172.31.255.10       router
172.31.255.11       gwa
172.31.255.12       gwb
172.31.255.13       public
172.31.255.14       proxya
172.31.255.15       proxyb
172.31.255.16       test_gwa
172.31.255.17       test_gwb
172.31.255.21       nest_gwa
172.31.255.22       nest_gwb
172.31.255.26       test_ngwa
172.31.255.27       test_ngwb
EOF
