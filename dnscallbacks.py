import asyncio
import utils
import logging
import random

import customdns
from customdns import dnsutils
from customdns.dnsresolver import DNSResolver

import dns
import dns.message
import dns.zone
import dns.rcode

from dns.exception import DNSException
from dns.rdataclass import *
from dns.rdatatype import *


class DNSCallbacks(object):
    def __init__(self, **kwargs):
        self._logger = logging.getLogger('DNSCallbacks')
        self._logger.setLevel(logging.WARNING)
        utils.set_attributes(self, **kwargs)
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
            n = random.randint(0, len(self.resolver_list) - 1)
        return self.resolver_list[n]

    def ddns_register_user(self, name, rdtype, ipaddr):
        # TO BE COMPLETED
        '''
        self._logger.warning('Register new user {} @{}'.format(name, ipaddr))
        # Add node to the DNS Zone
        zone = self._dns['zone']
        mydns.add_node(zone, name, rdtype, ipaddr)
        # Initialize address pool for user
        ap = self._poolcontainer.get('proxypool')
        ap.create_pool(ipaddr)
        # Download user data
        '''
        pass

    def ddns_deregister_user(self, name, rdtype, ipaddr):
        # TO BE COMPLETED
        '''
        self._logger.warning('Deregister user {} @{}'.format(name, ipaddr))
        # Delete node from the DNS Zone
        zone = self._dns['zone']
        mydns.delete_node(zone, name)
        # Delete all active connections
        pass
        # Destroy address pool for user
        ap = self._poolcontainer.get('proxypool')
        ap.destroy_pool(ipaddr)
        '''
        pass

    def ddns_process(self, query, addr, cback):
        """ Process DDNS query from DHCP server """
        self._logger.debug('process_update')
        try:
            rr_a = None
            #Filter hostname and operation
            for rr in query.authority:
                #Filter out non A record types
                if rr.rdtype == dns.rdatatype.A:
                    rr_a = rr
                    break

            if not rr_a:
                # isc-dhcp-server uses additional TXT records -> don't process
                self._logger.debug('Failed to find an A record')
                return

            name_str = rr_a.name.to_text()
            if rr_a.ttl:
                self.ddns_register_user(name_str, rr_a.rdtype, rr_a[0].address)
            else:
                self.ddns_deregister_user(name_str, rr_a.rdtype, rr_a[0].address)

            # Send generic DDNS Response NOERROR
            response = dnsutils.make_response_rcode(query, RetCodes.DNS_NOERROR)
            self._logger.debug('Sent DDNS response to {}:{}'.format(addr[0],addr[1]))
            cback(query, response, addr)
        except Exception as e:
            self._logger.error('Failed to process UPDATE DNS message')

    def dns_process_rgw_lan_soa(self, query, addr, cback):
        """ Process DNS query from private network of a name in a SOA zone """
        self._logger.warning('dns_process_rgw_lan_soa')
        fqdn = query.question[0].name.to_text()
        # Resolve locally
        pass

    def dns_process_rgw_lan_nosoa(self, query, addr, cback):
        """ Process DNS query from private network of a name not in a SOA zone """
        # Forward or continue to DNS resolver
        self._logger.warning('dns_process_rgw_lan_nosoa')
        q = query.question[0]
        key = (query.id, q.name, q.rdtype)
        self._logger.warning('Resolve query {0} {1}/{2} from {3}:{4}'.format(query.id, q.name.to_text(), dns.rdatatype.to_text(q.rdtype), addr[0], addr[1]))

        if key not in self.activequeries:
            # Create new resolution
            self._logger.warning(
                'Resolve normal query {0} {1}/{2} from {3}:{4}'.format(
                    query.id, q.name.to_text(), dns.rdatatype.to_text(
                        q.rdtype), addr[0], addr[1]))
            # Create factory
            resolver = DNSResolver(query, addr, cback, timeouts=[0])
            self.activequeries[key] = (resolver, query)
            raddr = self.dns_get_resolver()
            self.loop.create_task(self.loop.create_datagram_endpoint(lambda: resolver, remote_addr=raddr))
        else:
            # Continue ongoing resolution
            (resolver, query) = self.activequeries[key]
            resolver.process_query(query, addr)

    def dns_process_ces_lan_soa(self, query, addr, cback):
        """ Process DNS query from private network of a name in a SOA zone """
        fqdn = query.question[0].name.to_text()
        pass

    def dns_process_ces_lan_nosoa(self, query, addr, cback):
        """ Process DNS query from private network of a name not in a SOA zone """
        fqdn = query.question[0].name.to_text()
        pass

    def dns_process_rgw_wan_soa(self, query, addr, cback):
        """ Process DNS query from public network of a name in a SOA zone """
        self._logger.warning('dns_process_rgw_wan_soa')
        fqdn = query.question[0].name.to_text()
        # Resolve locally
        pass

    def dns_process_rgw_wan_nosoa(self, query, addr, cback):
        """ Process DNS query from public network of a name not in a SOA zone """
        self._logger.warning('dns_process_rgw_wan_nosoa')
        print(addr)
        print(query)
        fqdn = query.question[0].name.to_text()
        # Discard
        pass

    def dns_process_ces_wan_soa(self, query, addr, cback):
        """ Process DNS query from public network of a name in a SOA zone """
        fqdn = query.question[0].name.to_text()
        pass

    def dns_process_ces_wan_nosoa(self, query, addr, cback):
        """ Process DNS query from public network of a name not in a SOA zone """
        fqdn = query.question[0].name.to_text()
        pass