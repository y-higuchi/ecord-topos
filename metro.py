#!/usr/bin/env python
import json

from mininet.net import Mininet
from mininet.node import UserSwitch, DefaultController, RemoteController, Host
from mininet.topo import Topo
from mininet.log import  setLogLevel, info, error, warn
from mininet.cli import CLI
from mininet.link import OVSIntf
from mininet.util import quietRun

from domains import Domain, SegmentRoutedDomain
from opticalUtils import LINCSwitch, LINCLink

class OpticalDomain(Domain):
    """ An emulated optical metro core. It is Domain 0. """
    def build(self):
        for i in range (1,4):
            oean = { "optical.regens": 0 }
            self.addSwitch('OE%s' % i, dpid='0000ffffffffff0%s' % i, annotations=oean, cls=LINCSwitch)

        # ROADM port number OE"1" -> OE'2' = "1"'2'00
        # leaving port number up to 100 open for use by Och port
        an = { "durable": "true" }
        self.addLink('OE1', 'OE2', port1=1200, port2=2100, annotations=an, cls=LINCLink)
        self.addLink('OE2', 'OE3', port1=2300, port2=3200, annotations=an, cls=LINCLink)
        self.addLink('OE3', 'OE1', port1=3100, port2=1300, annotations=an, cls=LINCLink)

class FabricDomain(SegmentRoutedDomain):
    """
    An emulated CO fabric, which is basically a K(n,m) bipartite graph.

    Each FabricDomain should be given a unique Domain ID (did) to ensure unique
    names and addressing.
    """
    def __init__(self, did, ovs=True):
        SegmentRoutedDomain.__init__(self, did, self.toCfg, ovs)
        # hosts to gateway, for generating configs (see toCfg()).
        self.s2gw = {}

    def build(self, n=2, m=3, f=1):
        """
        bipartite graph, where n = spine; m = leaf; f = host fanout
        """
        l_nsw=[]
        l_msw=[]

        # create n spine switches.
        for sw in range(n):
            l_nsw.append(self.addSwitch('spine%s%s' % (self.getId(), sw+1),
                         cls=UserSwitch, dpopts='--no-local-port'))

        # create connection point to optical core (a leaf switch)
        tsw = self.addSwitch('leaf%s01' % self.getId(), cls=UserSwitch, dpopts='--no-local-port')
        self.addTether(tsw, 'tether%s' % self.getId(), '0000ffffffff000%s' % self.getId())
        self.s2gw[tsw] = '10.%s.1.254' % self.getId()
        l_msw.append(tsw)

        # attach f hosts to last m-1 leaves, and record IP blocks used
        for sw in range(1, m):
            msw = self.addSwitch('leaf%s0%s' % (self.getId(), sw+1),
                                 cls=UserSwitch, dpopts='--no-local-port')
            self.noteLeaf(msw)
            l_msw.append(msw)
            for h in range(f):
                self.s2gw[msw] = '10.%s.%s.254' % (self.getId(), sw+1)
                host = self.addHost('h%s%s%s' % (self.getId(), sw, f+h+1), cls=IpHost,
                                    ip='10.%s.%s.%s/24' % (self.getId(), sw+1, (f+h+1)),
                                    gateway=self.s2gw[msw])
                self.addLink(host, msw)
        # link up spines and leaves
        for nsw in l_nsw:
            for msw in l_msw:
                self.addLink(nsw, msw)

    def toCfg(self):
        """ Dump a file in segment routing config file format. """
        i = 1
        for sw in self.getSwitches():
            if sw.name in self.getLeaves():
                swid = self.addSwitchCfg(sw, '%s0%s' % (self.getId(), i), self.s2gw[sw.name],
                                         '00:00:00:0%s:0%s:80' % (self.getId(), i))
                # check for non-loopback ports facing a host with name of form 'h.*'.
                for iface in filter(lambda el: el.name != 'lo', sw.intfList()):
                    ep1, ep2 = iface.link.intf1.node, iface.link.intf2.node

                    if (ep1.name[0] == 'h' or ep2.name[0] == 'h' or
                        'tether' in ep1.name or 'tether' in ep2.name):
                        ifid = self.addPortCfg(sw, iface)
                        self.intfCfg(ifid, [self.s2gw[sw.name] + '/24'])
            else:
                self.addSwitchCfg(sw, '%s0%s' % (self.getId(), i),
                                  '192.168.%s.%s' % (self.getId(), i),
                                  '00:00:00:0%s:0%s:80' % (self.getId(), i))
            i = i + 1
        for h in self.getHosts():
            self.addHostCfg(h)

class IpHost(Host):
    def __init__(self, name, gateway, *args, **kwargs):
        super(IpHost, self).__init__(name, *args, **kwargs)
        self.gateway = gateway

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        mtu = "ifconfig "+self.name+"-eth0 mtu 1490"
        self.cmd(mtu)
        self.cmd('ip route add default via %s' % self.gateway)

def setup(argv):
    domains = []
    ctlsets = sys.argv[1:]

    # the controllers for the optical domain
    d0 = OpticalDomain()
    domains.append(d0)
    ctls = ctlsets[0].split(',')
    for i in range (len(ctls)):
        d0.addController('c0%s' % i, controller=RemoteController, ip=ctls[i])

    # the fabric domains - position 1 for domain 1, 2 for 2 ...
    for i in range (1,len(ctlsets)):
        f = FabricDomain(i)
        domains.append(f)
        ctls = ctlsets[i].split(',')
        for j in range (len(ctls)):
            f.addController('c%s%s' % (i,j), controller=RemoteController, ip=ctls[j])

    # netcfg for each domains
    # Note: Separate netcfg for domain0 is created in opticalUtils
    domainCfgs = []
    for i in range (0,len(ctlsets)):
        cfg = {}
        cfg['devices'] = {}
        cfg['ports'] = {}
        cfg['links'] = {}
        domainCfgs.append(cfg)

    # make/setup Mininet object
    net = Mininet()
    for d in domains:
        d.build()
        d.injectInto(net)

    # generate segment routing cfgs
    info('*** Generating routing configuration files for COs:\n')
    for i in range (1,len(domains)):
        info('\tCO%s: domain%s-cfg.json\n' % (i, i))
        domains[i].dumpCfg('domain%s-cfgv2.json' % i)

    # connect COs to core - sort of hard-wired at this moment
    # adding cross-connect links
    for i in range(1,len(domains)):
        # add 10 cross-connect links between domains
        xcPortNo=2
        ochPortNo=10
        for j in range(0, 10):
            an = { "bandwidth": 10, "durable": "true" }
            net.addLink(domains[i].getTether(), d0.getSwitches('OE%s' % i),
                        port1=xcPortNo+j, port2=ochPortNo+j, speed=10000, annotations=an, cls=LINCLink)
            xcId = 'of:' + domains[i].getSwitches(name=domains[i].getTether()).dpid + '/' + str(xcPortNo+j)
            ochId = 'of:' + d0.getSwitches('OE%s' % i).dpid + '/' + str(ochPortNo+j)
            domainCfgs[i]['ports'][xcId] = {'cross-connect': {'remote': ochId}}

    # fire everything up
    net.build()
    map(lambda x: x.start(), domains)

    # create a minimal copy of the network for configuring LINC.
    cfgnet = Mininet()
    cfgnet.switches = net.switches
    cfgnet.links = net.links
    cfgnet.controllers = d0.getControllers()
    LINCSwitch.bootOE(cfgnet, d0.getSwitches())

    # send netcfg json to each CO-ONOS
    for i in range(1,len(domains)):
        info('*** Pushing Topology.json to CO-ONOS %d\n' % i)
        filename = 'Topology%d.json' % i
        with open(filename, 'w') as outfile:
            json.dump(domainCfgs[i], outfile, indent=4, separators=(',', ': '))

        output = quietRun('%s/tools/test/bin/onos-netcfg %s %s &'\
                           % (LINCSwitch.onosDir,
                              domains[i].getControllers()[0].ip,
                              filename), shell=True)
        # successful output contains the two characters '{}'
        # if there is more output than this, there is an issue
        if output.strip('{}'):
            warn('***WARNING: Could not push topology file to ONOS: %s\n' % output)

    CLI(net)
    net.stop()
    LINCSwitch.shutdownOE()

if __name__ == '__main__':
    setLogLevel('info')
    import sys
    if len(sys.argv) < 2:
        print ("Usage: sudo -E ./metro.py ctl-set1 ... ctl-set4\n\n",
                "Where ctl-set are comma-separated controller IP's")
    else:
        setup(sys.argv)
