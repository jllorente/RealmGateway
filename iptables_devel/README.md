# Iptables development for Realm Gateway

We have developed a custom module for iptables to speed up packet processing and rule matching in iptables.

The module leverages the 32 bit skbuff mark to apply a DNAT IPv4 address translation on the packet.

The solution requires compiling and installing both a userspace and kernel module into the system.

The following instructions have been tested with Ubuntu 18 Bionic, Linux kernel v4.15 and iptables v.1.6.1.


## Installing the kernel module

Compile and install the module as follow:

```
cd /realmgateway/iptables_devel/kernel

make all
make -C /lib/modules/4.15.0-117-generic/build M=/realmgateway/iptables_devel/kernel modules
make[1]: Entering directory '/usr/src/linux-headers-4.15.0-117-generic'
  CC [M]  /realmgateway/iptables_devel/kernel/xt_MARKDNAT.o
  Building modules, stage 2.
  MODPOST 1 modules
  CC      /realmgateway/iptables_devel/kernel/xt_MARKDNAT.mod.o
  LD [M]  /realmgateway/iptables_devel/kernel/xt_MARKDNAT.ko
make[1]: Leaving directory '/usr/src/linux-headers-4.15.0-117-generic'

sudo make install
cp xt_MARKDNAT.ko /lib/modules/4.15.0-117-generic/kernel/net/netfilter
depmod
```

Verify the module can be loaded:

```
modinfo xt_MARKDNAT
filename:       /lib/modules/4.15.0-117-generic/kernel/net/netfilter/xt_MARKDNAT.ko
alias:          ipt_MARKDNAT
alias:          xt_MARKDNAT
description:    Xtables: packet mark and nat operations
author:         Jesus Llorente Santos <jesus.llorente.santos@aalto.fi>
license:        GPL
srcversion:     FF9196B1F5166E8981119EE
depends:        x_tables,nf_conntrack,nf_nat
retpoline:      Y
name:           xt_MARKDNAT
vermagic:       4.15.0-117-generic SMP mod_unload
```

## Installing the userspace module

Install the following build dependencies as follow:

```
sudo apt update
sudo apt install iptables-dev automake bison flex libmnl-dev libnftnl-dev libtool
```

Ensure the APT source lists include the correspondent `deb-src` repository to download the source package for `iptables`:

```
apt show iptables | grep "APT-Sources"
APT-Sources: http://archive.ubuntu.com/ubuntu bionic/main amd64 Packages

cat /etc/apt/sources.list | grep deb-src
deb-src http://archive.ubuntu.com/ubuntu bionic main restricted
```

Install the custom iptables userspace module as follow:

```
sudo apt update
cd /var/tmp/ && apt source iptables
cd /var/tmp/iptables-1.6.1
./autogen.sh
./configure
cp /realmgateway/iptables_devel/userspace/libxt_MARKDNAT.* /var/tmp/iptables-1.6.1/extensions
make all -C /var/tmp/iptables-1.6.1/extensions
sudo cp /var/tmp/iptables-1.6.1/extensions/libxt_MARKDNAT.so /usr/lib/x86_64-linux-gnu/xtables/libxt_MARKDNAT.so
```

Verify the module can be loaded:

```
iptables -j MARKDNAT --help
MARKDNAT target options:
  --set-xmark value[/mask]  Clear bits in mask and XOR value into nfmark
  --set-mark value[/mask]   Clear bits in mask and OR value into nfmark
  --and-mark bits           Binary AND the nfmark with bits
  --or-mark bits            Binary OR the nfmark with bits
  --xor-mark bits           Binary XOR the nfmark with bits
```

## Test

Verify both the userspace and kernel modules have been correctly installed:

```
sudo iptables -t nat -A PREROUTING -j MARKDNAT --set-xmark 0x0/0x0
sudo iptables -t nat -D PREROUTING -j MARKDNAT --set-xmark 0x0/0x0
```
