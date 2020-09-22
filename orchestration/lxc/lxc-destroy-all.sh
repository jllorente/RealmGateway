#!/bin/bash -eu

# LXC tools
# Copyright (C) 2012-2016 Infertux <infertux@infertux.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo:"
    echo "sudo $0 $*"
    exit 1
fi


LXC=/var/lib/lxc
ROOTFS=rootfs
RUNNING_CONTAINERS="$(lxc-ls)"

for container in $RUNNING_CONTAINERS; do
  echo "Stopping $container..."
  lxc-stop --name $container || true
done
for container in $RUNNING_CONTAINERS; do
  echo "Destroying $container..."
  lxc-autostart --kill --all || true
  lxc-destroy --name $container || true
done
for container in $RUNNING_CONTAINERS; do
  echo "Destroying $container..."
  lxc-autostart --kill --all || true
  lxc-destroy --name $container || true
done
