from netfilterqueue import NetfilterQueue
from scapy.all import *
from scapy.layers.inet import *
from scapy.layers.inet6 import *

import sys
import random

logmsg=''
counter=0

def print_and_accept(pkt):
    global logmsg
    global counter
    data = pkt.get_payload()
    ip = IP(data)
    print('{}: {}'.format(logmsg, ip.summary()))
    counter += 1
    if(counter%2):
        mark = 0x101
    else:
        mark = 0x102
    pkt.set_mark(mark)
    pkt.accept()
    print('Set mark {}'.format(mark))

def print_and_drop(pkt):
    global logmsg
    data = pkt.get_payload()
    ip = IP(data)
    print('{}: {}'.format(logmsg, ip.summary()))
    pkt.drop()

if __name__ == '__main__':
    global logmsg
    print(sys.argv)
    nqueue = int(sys.argv[1])
    action = sys.argv[2]
    logmsg = sys.argv[3]
    
    if action == 'accept' or action == 'a':
        callback = print_and_accept
    elif action == 'drop' or action == 'd':
        callback = print_and_drop
    else:
        print('sudo python{python3} netfilterqueueLog.py queueNum accept||drop logmsg{}'.format(nqueue, callback))
        sys.exit()
    
    print('Binding to queue {} and action {}'.format(nqueue, callback))
    nfqueue = NetfilterQueue()
    nfqueue.bind(nqueue, callback)
    try:
        nfqueue.run()
    except KeyboardInterrupt:
        print
    nfqueue.unbind()