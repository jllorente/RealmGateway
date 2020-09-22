# Provisioning

The repository features a Vagrantfile to provision a virtual machine with the required dependencies to ease the development and testing of Realm Gateway.


## Installation

Install the latest version of Virtual Box and Vagrant.


## Spawning the virtual machine

Use the following commands:

```
# Access the location of the Vagrantfile
$ cd provisioning

# Create the VM
$ vagrant up  realm-gateway

# SSH into the VM
$ vagrant ssh realm-gateway
```
