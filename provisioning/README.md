# Provisioning

The repository features a Vagrantfile to provision a virtual machine with the required dependencies to ease the development and testing of Realm Gateway.


## Installation

Install the latest versions of Virtual Box and Vagrant.

Install Vagrant plugin to control disk size:

```
vagrant plugin install vagrant-disksize
```


## Deploying the environments

### Spawning the Virtual Machine - VM

Use the following commands:

```
# Access the location of the Vagrantfile
cd provisioning/virtual_machine

# Create the VM
vagrant up  rgw-dev

# SSH into the VM
vagrant ssh rgw-dev
```

Use the following commands to maintain an updated copy of the modified repository files inside the VM:

```
# Access the location of the Vagrantfile
cd provisioning/virtual_machine

# Synchronize folders
vagrant rsync-auto rgw-dev
```


### Spawning the Linux Containers - LXC

Inside the SSH session of the VM use the following commands as root:

```
# Access the location of the Vagrantfile
cd /RealmGateway/provisioning/linux_containers

# Create the supporting networking infrastructure
./pre-up.sh

# Create the LXC(s)
vagrant up {router, public, gwa, ...} --provider=lxc

# Connect to the LXC(s)
lxc-attach {router, public, gwa, ...}
```


### Spawning the Linux Network Namespaces - netns

Inside the SSH session of the VM use the following commands as root:

```
# Access the location of the Vagrantfile
cd /RealmGateway/provisioning/network_namespaces

# Create the supporting networking infrastructure
./01_setup_environment.sh

# Connect to pre-configured TMUX session
./02_create_tmux_session.sh

# Destroy environment
./03_destroy_environment.sh
```
