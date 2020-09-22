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


echo "Enabling necesary kernel modules for CES/RealGateway"
for MODULE in sctp nf_conntrack_proto_sctp xt_sctp xt_MARKDNAT netmap openvswitch
do
	echo "> modprobe $MODULE"
	modprobe $MODULE
done
echo ""

echo "Remove lxc-start profile from Apparmor"
apparmor_parser --remove /etc/apparmor.d/usr.bin.lxc-start
ln -s /etc/apparmor.d/usr.bin.lxc-start /etc/apparmor.d/disable/

echo ""
for NIC in br-mgt0 br-wan0 br-wan1 br-wan2 br-wan1-gwa br-wan2-gwb br-lan0-gwa br-lan0-gwb br-lan0-ngwa br-lan0-ngwb
do
	echo "Setting up $NIC"
	ip link del dev $NIC 2> /dev/null
	ip link add dev $NIC txqueuelen 25000 type bridge forward_delay 0
	ip link set dev $NIC up
done

# Configure L3 interfaces for routing
## LXC management network
ip address add 10.0.0.1/24 dev br-mgt0
## Internet access for LXC public networks
ip address add 100.64.0.254/24 dev br-wan0
## Internal gateway for LXC public networks
ip route add 100.64.0.0/16 via 100.64.0.1

# Add static host entries
cat <<EOF >> /etc/hosts
10.0.0.10       router
10.0.0.11       gwa
10.0.0.12       gwb
10.0.0.13       public
10.0.0.14       proxygwa
10.0.0.15       proxygwb
10.0.0.16       test_gwa
10.0.0.17       test_gwb
10.0.0.21       nest_gwa
10.0.0.22       nest_gwb
10.0.0.26       test_ngwa
10.0.0.27       test_ngwb
EOF
