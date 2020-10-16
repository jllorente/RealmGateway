#!/bin/bash

echo "Provisioning environment for spawning a LXC deployment"

echo "Install dependencies"
export DEBIAN_FRONTEND=noninteractive
apt install -y apt-transport-https && apt update
apt install -y curl ethtool htop iptables iperf ipython3 lxc python3-lxc tcpdump tmux

echo "Install Vagrant and plugins"
wget --no-verbose --directory-prefix=/tmp https://releases.hashicorp.com/vagrant/2.2.10/vagrant_2.2.10_x86_64.deb
dpkg --skip-same-version --install /tmp/vagrant_2.2.10_x86_64.deb
rm /tmp/vagrant_2.2.10_x86_64.deb
vagrant plugin install vagrant-lxc

echo "Enable NAT"
/sbin/iptables -t nat -I POSTROUTING -o $(ip route show | grep default | awk '{ print $5}') -j MASQUERADE
sysctl -w net.ipv4.ip_forward=1
