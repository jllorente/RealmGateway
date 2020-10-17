#!/bin/bash

# BSD 3-Clause License
#
# Copyright (c) 2018, Jesus Llorente Santos
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


# WHAT IS THIS:
# This script is used to control network delay from an application perspective
# At a lower level, the network delay is enforced via a hierarchical structure with tc qdiscs and filters
# The supported network delays are defined in ms time unit for the sequence (SEQ_START SEQ_STEP SEQ_END).
#
# HOW TO RUN:
#   $ /mark_delay.sh --nic wan0 --start 1 --step 1 --end 250
#
# HOW TO USE:
# From the user perspective, set the packet mark to a configured value via:
# - MARK: Set the packet mark in the skbuff frame via iptables.
# - SO_MARK: Set the socket option SO_MARK with the intended value.
#
# CAVEATS:
# - The current version uses unoptimized tc filters which may reduce network performance.
#   Here is a tip how to improve this part: http://lartc.org/howto/lartc.adv-filter.hashing.html
# - Cleanup configured filters via:
#   $ tc qdisc delete dev $NIC root

# Default values
DEFAULT_RATE="100gbit"
DEFAULT_DELAY="0"
NIC="wan0"
SEQ_START="1"
SEQ_STEP="1"
SEQ_END="250"

while [[ $# -gt 0 ]]
do
key="$1"

case $key in
    --nic)
    NIC="$2"
    shift # past argument
    shift # past value
    ;;
    --start)
    SEQ_START="$2"
    shift # past argument
    shift # past value
    ;;
    --end)
    SEQ_END="$2"
    shift # past argument
    shift # past value
    ;;
    --step)
    SEQ_STEP="$2"
    shift # past argument
    shift # past value
    ;;
esac
done


## Create basic structure with default delay
tc qdisc delete  dev ${NIC} root
tc qdisc replace dev ${NIC} root handle 1:         htb default 1
tc class replace dev ${NIC}      parent 1:         classid  1:1      htb rate ${DEFAULT_RATE}
tc qdisc replace dev ${NIC}      parent 1:1        handle   2        netem delay ${DEFAULT_DELAY}ms limit 1000

## Loop over sequence and create TC handles
for DELAY in $(seq $SEQ_START $SEQ_STEP $SEQ_END)
do
    MAGICNUMBER=$(( DELAY * 16 ))
    echo "### delay = ${DELAY} ms // magic number = ${MAGICNUMBER} ###"
    # The subclass is calculated by shifting 4bit the intended delay. e.g. 1ms -> 1 << 4 = 16
    tc class  replace dev ${NIC} parent 1:               classid 1:${MAGICNUMBER} htb rate ${DEFAULT_RATE}
    tc qdisc  replace dev ${NIC} parent 1:${MAGICNUMBER} handle  ${MAGICNUMBER}:  netem delay ${DELAY}ms limit 1000
    tc filter replace dev ${NIC} protocol ip parent 1:0 prio 1 u32 match mark ${DELAY} 0xffffffff flowid 1:${MAGICNUMBER}
done
