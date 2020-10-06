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

# Print commands and their arguments as they are executed.
set -x

###############################################################################
# Destroy tmux session
###############################################################################

tmux kill-session -t rgw_netns

###############################################################################
# Remove supporting infrastructure for single instance of Realm Gateway
###############################################################################

# [COMMON]
## WAN side
ip link set dev ns-wan0 down
ip link del dev ns-wan0
ip link set dev ns-wan1 down
ip link del dev ns-wan1

# [RealmGateway-A]
## LAN side
ip link set dev ns-lan0-gwa down
ip link del dev ns-lan0-gwa


###############################################################################
# Create network namespace configuration
###############################################################################

# Remove the namespaces
for netns in router public gwa testgwa; do ip netns del $netns &> /dev/null; done

# Kill dnsmasq running in router netns and cleanup pid file
pkill -F /var/run/router.dnsmasq.pid &> /dev/null || true
rm       /var/run/router.dnsmasq.pid &> /dev/null || true

# Destroy OpenvSwitch instance created by RealmGateway
ovs-vsctl --if-exists del-br ovs-ces

echo "Cleanup completed!"
