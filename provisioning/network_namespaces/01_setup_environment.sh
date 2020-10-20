#!/bin/bash

#BSD 3-Clause License
#
#Copyright (c) 2018, Jesus Llorente Santos
#All rights reserved.
#
#Redistribution and use in source and binary forms, with or without
#modification, are permitted provided that the following conditions are met:
#
#* Redistributions of source code must retain the above copyright notice, this
#  list of conditions and the following disclaimer.
#
#* Redistributions in binary form must reproduce the above copyright notice,
#  this list of conditions and the following disclaimer in the documentation
#  and/or other materials provided with the distribution.
#
#* Neither the name of the copyright holder nor the names of its
#  contributors may be used to endorse or promote products derived from
#  this software without specific prior written permission.
#
#THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
#FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
#DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo:"
    echo "sudo $0 $*"
    exit 1
fi

setup_basic_netns () {
    echo "Creating basic configuration for netns $1"
    # Delete & recreate network namespace
    ip netns del $1 &> /dev/null
    ip netns add $1
    # Configure sysctl options
    ip netns exec $1 sysctl -w "net.ipv4.ip_forward=1"
    ip netns exec $1 sysctl -w "net.ipv6.conf.all.disable_ipv6=1"
    ip netns exec $1 sysctl -w "net.ipv6.conf.default.disable_ipv6=1"
    ip netns exec $1 sysctl -w "net.ipv6.conf.lo.disable_ipv6=1"
    # Configure the loopback interface in namespace
    ip netns exec $1 ip address add 127.0.0.1/8 dev lo
    ip netns exec $1 ip link set dev lo up
    # Create /etc mount point
    mkdir -p  /etc/netns/$1
    echo $1 > /etc/netns/$1/hostname
}


# Print commands and their arguments as they are executed.
set -x

###############################################################################
# Create supporting infrastructure for single instance of Realm Gateway
###############################################################################

echo "Enable IP forwarding"
sysctl -w "net.ipv4.ip_forward=1"
echo "Disable IPv6 for all interfaces"
sysctl -w "net.ipv6.conf.all.disable_ipv6=1"
sysctl -w "net.ipv6.conf.default.disable_ipv6=1"
sysctl -w "net.ipv6.conf.lo.disable_ipv6=1"
echo "Unloading iptables bridge kernel modules"
rmmod xt_physdev   &> /dev/null
rmmod br_netfilter &> /dev/null

# [COMMON]
## WAN side
ip link add dev ns-wan0 txqueuelen 1000 type bridge
ip link set dev ns-wan0 up
ip link add dev ns-wan1 txqueuelen 1000 type bridge
ip link set dev ns-wan1 up

# [RealmGateway-A]
## LAN side
ip link add dev ns-lan0-gwa txqueuelen 1000 type bridge
ip link set dev ns-lan0-gwa up


###############################################################################
# Create network namespace configuration
###############################################################################

# Create the default namespace
ln -s /proc/1/ns/net /var/run/netns/default &> /dev/null
# Create the other namespaces
for netns in router public gwa testgwa; do setup_basic_netns $netns; done

###############################################################################
# Create host configuration
###############################################################################

## Create a macvlan interface to provide NAT and communicate with the other virtual hosts
ip link add link ns-wan0 dev tap-wan0 txqueuelen 1000 type macvlan mode bridge
ip link set dev tap-wan0 up
ip address add 100.64.0.254/24 dev tap-wan0
ip route add 100.64.0.0/16 via 100.64.0.1


###############################################################################
# Create router configuration
###############################################################################

## Configure interface(s)
ip link add link ns-wan0 dev wan0 txqueuelen 1000 type macvlan mode bridge
ip link add link ns-wan1 dev wan1 txqueuelen 1000 type macvlan mode bridge
ip link set dev wan0 up netns router
ip link set dev wan1 up netns router
ip netns exec router ip address add 100.64.0.1/24 dev wan0
ip netns exec router ip address add 100.64.1.1/24 dev wan1
ip netns exec router ip route add default via 100.64.0.254 dev wan0
# Add _public_ test network(s) via public node
ip netns exec router ip route add 100.64.248.0/21 via 100.64.0.100 dev wan0

# Setting up TCP SYNPROXY in router - ipt_SYNPROXY
# https://r00t-services.net/knowledgebase/14/Homemade-DDoS-Protection-Using-IPTables-SYNPROXY.html
ip netns exec router sysctl -w net.ipv4.tcp_syncookies=1 # This might not be available in the network namespace
ip netns exec router sysctl -w net.ipv4.tcp_timestamps=1 # This might not be available in the network namespace
ip netns exec router sysctl -w net.netfilter.nf_conntrack_tcp_loose=0
# Configure iptables for SYNPROXY - Protect wan1 from incoming SYNs from wan0
ip netns exec router iptables -t raw    -F
ip netns exec router iptables -t raw    -A PREROUTING -i wan0 -p tcp -m tcp --syn -j CT --notrack
ip netns exec router iptables -t filter -F
ip netns exec router iptables -t filter -A FORWARD -i wan0 -o wan1 -p tcp -m tcp -m conntrack --ctstate INVALID,UNTRACKED -j SYNPROXY --sack-perm --timestamp --wscale 7 --mss 1460
ip netns exec router iptables -t filter -A FORWARD -p tcp -m conntrack --ctstate INVALID -j DROP

# Enable dnsmasq forwarding for gwa.demo domain and use upstream resolvers by default
ip netns exec router dnsmasq --server=/gwa.demo/100.64.1.130         \
                             --server=/cname-gwa.demo/100.64.1.130   \
                             --server=8.8.8.8 --server=8.8.4.4       \
                             --server=10.0.2.3                       \
                             --pid-file=/var/run/router.dnsmasq.pid  \
                             --no-negcache


###############################################################################
# Create public configuration
###############################################################################

## Configure interface(s)
ip link add link ns-wan0 dev wan0 txqueuelen 1000 type macvlan mode bridge
ip link set dev wan0 up netns public
ip netns exec public ip address add 100.64.0.100/24 dev wan0
ip netns exec public ip route add default via 100.64.0.1 dev wan0
echo "nameserver 100.64.0.1" > /etc/netns/public/resolv.conf
# Add _public_ test network(s) IP addresses to public node
ip netns exec public bash -c "for ip in 100.64.{248..255}.{0..16}; do ip address add \$ip/32 dev wan0; done"
# Configure delay buckets
ip netns exec public mark_delay --nic wan0 --start 1 --step 1 --end 250
# Disable conntrack
ip netns exec public iptables -t raw -I OUTPUT     -j CT --notrack
ip netns exec public iptables -t raw -I PREROUTING -j CT --notrack

###############################################################################
# Create gwa configuration
###############################################################################

## Configure interface(s)
ip link add link ns-wan1     dev wan0 txqueuelen 1000 type macvlan mode bridge
ip link add link ns-lan0-gwa dev lan0 txqueuelen 1000 type macvlan mode bridge
ip link set dev wan0 up netns gwa
ip link set dev lan0 up netns gwa
ip netns exec gwa ip address add 192.168.0.1/24  dev lan0
ip netns exec gwa ip address add 100.64.1.130/24 dev wan0
ip netns exec gwa ip route add default via 100.64.1.1 dev wan0
echo "nameserver 100.64.0.1" > /etc/netns/gwa/resolv.conf

# Add Circular Pool address for ARP responses
ip netns exec gwa bash -c "for ip in 100.64.1.{131..142}; do ip address add \$ip/24 dev wan0; done"


###############################################################################
# Create testgwa configuration
###############################################################################

ip link add link ns-lan0-gwa dev lan0 txqueuelen 1000 type macvlan mode bridge
ip link set dev lan0 up netns testgwa
ip netns exec testgwa ip address add 192.168.0.100/24 dev lan0
ip netns exec testgwa ip route add default via 192.168.0.1 dev lan0
# Disable conntrack
ip netns exec public iptables -t raw -I OUTPUT     -j CT --notrack
ip netns exec public iptables -t raw -I PREROUTING -j CT --notrack
echo "nameserver 192.168.0.1" > /etc/netns/testgwa/resolv.conf
# Add _private_ test IP addresses to testgwa node
ip netns exec testgwa bash -c "for ip in 192.168.0.{200..209}; do ip address add \$ip/32 dev lan0; done"
ip netns exec testgwa bash -c "/RealmGateway/scripts/echoserver.py                \
                                  --tcp $(echo 192.168.0.{200..209}:{2000..2009}) \
                                  --udp $(echo 192.168.0.{200..209}:{2000..2009})" &> /dev/null &

echo "Setup completed!"
