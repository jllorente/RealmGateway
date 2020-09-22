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

secs=2
while [ $secs -gt 0 ]; do
   echo -ne "Waiting $secs seconds before starting tmux session\033[0K\r"
   sleep 1
   : $((secs--))
done
echo ""

# Create new session and configure first window for gwa.demo
tmux new-session -d -s rgw_netns -n background

## Split window
tmux split-window -h -p 50
tmux split-window -v -p 50

### Access panes and run commands
tmux select-pane -t 0
tmux send-keys 'nsbash gwa' Enter
tmux select-pane -t 1
tmux send-keys 'nsbash public' Enter
tmux select-pane -t 2
tmux send-keys 'nsbash test_gwa' Enter

tmux select-pane -t 0
tmux send-keys 'cd /realmgateway' Enter
tmux send-keys './run_gwa_netns.sh' Enter

echo "Initializing RealmGateway gwa.demo "
sleep 10

tmux select-pane -t 1
# Workaround the lack of recursive resolver
tmux send-keys 'ping $(dig icmp.test.gwa.demo +short) -c 3' Enter
tmux select-pane -t 2
tmux send-keys 'cd / && python3 -m http.server 8008' Enter
tmux select-pane -t 1
tmux send-keys 'curl http://$(dig test.gwa.demo +short):8008/etc/hostname' Enter

### Select pane 3 // public
tmux select-pane -t 1

# Attach to session
tmux -2 attach-session -d
