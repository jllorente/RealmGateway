import asyncio
import logging
import random
import pprint
from functools import partial
from operator import getitem

from aalto_helpers import utils3
from aalto_helpers import network_helper3

import customdns
from customdns import dnsutils
from customdns.dnsresolver import DNSResolver, uDNSResolver

import dns
import dns.message
import dns.zone
import dns.rcode

from dns.exception import DNSException
from dns.rdataclass import *
from dns.rdatatype import *

import host
from host import HostEntry

import connection
from connection import ConnectionLegacy

from loglevel import LOGLEVEL_DNSCALLBACK, LOGLEVEL_PACKETCALLBACK

# For debugging
import time

class DNSCallbacks(object):
    def __init__(self, **kwargs):
        self._logger = logging.getLogger('DNSCallbacks')
        self._logger.setLevel(LOGLEVEL_DNSCALLBACK)
        self._dns_timeout = {None:[0]} # Default single blocking query
        utils3.set_attributes(self, **kwargs)
        self.loop = asyncio.get_event_loop()
        self.state = {}
        self.soa_list = []
        self.resolver_list = []
        self.registry = {}
        self.activequeries = {}

    def get_object(self, name=None):
        if name is None:
            return self.registry.values()
        return self.registry[name]

    def register_object(self, name, value):
        self._logger.debug('Registering object {} {}'.format(name, id(value)))
        self.registry[name] = value

    def unregister_object(self, name):
        del self.registry[name]

    def dns_register_soa(self, name):
        if not name.endswith('.'):
            name += '.'
        if name not in self.soa_list:
            self.soa_list.append(name)

    def dns_get_soa(self):
        return list(self.soa_list)

    def dns_register_resolver(self, addr):
        if addr not in self.resolver_list:
            self.resolver_list.append(addr)

    def dns_get_resolver(self, any=True):
        n = 0
        if any:
            n = random.randrange(len(self.resolver_list))
        return self.resolver_list[n]

    def dns_get_timeout(self, record_type = None):
        if record_type not in self._dns_timeout:
            # Return default timeout values
            return self._dns_timeout[None]
        else:
            # Return specific timeout values for record type
            return self._dns_timeout[record_type]

    def dns_register_timeout(self, timeouts, record_type = None):
        self._dns_timeout[record_type] = timeouts

    @asyncio.coroutine
    def ddns_register_user(self, fqdn, rdtype, ipaddr):
        # TODO: Move all this complexity to network module? Maybe it's more fitting...
        self._logger.info('Register new user {} @ {}'.format(fqdn, ipaddr))
        # Download user data
        user_data = yield from self.datarepository.get_policy_host(fqdn, default = None)
        if user_data is None:
            self._logger.info('Generating default subscriber data for {}'.format(fqdn))
            user_data = yield from self.datarepository.get_policy_host_default(fqdn, ipaddr)

        host_obj = HostEntry(name=fqdn, fqdn=fqdn, ipv4=ipaddr, services=user_data)
        self.hosttable.add(host_obj)

        # Create network resources
        hostname = ipaddr
        self.network.ipt_add_user(hostname, ipaddr)

        ## Add all user groups
        user_groups = host_obj.get_service('GROUP', [])
        self.network.ipt_add_user_groups(hostname, ipaddr, user_groups)

        ## Add all firewall rules
        fw_d = host_obj.get_service('FIREWALL', {})
        admin_fw = fw_d.setdefault('FIREWALL_ADMIN', [])
        user_fw  = fw_d.setdefault('FIREWALL_USER', [])
        self.network.ipt_add_user_fwrules(hostname, ipaddr, 'admin', admin_fw)
        self.network.ipt_add_user_fwrules(hostname, ipaddr, 'user', user_fw)

        ## CarrierGrade services if available
        if host_obj.has_service('CARRIERGRADE'):
            carriergrade_ipt = host_obj.get_service('CARRIERGRADE', [])
            self.network.ipt_add_user_carriergrade(hostname, carriergrade_ipt)


    @asyncio.coroutine
    def ddns_deregister_user(self, fqdn, rdtype, ipaddr):
        self._logger.info('Deregister user {} @ {}'.format(fqdn, ipaddr))
        if not self.hosttable.has((host.KEY_HOST_FQDN, fqdn)):
            self._logger.warning('Failed to deregister: user {} not found'.format(fqdn))
            return
        host_obj = self.hosttable.get((host.KEY_HOST_FQDN, fqdn))
        self.hosttable.remove(host_obj)
        # Remove network resources
        hostname = ipaddr
        ## Remove all user groups
        user_groups = host_obj.get_service('GROUP', [])
        self.network.ipt_remove_user_groups(hostname, ipaddr, user_groups)
        ## Remove all firewall rules
        self.network.ipt_remove_user(hostname, ipaddr)
        ## CarrierGrade services if available
        if host_obj.has_service('CARRIERGRADE'):
            carriergrade_ipt = host_obj.get_service('CARRIERGRADE', [])
            self.network.ipt_remove_user_fwrules(hostname, carriergrade_ipt)

    @asyncio.coroutine
    def ddns_process(self, query, addr, cback):
        """ Process DDNS query from DHCP server """
        self._logger.debug('process_update')
        try:
            #Filter hostname and operation
            for rr in query.authority:
                #Filter out non A record types
                if rr.rdtype == dns.rdatatype.A and rr.ttl != 0:
                    yield from self.ddns_register_user(format(rr.name), rr.rdtype, rr[0].address)
                elif rr.rdtype == dns.rdatatype.A and rr.ttl == 0:
                    yield from self.ddns_deregister_user(format(rr.name), rr.rdtype, rr[0].address)
        except Exception as e:
            self._logger.warning('Failed to process UPDATE DNS message {}'.format(e))
        finally:
            # Send generic DDNS Response NOERROR
            response = dnsutils.make_response_rcode(query)
            self._logger.debug('Sent DDNS response to {}:{}'.format(addr[0],addr[1]))
            cback(query, addr, response)

        '''
    @asyncio.coroutine
    def dns_process_rgw_lan_soa(self, query, addr, cback):
        """ Process DNS query from private network of a name in a SOA zone """
        # Forward or continue to DNS resolver
        fqdn = format(query.question[0].name)
        rdtype = query.question[0].rdtype

        if not self.hosttable.has((host.KEY_HOST_SERVICE, fqdn)):
            # FQDN not found! Answer NXDOMAIN
            response = dnsutils.make_response_rcode(query, dns.rcode.NXDOMAIN)
            cback(query, addr, response)
            return

        host_obj = self.hosttable.get((host.KEY_HOST_SERVICE, fqdn))
        if rdtype == 1:
            # Resolve A type and answer with IPv4 address of the host
            response = dnsutils.make_response_answer_rr(query, fqdn, rdtype, host_obj.ipv4, rdclass=1, ttl=30)
        elif rdtype == 12:
            # Resolve PTR type and answer with FQDN of the host
            response = dnsutils.make_response_answer_rr(query, fqdn, rdtype, host_obj.fqdn, rdclass=1, ttl=30)
        else:
            # Answer with empty records for other types
            response = dnsutils.make_response_rcode(query)
        cback(query, addr, response)
        '''

    @asyncio.coroutine
    def dns_process_rgw_lan_soa(self, query, addr, cback):
        """ Process DNS query from private network of a name in a SOA zone """
        # Forward or continue to DNS resolver
        # Same as in dns_process_rgw_wan_soa()
        fqdn = format(query.question[0].name)
        rdtype = query.question[0].rdtype
        host_obj = None
        # The service exists in RGW
        if self.hosttable.has((host.KEY_HOST_SERVICE, fqdn)):
            host_obj = self.hosttable.get((host.KEY_HOST_SERVICE, fqdn))
            service_data = host_obj.get_service_sfqdn(fqdn)
        elif self.hosttable.has_carriergrade(fqdn):
            host_obj = self.hosttable.get_carriergrade(fqdn)
            service_data = host_obj.get_service_sfqdn(host_obj.fqdn)
        elif fqdn in self.soa_list:
            self._logger.debug('Use NS address for {}'.format(fqdn))
            host_obj = self.hosttable.get((host.KEY_HOST_FQDN, fqdn))
            # Create DNS Response
            response = dnsutils.make_response_answer_rr(query, fqdn, 1, host_obj.ipv4, rdclass=1, ttl=60)
            self._logger.debug('Send DNS response to {}:{}'.format(addr[0],addr[1]))
            cback(query, addr, response)
            return
        else:
            # FQDN not found! Answer NXDOMAIN
            self._logger.debug('Answer {} with NXDOMAIN'.format(fqdn))
            response = dnsutils.make_response_rcode(query, dns.rcode.NXDOMAIN)
            cback(query, addr, response)
            return

        # Evaluate host and service
        if service_data.setdefault('carriergrade', False) and rdtype == 1:
            # Resolve A type with IPv4 address of the CarrierGrade host
            # HACK: Same code as from _dns_process_rgw_wan_soa_carriergrade
            # TODO: Make a single function to resolve and get address, so it can be called from several places
            self._logger.debug('Process {} with CarrierGrade resolution'.format(fqdn))
            cgresolver = uDNSResolver()
            try:
                cgresponse = yield from cgresolver.do_resolve(query, (host_obj.ipv4, 53), timeouts=self.dns_get_timeout('a'))
            except ConnectionRefusedError:
                # Refused to allocate an address - Drop DNS Query
                self._logger.warning('ConnectionRefusedError: Resolving CarrierGrade IP from {} for {}'.format(host_obj.ipv4, fqdn))
                response = dnsutils.make_response_rcode(query, dns.rcode.REFUSED)
                cback(query, addr, response)
                return

            if not cgresponse:
                # Failed to allocate an address - Drop DNS Query
                self._logger.warning('ResolutionFailure: Failed to resolve address from {} for {}'.format(host_obj.ipv4, fqdn))
                response = dnsutils.make_response_rcode(query, dns.rcode.SERVFAIL)
                cback(query, addr, response)

            host_cgaddr = dnsutils.get_first_record(cgresponse)
            if not host_cgaddr:
                # Failed to allocate an address - Drop DNS Query
                self._logger.warning('EmptyDNSResponse: Failed to obtain Carrier Grage IP from {} for {}'.format(host_obj.ipv4, fqdn))
                response = dnsutils.make_response_rcode(query, dns.rcode.SERVFAIL)
                cback(query, addr, response)
                return

            # Get service carriergrade and verify the IP address
            host_cgaddrs = host_obj.get_service('CARRIERGRADE', [])
            if not any(getitem(_, 'ipv4') == host_cgaddr for _ in host_cgaddrs):
                # Failed to verify carrier address in host pool - Drop DNS Query
                self._logger.warning('Failed to verify CarrierGrade IP address {} in {}'.format(host_cgaddr, host_cgaddrs))
                response = dnsutils.make_response_rcode(query, dns.rcode.SERVFAIL)
                cback(query, addr, response)
                return

            self._logger.info('Obtained {} from CarrierGrade resolution of {}'.format(host_cgaddr, fqdn))
            # Answer query with A type and answer with IPv4 address of the host
            response = dnsutils.make_response_answer_rr(query, fqdn, rdtype, host_cgaddr, rdclass=1, ttl=30)
            cback(query, addr, response)

        elif rdtype == 1:
            # Resolve A type and answer with IPv4 address of the host
            response = dnsutils.make_response_answer_rr(query, fqdn, rdtype, host_obj.ipv4, rdclass=1, ttl=30)
            cback(query, addr, response)

        elif rdtype == 12:
            # Resolve PTR type and answer with FQDN of the host
            response = dnsutils.make_response_answer_rr(query, fqdn, rdtype, host_obj.fqdn, rdclass=1, ttl=30)
            cback(query, addr, response)

        else:
            # Answer with empty records for other types
            response = dnsutils.make_response_rcode(query)
            cback(query, addr, response)


    @asyncio.coroutine
    def dns_process_rgw_lan_nosoa(self, query, addr, cback):
        """ Process DNS query from private network of a name not in a SOA zone """
        # Forward or continue to DNS resolver
        q = query.question[0]
        key = (query.id, q.name, q.rdtype, addr)
        fqdn = q.name

        if key in self.activequeries:
            # Continue ongoing resolution
            resolver = self.activequeries[key]
            resolver.do_continue(query)
            return

        # Create factory for new resolution
        raddr = self.dns_get_resolver()
        resolver = uDNSResolver()
        self.activequeries[key] = resolver
        try:
            response = yield from resolver.do_resolve(query, raddr, timeouts=self.dns_get_timeout('a'))
        except ConnectionRefusedError:
            # Refused to allocate an address - Drop DNS Query
            self._logger.warning('ConnectionRefusedError: Resolving {} via {}:{}'.format(fqdn, raddr[0], raddr[1]))
            response = dnsutils.make_response_rcode(query, dns.rcode.REFUSED)
        if not response:
            # Failed to resolve DNS query - Drop DNS Query
            self._logger.warning('ResolutionFailure: Failed to resolve address for {} via {}:{}'.format(fqdn, raddr[0], raddr[1]))
            response = dnsutils.make_response_rcode(query, dns.rcode.SERVFAIL)
        # Resolution ended, send generated response
        del self.activequeries[key]
        cback(query, addr, response)

    @asyncio.coroutine
    def dns_process_rgw_wan_soa(self, query, addr, cback):
        """ Process DNS query from public network of a name in a SOA zone """
        fqdn = format(query.question[0].name)
        self._logger.debug('dns_process_rgw_wan_soa {}'.format(fqdn))
        rdtype = query.question[0].rdtype
        host_obj = None
        # The service exists in RGW
        if self.hosttable.has((host.KEY_HOST_SERVICE, fqdn)):
            host_obj = self.hosttable.get((host.KEY_HOST_SERVICE, fqdn))
            service_data = host_obj.get_service_sfqdn(fqdn)
        elif self.hosttable.has_carriergrade(fqdn):
            host_obj = self.hosttable.get_carriergrade(fqdn)
            service_data = host_obj.get_service_sfqdn(host_obj.fqdn)
        elif fqdn in self.soa_list:
            self._logger.debug('Use NS address for {}'.format(fqdn))
            host_obj = self.hosttable.get((host.KEY_HOST_FQDN, fqdn))
            # Create DNS Response
            response = dnsutils.make_response_answer_rr(query, fqdn, 1, host_obj.ipv4, rdclass=1, ttl=60)
            self._logger.debug('Send DNS response to {}:{}'.format(addr[0],addr[1]))
            cback(query, addr, response)
            return
        else:
            # FQDN not found! Answer NXDOMAIN
            self._logger.debug('Answer {} with NXDOMAIN'.format(fqdn))
            response = dnsutils.make_response_rcode(query, dns.rcode.NXDOMAIN)
            cback(query, addr, response)
            return

        # Evaluate host and service
        if service_data.setdefault('carriergrade', False) and rdtype == 1:
            # Resolve A type via CarrierGrade host
            self._logger.debug('Process {} with CircularPool CarrierGrade'.format(fqdn))
            yield from self._dns_process_rgw_wan_soa_carriergrade(query, addr, cback, host_obj, service_data)
        elif rdtype == 1:
            # Resolve A type via Circular Pool
            self._logger.debug('Process {} with CircularPool'.format(fqdn))
            yield from self._dns_process_rgw_wan_soa_a(query, addr, cback, host_obj, service_data)
        else:
            # Answer with empty records for other types
            self._logger.debug('Answer {} with no records'.format(fqdn))
            response = dnsutils.make_response_rcode(query)
            cback(query, addr, response)

    @asyncio.coroutine
    def _dns_process_rgw_wan_soa_carriergrade(self, query, addr, cback, host_obj, service_data):
        fqdn = format(query.question[0].name)
        self._logger.debug('_dns_process_rgw_wan_soa_carriergrade {}'.format(fqdn))
        rdtype = query.question[0].rdtype

        if not self._check_policyrgw(host_obj, addr[0], None):
            # Failed to allocate an address - Drop DNS Query
            self._logger.warning('Policy exceeded. Failed to allocate an address for {}'.format(fqdn))
            return

        # Resolve A type via CarrierGrade Circular Pool
        self._logger.info('CarrierGrade resolution of {} via {}'.format(fqdn, host_obj.ipv4))
        cgresolver = uDNSResolver()
        try:
            cgresponse = yield from cgresolver.do_resolve(query, (host_obj.ipv4, 53), timeouts=self.dns_get_timeout('a'))
        except ConnectionRefusedError:
            # Refused to allocate an address - Drop DNS Query
            self._logger.warning('ConnectionRefusedError: Resolving CarrierGrade IP from {} for {}'.format(host_obj.ipv4, fqdn))
            response = dnsutils.make_response_rcode(query, dns.rcode.REFUSED)
            cback(query, addr, response)
            return

        if not cgresponse:
            # Failed to allocate an address - Drop DNS Query
            self._logger.warning('ResolutionFailure: Failed to resolve address from {} for {}'.format(host_obj.ipv4, fqdn))
            response = dnsutils.make_response_rcode(query, dns.rcode.SERVFAIL)
            cback(query, addr, response)
            return

        host_cgaddr = dnsutils.get_first_record(cgresponse)
        if not host_cgaddr:
            # Failed to allocate an address - Drop DNS Query
            self._logger.warning('EmptyDNSResponse: Failed to obtain Carrier Grage IP from {} for {}'.format(host_obj.ipv4, fqdn))
            response = dnsutils.make_response_rcode(query, dns.rcode.SERVFAIL)
            cback(query, addr, response)
            return

        # Get service carriergrade and verify the IP address
        host_cgaddrs = host_obj.get_service('CARRIERGRADE', [])
        if not any(getitem(_, 'ipv4') == host_cgaddr for _ in host_cgaddrs):
            # Failed to verify carrier address in host pool - Drop DNS Query
            self._logger.warning('Failed to verify CarrierGrade IP address {} in {}'.format(host_cgaddr, host_cgaddrs))
            response = dnsutils.make_response_rcode(query, dns.rcode.SERVFAIL)
            cback(query, addr, response)
            return

        self._logger.debug('Use CircularPool address pool for {} @ {}'.format(fqdn, host_cgaddr))
        # Get service data based on host FQDN
        allocated_ipv4 = self._create_connectionentryrgw(host_obj, host_cgaddr, addr[0], None, fqdn, service_data)

        if not allocated_ipv4:
            # Failed to allocate an address - Drop DNS Query
            self._logger.warning('Failed to allocate an address for {}'.format(fqdn))
            return

        # Create DNS Response
        response = dnsutils.make_response_answer_rr(query, fqdn, 1, allocated_ipv4, rdclass=1, ttl=0)
        self._logger.debug('Send DNS response to {}:{}'.format(addr[0],addr[1]))
        cback(query, addr, response)

    @asyncio.coroutine
    def _dns_process_rgw_wan_soa_a(self, query, addr, cback, host_obj, service_data):
        """ Process DNS query from public network of a name in a SOA zone """
        allocated_ipv4 = None
        # Get host object
        fqdn = format(query.question[0].name)
        if service_data['proxy_required']:
            self._logger.debug('Use servicepool address pool for {}'.format(fqdn))
            ap_spool = self.pooltable.get('servicepool')
            allocated_ipv4 = ap_spool.allocate()
            ap_spool.release(allocated_ipv4)
        elif self._check_policyrgw(host_obj, addr[0], None):
            self._logger.debug('Use CircularPool address pool for {}'.format(fqdn))
            allocated_ipv4 = self._create_connectionentryrgw(host_obj, host_obj.ipv4, addr[0], None, fqdn, service_data)

        if not allocated_ipv4:
            # Failed to allocate an address - Drop DNS Query
            self._logger.warning('Failed to allocate an address for {}'.format(fqdn))
            return
        else:
            # Create DNS Response
            response = dnsutils.make_response_answer_rr(query, fqdn, 1, allocated_ipv4, rdclass=1, ttl=0)
            self._logger.debug('Send DNS response to {}:{}'.format(addr[0],addr[1]))
            cback(query, addr, response)

    @asyncio.coroutine
    def dns_process_rgw_wan_nosoa(self, query, addr, cback):
        """ Process DNS query from public network of a name not in a SOA zone """
        fqdn = format(query.question[0].name)
        self._logger.warning('Drop DNS query for non-SOA domain {}'.format(fqdn))
        # Drop DNS Query
        return

    def dns_process_ces_lan_soa(self, query, addr, cback):
        """ Process DNS query from private network of a name in a SOA zone """
        pass

    def dns_process_ces_lan_nosoa(self, query, addr, cback):
        """ Process DNS query from private network of a name not in a SOA zone """
        pass

    def dns_process_ces_wan_soa(self, query, addr, cback):
        """ Process DNS query from public network of a name in a SOA zone """
        self._logger.warning('dns_process_ces_wan_soa')
        # Drop DNS Query
        return

    def dns_process_ces_wan_nosoa(self, query, addr, cback):
        """ Process DNS query from public network of a name not in a SOA zone """
        self._logger.warning('dns_process_ces_wan_nosoa')
        # Drop DNS Query
        return

    def _check_policyrgw(self, host_obj, dns_server_ip, dns_client_ip):
        # Get RGW and host objects
        rgw_policies = self.datarepository.get_policy_ces('CIRCULARPOOL', [])
        if not rgw_policies:
            self._logger.warning('RealmGateway CIRCULARPOOL policy not found!')
            return False
        # Update table and remove for expired connections
        self.connectiontable.update_all_rgw()
        # Get Circular Pool address pool stats
        ap_cpool = self.pooltable.get('circularpool')
        pool_size, pool_allocated, pool_available = ap_cpool.get_stats()
        # Get host usage stats of the pool - lookup because there could be none
        rgw_conns = self.connectiontable.stats(connection.KEY_RGW)
        host_conns = self.connectiontable.stats((connection.KEY_RGW, host_obj.fqdn)) # Use host fqdn as connection id
        # Get Circular Pool policies for RGW and host
        rgw_policy = rgw_policies[0]
        host_policy = host_obj.get_service('CIRCULARPOOL')[0]

        if rgw_conns >= rgw_policy['max']:
            self._logger.warning('RealmGateway global policy exceeded: {}'.format(rgw_policy['max']))
            return False
        if host_conns >= host_policy['max']:
            self._logger.warning('RealmGateway host policy exceeded: {}'.format(host_policy['max']))
            return False
        # No policy has been exceeded
        return True

    def _create_connectionentryrgw(self, host_obj, host_ipaddr, dns_server_ip, dns_client_ip, fqdn, service_data):
        """ Return the allocated IPv4 address """
        allocated_ipv4 = None
        # Get Circular Pool address pool
        ap_cpool = self.pooltable.get('circularpool')
        # Check if existing connections can be overloaded
        self._logger.debug('Overload connection for {} @ {}:{}'.format(fqdn, service_data['port'], service_data['protocol']))
        allocated_ipv4 = self._overload_connectionentryrgw(service_data['port'], service_data['protocol'])

        if allocated_ipv4:
            self._logger.info('Overloading {} for {}'.format(allocated_ipv4, fqdn))
        else:
            self._logger.debug('Cannot overload address for {}'.format(fqdn))
            allocated_ipv4 = ap_cpool.allocate()
            if allocated_ipv4 is None:
                return None
            self._logger.info('Allocated IP address from Circular Pool: {} @ {} via {} '.format(fqdn, host_ipaddr, allocated_ipv4))

        # Create RealmGateway connection
        conn_param = {'private_ip': host_ipaddr, 'private_port': service_data['port'],
                      'outbound_ip': allocated_ipv4, 'outbound_port': service_data['port'],
                      'protocol': service_data['protocol'], 'fqdn': fqdn, 'dns_server': dns_server_ip,
                      'loose_packet': service_data.setdefault('loose_packet', 0), 'id':host_obj.fqdn,
                      'autobind': service_data.setdefault('autobind', True),
                      'timeout': service_data.setdefault('timeout', 0)}
        new_conn = ConnectionLegacy(**conn_param)
        # Monkey patch delete function
        new_conn.delete = partial(self._delete_connectionentryrgw, new_conn)
        # Add connection to table
        self.connectiontable.add(new_conn)
        # Log new connection create
        self._logger.info('Created new connection: {}'.format(new_conn))
        return allocated_ipv4

    def _overload_connectionentryrgw(self, port, protocol):
        """ Returns the IPv4 address to overload or None """
        self._logger.debug('Attempt to overload connection for {}:{}'.format(port, protocol))
        # Get Circular Pool address pool
        ap_cpool = self.pooltable.get('circularpool')
        # Iterate all RealmGateway connections and try to reuse existing allocated IP addresses
        for ipv4 in ap_cpool.get_allocated():
            addrinuse = False
            conns = self.connectiontable.get((connection.KEY_RGW, ipv4))
            for conn in conns:
                c_port, c_proto = conn.outbound_port, conn.protocol
                d_port, d_proto = port, protocol
                self._logger.debug('Comparing {} vs {} @{}'.format((c_port, c_proto),(d_port, d_proto), ipv4))
                # The following statements match when IP overloading cannot be performed
                if (c_port == 0 and c_proto == 0) or (d_port == 0 and d_proto == 0):
                    self._logger.debug('0. Port & Protocol blocked')
                    addrinuse = True
                    break
                elif (c_port == d_port) and (c_proto == d_proto or c_proto == 0 or d_proto == 0):
                    self._logger.debug('1. Port blocked')
                    addrinuse = True
                    break
                elif (c_proto == d_proto) and (c_port == 0 or d_port == 0):
                    self._logger.debug('2. Port blocked')
                    addrinuse = True
                    break

            if not addrinuse:
                return ipv4

    def _delete_connectionentryrgw(self, conn):
        # Get Circular Pool address pool
        ap_cpool = self.pooltable.get('circularpool')
        ipaddr = conn.outbound_ip
        # Get RealmGateway connections
        if self.connectiontable.has((connection.KEY_RGW, ipaddr)):
            self._logger.info('Cannot release IP address to Circular Pool: {} ({}) still in use for {:.3f} msec'.format(ipaddr, conn.fqdn, conn.age*1000))
            return
        ap_cpool.release(ipaddr)
        self._logger.info('Released IP address to Circular Pool: {} ({}) in {:.3f} msec'.format(ipaddr, conn, conn.age*1000))

    def _do_callback(self, query, addr, response=None):
        try:
            q = query.question[0]
            key = (query.id, q.name, q.rdtype, addr)
            (resolver, cback) = self.activequeries.pop(key)
        except KeyError:
            self._logger.warning(
                'Query has already been processed {0} {1}/{2} from {3}:{4}'.format(
                    query.id, q.name, dns.rdatatype.to_text(q.rdtype),
                    addr[0], addr[1]))
            return

        if response is None:
            self._logger.warning('??? This seems a good place to create negative caching ???')

        # Callback to send response to host
        cback(query, addr, response)

class PacketCallbacks(object):
    def __init__(self, **kwargs):
        self._logger = logging.getLogger('PacketCallbacks')
        self._logger.setLevel(LOGLEVEL_PACKETCALLBACK)
        utils3.set_attributes(self, **kwargs)

    def _format_5tuple(self, packet_fields):
        if packet_fields['proto'] == 6:
            return '{}:{} {}:{} [{}] (TTL {}) flags/{:08b}'.format(packet_fields['src'], packet_fields['sport'],
                                                                  packet_fields['dst'], packet_fields['dport'],
                                                                  packet_fields['proto'], packet_fields['ttl'],
                                                                  packet_fields['tcp_flags'])
        elif packet_fields['proto'] == 132:
            return '{}:{} {}:{} [{}] (TTL {}) tag/{:x}'.format(packet_fields['src'], packet_fields['sport'],
                                                                packet_fields['dst'], packet_fields['dport'],
                                                                packet_fields['proto'], packet_fields['ttl'],
                                                                packet_fields['sctp_tag'])
        else:
            return '{}:{} {}:{} [{}] (TTL {})'.format(packet_fields['src'], packet_fields['sport'],
                                                      packet_fields['dst'], packet_fields['dport'],
                                                      packet_fields['proto'], packet_fields['ttl'])

    def packet_in_circularpool(self, packet):
        # Get IP data
        data = self.network.ipt_nfpacket_payload(packet)
        # Parse packet
        packet_fields = network_helper3.parse_packet_custom(data)
        # Select appropriate values for building the keys
        src, dst = packet_fields['src'], packet_fields['dst']
        proto, ttl = packet_fields['proto'], packet_fields['ttl']
        sport = packet_fields.setdefault('sport', 0)
        dport = packet_fields.setdefault('dport', 0)
        sender = '{}:{}'.format(src, sport)
        self._logger.debug('Received PacketIn: {}'.format(packet_fields))

        # Build connection lookup keys
        # key1: Basic IP destination for early drop
        key1 = (connection.KEY_RGW, dst)
        # key2: Full fledged 5-tuple
        key2 = (connection.KEY_RGW, dst, dport, src, sport, proto)
        # key3: Semi-full fledged 3-tuple
        key3 = (connection.KEY_RGW, dst, dport, proto)
        # key4: Basic 3-tuple with wildcards
        key4 = (connection.KEY_RGW, dst, 0, 0)
        # key5: Basic 3-tuple with wildcards
        key5 = (connection.KEY_RGW, dst, dport, 0)
        # key6: Basic 3-tuple with wildcards
        key6 = (connection.KEY_RGW, dst, 0, proto)

        # Lookup connection in table with basic key for for early drop
        if not self.connectiontable.has(key1):
            self._logger.info('No connection reserved for IP {}: [{}]'.format(dst,self._format_5tuple(packet_fields)))
            self.network.ipt_nfpacket_drop(packet)
            return

        # Lookup connection in table with rest of the keys
        conn = None
        for key in [key2, key3, key4, key5, key6]:
            if self.connectiontable.has(key):
                self._logger.debug('Connection found for n-tuple* {}: [{}]'.format(key,self._format_5tuple(packet_fields)))
                conn = self.connectiontable.get(key)
                break

        if conn is None:
            self._logger.warning('No connection found for packet: [{}]'.format(self._format_5tuple(packet_fields)))
            self.network.ipt_nfpacket_drop(packet)
            return

        # DNAT to private host
        self._logger.info('DNAT to {} @ {} via {}: [{}]'.format(conn.fqdn, conn.private_ip, dst, self._format_5tuple(packet_fields)))
        self.network.ipt_nfpacket_dnat(packet, conn.private_ip)

        if conn.post_processing(self.connectiontable, src, sport):
            # Delete connection and trigger IP address release
            self.connectiontable.remove(conn)