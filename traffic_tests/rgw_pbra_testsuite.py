#!/usr/bin/env python3

"""
BSD 3-Clause License

Copyright (c) 2018, Jesus Llorente Santos, Aalto University, Finland
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

"""
NOTE: If run into the problem of too many files open, add to the file /etc/security/limits.conf
* soft nofile 65535
* hard nofile 65535

In this test suite we attempt to generate a deterministic amount of Internet traffic to model our algorithms deployed in Realm Gateway.

We consider the following types of traffic:
1. Legitimate DNS+data clients (desired users)
2. Legitimate DNS clients      (produce address expiration)
3. Legitimate data clients     (scanner/spiders/attack via TCP)
4. Spoofed DNS clients         (produce address expiration)
5. Spoofed data clients        (SYN spoofing attacks)


####################################################################################################
"""

import asyncio
import argparse
import base64
import functools
import json
import logging
import math
import os
import random
import socket
import statistics
import struct
import sys
import time
import yaml

import dns
import dns.message
import dns.edns
import dns.inet
import dns.rdataclass
import dns.rdatatype

# For Scapy
logging.getLogger('scapy.runtime').setLevel(logging.ERROR)
from scapy.all import *
from scapy.layers.inet import *
from scapy.layers.inet6 import *

# Global message counter
MSG_SENT = 0
MSG_RECV = 0

WATCHDOG = 1.0 #Sleep 1 second before displaying loop stats
RESULTS = []   #List to store TestResult objects

loop = asyncio.get_event_loop()
TS_ZERO = loop.time()
TASK_NUMBER = 0

DETERMINISTIC_ALLOCATION = True

LAST_UDP_PORT = 30000
LAST_TCP_PORT = 30000
LAST_QUERY_ID = 30000
UDP_PORT_RANGE = (20000, 65535)
TCP_PORT_RANGE = (20000, 65535)
QUERY_ID_RANGE = (20000, 65535)

def get_deterministic_port(proto):
    if proto in ['tcp', 6, socket.SOCK_STREAM]:
        global LAST_TCP_PORT
        LAST_TCP_PORT += 1
        # Further logic to port allocation
        if LAST_TCP_PORT > TCP_PORT_RANGE[1]:
            LAST_TCP_PORT = TCP_PORT_RANGE[0]
        port = LAST_TCP_PORT
    elif proto in ['udp', 17, socket.SOCK_DGRAM]:
        global LAST_UDP_PORT
        LAST_UDP_PORT += 1
        # Further logic to port allocation
        if LAST_UDP_PORT > UDP_PORT_RANGE[1]:
            LAST_UDP_PORT = UDP_PORT_RANGE[0]
        port = LAST_UDP_PORT
    return port

def get_deterministic_queryid():
    global LAST_QUERY_ID
    LAST_QUERY_ID += 1
    # Further logic to port allocation
    if LAST_QUERY_ID > QUERY_ID_RANGE[1]:
        LAST_QUERY_ID = QUERY_ID_RANGE[0]
    queryid = LAST_QUERY_ID
    return queryid

if DETERMINISTIC_ALLOCATION is False:
    get_deterministic_port = lambda x: random.randrange(1025, 65536)
    get_deterministic_queryid = lambda : random.randrange(1025, 65536)


def set_attributes(obj, override=False, **kwargs):
    """Set attributes in object from a dictionary"""
    for k,v in kwargs.items():
        if hasattr(obj, k) and not override:
            continue
        setattr(obj, k, v)

def _now(ref = 0):
    """ Return current time based on event loop """
    return loop.time() - ref

async def _timeit(coro, scale = 1):
    """ Execute a coroutine and return the time consumed in second scale """
    t0 = _now()
    r = await coro
    return (_now(t0)*scale, r)

async def _socket_connect(raddr, laddr, family, type, reuseaddr=True, timeout=0, mark=0):
    # Set socket family
    if family in ['ipv4', 0x0800]:
        socketfamily = socket.AF_INET
    elif family in ['ipv6', 0x86dd]:
        socketfamily = socket.AF_INET6
    # Set socket type
    if type in ['tcp', 6]:
        sockettype = socket.SOCK_STREAM
    elif type in ['udp', 17]:
        sockettype = socket.SOCK_DGRAM

    # Create socket object
    sock = socket.socket(socketfamily, sockettype)
    # Sanitize connect timeout value
    timeout = 0 if timeout is None else int(timeout)
    # Enable address reuse
    if reuseaddr:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if not laddr:
        laddr = ('0.0.0.0', 0)

    if sockettype == socket.SOCK_STREAM:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # Set SO_MARK
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, int(mark))

    # Check local port selection and use deterministic approach if not selected
    _local_addr, _local_port = laddr[0], laddr[1]
    if _local_port == 0:
        _local_port = get_deterministic_port(type)

    # Try to bind a port up to 2 times. Get a new deterministic port if the first choice fails.
    for i in range(2):
        try:
            sock.bind((_local_addr, _local_port))
            sock.setblocking(False)
            await asyncio.wait_for(loop.sock_connect(sock, raddr), timeout=timeout, loop=loop)
            return sock
        except OSError as e:
            logger = logging.getLogger('_socket_connect')
            logger.error('{} @ {}:{} [{}] - reattempt'.format(e, _local_addr, _local_port, type))
            _local_port = get_deterministic_port(type)
            continue
        except Exception as e:
            logger = logging.getLogger('_socket_connect')
            logger.error('{} @ {}:{} [{}]'.format(e, _local_addr, _local_port, type))
            return None
    return None


from asyncio import Queue
class AsyncSocketQueue(object):
    """
    This class attempts to solve the bug found with loop.sock_recv() used via asyncio.wait_for()
    It uses a simple internal asyncio.Queue() to store the received messages of a *connected socket*
    """
    def __init__(self, sock, loop, queuesize=0, msgsize=1024):
        self._sock = sock
        self._loop = loop
        self._queue = Queue(maxsize=queuesize, loop=loop)
        # Register reader in loop
        self._sock.setblocking(False)
        self._loop.add_reader(self._sock.fileno(), AsyncSocketQueue._recv_callback, self._sock, self._queue, msgsize)

    def _recv_callback(sock, queue, msgsize):
        # Socket is read-ready
        try:
            data = sock.recv(msgsize)
        except ConnectionRefusedError:
            data = None
        finally:
            queue.put_nowait(data)

    async def recv(self):
        data = await self._queue.get()
        self._queue.task_done()
        return data

    async def sendall(self, data):
        await self._loop.sock_sendall(self._sock, data)

    def close(self):
        # Deregister reader in loop
        self._loop.remove_reader(self._sock.fileno())
        self._sock.close()
        del self._sock
        del self._queue

####################################################################################################
# Copied from my own edns.py module. Added here for self-contained file.                           #
####################################################################################################

ECS = 8
class _EDNS0_ECSOption_(dns.edns.Option):
    """EDNS Client Subnet (ECS, RFC7871)"""

    def __init__(self, address, srclen=None, scopelen=0):
        """*address*, a ``text``, is the client address information.
        *srclen*, an ``int``, the source prefix length, which is the
        leftmost number of bits of the address to be used for the
        lookup.  The default is 24 for IPv4 and 56 for IPv6.
        *scopelen*, an ``int``, the scope prefix length.  This value
        must be 0 in queries, and should be set in responses.
        """

        super(_EDNS0_ECSOption_, self).__init__(ECS)
        af = dns.inet.af_for_address(address)

        if af == dns.inet.AF_INET6:
            self.family = 2
            if srclen is None:
                srclen = 56
        elif af == dns.inet.AF_INET:
            self.family = 1
            if srclen is None:
                srclen = 24
        else:
            raise ValueError('Bad ip family')

        self.address = address.decode() if type(address) is bytes else address
        self.srclen = srclen
        self.scopelen = scopelen

        addrdata = dns.inet.inet_pton(af, address)
        nbytes = int(math.ceil(srclen/8.0))

        # Truncate to srclen and pad to the end of the last octet needed
        # See RFC section 6
        self.addrdata = addrdata[:nbytes]
        nbits = srclen % 8
        if nbits != 0:
            last = struct.pack('B', ord(self.addrdata[-1:]) & (0xff << nbits))
            self.addrdata = self.addrdata[:-1] + last

    def to_text(self):
        return 'ECS {}/{} scope/{}'.format(self.address, self.srclen, self.scopelen)

    def to_wire(self, file):
        file.write(struct.pack('!H', self.family))
        file.write(struct.pack('!BB', self.srclen, self.scopelen))
        file.write(self.addrdata)

    @classmethod
    def from_wire(cls, otype, wire, cur, olen):
        family, src, scope = struct.unpack('!HBB', wire[cur:cur+4])
        cur += 4

        addrlen = int(math.ceil(src/8.0))

        if family == 1:
            af = dns.inet.AF_INET
            pad = 4 - addrlen
        elif family == 2:
            af = dns.inet.AF_INET6
            pad = 16 - addrlen
        else:
            raise ValueError('unsupported family')

        addr = dns.inet.inet_ntop(af, wire[cur:cur+addrlen] + b'\x00' * pad)
        return cls(addr, src, scope)

    def _cmp(self, other):
        if self.addrdata == other.addrdata:
            return 0
        if self.addrdata > other.addrdata:
            return 1
        return -1

ECI = 0xFF01
class _EDNS0_EClientInfoOption_(dns.edns.Option):
    """
    EDNS Client Information (own development)
        * Client Information (0xFF01) (Encoded lenght 80 0x50 for IPv4 and 176 0xb0 for IPv6)
        -> 16 bits: Client Address Family (1 for IPv4, 2 for IPv6, x for custom UniqueLocalHostIdentifier)
        -> n  bits: Client Address
        -> 16 bits: Client Protocol
        -> 16 bits: Client Transaction ID
    """

    def __init__(self, address, protocol=17, query_id=0):
        super(_EDNS0_EClientInfoOption_, self).__init__(ECI)
        af = dns.inet.af_for_address(address)

        if af == dns.inet.AF_INET6:
            self.family = 2
        elif af == dns.inet.AF_INET:
            self.family = 1
        else:
            raise ValueError('Bad ip family')

        self.address = address.decode() if type(address) is bytes else address
        self.protocol = protocol
        self.query_id = query_id
        self.addrdata = dns.inet.inet_pton(af, address)

    def to_text(self):
        return 'ECI source/{} proto/{} query_id/{}'.format(self.address, self.protocol, self.query_id)

    def to_wire(self, file):
        file.write(struct.pack('!H', self.family))
        file.write(self.addrdata)
        file.write(struct.pack('!HH', self.protocol, self.query_id))

    @classmethod
    def from_wire(cls, otype, wire, cur, olen):
        family = struct.unpack('!H', wire[cur:cur+2])[0]
        cur += 2

        if family == 1:
            af = dns.inet.AF_INET
            addrlen = 4
        elif family == 2:
            af = dns.inet.AF_INET6
            addrlen = 16
        else:
            raise ValueError('unsupported family')

        addr = dns.inet.inet_ntop(af, wire[cur:cur+addrlen])
        cur += addrlen
        protocol, query_id = struct.unpack('!HH', wire[cur:cur+4])
        return cls(addr, protocol, query_id)

    def _cmp(self, other):
        if self.addrdata == other.addrdata and self.protocol == other.protocol and self.query_id == query_id:
            return 0
        return -1

ECID = 0xFF02
class _EDNS0_EClientID_(dns.edns.Option):
    """
    EDNS Client Identification (own development)
        * Client ID (0xFF02)
            -> n  bits: Client ID (ID generated by resolving server)
    """

    def __init__(self, id_data):
        super(_EDNS0_EClientID_, self).__init__(ECID)
        self.id_data = id_data

    def to_text(self):
        return 'ECID id/{}'.format(self.id_data)

    def to_wire(self, file):
        file.write(self.id_data)

    @classmethod
    def from_wire(cls, otype, wire, cur, olen):
        id_data = wire[cur:cur+olen]
        return cls(id_data)

    def _cmp(self, other):
        if self.id_data == other.id_data:
            return 0
        if self.id_data > other.id_data:
            return 1
        return -1

# Add extensions to dnspython dns.edns module
dns.edns._type_to_class[ECS]   = _EDNS0_ECSOption_
dns.edns._type_to_class[ECI]   = _EDNS0_EClientInfoOption_
dns.edns._type_to_class[ECID]  = _EDNS0_EClientID_
####################################################################################################
####################################################################################################

def _make_query(fqdn, rdtype, rdclass, socktype='udp', client_addr=None, ecs_srclen=None, edns_options=None):
    options = []
    # Create EDNS options from iterable
    if edns_options is not None:
        for opt in edns_options:
            if opt == 'ecs':
                options.append(_EDNS0_ECSOption_(client_addr, srclen=ecs_srclen, scopelen=0))
            elif opt == 'eci':
                # Set socket type
                if socktype in ['tcp', 6]:
                    protocol = 6
                elif socktype in ['udp', 17]:
                    protocol = 17
                options.append(_EDNS0_EClientInfoOption_(client_addr, protocol=protocol, query_id=0))
            elif opt == 'ecid':
                # Use IP address as Extended Client ID / it could be a hash or any binary data
                options.append(_EDNS0_EClientID_(client_addr.encode()))
            else:
                print('EDNS option not recognized! <{}>'.format(opt))
                continue
    # Build query message
    query = dns.message.make_query(fqdn, rdtype, rdclass, options=options)
    query.id = get_deterministic_queryid()
    return query

async def _sendrecv(data, raddr, laddr, timeouts=[0], socktype='udp', reuseaddr=True, mark=0):
    """
    data: Data to send
    raddr: Remote tuple information
    laddr: Source tuple information
    timeouts: List with retransmission timeout scheme
    socktype: L4 protocol ['udp', 'tcp']

    There seem to be issues with iterating over asyncio.wait_for(loop.sock_recv())
    """
    global MSG_SENT
    global MSG_RECV

    logger = logging.getLogger('sendrecv')

    # Connect socket or fail early
    sock = await _socket_connect(raddr, laddr, family='ipv4', type=socktype, reuseaddr=reuseaddr, timeout=2, mark=mark)
    if sock is None:
        logger.warning('Socket failed to connect: {}:{} > {}:{} ({})'.format(laddr[0], laddr[1], raddr[0], raddr[1], socktype))
        return (None, 0)

    _laddr = sock.getsockname()
    logger.debug('Socket succeeded to connect: {}:{} > {}:{} ({})'.format(_laddr[0], _laddr[1], raddr[0], raddr[1], socktype))

    # Create async socket wrapper object
    asock = AsyncSocketQueue(sock, loop)

    for i, tout in enumerate(timeouts):
        try:
            await asock.sendall(data)
            MSG_SENT += 1
            recvdata = await asyncio.wait_for(asock.recv(), timeout=tout)
            MSG_RECV += 1
            logger.debug('[#{}] Received response: {}:{} > {}:{} ({}) / {}'.format(i+1, _laddr[0], _laddr[1], raddr[0], raddr[1], socktype, recvdata))
            break
        except asyncio.TimeoutError:
            logger.debug('#{} timeout expired ({:.4f} sec): {}:{} > {}:{} ({})'.format(i+1, tout, _laddr[0], _laddr[1], raddr[0], raddr[1], socktype))
            recvdata = None
            continue
        except Exception as e:
            logger.exception('Exception <{}>: {}:{} > {}:{} ({}) / {}'.format(e, _laddr[0], _laddr[1], raddr[0], raddr[1], socktype, data))
            recvdata = None
            break

    attempt = i+1
    asock.close()
    return (recvdata, attempt)


async def _gethostbyname(fqdn, raddr, laddr, timeouts=[0], socktype='udp', reuseaddr=True, client_addr=None, ecs_srclen=None, edns_options=None, mark=0):
    """
    fqdn: Domain name to be resolved
    raddr: Remote tuple information
    raddr: Local tuple information
    timeouts: List with retransmission timeout scheme
    """
    global TS_ZERO
    logger = logging.getLogger('gethostbyname')
    logger.debug('Resolving {} via {}:{} > {}:{} ({}) with timeouts {}'.format(fqdn, laddr[0], laddr[1], raddr[0], raddr[1], socktype, timeouts))
    rdtype = dns.rdatatype.A
    rdclass = dns.rdataclass.IN
    ipaddr = None
    attempt = 0
    response = None

    # Create DNS query
    query = _make_query(fqdn, rdtype, rdclass, socktype, client_addr, ecs_srclen, edns_options)

    if socktype == 'udp':
        data = query.to_wire()
        # Send query and await for response with retransmission template
        data_recv, data_attempts = await _sendrecv(data, raddr, laddr, timeouts, socktype, reuseaddr, mark)
        # Resolution did not succeed
        if data_recv is None:
            logger.debug('Resolution failed: {} via {}:{} > {}:{} ({})'.format(fqdn, laddr[0], laddr[1], raddr[0], raddr[1], socktype))
            return (None, query.id, data_attempts)
        response = dns.message.from_wire(data_recv)
        assert(response.id == query.id)
        # Check if response is truncated and retry in TCP with a recursive call
        if (response.flags & dns.flags.TC == dns.flags.TC):
            logger.debug('Truncated response, reattempt via TCP: {} via {}:{} > {}:{} ({})'.format(fqdn, laddr[0], laddr[1], raddr[0], raddr[1], socktype))
            return await _gethostbyname(fqdn, raddr, laddr, timeouts, socktype='tcp', reuseaddr=reuseaddr, client_addr=client_addr, ecs_srclen=ecs_srclen, edns_options=edns_options, mark=mark)

    elif socktype == 'tcp':
        _data = query.to_wire()
        data = struct.pack('!H', len(_data)) + _data
        # Send query and await for response with retransmission template
        data_recv, data_attempts = await _sendrecv(data, raddr, laddr, timeouts, socktype, reuseaddr, mark)
        # Resolution did not succeed
        if data_recv is None:
            logger.debug('Resolution failed: {} via {}:{} > {}:{} ({})'.format(fqdn, laddr[0], laddr[1], raddr[0], raddr[1], socktype))
            return (None, query.id, data_attempts)
        _len = struct.unpack('!H', data_recv[:2])[0]
        response = dns.message.from_wire(data_recv[2:2+_len])
        assert(response.id == query.id)

    # Parsing result
    ## With new PBRA DNS design, we might receive a CNAME instead of an A record, so we have to follow up with a new query to the given domain
    ## First try to obtain the A record and return if successful
    for rrset in response.answer:
        for rdata in rrset:
            if rdata.rdtype == dns.rdatatype.A:
                ipaddr = rdata.address
                logger.debug('Resolution succeeded: {} via {}:{} > {}:{} ({}) yielded {}'.format(fqdn, laddr[0], laddr[1], raddr[0], raddr[1], socktype, ipaddr))
                return (ipaddr, query.id, data_attempts)

    ## Alternatively, try to follow-up through the CNAME record and with a recursive call
    for rrset in response.answer:
        for rdata in rrset:
            if rdata.rdtype == dns.rdatatype.CNAME:
                target = rdata.to_text()
                logger.debug('Resolution continues: {} via {}:{} > {}:{} ({}) yielded {}'.format(fqdn, laddr[0], laddr[1], raddr[0], raddr[1], socktype, target))
                return await _gethostbyname(target, raddr, laddr, timeouts, socktype='udp', reuseaddr=reuseaddr, client_addr=client_addr, ecs_srclen=ecs_srclen, edns_options=edns_options, mark=mark)

    # Resolution did not succeed
    logger.debug('Resolution failed: {} via {}:{} > {}:{} ({})'.format(fqdn, laddr[0], laddr[1], raddr[0], raddr[1], socktype))
    return (None, query.id, data_attempts)


def _scapy_build_packet(src, dst, proto, sport, dport, payload=b''):
    if sport == 0:
        sport = random.randint(1,65535)
    if dport == 0:
        dport = get_deterministic_port(proto)
    if proto == 6:
        layer_4 = TCP(sport=sport, dport=dport, seq=random.randint(1,2**32-1))
    elif proto == 17:
        layer_4 = UDP(sport=sport, dport=dport)/Raw(payload)
    else:
        raise Exception('Protocol <{}> not supported'.format(proto))

    return Ether()/IP(src=src, dst=dst)/layer_4

_l2socket_cache = {}
def _scapy_send_packet(packet, iface):
    """ Accepts packet of type Packet() or bytes """
    try:
        # Get sending raw socket
        if iface is None and not isinstance(packet, bytes):
            sendp(packet, iface=iface, verbose=False)
            return True

        # Create new L2Socket and add it to the local cache
        if iface not in _l2socket_cache:
            _l2socket_cache[iface] = scapy.arch.linux.L2Socket(iface=iface)
        # Continue with L2Socket
        l2socket = _l2socket_cache[iface]
        # Obtain wire representation of the packet
        if not isinstance(packet, bytes):
            packet = bytes(packet)
        # Streamlined send function
        l2socket.outs.send(packet)
        return True
    except OSError as e:
        if isinstance(packet, bytes):
            # Packetize to enhance logging information
            packet = Ether(packet)
        logger.error('Failed to send packet via {} <{}> / {}'.format(iface, e, packet.command()))
        return False

def _get_service_tuple(local_l, remote_l):
    # Return a random match from the list of local and remote services tuples
    ## Use all options on the first iteration, then adjust protocol if no match was found
    if len(local_l) == 0:
        j = remote_l[random.randrange(0, len(remote_l))]
        return (None, j)
    elif len(remote_l) == 0:
        i = local_l[random.randrange(0, len(local_l))]
        return (i, None)

    base = list(local_l)
    while True:
        i = base[random.randrange(0, len(base))]
        r_matches = [_ for _ in remote_l if _[2]==i[2]]
        # No match found in remote services for given protocol, readjust base and try again
        if len(r_matches) == 0:
            base = [_ for _ in base if _[2]!=i[2]]
            continue

        j = r_matches[random.randrange(0, len(r_matches))]
        return (i, j)

def _get_data_dict(d, tree, default=''):
    # Generic function to access result data
    try:
        _d = dict(d)
        for branch in tree:
            _d = _d[branch]
        return _d
    except KeyError:
        return default

def add_result(name, success, metadata, ts_start, ts_end):
    # Add a result dictionary entry
    global RESULTS
    RESULTS.append({'name':name, 'success':success, 'metadata': metadata, 'ts_start': ts_start, 'ts_end': ts_end, 'duration': ts_end - ts_start})


class _TestTraffic(object):
    ''' Define base class and implement these methods for traffic tests '''
    @staticmethod
    def schedule_tasks(**kwargs):
        pass

    async def run(**kwargs):
        pass


class RealDNSDataTraffic(_TestTraffic):
    ''' Use static classes just to access the specific method for the tests '''
    logger = logging.getLogger('RealDNSDataTraffic')

    @staticmethod
    def schedule_tasks(**kwargs):
        ''' Return a list of schedule tasks in dictionary format for later spawning '''
        global TS_ZERO
        global TASK_NUMBER

        # Use a list to store scheduled tasks parameters
        scheduled_tasks = []
        # Set default variables that might not be defined in configuration / Allow easy test of specific features
        reuseaddr = kwargs.setdefault('reuseaddr', True)
        dns_delay_t = kwargs.setdefault('dns_delay', (0,0))
        data_delay_t = kwargs.setdefault('data_delay', (0,0))
        data_backoff_t = kwargs.setdefault('data_backoff', (0,0))
        metadata = kwargs.get('metadata', {})
        # Adjust next taskdelay time
        taskdelay = kwargs['ts_start']
        iterations = int(kwargs['load'] * kwargs['duration'])
        distribution = kwargs.setdefault('distribution', 'exp')
        for i in range(0, iterations):
            # Set starting time for task
            if distribution == 'exp':
                taskdelay += random.expovariate(kwargs['load'])
            elif distribution == 'uni':
                taskdelay += 1 / kwargs['load']

            TASK_NUMBER += 1
            task_nth = TASK_NUMBER
            task_type = kwargs['type']
            # Select parameters randomly
            dns_laddr, dns_raddr   = _get_service_tuple(kwargs['dns_laddr'],  kwargs['dns_raddr'])
            data_laddr, data_raddr = _get_service_tuple(kwargs['data_laddr'], kwargs['data_raddr'])
            # Use timeout template(s) and delays
            dns_timeouts, data_timeouts = kwargs['dns_timeouts'], kwargs['data_timeouts']
            dns_delay = int(random.uniform(*dns_delay_t) * 1000)
            data_delay = int(random.uniform(*data_delay_t) * 1000)
            data_backoff = random.uniform(*data_backoff_t)
            # Log task parameters
            task_str = 'DNS {}:{}/{} => {}:{}/{} timeouts={} // Data {}:{}/{} => {}:{}/{} timeouts={} delay={:.4f}'.format(dns_laddr[0], dns_laddr[1], dns_laddr[2],
                                                                                                                           dns_raddr[0], dns_raddr[1], dns_raddr[2],
                                                                                                                           dns_timeouts,
                                                                                                                           data_laddr[0], data_laddr[1], data_laddr[2],
                                                                                                                           data_raddr[0], data_raddr[1], data_raddr[2],
                                                                                                                           data_timeouts, data_delay)
            RealDNSDataTraffic.logger.info('[#{}] Scheduled task {} @ {:.4f} / {}'.format(task_nth, task_type, taskdelay - TS_ZERO, task_str))
            # Build dictionary with selected parameters for running the task
            args_d = {'task_nth': task_nth, 'task_type': task_type, 'reuseaddr': reuseaddr,
                      'dns_laddr': dns_laddr, 'dns_raddr': dns_raddr, 'dns_timeouts': dns_timeouts, 'dns_delay': dns_delay,
                      'data_laddr': data_laddr, 'data_raddr': data_raddr, 'data_timeouts': data_timeouts, 'data_delay': data_delay, 'data_backoff': data_backoff,
                      'metadata': metadata,
                      }
            # Append the newly defined task with its parameters
            scheduled_tasks.append({'offset': taskdelay - TS_ZERO, 'cls': task_type, 'kwargs': args_d})

        # Return list of scheduled tasks for later spawning
        return scheduled_tasks


    async def run(**kwargs):
        global TS_ZERO
        # Get parameters
        task_nth        = kwargs['task_nth']
        task_type       = kwargs['task_type']
        dns_laddr       = kwargs['dns_laddr']
        dns_raddr       = kwargs['dns_raddr']
        dns_timeouts    = kwargs['dns_timeouts']
        dns_delay       = kwargs['dns_delay']
        data_laddr      = kwargs['data_laddr']
        data_raddr      = kwargs['data_raddr']
        data_timeouts   = kwargs['data_timeouts']
        data_delay      = kwargs['data_delay']
        data_backoff    = kwargs['data_backoff']
        reuseaddr       = kwargs['reuseaddr']
        metadata        = kwargs['metadata']

        RealDNSDataTraffic.logger.info('[{:.4f}] Running task #{}'.format(_now(TS_ZERO), task_nth))
        ts_start = _now()
        metadata_d = {}

        # Unpack DNS related data
        dns_ripaddr, dns_rport, dns_rproto = dns_raddr
        dns_lipaddr, dns_lport, dns_lproto = dns_laddr
        # Select socket type based on protocol number
        dns_sockettype = 'tcp' if dns_rproto == 6 else 'udp'

        # Unpack Data related data
        data_fqdn,    data_rport, data_rproto = data_raddr
        data_lipaddr, data_lport, data_lproto = data_laddr
        # Select socket type based on protocol number
        data_sockettype = 'tcp' if data_rproto == 6 else 'udp'

        # Get variable metadata
        edns_options = metadata.get('edns_options', None)
        ecs_srclen = metadata.get('edns_ecs_srclen', 24)

        ## Run DNS resolution
        data_ripaddr, query_id, dns_attempts = await _gethostbyname(data_fqdn, (dns_ripaddr, dns_rport), (dns_lipaddr, dns_lport),
                                                                    timeouts=dns_timeouts, socktype=dns_sockettype,
                                                                    reuseaddr=reuseaddr, client_addr=data_lipaddr, ecs_srclen=ecs_srclen,
                                                                    edns_options=edns_options, mark=dns_delay)

        # Populate partial results
        ts_end = _now()
        metadata_d['dns_attempts'] = dns_attempts
        metadata_d['dns_duration'] = ts_end - ts_start
        metadata_d['dns_start']    = ts_start
        metadata_d['dns_end']      = ts_end
        metadata_d['dns_laddr']    = dns_laddr
        metadata_d['dns_raddr']    = dns_raddr
        metadata_d['dns_fqdn']     = data_fqdn

        # Evaluate DNS resolution
        if data_ripaddr is None:
            sucess = False
            metadata_d['dns_success'] = False
            metadata_d['duration'] = ts_end - ts_start
            add_result(task_type, sucess, metadata_d, ts_start, ts_end)
            return
        else:
            metadata_d['dns_success'] = True

        # This represents the network delay between DNS client and resolver
        if data_backoff > 0:
            RealDNSDataTraffic.logger.debug('Backoff {:.3f} ms before initiating data connection'.format(data_backoff))
            await asyncio.sleep(data_backoff)

        ## Run data transfer
        ts_start_data = _now()
        data_b = '{}@{}'.format(data_fqdn, data_ripaddr)
        data_recv, data_attempts = await _sendrecv(data_b.encode(), (data_ripaddr, data_rport), (data_lipaddr, data_lport),
                                                   timeouts=data_timeouts, socktype=data_sockettype,
                                                   reuseaddr=reuseaddr, mark=data_delay)
        # Populate partial results
        ts_end = _now()
        metadata_d['data_attempts'] = data_attempts
        metadata_d['data_duration'] = ts_end - ts_start_data
        metadata_d['data_start']    = ts_start_data
        metadata_d['data_end']      = ts_end
        metadata_d['data_laddr']    = data_laddr
        metadata_d['data_raddr']    = (data_ripaddr, data_rport, data_rproto)
        metadata_d['duration']      = ts_end - ts_start

        # Evaluate data transfer
        if data_recv is None:
            sucess = False
            metadata_d['data_success'] = False
        else:
            sucess = True
            metadata_d['data_success'] = True

        add_result(task_type, sucess, metadata_d, ts_start, ts_end)


class RealDNSTraffic(_TestTraffic):
    ''' Use static classes just to access the specific method for the tests '''
    logger = logging.getLogger('RealDNSTraffic')

    @staticmethod
    def schedule_tasks(**kwargs):
        ''' Return a list of schedule tasks in dictionary format for later spawning '''
        global TS_ZERO
        global TASK_NUMBER

        # Use a list to store scheduled tasks parameters
        scheduled_tasks = []
        # Set default variables that might not be defined in configuration / Allow easy test of specific features
        reuseaddr = kwargs.setdefault('reuseaddr', True)
        dns_delay_t = kwargs.setdefault('dns_delay', (0,0))
        metadata = kwargs.get('metadata', {})
        # Adjust next taskdelay time
        taskdelay = kwargs['ts_start']
        iterations = int(kwargs['load'] * kwargs['duration'])
        distribution = kwargs.setdefault('distribution', 'exp')
        for i in range(0, iterations):
            # Set starting time for task
            if distribution == 'exp':
                taskdelay += random.expovariate(kwargs['load'])
            elif distribution == 'uni':
                taskdelay += 1 / kwargs['load']

            TASK_NUMBER += 1
            task_nth = TASK_NUMBER
            task_type = kwargs['type']
            # Select parameters randomly
            dns_laddr, dns_raddr   = _get_service_tuple(kwargs['dns_laddr'],  kwargs['dns_raddr'])
            data_laddr, data_raddr = _get_service_tuple(kwargs['data_laddr'], kwargs['data_raddr'])
            # Use timeout template(s) and delays
            dns_timeouts = kwargs['dns_timeouts']
            dns_delay = int(random.uniform(*dns_delay_t) * 1000)
            # Log task parameters
            task_str = 'DNS {}:{}/{} => {}:{}/{} timeouts={} // Data {}:{}/{}'.format(dns_laddr[0], dns_laddr[1], dns_laddr[2],
                                                                                      dns_raddr[0], dns_raddr[1], dns_raddr[2],
                                                                                      dns_timeouts,
                                                                                      data_raddr[0], data_raddr[1], data_raddr[2])
            RealDNSTraffic.logger.info('[#{}] Scheduled task {} @ {:.4f} / {}'.format(task_nth, task_type, taskdelay - TS_ZERO, task_str))
            # Build dictionary with selected parameters for running the task
            args_d = {'task_nth': task_nth, 'task_type': task_type, 'reuseaddr': reuseaddr,
                      'dns_laddr': dns_laddr, 'dns_raddr': dns_raddr, 'dns_timeouts': dns_timeouts, 'dns_delay': dns_delay,
                      'data_laddr': data_laddr, 'data_raddr': data_raddr,
                      'metadata': metadata,
                      }
            # Append the newly defined task with its parameters
            scheduled_tasks.append({'offset': taskdelay - TS_ZERO, 'cls': task_type, 'kwargs': args_d})

        # Return list of scheduled tasks for later spawning
        return scheduled_tasks

    async def run(**kwargs):
        global TS_ZERO
        # Get parameters
        task_nth        = kwargs['task_nth']
        task_type       = kwargs['task_type']
        dns_laddr       = kwargs['dns_laddr']
        dns_raddr       = kwargs['dns_raddr']
        dns_timeouts    = kwargs['dns_timeouts']
        dns_delay       = kwargs['dns_delay']
        data_laddr      = kwargs['data_laddr']
        data_raddr      = kwargs['data_raddr']
        reuseaddr       = kwargs['reuseaddr']
        metadata        = kwargs['metadata']

        RealDNSTraffic.logger.info('[{:.4f}] Running task #{}'.format(_now(TS_ZERO), task_nth))
        ts_start = _now()
        metadata_d = {}

        # Unpack DNS related data
        dns_ripaddr, dns_rport, dns_rproto = dns_raddr
        dns_lipaddr, dns_lport, dns_lproto = dns_laddr
        # Select socket type based on protocol number
        dns_sockettype = 'tcp' if dns_rproto == 6 else 'udp'

        # Unpack Data related data
        data_fqdn,    data_rport, data_rproto = data_raddr
        data_lipaddr, data_lport, data_lproto = data_laddr

        # Get variable metadata
        edns_options = metadata.get('edns_options', None)
        ecs_srclen = metadata.get('edns_ecs_srclen', 24)

        ## Run DNS resolution
        data_ripaddr, query_id, dns_attempts = await _gethostbyname(data_fqdn, (dns_ripaddr, dns_rport), (dns_lipaddr, dns_lport),
                                                                    timeouts=dns_timeouts, socktype=dns_sockettype,
                                                                    reuseaddr=reuseaddr, client_addr=data_lipaddr, ecs_srclen=ecs_srclen,
                                                                    edns_options=edns_options, mark=dns_delay)

        # Populate partial results
        ts_end = _now()
        metadata_d['dns_attempts'] = dns_attempts
        metadata_d['dns_duration'] = ts_end - ts_start
        metadata_d['dns_start']    = ts_start
        metadata_d['dns_end']      = ts_end
        metadata_d['dns_laddr']    = dns_laddr
        metadata_d['dns_raddr']    = dns_raddr
        metadata_d['dns_fqdn']     = data_fqdn
        metadata_d['duration']     = ts_end - ts_start
        metadata_d['data_raddr']   = (data_ripaddr, data_rport, data_rproto)

        # Evaluate DNS resolution
        if data_ripaddr is None:
            sucess = False
            metadata_d['dns_success'] = False
        else:
            sucess = True
            metadata_d['dns_success'] = True

        add_result(task_type, sucess, metadata_d, ts_start, ts_end)


class RealDataTraffic(_TestTraffic):
    ''' Use static classes just to access the specific method for the tests '''
    logger = logging.getLogger('RealDataTraffic')

    @staticmethod
    def schedule_tasks(**kwargs):
        ''' Return a list of schedule tasks in dictionary format for later spawning '''
        global TS_ZERO
        global TASK_NUMBER

        # Use a list to store scheduled tasks parameters
        scheduled_tasks = []
        # Set default variables that might not be defined in configuration / Allow easy test of specific features
        reuseaddr = kwargs.setdefault('reuseaddr', True)
        data_delay_t = kwargs.setdefault('data_delay', (0,0))
        data_backoff_t = kwargs.setdefault('data_backoff', (0,0))
        # Adjust next taskdelay time
        taskdelay = kwargs['ts_start']
        iterations = int(kwargs['load'] * kwargs['duration'])
        distribution = kwargs.setdefault('distribution', 'exp')
        for i in range(0, iterations):
            # Set starting time for task
            if distribution == 'exp':
                taskdelay += random.expovariate(kwargs['load'])
            elif distribution == 'uni':
                taskdelay += 1 / kwargs['load']

            TASK_NUMBER += 1
            task_nth = TASK_NUMBER
            task_type = kwargs['type']
            # Select parameters randomly
            data_laddr, data_raddr = _get_service_tuple(kwargs['data_laddr'],  kwargs['data_raddr'])
            # Use timeout template(s) and delays
            data_timeouts = kwargs['data_timeouts']
            data_delay = int(random.uniform(*data_delay_t) * 1000)
            data_backoff = random.uniform(*data_backoff_t)
            # Log task parameters
            task_str = 'Data {}:{}/{} => {}:{}/{} timeouts={}'.format(data_laddr[0], data_laddr[1], data_laddr[2],
                                                                      data_raddr[0], data_raddr[1], data_raddr[2],
                                                                      data_timeouts)
            RealDataTraffic.logger.info('[#{}] Scheduled task {} @ {:.4f} / {}'.format(task_nth, task_type, taskdelay - TS_ZERO, task_str))
            # Build dictionary with selected parameters for running the task
            args_d = {'task_nth': task_nth, 'task_type': task_type, 'reuseaddr': reuseaddr,
                      'data_laddr': data_laddr, 'data_raddr': data_raddr, 'data_timeouts': data_timeouts, 'data_delay': data_delay, 'data_backoff': data_backoff,
                      }
            # Append the newly defined task with its parameters
            scheduled_tasks.append({'offset': taskdelay - TS_ZERO, 'cls': task_type, 'kwargs': args_d})

        # Return list of scheduled tasks for later spawning
        return scheduled_tasks

    async def run(**kwargs):
        global TS_ZERO
        # Get parameters
        task_nth        = kwargs['task_nth']
        task_type       = kwargs['task_type']
        data_laddr      = kwargs['data_laddr']
        data_raddr      = kwargs['data_raddr']
        data_timeouts   = kwargs['data_timeouts']
        data_delay      = kwargs['data_delay']
        data_backoff    = kwargs['data_backoff']
        reuseaddr       = kwargs['reuseaddr']

        RealDataTraffic.logger.info('[{:.4f}] Running task #{}'.format(_now(TS_ZERO), task_nth))
        ts_start = _now()
        metadata_d = {}
        # Unpack Data related data
        data_ripaddr, data_rport, data_rproto = data_raddr
        data_lipaddr, data_lport, data_lproto = data_laddr
        # Select socket type based on protocol number
        data_sockettype = 'tcp' if data_rproto == 6 else 'udp'

        # This represents the network delay between DNS client and resolver
        if data_backoff > 0:
            RealDataTraffic.logger.debug('Backoff {:.3f} ms before initiating data connection'.format(data_backoff))
            await asyncio.sleep(data_backoff)

        ## Run data transfer
        data_b = '{}@{}'.format(data_ripaddr, data_ripaddr)
        data_recv, data_attempts = await _sendrecv(data_b.encode(), (data_ripaddr, data_rport), (data_lipaddr, data_lport),
                                                   timeouts=data_timeouts, socktype=data_sockettype,
                                                   reuseaddr=reuseaddr, mark=data_delay)
        # Populate partial results
        ts_end = _now()
        metadata_d['data_attempts'] = data_attempts
        metadata_d['data_duration'] = ts_end - ts_start
        metadata_d['data_start']    = ts_start
        metadata_d['data_end']      = ts_end
        metadata_d['data_laddr']    = data_laddr
        metadata_d['data_raddr']    = data_raddr
        metadata_d['duration']      = ts_end - ts_start

        # Evaluate data transfer
        if data_recv is None:
            sucess = False
            metadata_d['data_success'] = False
        else:
            sucess = True
            metadata_d['data_success'] = True

        add_result(task_type, sucess, metadata_d, ts_start, ts_end)


class SpoofDNSTraffic(_TestTraffic):
    ''' Use static classes just to access the specific method for the tests '''
    logger = logging.getLogger('SpoofDNSTraffic')

    @staticmethod
    def schedule_tasks(**kwargs):
        ''' Return a list of schedule tasks in dictionary format for later spawning '''
        global TS_ZERO
        global TASK_NUMBER

        # Use a list to store scheduled tasks parameters
        scheduled_tasks = []
        # Adjust next taskdelay time
        taskdelay = kwargs['ts_start']
        iterations = int(kwargs['load'] * kwargs['duration'])
        distribution = kwargs.setdefault('distribution', 'exp')
        for i in range(0, iterations):
            # Set starting time for task
            if distribution == 'exp':
                taskdelay += random.expovariate(kwargs['load'])
            elif distribution == 'uni':
                taskdelay += 1 / kwargs['load']

            TASK_NUMBER += 1
            task_nth = TASK_NUMBER
            task_type = kwargs['type']
            # Select parameters randomly
            dns_laddr, dns_raddr   = _get_service_tuple(kwargs['dns_laddr'],  kwargs['dns_raddr'])
            data_laddr, data_raddr = _get_service_tuple(kwargs['data_laddr'], kwargs['data_raddr'])
            # Pre-compute packet build to avoid lagging due to Scapy.
            ## Build query message
            interface = kwargs.get('interface', None)
            metadata = kwargs.get('metadata', {})
            edns_options = metadata.get('edns_options', None)
            ecs_srclen = metadata.get('edns_ecs_srclen', 24)
            query = _make_query(data_raddr[0], dns.rdatatype.A, dns.rdataclass.IN, 'udp', dns_laddr[0], ecs_srclen, edns_options)
            data_b = query.to_wire()
            eth_pkt = _scapy_build_packet(dns_laddr[0], dns_raddr[0], dns_raddr[2], dns_laddr[1], dns_raddr[1], data_b)
            ## Encode/decode to base64 for obtaning str representation / serializable
            eth_pkt_str = base64.b64encode(bytes(eth_pkt)).decode('utf-8')
            # Log task parameters
            task_str = 'SpoofDNS {}:{}/{} => {}:{}/{} // Data {}:{}/{} // via {}'.format(dns_laddr[0], dns_laddr[1], dns_laddr[2],
                                                                                         dns_raddr[0], dns_raddr[1], dns_raddr[2],
                                                                                         data_raddr[0], data_raddr[1], data_raddr[2],
                                                                                         interface)
            SpoofDNSTraffic.logger.info('[#{}] Scheduled task {} @ {:.4f} / {}'.format(task_nth, task_type, taskdelay - TS_ZERO, task_str))
            # Build dictionary with selected parameters for running the task
            args_d = {'task_nth': task_nth, 'task_type': task_type,
                      'dns_laddr': dns_laddr, 'dns_raddr': dns_raddr,
                      'data_laddr': data_laddr, 'data_raddr': data_raddr,
                      'eth_pkt': eth_pkt_str, 'interface': interface,
                      'metadata': metadata,
                      }
            # Append the newly defined task with its parameters
            scheduled_tasks.append({'offset': taskdelay - TS_ZERO, 'cls': task_type, 'kwargs': args_d})

        # Return list of scheduled tasks for later spawning
        return scheduled_tasks

    async def run(**kwargs):
        global TS_ZERO
        # Get parameters
        task_nth        = kwargs['task_nth']
        task_type       = kwargs['task_type']
        dns_laddr       = kwargs['dns_laddr']
        dns_raddr       = kwargs['dns_raddr']
        data_laddr      = kwargs['data_laddr']
        data_raddr      = kwargs['data_raddr']
        eth_pkt         = kwargs['eth_pkt']
        interface       = kwargs['interface']

        SpoofDNSTraffic.logger.info('[{:.4f}] Running task #{}'.format(_now(TS_ZERO), task_nth))
        ts_start = _now()
        metadata_d = {}
        # Unpack DNS related data
        dns_ripaddr, dns_rport, dns_rproto = dns_raddr
        dns_lipaddr, dns_lport, dns_lproto = dns_laddr
        # Unpack Data related data
        data_fqdn, data_rport, data_rproto = data_raddr
        # Send the packet
        ## decode from base64 to obtain bytes representation
        success = _scapy_send_packet(base64.b64decode(eth_pkt), interface)
        # Populate partial results
        ts_end = _now()
        metadata_d['dns_duration'] = ts_end - ts_start
        metadata_d['dns_start']    = ts_start
        metadata_d['dns_end']      = ts_end
        metadata_d['dns_laddr'] = dns_laddr
        metadata_d['dns_raddr'] = dns_raddr
        metadata_d['dns_fqdn'] = data_fqdn
        # Add results
        add_result(task_type, success, metadata_d, ts_start, ts_end)


class SpoofDataTraffic(_TestTraffic):
    ''' Use static classes just to access the specific method for the tests '''
    logger = logging.getLogger('SpoofDataTraffic')

    @staticmethod
    def schedule_tasks(**kwargs):
        ''' Return a list of schedule tasks in dictionary format for later spawning '''
        global TS_ZERO
        global TASK_NUMBER

        # Use a list to store scheduled tasks parameters
        scheduled_tasks = []
        # Adjust next taskdelay time
        taskdelay = kwargs['ts_start']
        iterations = int(kwargs['load'] * kwargs['duration'])
        distribution = kwargs.setdefault('distribution', 'exp')
        for i in range(0, iterations):
            # Set starting time for task
            if distribution == 'exp':
                taskdelay += random.expovariate(kwargs['load'])
            elif distribution == 'uni':
                taskdelay += 1 / kwargs['load']

            TASK_NUMBER += 1
            task_nth = TASK_NUMBER
            task_type = kwargs['type']
            # Select parameters randomly
            data_laddr, data_raddr = _get_service_tuple(kwargs['data_laddr'], kwargs['data_raddr'])
            # Pre-compute packet build to avoid lagging due to Scapy
            interface = kwargs.get('interface', None)
            data_b = '{}@{}'.format(data_raddr[0], data_raddr[0]).encode()
            eth_pkt = _scapy_build_packet(data_laddr[0], data_raddr[0], data_raddr[2], data_laddr[1], data_raddr[1], data_b)
            ## Encode/decode to base64 for obtaning str representation / serializable
            eth_pkt_str = base64.b64encode(bytes(eth_pkt)).decode('utf-8')
            # Log task parameters
            task_str = 'SpoofData {}:{}/{} => {}:{}/{} // via {}'.format(data_laddr[0], data_laddr[1], data_laddr[2],
                                                                         data_raddr[0], data_raddr[1], data_raddr[2],
                                                                         interface)
            SpoofDataTraffic.logger.info('[#{}] Scheduled task {} @ {:.4f} / {}'.format(task_nth, task_type, taskdelay - TS_ZERO, task_str))
            # Build dictionary with selected parameters for running the task
            args_d = {'task_nth': task_nth, 'task_type': task_type,
                      'data_laddr': data_laddr, 'data_raddr': data_raddr,
                      'eth_pkt': eth_pkt_str, 'interface': interface,
                      }
            # Append the newly defined task with its parameters
            scheduled_tasks.append({'offset': taskdelay - TS_ZERO, 'cls': task_type, 'kwargs': args_d})

        # Return list of scheduled tasks for later spawning
        return scheduled_tasks

    async def run(**kwargs):
        global TS_ZERO
        # Get parameters
        task_nth        = kwargs['task_nth']
        task_type       = kwargs['task_type']
        data_laddr      = kwargs['data_laddr']
        data_raddr      = kwargs['data_raddr']
        eth_pkt         = kwargs['eth_pkt']
        interface       = kwargs['interface']

        SpoofDataTraffic.logger.info('[{:.4f}] Running task #{}'.format(_now(TS_ZERO), task_nth))
        ts_start = _now()
        metadata_d = {}
        # Unpack Data related data
        data_ripaddr, data_rport, data_rproto = data_raddr
        data_lipaddr, data_lport, data_lproto = data_laddr
        # Send the packet
        ## decode from base64 to obtain bytes representation
        success = _scapy_send_packet(base64.b64decode(eth_pkt), interface)
        # Populate partial results
        ts_end = _now()
        metadata_d['data_duration'] = ts_end - ts_start
        metadata_d['data_start']    = ts_start
        metadata_d['data_end']      = ts_end
        metadata_d['data_laddr'] = data_laddr
        metadata_d['data_raddr'] = data_raddr
        # Add results
        add_result(task_type, success, metadata_d, ts_start, ts_end)



class MainTestClient(object):
    def __init__(self, args):
        self.logger = logging.getLogger('MainTestClient')
        self.args = args

        # Create list to store the schedule tasks
        self.scheduled_tasks = []

        # Iterate configuration file(s) and add to scheduled tasks
        for filename in self.args.config:
            # Read YAML configuration file
            with open(filename, 'r') as infile:
                config_d = yaml.load(infile)
            # Return a list of tasks with scheduled test instances
            task_list = self._create_schedule_session(config_d)
            self.logger.warning('Scheduled {} task(s) from config file {}'.format(len(task_list), filename))
            self.scheduled_tasks += task_list

        # Iterate session file(s) and add to scheduled tasks
        for filename in self.args.session:
            # Read JSON session schedule
            with open(filename, 'r') as infile:
                task_list = json.load(infile)
            self.logger.warning('Scheduled {} task(s) from session file {}'.format(len(task_list), filename))
            self.scheduled_tasks += task_list

        self.logger.warning('Processing {} task(s) in total!'.format(len(self.scheduled_tasks)))

        # Dump session tasks to json
        self._dump_session_to_json(self.scheduled_tasks)

        if self.args.dry_run:
            self.logger.warning('Executing in dry-run mode!')
            return

        # Continue with ready session
        # Spawn test session
        self._spawn_test_session(self.scheduled_tasks)


    def _create_schedule_session(self, config_d):
        ''' Take config_d configuration as read from YAML. Populates self.scheduled_tasks list in the compatible format for later spawn. '''
        global TS_ZERO
        duration = config_d['duration']
        ts_backoff = config_d['backoff']
        ts_start = _now() + ts_backoff
        task_list = []

        self.logger.warning('({:.3f}) Starting task generation!'.format(_now(TS_ZERO)))
        self.logger.warning('({:.3f}) Scheduling first task @{}!'.format(_now(TS_ZERO), ts_backoff))

        # Define test test specific parameters
        type2config = {'dnsdata':   RealDNSDataTraffic,
                       'dns':       RealDNSTraffic,
                       'data':      RealDataTraffic,
                       'dnsspoof':  SpoofDNSTraffic,
                       'dataspoof': SpoofDataTraffic,
                       }

        for item_d in config_d['traffic']:
            # Get global parameters for given traffic type
            traffic_type = item_d['type']
            global_traffic_d = config_d.get('global_traffic', {})
            global_item_d    = global_traffic_d.get(traffic_type, {})
            # Set global parameters if not defined in test
            for k, v in global_item_d.items():
                item_d.setdefault(k, v)

            # Set specific parameters if not defined in the test
            item_d['ts_start'] = ts_start + item_d.setdefault('ts_start', 0)
            item_d.setdefault('duration', duration)

            # Get class and config parameters
            cls = type2config[traffic_type]

            # Append scheduled tasks to local list
            task_list += cls.schedule_tasks(**item_d)

        # Normalize task offset according to test duration
        self._normalize_tasklist(task_list, duration + ts_backoff)

        self.logger.warning('({:.3f}) Terminated generation of {} tasks'.format(_now(TS_ZERO), len(task_list)))
        return task_list

    def _normalize_tasklist(self, tasks, duration):
        """ Normalize scheduled task list up to duration """
        # Define lambda functions
        sort_key = lambda x:x['offset']
        norm_01  = lambda _data,_min,_range: (_data - _min) / _range
        norm_xy  = lambda _data,_min,_max:   (_data * (_max - _min)) + _min

        # Normalize values to [0 ,1]
        _min = sort_key(min(tasks, key=sort_key))
        _max = sort_key(max(tasks, key=sort_key))
        _range = _max - _min;

        if _range == 0:
            self.logger.warning('Skipping normalization of interval with range 0')
            return

        for t in tasks:
            offset = t['offset']
            offset_01 = norm_01(offset, _min, _range)
            offset_xy = norm_xy(offset_01, _min, duration)
            t['offset'] = offset_xy

        self.logger.warning('Normalized scheduled events to test duration. Corrected from {:.3f} to {:.3f} ({:.3f}%)'.format(_max, duration, (duration/_max*100)-100))

    def _spawn_test_session(self, tasks):
        # TODO: Use parameters defined in globals as base, then overwrite with test specific?
        global TS_ZERO
        ts_start = _now()

        # Define test test specific parameters
        type2cls = {'dnsdata':   RealDNSDataTraffic,
                    'dns':       RealDNSTraffic,
                    'data':      RealDataTraffic,
                    'dnsspoof':  SpoofDNSTraffic,
                    'dataspoof': SpoofDataTraffic,
                    }

        for entry in tasks:
            # Obtain parameters from entry
            offset = entry['offset']
            cls    = type2cls[entry['cls']]
            kwargs = entry['kwargs']
            taskdelay = TS_ZERO + offset
            cb = functools.partial(asyncio.ensure_future, cls.run(**kwargs))
            loop.call_at(taskdelay, cb)

    async def monitor_pending_tasks(self, watchdog = WATCHDOG):
        # Monitor number of remaining tasks and exit when done
        i = 0
        global TS_ZERO
        while len(loop._scheduled):
            i += 1 # Counter of iterations
            self.logger.warning('({:.3f}) [{}] Pending tasks: {}'.format(_now(TS_ZERO), i, len(loop._scheduled)))
            await asyncio.sleep(watchdog)
        self.logger.warning('({:.3f}) [{}] All tasks completed!'.format(_now(TS_ZERO), i))
        return loop.time()

    def process_results(self):
        # Process results and show brief statistics
        self.logger.warning('Processing results')
        self._save_to_json()
        self._save_to_csv()
        self._save_to_csv_summarized()

    def _save_to_csv_summarized(self):
        # Save a CSV file
        global RESULTS

        # Classify indidivual results from RESULTS list into a dictionary indexed by type
        results_d = {}
        for result_d in RESULTS:
            data_l = results_d.setdefault(result_d['name'], [])
            data_l.append(result_d)

        # Create list of lines to save result statistics
        lines = []
        header_fmt = 'name,total,success,failure,dns_success,dns_failure,dns_1,dns_2,dns_3,dns_4,dns_5,data_success,data_failure,file'
        lines.append(header_fmt)

        for data_key, data_l in results_d.items():
            name = data_key
            total = len(data_l)
            success = len([1 for _ in data_l if _['success'] == True])
            failure = len([1 for _ in data_l if _['success'] == False])
            dns_success = len([1 for _ in data_l if _get_data_dict(_,['metadata','dns_success'],False) == True])
            dns_failure = len([1 for _ in data_l if _get_data_dict(_,['metadata','dns_success'],True) == False])
            data_success = len([1 for _ in data_l if _get_data_dict(_,['metadata','data_success'],False) == True])
            data_failure = len([1 for _ in data_l if _get_data_dict(_,['metadata','data_success'],True) == False])
            # Calculate DNS retransmission if DNS phase was successful
            dns_1 = len([1 for _ in data_l if _get_data_dict(_,['metadata','dns_success'],False) == True and _get_data_dict(_,['metadata','dns_attempts'],0) == 1])
            dns_2 = len([1 for _ in data_l if _get_data_dict(_,['metadata','dns_success'],False) == True and _get_data_dict(_,['metadata','dns_attempts'],0) == 2])
            dns_3 = len([1 for _ in data_l if _get_data_dict(_,['metadata','dns_success'],False) == True and _get_data_dict(_,['metadata','dns_attempts'],0) == 3])
            dns_4 = len([1 for _ in data_l if _get_data_dict(_,['metadata','dns_success'],False) == True and _get_data_dict(_,['metadata','dns_attempts'],0) == 4])
            dns_5 = len([1 for _ in data_l if _get_data_dict(_,['metadata','dns_success'],False) == True and _get_data_dict(_,['metadata','dns_attempts'],0) == 5])
            #
            filename = '{}.csv'.format(self.args.results)
            # Create comma separated line matching header_fmt
            line = '{},{},{},{},{},{},{},{},{},{},{},{},{},{}'.format(name,total,success,failure,
                                                                      dns_success,dns_failure,
                                                                      dns_1,dns_2,dns_3,dns_4,dns_5,
                                                                      data_success,data_failure,
                                                                      filename)
            lines.append(line)
            # Log via console
            self.logger.warning('{0: <10}\tsuccess={1}\tfailure={2}\tdns_success={3}\tdns_failure={4}\tdns_rtx={5}'.format(name, success, failure, dns_success, dns_failure, (dns_1,dns_2,dns_3,dns_4,dns_5)))
        # Add extra line for file merge
        lines.append('')
        # Save results to file in CSV
        if self.args.results:
            filename = self.args.results + '.summary.csv'
            self.logger.warning('Writing results to file <{}>'.format(filename))
            with open(filename, 'w') as outfile:
                outfile.writelines('\n'.join(lines))

    def _save_to_csv(self):
        # Save a CSV file
        global RESULTS

        # Create list of lines to save result statistics
        lines = []
        header_fmt = 'name,success,ts_start,ts_end,duration,dns_success,dns_attempts,dns_start,dns_end,dns_duration,data_success,data_attempts,data_start,data_end,data_duration'
        lines.append(header_fmt)

        for result_d in RESULTS:
            name          = result_d['name']
            success       = result_d['success']
            ts_start      = result_d['ts_start']
            ts_end        = result_d['ts_end']
            duration      = result_d['duration']
            metadata_d    = result_d.setdefault('metadata', {})
            dns_success   = metadata_d.get('dns_success', '')
            dns_attempts  = metadata_d.get('dns_attempts', '')
            dns_start     = metadata_d.get('dns_start', '')
            dns_end       = metadata_d.get('dns_end', '')
            dns_duration  = metadata_d.get('dns_duration', '')
            data_success  = metadata_d.get('data_success', '')
            data_attempts = metadata_d.get('data_attempts', '')
            data_start    = metadata_d.get('data_start', '')
            data_end      = metadata_d.get('data_end', '')
            data_duration = metadata_d.get('data_duration', '')
            line = '{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}'.format(
                     name,success,ts_start,ts_end,duration,
                     dns_success,dns_attempts,dns_start,dns_end,dns_duration,
                     data_success,data_attempts,data_start,data_end,data_duration)
            lines.append(line)
        # Add extra line for file merge
        lines.append('')
        # Save results to file in csv
        if self.args.results:
            filename = self.args.results + '.csv'
            self.logger.warning('Writing results to file <{}>'.format(filename))
            with open(filename, 'w') as outfile:
                outfile.writelines('\n'.join(lines))

    def _save_to_json(self):
        # Save results to file in json
        global RESULTS
        if self.args.results:
            filename = self.args.results + '.json'
            self.logger.warning('Writing results to file <{}>'.format(filename))
            with open(filename, 'w') as outfile:
                json.dump(RESULTS, outfile)

    def _dump_session_to_json(self, tasks):
        # Save scheduled session tasks to file in json
        if self.args.session_name:
            filename = self.args.session_name
            self.logger.warning('Writing session tasks to file <{}>'.format(filename))
            with open(filename, 'w') as outfile:
                json.dump(tasks, outfile)


def setup_logging_yaml(default_path='logging.yaml',
                       default_level=logging.INFO,
                       env_path='LOG_CFG',
                       env_level='LOG_LEVEL'):
    """Setup logging configuration"""
    path = os.getenv(env_path, default_path)
    level = os.getenv(env_level, default_level)
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        #logging.basicConfig(level=level)
        logging.basicConfig(level=level, format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")

def parse_arguments():
    parser = argparse.ArgumentParser(description='Realm Gateway Traffic Test Suite v0.1')
    parser.add_argument('--config', type=str, nargs='*', default=[],
                        help='Input configuration file(s) (yaml)')
    parser.add_argument('--session', type=str, nargs='*', default=[],
                        help='Input session file(s) (json)')
    parser.add_argument('--session-name', type=str,
                        help='Output session file (json)')
    parser.add_argument('--results', type=str,
                        help='Output results file (json)')
    parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                        help='Execute in dry run mode')
    args = parser.parse_args()
    # Validate args
    assert (args.config or args.session)
    return args


if __name__ == '__main__':
    # Use function to configure logging from file
    setup_logging_yaml()
    logger = logging.getLogger('')

    # Parse arguments
    args = parse_arguments()

    loop = asyncio.get_event_loop()
    #loop.set_debug(True)

    try:
        main = MainTestClient(args)
        loop.run_until_complete(main.monitor_pending_tasks())
    except KeyboardInterrupt:
        logger.warning('KeyboardInterrupt!')

    #logger.warning('All tasks completed!')
    loop.stop()
    main.process_results()

    print('MSG_SENT      {}'.format(MSG_SENT))
    print('MSG_RECV      {}'.format(MSG_RECV))
    print('LAST_UDP_PORT {}'.format(LAST_UDP_PORT))
    print('LAST_TCP_PORT {}'.format(LAST_TCP_PORT))
    sys.exit(0)



"""
File: example_traffic.yaml

# YAML configuration file for Realm Gateway Traffic Test Suite v0.2

# Total duration of the test (sec)
duration: 1

# Backoff time before scheduling tests (sec)
backoff: 3

# Global definitions for traffic tests, used if no test specific parameter is defined
global_traffic:
    dnsdata:
        dns_laddr: [["0.0.0.0", 0, 6], ["0.0.0.0", 0, 17]]
        dns_raddr: [["8.8.8.8", 53, 17], ["8.8.8.8", 53, 6], ["8.8.4.4", 53, 17], ["8.8.4.4", 53, 6]]
        data_laddr: [["0.0.0.0", 0, 6], ["0.0.0.0", 0, 17]]
        data_raddr: [["example.com", 80, 6], ["google-public-dns-a.google.com", 53, 17]]
        dns_timeouts: [1,5,5,5]
        data_timeouts: [1]
        # Traffic Control parameters / network delay (sec) via tc and netem
        ## Random delay following uniform distribution [a,b]
        dns_delay: [0.250, 0.250]
        data_delay: [0.200, 0.200]
    dns:
        dns_laddr: [["0.0.0.0", 0, 6], ["0.0.0.0", 0, 17]]
        dns_raddr: [["8.8.8.8", 53, 17], ["8.8.8.8", 53, 6], ["8.8.4.4", 53, 17], ["8.8.4.4", 53, 6]]
        data_raddr: [["example.com", 0, 0], ["google-public-dns-a.google.com", 0, 0]]
        dns_timeouts: [1,5,5,5]
        # Traffic Control parameters / network delay (sec) via tc and netem
        ## Random delay following uniform distribution [a,b]
        dns_delay: [0.250, 0.250]
    data:
        data_laddr: [["0.0.0.0", 0, 6], ["0.0.0.0", 0, 17]]
        data_raddr: [["93.184.216.34", 80, 6], ["8.8.8.8", 53, 17]]
        data_timeouts: [1]
        # Traffic Control parameters / network delay (sec) via tc and netem
        ## Random delay following uniform distribution [a,b]
        data_delay: [0.200, 0.200]
    dnsspoof:
        dns_laddr: [["1.1.1.1", 2000, 17], ["2.2.2.2", 2000, 17]]
        dns_raddr: [["8.8.8.8", 53, 17], ["8.8.4.4", 53, 17], ["195.148.125.201", 53, 17], ["100.64.1.130", 53, 17]]
        data_raddr: [["dnsspoof.example.com", 0, 0], ["dnsspoof.google.es", 0, 0]]
        interface: "wan0"
    dataspoof:
        data_laddr: [["1.1.1.1", 3000, 17], ["1.1.1.1", 0, 6]]
        data_raddr: [["8.8.8.8", 0, 17], ["8.8.8.8", 0, 6], ["195.148.125.201", 0, 17], ["195.148.125.201", 0, 6], ["100.64.1.130", 0, 17], ["100.64.1.130", 0, 6]]
        interface: "wan0"

# This models all the test traffic
traffic:
    # Example of tests with global_traffic parameters
    - {type: "dnsdata",   load: 2}
    - {type: "dns",       load: 2, distribution: "exp", metadata: {edns_options: ["ecs"], edns_ecs_srclen: 32}}}
    - {type: "data",      load: 2, distribution: "uni"}
    - {type: "dataspoof", load: 2, interface: "ens18"}
    - {type: "dnsspoof",  load: 2, interface: "ens18"}

    ## Example of tests with specific values
    ## dnsdata: Specific duration and starting time
    - {type: "dnsdata",   load: 2, ts_start: 10, duration: 10}
"""
