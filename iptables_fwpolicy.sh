# How to: Linux Iptables block common attacks
# http://www.cyberciti.biz/tips/linux-iptables-10-how-to-block-common-attack.html
#

# Definition of variables
VTEP_NIC="cesa-vetp"
WAN_NIC="cesa-wan"
LAN_NIC="cesa-lan"
LAN_NET="192.168.0.0/24"
PROXY_NET="172.16.0.0/24"

SPOOF_IPS="0.0.0.0/8 127.0.0.0/8 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 224.0.0.0/3"

# Packet marks per interface
hMARK_OUT_LAN2LOCAL="0x4" #0b00100
hMARK_OUT_LAN2WAN="0x6"   #0b00110
hMARK_OUT_LAN2CES="0x7"   #0b00111
hMARK_IN_WAN2LOCAL="0x18" #0b11000
hMARK_IN_WAN2LAN="0x19"   #0b11001
hMARK_IN_CES2LAN="0x1d"   #0b11101

hMARK_INOUT_MASK="0x10"   #0b10000
hMARK_OUT_MASK="0x00"     #0b00000
hMARK_IN_MASK="0x10"      #0b10000



# DEFINITION OF FIREWALL POLICIES TO PROTECT FROM ATTACKS
iptables -N FIREWALL_POLICY

# Force SYN packets check
iptables -A FIREWALL_POLICY -p tcp ! --syn -m state --state NEW -j doREJECT

# Force Fragments packets check
iptables -A FIREWALL_POLICY -f -j doREJECT

# XMAS packets
iptables -A FIREWALL_POLICY -p tcp --tcp-flags ALL ALL -j doREJECT

# Drop all NULL packets
iptables -A FIREWALL_POLICY -p tcp --tcp-flags ALL NONE -j doREJECT

# Drop vulnerable multiport TCP services
# http://howtonixnux.blogspot.fi/2008/03/iptables-using-multiport.html
TCP_MULTIPORTS="135,137,138,139"
iptables -A FIREWALL_POLICY -p tcp -m state --state NEW -m multiport --dports $TCP_MULTIPORTS -j doREJECT


# Linux Iptables Avoid IP Spoofing And Bad Addresses Attacks
# http://www.cyberciti.biz/tips/linux-iptables-8-how-to-avoid-spoofing-and-bad-addresses-attack.html
iptables -A FIREWALL_POLICY -i $VTEP_NIC ! -s $PROXY_NET -j doREJECT
iptables -A FIREWALL_POLICY -i $LAN_NIC  ! -s $LAN_NET   -j doREJECT

## Drop all other spoofed traffic
for ip in $SPOOF_IPS
do
    iptables -A FIREWALL_POLICY -i $WAN_NIC -s $ip -j doREJECT
done


# Linux Iptables allow or block ICMP ping request
# http://www.cyberciti.biz/tips/linux-iptables-9-allow-icmp-ping.html