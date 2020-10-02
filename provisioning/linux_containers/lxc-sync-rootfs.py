#!/usr/bin/env python3

"""
BSD 3-Clause License

Copyright (c) 2020, Jesus Llorente Santos
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""

import argparse
import logging
import io
import os
import stat
import subprocess
import sys
import time

# Export environmental variable for installing packages without user interaction
os.environ["DEBIAN_FRONTEND"] = "noninteractive"

# Define loglevel
logging.basicConfig(level=os.getenv("LOGLEVEL", logging.INFO))
logger = logging.getLogger()

# Define variables
SYSEXEC_BACKOFF = 0.25


def sync_rootfs_container(name, path):
    logger.debug("Syncing rootfs: {}".format(name))
    # Backup current working directory
    cwd = os.getcwd()
    # Change to rootfs path
    os.chdir(path)
    for root, dirs, files in os.walk("."):
        for file in files:
            # Make absolute file in host
            _file = os.path.join(os.getcwd(), root, file)
            # Make absolute path in container
            ct_file = os.path.join(root, file)[1:]
            ct_sync_file(name, _file, ct_file)
    # Change to previous working directory
    os.chdir(cwd)


def ct_sync_file(name, src, dst):
    # Get file's permissions
    fmode = os.stat(src).st_mode
    fmode_chmod = oct(fmode)[-3:]
    # Create directory
    logger.debug("[{}] >> Creating directory {} ...".format(name, os.path.dirname(dst)))
    command = "/usr/bin/lxc-attach -n {} -- /bin/mkdir -p -m {} {}".format(
        name, "755", os.path.dirname(dst)
    )
    _sysexec(command, name)
    # Create file - Delete existing file to avoid problem with symbolic links
    logger.info("[{}] >> Copying {}".format(name, dst))
    command = "/usr/bin/lxc-attach -n {} -- /bin/rm -f {}".format(name, dst)
    _sysexec(command, name)
    command = '/bin/cat {} | /usr/bin/lxc-attach -n {} -- /bin/bash -c "/bin/cat > {}"'.format(
        src, name, dst
    )
    _sysexec(command, name)
    # Set permissions to file
    logger.debug(
        "[{}] >> Setting file permissions {}".format(name, os.path.dirname(dst))
    )
    command = "/usr/bin/lxc-attach -n {} -- /bin/chmod {} {}".format(
        name, fmode_chmod, dst
    )
    _sysexec(command, name)


def _sysexec(command, name=""):
    logger.debug("_sysexec: @{}# {}".format(command, name))
    try:
        time.sleep(SYSEXEC_BACKOFF)
        subprocess.check_call(command, shell=True)
    except Exception as e:
        logger.error("_sysexec: {}".format(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Data test server with python3 and asyncio"
    )
    parser.add_argument(
        "--name", type=str, required=True, help="LXC container name",
    )
    parser.add_argument(
        "--path", type=str, required=True, help="Path of root filesystem",
    )
    args = parser.parse_args()

    # Sync container rootfs
    sync_rootfs_container(args.name, os.path.abspath(args.path))
