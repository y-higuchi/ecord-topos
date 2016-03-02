import json
from mininet.net import Mininet

class Domain(object):
    """
    A container for switch, host, link, and controller information to be dumped
    into the Mininet mid-level API.
    """

    def __init__ (self, did=0):
        # each Domain has a numeric ID for sanity/convenience
        self.__dId = did

        # information about network elements - for calling the "mid-level" APIs
        self.__ctrls = {}
        self.__switches = {}
        self.__hosts = {}
        self.__links = {}
        # maps of devices, hosts, and controller names to actual objects
        self.__smap = {}
        self.__hmap = {}
        self.__cmap = {}
        self.__lmap = {}

    def addController(self, name, **args):
        self.__ctrls[name] = args if args else {}
        return name

    # Note: This method will return the name of the swich, not the switch object
    def addSwitch(self, name, **args):
        self.__switches[name] = args if args else {}
        return name

    def addHost(self, name, **args):
        self.__hosts[name] = args if args else {}
        return name

    def addLink(self, src, dst, **args):
        self.__links[(src, dst)] = args if args else {}
        return (src, dst)

    def getId( self):
        return self.__dId

    def getControllers(self, name=None):
        return self.__cmap.values() if not name else self.__cmap.get(name)

    def getSwitches(self, name=None):
        return self.__smap.values() if not name else self.__smap.get(name)

    def getHosts(self, name=None):
        return self.__hmap.values() if not name else self.__hmap.get(name)

    def injectInto(self, net):
        """ Adds available topology info to a supplied Mininet object. """
        # add switches, hosts, then links to mininet object
        for sw, args in self.__switches.iteritems():
            self.__smap[sw] = net.addSwitch(sw, **args)
        for h, args in self.__hosts.iteritems():
            self.__hmap[h] = net.addHost(h, **args)
        for l, args in self.__links.iteritems():
            src = self.__smap.get(l[0])
            dst = self.__smap.get(l[1])
            self.__lmap[l] = net.addLink(src if src else self.__hmap.get(l[0]),
                             dst if dst else self.__hmap.get(l[1]), **args)
        # then controllers
        for c, args in self.__ctrls.iteritems():
            self.__cmap[c] = net.addController(c, **args)

    def start(self):
        """ starts the switches with the correct controller. """
        map(lambda c: c.start(), self.__cmap.values())
        map(lambda s: s.start(self.__cmap.values()), self.__smap.values())

    def build(self, *args):
        """ override for custom topology, similar to Topo """
        pass

class SegmentRoutedDomain(Domain):
    """
    A domain where nodes implement segment routing, as in a CO.
    """
    # base for DPID string to format them in way network config likes them
    id_base='0000000000000000'

    def __init__(self, did, tocfg, ovs=True):
        """
        did : globally unique domain ID
        tocfg : function used to format segment routing config file
        ovs : add a metro-facing OVS between routers and metro
        """
        Domain.__init__(self, did)
 
        self.useOvs = ovs
        self.toCfg = tocfg
        # netcfg for segment routing
        self.__cfg = {}
        self.__cfg['ports'] = {}
        self.__cfg['devices'] = {}
        self.__cfg['hosts'] = {}

        # list of leaves (facing non-tagged/differently tagged links)
        self.__leaves = []
        # map of switches to formatted device IDs - convenience 
        self.__sw2id = {}

    def addTether(self, name, tname=None, tdpid=None):
        """
        add an OVS with name 'tname' and dpid 'tdpid' for connecting fabric
        domains to the core.  name: the UserSwitch to connect the OVS to.
        """
        if self.useOvs and tname and tdpid:
            self.__tether = self.addSwitch(tname, dpid=tdpid)
            # Note: OVS port number '1' reserved for port facing the fabric
            self.addLink(tname, name, port1=1)
        else:
            self.__tether = name
        self.noteLeaf(name)

    def getTether(self):
        """ get the switch name of this fabric facing the core """
        return self.__tether

    def noteLeaf(self, leaf):
        """ note down a node as a leaf """
        self.__leaves.append(leaf)
        return leaf

    def getLeaves(self):
        """ get the names of the known leaves """
        return self.__leaves

    def addSwitchCfg(self, sw, sid, ip, mac, adjsids=[]):
        """ add a router netcfg block """
        cfg = {}
        cfg['name'] = sw.name
        cfg['nodeSid'] = sid
        # Router IP/MAC for routing and ARP - IP matching IP block of host(s) attached
        cfg['routerIp'] = ip 
        cfg['routerMac'] = mac
        cfg['isEdgeRouter'] = 'true' if sw.name in self.__leaves else 'false'
        cfg['adjacencySids'] = adjsids
        # At times, DPIDs generated by Mininet are < 16 digits. Add back the 0s.
        did = 'of:%s' % (self.id_base[:(16 - len(sw.dpid))] + sw.dpid)
        sw_ent = { 'segmentrouting' : cfg }
        self.__cfg['devices'][did] = sw_ent
        self.__sw2id[sw] = did
        return did

    def addPortCfg(self, sw, iface):
        """ 
        sw : the Switch object associated with this port
        iface : the Intf object
        """
        ifid = '%s/%s' % (self.__sw2id[sw], sw.ports[iface])
        self.__cfg['ports'][ifid] = { 'interfaces' : [] }
        return ifid

    def intfCfg(self, ifid, ips=[], vlan='-1'):
        """
        ifid : connect point identifier of form 'scheme:did/port'
        ips : a list of CIDR-notation IP blocks
        vlan : tab to use (default of -1 is 'untagged')
        """
        cfg = { 'vlan' : vlan } if not ips else { 'ips' : ips, 'vlan' : vlan }
        self.__cfg['ports'][ifid]['interfaces'].append(cfg)

    def addHostCfg(self, host, tag=-1):
        """ add a host configuration given a Host object """
        # 4093 - starting VLAN tag value for L2 switching - segment routing convention
        # assume that first non-loopback interface is sufficient
        iface = filter(lambda i: i.name != 'lo', host.intfList())[0]
        if iface is not None:
            if1, if2 = iface.link.intf1, iface.link.intf2
            locif = if1 if if1.node.name != host.name else if2
            did = self.__sw2id[locif.node]
            ent = { 'basic' : {} }
            ent['basic']['ips'] = [host.params.get('ip').split('/')[0]]
            ent['basic']['location'] = '%s/%s' % (did, locif.node.ports[locif])
            hid = '%s/%s' % (iface.mac, tag)
            self.__cfg['hosts'][hid] = ent
            return hid

    def dumpCfg(self, fname):
        self.toCfg()
        with open(fname, 'w') as outfile:
            json.dump(self.__cfg, outfile, indent=4, separators=(',', ': '))

    def build(self, *args):
        """"Construct a topology. Override in custom topology"""
        pass
