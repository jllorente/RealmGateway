#!/bin/bash

echo "Provisioning environment for spawning a local deployment with network namespaces"

echo "Install dependencies"
export DEBIAN_FRONTEND=noninteractive
apt install -y apt-transport-https && apt update
apt install -y build-essential python3-dev python3-pip ipython3 libnetfilter-queue-dev
apt install -y iptables-dev automake bison flex libmnl-dev libnftnl-dev libtool
apt install -y iptables ipset bridge-utils conntrack python3-yaml openvswitch-switch openvswitch-vtep
apt install -y dnsutils dnsmasq curl htop ethtool git tmux tree psmisc tmux tcpdump iperf hping3 lksctp-tools

python3 -m pip install --upgrade pip setuptools
python3 -m pip install --upgrade --use-feature=2020-resolver aiohttp dnspython==1.16.0 NetfilterQueue python-iptables pyroute2 ryu scapy

echo "Enable NAT"
/sbin/iptables -t nat -I POSTROUTING -o $(ip route show | grep default | awk '{ print $5}') -j MASQUERADE
sysctl -w net.ipv4.ip_forward=1

echo "Doing some system configurations..."
systemctl disable apt-daily.timer apt-daily-upgrade.timer systemd-resolved
systemctl stop    apt-daily.timer apt-daily-upgrade.timer systemd-resolved

# Write custom configuration for local dnsmasq instance
DEFAULT_NS=$(cat /etc/resolv.conf | grep nameserver | head -n 1 | awk '{print $2}')
cat <<EOF > /etc/dnsmasq.d/10-rgw.conf
# Forward to router *.demo SOA zone
server=/demo/100.64.0.1#53

# Forward to router *.64.100.in-addr.arpa SOA zone
server=/64.100.in-addr.arpa/100.64.0.1#53

# Forward to VirtualBox and Google DNS all other queries
server=${DEFAULT_NS}
server=8.8.8.8
server=8.8.4.4

# Other options
no-dhcp-interface=lo
no-negcache
user=dnsmasq
pid-file=/var/run/dnsmasq/dnsmasq.pid
log-facility=/var/log/dnsmasq
EOF

# Restart dnsmasq with new configuration
systemctl enable  dnsmasq.service
systemctl restart dnsmasq.service

# Use local dnsmasq instance
unlink /etc/resolv.conf
cat <<EOF > /etc/resolv.conf
nameserver 127.0.0.1
EOF

cat <<EOF >> /root/.bashrc
# Alias to ssh with the UserAgent, do not store known host and disable key checking
alias sshq='ssh -A -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
EOF

cat <<EOF >> $HOME/.bashrc
# Alias to ssh with the UserAgent, do not store known host and disable key checking
alias sshq='ssh -A -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
EOF

# Copy rootfs files
cp -R ./rootfs/* /
chmod 600 /root/.ssh/id_rsa

# Start systemd services
systemctl daemon-reload
systemctl start runatstartup

# Reload sysctl parameters
sysctl --system

# Print out some useful information
ulimit -Ha
