#!/usr/bin/env python3

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

#1. Legitimate DNS+data clients
We distinguish 2 phases:
a. DNS resolution: Resolve an FQDN issuing an A query request to a DNS server.
b. Data transfer: Begin an echo client instance (TCP/UDP) to the given IP address and port.


#2. Legitimate DNS clients
a. DNS resolution: Resolve an FQDN issuing an A query request to a DNS server.


#3. Legitimate data clients
b. Data transfer: Begin an echo client instance (TCP/UDP) to the given IP address and port.


#4. Spoofed DNS clients
c. Spoofed DNS resolution: Resolve an FQDN issuing an A query request to a DNS server impersonating another host/server.
This is a special case because impersonating a DNS resolver we could try to fake DNS options to also affect reputation of a host.

#5. Spoofed data clients
d. Spoofed data transfer: Send TCP SYN or UDP messages as an echo client instance to the given IP address and port.



How do we mix all of this in the same program?
We define the requirements for actions {a,b,c,d} separately.

#a. DNS resolution
 - FQDN
 - Query type fixed to A and recursive enabled
 - Source socket address
 - Remote socket address
 - Retransmission scheme

#b. Data transfer
 - Source socket address
 - Remote socket address
 - Protocol
 - Retransmission scheme

#c. Spoofed DNS resolution
 - FQDN
 - Query type fixed to A and recursive enabled
 - EDNS0 options?
 - Source socket address
 - Remote socket address
 - Retransmission scheme
 - Implementation details:
    + Use the same code as "a. DNS resolution" from a *fake* IP source
    + Measure success/failure based on A record type found in response

#d. Spoofed data transfer
 - Source socket address
 - Remote socket address
 - Protocol
 - Implementation details:
    + Use the same code as "b. Data transfer" from a *fake* IP source
    + TCP: Measure success/failure based on TCP SYN.ACK TCP opt parameters (or TCP RST) (scapy?)
    + UDP: Measure success/failure based on any response



There seems to be a rather common amount of data required for all phases.

Modelling FQDN:
 - A tuple consisting on ((s)fqdn, port, protocol)
 - Read from a file and build pool?

Modelling DNS resolvers for #1 and #2:
 - A tuple consisting on (ip, port, protocol)
 - Read from a file and build pool?

Modelling spoofed sources for DNS/data:
 - A tuple consisting on (ip, port, protocol)
 - Read from a file and build pool?

Modelling spoofed destinations for DNS:
 - A tuple consisting on (ip, port, protocol)
 - Read from a file and build pool?

Modelling spoofed destinations for data:
 - A tuple consisting on (ip, port, protocol)
 - Read from a file and build pool?


# Modelling configuration file
    config_d = {
     'duration': 1,
     # Globals for traffic tests
     'global_traffic': {
        'dnsdata': {
            'dns_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'dns_raddr': [('1.2.3.4', 53, 17), ('8.8.8.8', 53, 17), ('8.8.4.4', 53, 17), ('8.8.8.8', 53, 6), ('8.8.4.4', 53, 6)],
            'data_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'data_raddr': [('example.com', 2000, 17), ('google.es', 2000, 6)],
        },
        'dns': {
            'dns_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'dns_raddr': [('1.2.3.4', 53, 17), ('8.8.8.8', 53, 17), ('8.8.4.4', 53, 17), ('8.8.8.8', 53, 6), ('8.8.4.4', 53, 6)],
            'data_raddr': [('dnsonly.example.com', 2000, 17), ('dnsonly.google.es', 2000, 6)],
        },
        'data': {
            'data_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'data_raddr': [('1.2.3.4', 2000, 17), ('8.8.8.8', 2000, 6)],
        },
        'dnsspoof': {
            'dns_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'dns_raddr': [('1.2.3.4', 53, 17), ('8.8.8.8', 53, 17), ('8.8.4.4', 53, 17), ('8.8.8.8', 53, 6), ('8.8.4.4', 53, 6)],
            'data_raddr': [('dnsspoof.example.com', 2000, 17), ('dnsspoof.google.es', 2000, 6)],
        },
        'dataspoof': {
            'data_laddr': [('1.1.1.1', 2000, 17), ('2.2.2.2', 2000, 6)],
            'data_raddr': [('1.2.3.4', 2000, 17), ('8.8.8.8', 2000, 6)],
        },
     },
     # This models all the test traffic
     'traffic': [
                # dnsdata: TCP based data & UDP based resolution
                 {'type': 'dnsdata',  'load': 1, 'dns_laddr':[('0.0.0.0', 0, 17)], 'dns_raddr':[('8.8.8.8', 53, 17)], 'data_laddr': [('0.0.0.0', 0, 6)],  'data_raddr': [('google.es', 2000, 6)]},
                # dnsdata: UDP based data & UDP based resolution
                # {'type': 'dnsdata',  'load': 1, 'dns_laddr':[('0.0.0.0', 0, 17)], 'dns_raddr':[('8.8.8.8', 53, 17)], 'data_laddr': [('0.0.0.0', 0, 17)], 'data_raddr': [('udp2001.host.demo', 2001, 17)]},

                # dns: UDP based resolution
                # {'type': 'dns',      'load': 1, 'dns_laddr':[('0.0.0.0', 0, 17)], 'dns_raddr':[('8.8.8.8', 53, 17)], 'data_raddr': [('udp2002.host.demo', 2002, 17)]},

                # data: TCP based data
                # {'type': 'data',     'load': 1,                                                                      'data_laddr': [('0.0.0.0', 0, 6)],  'data_raddr': [('195.148.125.202', 3000, 6)]},
                # data: UDP based data
                # {'type': 'data',     'load': 1,                                                                      'data_laddr': [('0.0.0.0', 0, 17)], 'data_raddr': [('195.148.125.202', 3001, 17)]},

                # dnsspoof: UDP based resolution only
                # {'type': 'dnsspoof', 'load': 1, 'dns_laddr':[('198.18.0.1', 0, 17)], 'dns_raddr':[('195.148.125.201', 53, 17)], 'data_raddr': [('udp5002.host.demo', 5002, 17)]},

                # dataspoof: UDP based data
                # {'type': 'dataspoof', 'load': 1,                                                                     'data_laddr': [('1.1.1.1', 65535, 6)],  'data_raddr': [('9.9.9.9', 65535, 6)]},
                # {'type': 'dataspoof', 'load': 1,                                                                     'data_laddr': [('2.2.2.2', 65535, 17)], 'data_raddr': [('9.9.9.9', 65535, 17)]},

                ## Test for global_traffic
                # {'type': 'dnsdata',   'load': 1},
                # {'type': 'dns',       'load': 1},
                # {'type': 'data',      'load': 1},
                # {'type': 'dataspoof', 'load': 1},
                # {'type': 'dnsspoof',  'load': 1},
                 ]
     }

Run as:   ./async_echoclient_v4.py --duration 3 --load 300 --distribution const --dnstimeout 1 1 1 --datatimeout 1 --fqdn localhost.demo:12345 --dnsaddr 127.0.0.1 --dnsport 54
Requires: ./async_echoserver_v3.py -b 127.0.0.1:12345

Run as: ./async_echoclient_v4.py --duration 3 --load 300 --distribution const --dnstimeout 1 1 1 --datatimeout 1 --dnsaddr 127.0.0.1 --dnsport 54 --fqdn localhost.demo:2000 --sfqdn udp2000.localhost.demo:2000 udp2001.localhost.demo:2001 udp2002.localhost.demo:2002 udp2003.localhost.demo:2003 udp2004.localhost.demo:2004 udp2005.localhost.demo:2005 udp2006.localhost.demo:2006 udp2007.localhost.demo:2007 udp2008.localhost.demo:2008 udp2009.localhost.demo:2009 --trafficshape 0
Requires: ./async_echoserver_v3.py -b 127.0.0.1:2000 127.0.0.1:2001 127.0.0.1:2002 127.0.0.1:2003 127.0.0.1:2004 127.0.0.1:2005 127.0.0.1:2006 127.0.0.1:2007 127.0.0.1:2008 127.0.0.1:2009
"""


import asyncio
import argparse
import functools
import json
import logging
import math
import os
import pprint
import random
import socket
import statistics
import struct
import sys
import time
import uuid

import dns
import dns.message
import dns.edns
import dns.rdatatype

# For Scapy
logging.getLogger('scapy.runtime').setLevel(logging.ERROR)
from scapy.all import *
from scapy.layers.inet import *
from scapy.layers.inet6 import *


WATCHDOG = 1.0 #Sleep 1 second before displaying loop stats
RESULTS = []   #List to store TestResult objects

def set_attributes(obj, override=False, **kwargs):
    """Set attributes in object from a dictionary"""
    for k,v in kwargs.items():
        if hasattr(obj, k) and not override:
            continue
        setattr(obj, k, v)

loop = asyncio.get_event_loop()
def _now(ref = 0):
    """ Return current time based on event loop """
    return loop.time() - ref

@asyncio.coroutine
def _timeit(coro, scale = 1):
    """ Execute a coroutine and return the time consumed in second scale """
    t0 = _now()
    r = yield from coro
    return (_now(t0)*scale, r)

@asyncio.coroutine
def _socket_connect(raddr, laddr, family=socket.AF_INET, type=socket.SOCK_DGRAM, reuseaddr=True, timeout=1):
    sock = socket.socket(family, type)
    if reuseaddr:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if not laddr:
        laddr=('0.0.0.0', 0)
    sock.bind(laddr)
    sock.setblocking(False)
    try:
        yield from asyncio.wait_for(loop.sock_connect(sock, raddr), timeout=timeout)
        return sock
    except:
        return None

@asyncio.coroutine
def _gethostbyname(fqdn, raddr, laddr, timeouts=[0], socktype='udp'):
    """
    fqdn: Domain name to be resolved
    raddr: Remote tuple information
    raddr: Local tuple information
    timeouts: List with retransmission timeout scheme
    """
    logger = logging.getLogger('gethostbyname')
    logger.debug('Resolving to {} with timeouts {}'.format(raddr, timeouts))
    rdtype = 1
    rdclass = 1
    ipaddr = None
    attempt = 0
    response = None

    # Build query message
    query = dns.message.make_query(fqdn, rdtype, rdclass)

    # Connect socket or fail early
    _socktype = socket.SOCK_STREAM if socktype == 'tcp' else socket.SOCK_DGRAM
    sock = yield from _socket_connect(raddr, laddr, family=socket.AF_INET, type=_socktype, reuseaddr=True, timeout=1)
    if sock is None:
        logger.debug('Socket failed to connect: {}:{} ({}) / {} ({})'.format(raddr[0], raddr[1], socktype, fqdn, dns.rdatatype.to_text(rdtype)))
        return (ipaddr, query.id, attempt)

    for tout in timeouts:
        attempt += 1
        try:
            if socktype == 'udp':
                _data = query.to_wire()
                yield from loop.sock_sendall(sock, _data)
                dataresponse = yield from asyncio.wait_for(loop.sock_recv(sock, 1024), timeout=tout)

            elif socktype == 'tcp':
                _data = query.to_wire()
                _data = struct.pack('!H', len(_data)) + _data
                yield from loop.sock_sendall(sock, _data)
                dataresponse = yield from asyncio.wait_for(loop.sock_recv(sock, 1024), timeout=tout)
                _len = struct.unpack('!H', dataresponse[:2])[0]
                dataresponse = dataresponse[2:2+_len]

            response = dns.message.from_wire(dataresponse)
            assert(response.id == query.id)
            # Parsing result
            rrset = response.find_rrset(response.answer, query.question[0].name, rdtype, rdclass)
            ipaddr = None
            for rdata in rrset:
                if rdtype == dns.rdatatype.A:
                    ipaddr = rdata.address
                    break
            if ipaddr:
                break
        except asyncio.TimeoutError:
            logger.info('#{} timeout expired ({:.4f} sec): {}:{} ({}) / {} ({})'.format(attempt, tout, raddr[0], raddr[1], socktype, fqdn, dns.rdatatype.to_text(rdtype)))
            continue
        except ConnectionRefusedError:
            logger.debug('Socket failed to connect: {}:{} ({}) / {} ({})'.format(raddr[0], raddr[1], socktype, fqdn, dns.rdatatype.to_text(rdtype)))
            break
        except AssertionError:
            logger.info('Wrong message id: {}!={} / {} ({})'.format(query.id, response.id, fqdn, dns.rdatatype.to_text(rdtype)))
            break
        except KeyError:
            logger.info('Resource records not found: {} ({})'.format(fqdn, dns.rdatatype.to_text(rdtype)))
            break
        except Exception as e:
            logger.warning('Exception {}: {}:{} ({}) / {} ({})'.format(e, raddr[0], raddr[1], socktype, fqdn, dns.rdatatype.to_text(rdtype)))
            break

    sock.close()
    return (ipaddr, query.id, attempt)

@asyncio.coroutine
def _sendrecv(data, raddr, laddr, timeouts=[0], socktype='udp'):
    """
    data: Data to send
    raddr: Remote tuple information
    laddr: Source tuple information
    timeouts: List with retransmission timeout scheme
    socktype: L4 protocol ['udp', 'tcp']
    """
    logger = logging.getLogger('sendrecv')
    logger.debug('Echoing to {}:{} ({}) with timeouts {}'.format(raddr[0], raddr[1], socktype, timeouts))
    recvdata = None
    attempt = 0

    # Connect socket or fail early
    _socktype = socket.SOCK_STREAM if socktype == 'tcp' else socket.SOCK_DGRAM
    sock = yield from _socket_connect(raddr, laddr, family=socket.AF_INET, type=_socktype, reuseaddr=True, timeout=1)
    if sock is None:
        logger.debug('Socket failed to connect: {}:{} ({})'.format(raddr[0], raddr[1], socktype))
        return (recvdata, attempt)

    for tout in timeouts:
        attempt += 1
        try:
            yield from loop.sock_sendall(sock, data)
            recvdata = yield from asyncio.wait_for(loop.sock_recv(sock, 1024), timeout=tout)
            break
        except asyncio.TimeoutError:
            logger.info('#{} timeout expired ({:.4f} sec): {}:{} ({})'.format(attempt, tout, raddr[0], raddr[1], socktype))
            continue
        except ConnectionRefusedError:
            logger.debug('Socket failed to connect: {}:{} ({}) / echoing {}'.format(raddr[0], raddr[1], socktype, data))
            break
        except Exception as e:
            logger.warning('Exception {}: {}:{} ({}) / echoing {}'.format(e, raddr[0], raddr[1], socktype, data))
            break

    sock.close()
    return (recvdata, attempt)


def _scapy_build_packet(src, dst, proto, sport, dport, payload=b''):
    if sport == 0:
        sport = random.randint(1,65535)
    if dport == 0:
        dport = random.randint(1,65535)
    if proto == 6:
        layer_4 = TCP(sport=sport, dport=dport)
    elif proto == 17:
        layer_4 = UDP(sport=sport, dport=dport)/Raw(payload)
    else:
        raise Exception('Protocol <{}> not supported'.format(proto))

    eth_pkt = Ether()/IP(src=src, dst=dst)/layer_4
    return eth_pkt

def _scapy_send_packet(packet, iface):
    sendp(packet, iface=iface, verbose=False)


def add_result(name, success, metadata, ts_start, ts_end):
    # Add a result dictionary entry
    global RESULTS
    RESULTS.append({'name':name, 'success':success, 'metadata': metadata, 'ts_start': ts_start, 'ts_end': ts_end})


class RealDNSDataTraffic(object):
    def __init__(self, **kwargs):
        '''
        # Common parameters
        duration: (int) test duration in seconds
        ts_start: (float) absolute starting time to schedule events
        results: (list) results list
        '''
        set_attributes(self, override=True, **kwargs)
        self.logger = logging.getLogger('RealDNSDataTraffic')

        # Adjust next taskdelay time
        taskdelay = self.ts_start
        iterations = int(self.load * self.duration)
        for i in range(0, iterations):
            # Set starting time for task
            taskdelay += random.expovariate(self.load)
            # Select parameters randomly
            _dns_laddr, _dns_raddr, = self._get_dns_parameters()
            _data_laddr, _data_raddr, = self._get_data_parameters()
            # Schedule task
            args = (_dns_laddr, _dns_raddr, _data_laddr, _data_raddr)
            cb = functools.partial(asyncio.ensure_future, self.run(*args))
            loop.call_at(taskdelay, cb)
            self.logger.info('Scheduled task / {} @ {} / {}'.format(self.type, taskdelay, args))

    def _get_dns_parameters(self):
        i = self.dns_raddr[random.randint(0, len(self.dns_raddr) - 1)]
        _pmatch = [_ for _ in self.dns_laddr if _[2]==i[2]]
        j = _pmatch[random.randint(0, len(_pmatch) - 1)]
        return (j, i)

    def _get_data_parameters(self):
        i = self.data_raddr[random.randint(0, len(self.data_raddr) - 1)]
        _pmatch = [_ for _ in self.data_laddr if _[2]==i[2]]
        j = _pmatch[random.randint(0, len(_pmatch) - 1)]
        return (j, i)

    @asyncio.coroutine
    def run(self, dns_laddr, dns_raddr, data_laddr, data_raddr):
        self.logger.info('[{}] Running task / {}'.format(_now(), (dns_laddr, dns_raddr, data_laddr, data_raddr)))
        ts_start = _now()
        metadata_d = {}

        # Unpack DNS related data
        dns_ripaddr, dns_rport, dns_rproto = dns_raddr
        dns_lipaddr, dns_lport, dns_lproto = dns_laddr
        # Select socket type based on protocol number
        dns_sockettype = 'tcp' if dns_rproto == 6 else 'udp'
        # DNS timeout template
        dns_timeouts = [5, 5, 5, 1]

        # Unpack Data related data
        data_fqdn,    data_rport, data_rproto = data_raddr
        data_lipaddr, data_lport, data_lproto = data_laddr
        # Select socket type based on protocol number
        data_sockettype = 'tcp' if data_rproto == 6 else 'udp'
        # DNS timeout template
        data_timeouts = [1]

        ## Run DNS resolution
        data_ripaddr, query_id, dns_attempt = yield from _gethostbyname(data_fqdn, (dns_ripaddr, dns_rport), (dns_lipaddr, dns_lport),
                                                                        timeouts=dns_timeouts, socktype=dns_sockettype)

        # Populate partial results
        ts_end = _now()
        metadata_d['dns_attempts'] = dns_attempt
        metadata_d['dns_duration'] = ts_end - ts_start
        metadata_d['dns_laddr'] = dns_laddr
        metadata_d['dns_raddr'] = dns_raddr
        metadata_d['dns_fqdn'] = data_fqdn

        # Evaluate DNS resolution
        if data_ripaddr is None:
            metadata_d['sucess'] = False
            metadata_d['dns_sucess'] = False
            metadata_d['duration'] = ts_end - ts_start
            add_result(self.type, False, metadata_d, ts_start, ts_end)
            return
        else:
            metadata_d['dns_sucess'] = True

        ## Run data transfer
        ts_start_data = _now()
        data_b = '{}@{}'.format(data_fqdn, data_ripaddr)
        data_recv, data_attempt = yield from _sendrecv(data_b.encode(), (data_ripaddr, data_rport), (data_lipaddr, data_lport),
                                                           timeouts=data_timeouts, socktype=data_sockettype)
        # Populate partial results
        ts_end = _now()
        metadata_d['data_attempts'] = data_attempt
        metadata_d['data_duration'] = ts_end - ts_start_data
        metadata_d['data_laddr'] = data_laddr
        metadata_d['data_raddr'] = (data_ripaddr, data_rport, data_rproto)
        metadata_d['duration'] = ts_end - ts_start

        # Evaluate data transfer
        if data_recv is None:
            metadata_d['sucess'] = False
            metadata_d['data_sucess'] = False
            add_result(self.type, False, metadata_d, ts_start, ts_end)
            return
        else:
            metadata_d['sucess'] = True
            metadata_d['data_sucess'] = True

        add_result(self.type, False, metadata_d, ts_start, ts_end)


class RealDNSTraffic(object):
    def __init__(self, **kwargs):
        '''
        # Common parameters
        duration: (int) test duration in seconds
        ts_start: (float) absolute starting time to schedule events
        results: (list) results list
        '''
        set_attributes(self, override=True, **kwargs)
        self.logger = logging.getLogger('RealDNSTraffic')

        # Adjust next taskdelay time
        taskdelay = self.ts_start
        iterations = int(self.load * self.duration)
        for i in range(0, iterations):
            # Set starting time for task
            taskdelay += random.expovariate(self.load)
            # Select parameters randomly
            _dns_laddr, _dns_raddr, = self._get_dns_parameters()
            _data_laddr, _data_raddr, = self._get_data_parameters()
            # Schedule task
            args = (_dns_laddr, _dns_raddr, _data_laddr, _data_raddr)
            cb = functools.partial(asyncio.ensure_future, self.run(*args))
            loop.call_at(taskdelay, cb)
            self.logger.info('Scheduled task / {} @ {} / {}'.format(self.type, taskdelay, args))

    def _get_dns_parameters(self):
        i = self.dns_raddr[random.randint(0, len(self.dns_raddr) - 1)]
        _pmatch = [_ for _ in self.dns_laddr if _[2]==i[2]]
        j = _pmatch[random.randint(0, len(_pmatch) - 1)]
        return (j, i)

    def _get_data_parameters(self):
        i = self.data_raddr[random.randint(0, len(self.data_raddr) - 1)]
        j = None
        return (j, i)

    @asyncio.coroutine
    def run(self, dns_laddr, dns_raddr, data_laddr, data_raddr):
        self.logger.info('[{}] Running task / {}'.format(_now(), (dns_laddr, dns_raddr, data_laddr, data_raddr)))
        ts_start = _now()
        metadata_d = {}

        # Unpack DNS related data
        dns_ripaddr, dns_rport, dns_rproto = dns_raddr
        dns_lipaddr, dns_lport, dns_lproto = dns_laddr
        # Select socket type based on protocol number
        dns_sockettype = 'tcp' if dns_rproto == 6 else 'udp'
        # DNS timeout template
        dns_timeouts = [5, 5, 5, 1]

        # Unpack Data related data
        data_fqdn, data_rport, data_rproto = data_raddr

        ## Run DNS resolution
        data_ripaddr, query_id, dns_attempt = yield from _gethostbyname(data_fqdn, (dns_ripaddr, dns_rport), (dns_lipaddr, dns_lport),
                                                                            timeouts=dns_timeouts, socktype=dns_sockettype)

        # Populate partial results
        ts_end = _now()
        metadata_d['dns_attempts'] = dns_attempt
        metadata_d['dns_duration'] = ts_end - ts_start
        metadata_d['dns_laddr'] = dns_laddr
        metadata_d['dns_raddr'] = dns_raddr
        metadata_d['dns_fqdn'] = data_fqdn
        metadata_d['duration'] = ts_end - ts_start
        metadata_d['data_raddr'] = (data_ripaddr, data_rport, data_rproto)

        # Evaluate DNS resolution
        if data_ripaddr is None:
            metadata_d['sucess'] = False
            metadata_d['dns_sucess'] = False
            add_result(self.type, False, metadata_d, ts_start, ts_end)
            return
        else:
            metadata_d['sucess'] = True
            metadata_d['dns_sucess'] = True

        add_result(self.type, False, metadata_d, ts_start, ts_end)


class RealDataTraffic(object):
    def __init__(self, **kwargs):
        '''
        # Common parameters
        duration: (int) test duration in seconds
        ts_start: (float) absolute starting time to schedule events
        results: (list) results list
        '''
        set_attributes(self, override=True, **kwargs)
        self.logger = logging.getLogger('RealDataTraffic')

        # Adjust next taskdelay time
        taskdelay = self.ts_start
        iterations = int(self.load * self.duration)
        for i in range(0, iterations):
            # Set starting time for task
            taskdelay += random.expovariate(self.load)
            # Select parameters randomly
            _data_laddr, _data_raddr, = self._get_data_parameters()
            # Schedule task
            args = (_data_laddr, _data_raddr)
            cb = functools.partial(asyncio.ensure_future, self.run(*args))
            loop.call_at(taskdelay, cb)
            self.logger.info('Scheduled task / {} @ {} / {}'.format(self.type, taskdelay, args))

    def _get_data_parameters(self):
        i = self.data_raddr[random.randint(0, len(self.data_raddr) - 1)]
        _pmatch = [_ for _ in self.data_laddr if _[2]==i[2]]
        j = _pmatch[random.randint(0, len(_pmatch) - 1)]
        return (j, i)

    @asyncio.coroutine
    def run(self, data_laddr, data_raddr):
        self.logger.info('[{}] Running task / {}'.format(_now(), (data_laddr, data_raddr)))
        ts_start = _now()
        metadata_d = {}

        # Unpack Data related data
        data_ripaddr, data_rport, data_rproto = data_raddr
        data_lipaddr, data_lport, data_lproto = data_laddr
        # Select socket type based on protocol number
        data_sockettype = 'tcp' if data_rproto == 6 else 'udp'
        # Data timeout template
        data_timeouts = [1]

        ## Run data transfer
        data_b = '{}@{}'.format(data_ripaddr, data_ripaddr)
        data_recv, data_attempt = yield from _sendrecv(data_b.encode(), (data_ripaddr, data_rport), (data_lipaddr, data_lport),
                                                           timeouts=data_timeouts, socktype=data_sockettype)
        # Populate partial results
        ts_end = _now()
        metadata_d['data_attempts'] = data_attempt
        metadata_d['data_duration'] = ts_end - ts_start
        metadata_d['data_laddr'] = data_laddr
        metadata_d['data_raddr'] = data_raddr
        metadata_d['duration'] = ts_end - ts_start

        # Evaluate data transfer
        if data_recv is None:
            metadata_d['sucess'] = False
            metadata_d['data_sucess'] = False
            add_result(self.type, False, metadata_d, ts_start, ts_end)
            return
        else:
            metadata_d['sucess'] = True
            metadata_d['data_sucess'] = True

        add_result(self.type, False, metadata_d, ts_start, ts_end)


class SpoofDNSTraffic(object):
    def __init__(self, **kwargs):
        '''
        # Common parameters
        duration: (int) test duration in seconds
        ts_start: (float) absolute starting time to schedule events
        results: (list) results list
        '''
        self.interface = None
        set_attributes(self, override=True, **kwargs)
        self.logger = logging.getLogger('SpoofDNSTraffic')

        # Adjust next taskdelay time
        taskdelay = self.ts_start
        iterations = int(self.load * self.duration)
        for i in range(0, iterations):
            # Set starting time for task
            taskdelay += random.expovariate(self.load)
            # Select parameters randomly
            _dns_laddr, _dns_raddr, = self._get_dns_parameters()
            _data_laddr, _data_raddr, = self._get_data_parameters()
            # Schedule task
            args = (_dns_laddr, _dns_raddr, _data_laddr, _data_raddr)
            cb = functools.partial(asyncio.ensure_future, self.run(*args))
            loop.call_at(taskdelay, cb)
            self.logger.info('Scheduled task / {} @ {} / {}'.format(self.type, taskdelay, args))

    def _get_dns_parameters(self):
        i = self.dns_raddr[random.randint(0, len(self.dns_raddr) - 1)]
        _pmatch = [_ for _ in self.dns_laddr if _[2]==i[2]]
        j = _pmatch[random.randint(0, len(_pmatch) - 1)]
        return (j, i)

    def _get_data_parameters(self):
        i = self.data_raddr[random.randint(0, len(self.data_raddr) - 1)]
        j = None
        return (j, i)

    @asyncio.coroutine
    def run(self, dns_raddr, dns_laddr, data_laddr, data_raddr):
        self.logger.info('[{}] Running task / {}'.format(_now(), (data_laddr, data_raddr)))
        ts_start = _now()
        metadata_d = {}

        # Unpack DNS related data
        dns_ripaddr, dns_rport, dns_rproto = dns_raddr
        dns_lipaddr, dns_lport, dns_lproto = dns_laddr
        # Unpack Data related data
        data_fqdn, data_rport, data_rproto = data_raddr
        # Data timeout template
        data_timeouts = [1]

        # Build query message
        query = dns.message.make_query(data_fqdn, 1, 1)
        data_b = query.to_wire()

        # Use Scapy to build and send a packet
        eth_pkt = _scapy_build_packet(dns_lipaddr, dns_ripaddr, dns_rproto, dns_lport, dns_rport, data_b)
        _scapy_send_packet(eth_pkt, self.interface)

        # Populate partial results
        ts_end = _now()
        metadata_d['dns_laddr'] = dns_laddr
        metadata_d['dns_raddr'] = dns_raddr
        metadata_d['dns_fqdn'] = data_fqdn

        # Add results
        add_result(self.type, True, metadata_d, ts_start, ts_end)


class SpoofDataTraffic(object):
    def __init__(self, **kwargs):
        '''
        # Common parameters
        duration: (int) test duration in seconds
        ts_start: (float) absolute starting time to schedule events
        results: (list) results list
        '''
        self.interface = None
        set_attributes(self, override=True, **kwargs)
        self.logger = logging.getLogger('SpoofDataTraffic')

        # Adjust next taskdelay time
        taskdelay = self.ts_start
        iterations = int(self.load * self.duration)
        for i in range(0, iterations):
            # Set starting time for task
            taskdelay += random.expovariate(self.load)
            # Select parameters randomly
            _data_laddr, _data_raddr, = self._get_data_parameters()
            # Schedule task
            args = (_data_laddr, _data_raddr)
            cb = functools.partial(asyncio.ensure_future, self.run(*args))
            loop.call_at(taskdelay, cb)
            self.logger.info('Scheduled task / {} @ {} / {}'.format(self.type, taskdelay, args))

    def _get_data_parameters(self):
        i = self.data_raddr[random.randint(0, len(self.data_raddr) - 1)]
        _pmatch = [_ for _ in self.data_laddr if _[2]==i[2]]
        j = _pmatch[random.randint(0, len(_pmatch) - 1)]
        return (j, i)

    @asyncio.coroutine
    def run(self, data_laddr, data_raddr):
        self.logger.info('[{}] Running task / {}'.format(_now(), (data_laddr, data_raddr)))
        ts_start = _now()
        metadata_d = {}

        # Unpack Data related data
        data_ripaddr, data_rport, data_rproto = data_raddr
        data_lipaddr, data_lport, data_lproto = data_laddr
        # Data timeout template
        data_timeouts = [1]

        # Use Scapy to build and send a packet
        data_b = '{}@{}'.format(data_ripaddr, data_ripaddr).encode()
        eth_pkt = _scapy_build_packet(data_lipaddr, data_ripaddr, data_rproto, data_lport, data_rproto, data_b)
        _scapy_send_packet(eth_pkt, self.interface)

        # Populate partial results
        ts_end = _now()
        metadata_d['data_laddr'] = data_laddr
        metadata_d['data_raddr'] = data_raddr

        # Add results
        add_result(self.type, True, metadata_d, ts_start, ts_end)



class MainTestClient(object):
    def __init__(self, config_d):
        self.logger = logging.getLogger('MainTestClient')

        # Main dictionary to store results
        duration = config_d['duration']
        ts_backoff = 3
        ts_start = _now() + ts_backoff

        type2config = {'dnsdata':   (RealDNSDataTraffic, ['dns_laddr', 'dns_raddr', 'data_laddr', 'data_raddr']),
                       'dns':       (RealDNSTraffic,     ['dns_laddr', 'dns_raddr', 'data_raddr']),
                       'data':      (RealDataTraffic,    ['data_laddr', 'data_raddr']),
                       'dnsspoof':  (SpoofDNSTraffic,    ['dns_laddr', 'dns_raddr', 'data_raddr']),
                       'dataspoof': (SpoofDataTraffic,   ['data_laddr', 'data_raddr']),
                       }

        def _get_global_traffic_param(config_d, traffic_type, parameter):
            try:
                return config_d['global_traffic'][traffic_type][parameter]
            except KeyError:
                return []

        for item_d in config_d['traffic']:
            # Get class and config parameters
            cls, parameters = type2config[item_d['type']]

            # Add globals to parameter dictionary
            item_d.setdefault('duration', duration)
            item_d.setdefault('ts_start', ts_start)

            for p in parameters:
                # Use global settings if test-specific are not enabled
                global_param_d = _get_global_traffic_param(config_d, item_d['type'], p)
                item_d.setdefault(p, global_param_d)

            # Create object
            obj = cls(**item_d)


    @asyncio.coroutine
    def monitor_pending_tasks(self, watchdog = WATCHDOG):
        # Monitor number of remaining tasks and exit when done
        i = 0
        t0 = loop.time()
        while len(loop._scheduled):
            i += 1 # Counter of iterations
            self.logger.warning('({:.3f}) [{}] Pending tasks: {}'.format(_now(t0), i, len(loop._scheduled)))
            yield from asyncio.sleep(watchdog)
        self.logger.warning('({:.3f}) [{}] All tasks completed!'.format(_now(t0), i))
        return loop.time()

    def process_results(self):
        # Process results and show brief statistics
        global RESULTS
        results_d = {}
        for result_obj in RESULTS:
            data_l = results_d.setdefault(result_obj['name'], [])
            data_l.append(result_obj)

        for data_key, data_l in results_d.items():
            nof_ok  = len([1 for _ in data_l if _['success'] is True])
            nof_nok = len([0 for _ in data_l if _['success'] is False])
            self.logger.info('{} ok={} nok={}'.format(data_key, nof_ok, nof_nok))

        pprint.pprint(RESULTS)


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
        logging.basicConfig(level=level)


if __name__ == '__main__':
    # Use function to configure logging from file
    setup_logging_yaml()

    loop = asyncio.get_event_loop()
    #loop.set_debug(True)

    logger = logging.getLogger('')

    config_d = {
     'duration': 1,
     # Globals for traffic tests
     'global_traffic': {
        'dnsdata': {
            'dns_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'dns_raddr': [('1.2.3.4', 53, 17), ('8.8.8.8', 53, 17), ('8.8.4.4', 53, 17), ('8.8.8.8', 53, 6), ('8.8.4.4', 53, 6)],
            'data_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'data_raddr': [('example.com', 2000, 17), ('google.es', 2000, 6)],
        },
        'dns': {
            'dns_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'dns_raddr': [('1.2.3.4', 53, 17), ('8.8.8.8', 53, 17), ('8.8.4.4', 53, 17), ('8.8.8.8', 53, 6), ('8.8.4.4', 53, 6)],
            'data_raddr': [('dnsonly.example.com', 0, 0), ('dnsonly.google.es', 0, 0)],
        },
        'data': {
            'data_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'data_raddr': [('1.2.3.4', 2000, 17), ('8.8.8.8', 2000, 6)],
        },
        'dnsspoof': {
            'dns_laddr': [('0.0.0.0', 0, 6), ('0.0.0.0', 0, 17)],
            'dns_raddr': [('1.2.3.4', 53, 17), ('8.8.8.8', 53, 17), ('8.8.4.4', 53, 17), ('8.8.8.8', 53, 6), ('8.8.4.4', 53, 6)],
            'data_raddr': [('dnsspoof.example.com', 0, 0), ('dnsspoof.google.es', 0, 0)],
        },
        'dataspoof': {
            'data_laddr': [('1.1.1.1', 2000, 17), ('2.2.2.2', 2000, 6)],
            'data_raddr': [('1.2.3.4', 2000, 17), ('8.8.8.8', 2000, 6)],
        },
     },
     # This models all the test traffic
     'traffic': [
                # dnsdata: TCP based data & UDP based resolution
                 {'type': 'dnsdata',  'load': 1, 'dns_laddr':[('0.0.0.0', 0, 17)], 'dns_raddr':[('8.8.8.8', 53, 17)], 'data_laddr': [('0.0.0.0', 0, 6)],  'data_raddr': [('google.es', 2000, 6)]},
                # dnsdata: UDP based data & UDP based resolution
                # {'type': 'dnsdata',  'load': 1, 'dns_laddr':[('0.0.0.0', 0, 17)], 'dns_raddr':[('8.8.8.8', 53, 17)], 'data_laddr': [('0.0.0.0', 0, 17)], 'data_raddr': [('udp2001.host.demo', 2001, 17)]},

                # dns: UDP based resolution
                # {'type': 'dns',      'load': 1, 'dns_laddr':[('0.0.0.0', 0, 17)], 'dns_raddr':[('8.8.8.8', 53, 17)], 'data_raddr': [('udp2002.host.demo', 2002, 17)]},

                # data: TCP based data
                # {'type': 'data',     'load': 1,                                                                      'data_laddr': [('0.0.0.0', 0, 6)],  'data_raddr': [('195.148.125.202', 3000, 6)]},
                # data: UDP based data
                # {'type': 'data',     'load': 1,                                                                      'data_laddr': [('0.0.0.0', 0, 17)], 'data_raddr': [('195.148.125.202', 3001, 17)]},

                # dnsspoof: UDP based resolution only
                # {'type': 'dnsspoof', 'load': 1, 'dns_laddr':[('198.18.0.1', 0, 17)], 'dns_raddr':[('195.148.125.201', 53, 17)], 'data_raddr': [('udp5002.host.demo', 5002, 17)]},

                # dataspoof: UDP based data
                # {'type': 'dataspoof', 'load': 1,                                                                     'data_laddr': [('1.1.1.1', 65535, 6)],  'data_raddr': [('9.9.9.9', 65535, 6)]},
                # {'type': 'dataspoof', 'load': 1,                                                                     'data_laddr': [('2.2.2.2', 65535, 17)], 'data_raddr': [('9.9.9.9', 65535, 17)]},

                # Test for global_traffic
                 {'type': 'dnsdata',   'load': 1},
                 {'type': 'dns',       'load': 1},
                 {'type': 'data',      'load': 1},
                 {'type': 'dataspoof', 'load': 1},
                 {'type': 'dnsspoof',  'load': 1},
                 ]
     }

    try:
        main = MainTestClient(config_d)
        loop.run_until_complete(main.monitor_pending_tasks())
    except KeyboardInterrupt:
        logger.warning('KeyboardInterrupt!')

    #logger.warning('All tasks completed!')
    loop.stop()
    logger.warning('Processing results...')
    main.process_results()
    sys.exit(0)
