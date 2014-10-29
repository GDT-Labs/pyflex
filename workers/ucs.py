#!/usr/bin/env python
""" UCS worker class for pyflex

    In the future, this will really be the core renderer. All of the 
    work of deleting config that shouldn't be there, or creating it
    when it should, will be handled here.

"""
from worker import FlexWorker
#from functions.functions_ucs import UcsFunctions
from functions.newfunctions_ucs import NewUcsFunctions
from UcsSdk import UcsHandle


class UcsWorker(FlexWorker):
    """ A child worker class that pertains specifically to UCS """

    FABRICS = ['A', 'B']

    def startworker(self):
        """ Starts this worker """

        #Connect to UCSM
        handle = UcsHandle()

        ucsauth = self.config['auth']['ucs']

        print ucsauth

        handle.Login(
            ucsauth['host'],
            ucsauth['user'],
            ucsauth['pass']
        )

        newfxns = NewUcsFunctions(handle, self.config['general']['org'])

        """ VLANS """
        vlans = {}

        #Get a list of all VLANs, regardless of group
        for group in self.config['vlans']:

            #Exclusing VLANs used for FCoE
            if group != 'storage':

                #TODO: This is really ugly because of the VLAN layout in the
                #config file. Maybe need to figure out a way to restructure it
                for vlanid, vlanname in self.config['vlans'][group].iteritems():
                    vlans[vlanid] = vlanname

        #Add all VLANs in the list
        for vlanid, vlanname in vlans.iteritems():
            newfxns.createVLAN(vlanid, vlanname)

        #Remove any VLANs within UCS that are not in the config
        for mo in newfxns.getVLANs().OutConfigs.GetChild():
            if int(mo.Id) in vlans:
                pass
            else:
                newfxns.removeVLAN(mo)


        """ VSANS """

        vsans = {}

        #Create VSANs from the list
        for vsanid, vsanname in self.config['vsans']['a'].iteritems():
            newfxns.createVSAN("A", vsanid, vsanname)
        for vsanid, vsanname in self.config['vsans']['b'].iteritems():
            newfxns.createVSAN("B", vsanid, vsanname)

        #Remove any VSANs within UCS that are not in the config
        for mo in newfxns.getVSANs().OutConfigs.GetChild():
            if int(mo.Id) in self.config['vsans']['a'] or int(mo.Id) in self.config['vsans']['b']:
                pass
            else:
                newfxns.removeVSAN(mo)

        """ MAC POOLS """

        #Pull MAC Pool Configuration Info
        macpools = self.config['ucs']['pools']['mac']

        #MAC Pools
        for fabric in macpools: #TODO: This loop is here for the future, but obviously since the name is statically set, this only works with a single pool per fabric, currently.
            newfxns.createMacPool(fabric, macpools[fabric]['blockbegin'], macpools[fabric]['blockend'])

        """ WWPN POOLS """

        #Pull WWPN Pool Configuration Info
        wwpnpools = self.config['ucs']['pools']['wwpn']

        #WWPN Pools
        for fabric in wwpnpools: #TODO: This loop is here for the future, but obviously since the name is statically set, this only works with a single pool per fabric, currently.
            newfxns.createWwpnPool(fabric, wwpnpools[fabric]['blockbegin'], wwpnpools[fabric]['blockend'])

        #TODO: UUID POOL

        #TODO: WWNN POOL

        """ GLOBAL POLICIES """

        newfxns.setPowerPolicy("grid")
        newfxns.setChassisDiscoveryPolicy(str(self.config['ucs']['links']))

        """ QOS """

        newfxns.setGlobalQosPolicy(self.config['qos'])
        for classname, hostcontrol in self.config['qos']['classes'].iteritems():
            newfxns.createQosPolicy(classname, hostcontrol)

        """ ORG-SPECIFIC POLICIES """

        newfxns.createLocalDiskPolicy("NO_LOCAL", "no-local-storage")
        newfxns.createLocalDiskPolicy("RAID1", "raid-mirrored")
        newfxns.createHostFWPackage("HOST_FW_PKG")
        newfxns.createMaintPolicy("MAINT_USERACK", "user-ack")
        newfxns.createNetControlPolicy("NTKCTRL-CDP")

        """ VNIC TEMPLATES """

        # Create vNIC Templates
        for vnicprefix, vlangroup in self.config['ucs']['vlangroups'].iteritems():
            for fabricid in self.FABRICS:
                #TODO: that weird "return as list" issue (resulting in the list index below)
                vnic = newfxns.createVnicTemplate(vnicprefix, fabricid)[0]
                for vlanid, vlanname in self.config['vlans'][vlangroup].iteritems():
                    newfxns.createVnicVlan(vnic, vlanname)
        
        templates = ["ESX-PROD-A", "ESX-PROD-B"]

        for template in templates:

            vnic = newfxns.getVnicTemplate(template)

            #TODO: Need to check here (and anywhere else you're doing getChild) to make sure the "vnic" array has members (otherwise your search is bad)

            #Remove any VLANs on this vNIC Template that are not in the config
            for vlanMo in newfxns.getVnicVlans(vnic[0]).OutConfigs.GetChild():      #TODO: that weird "return as list" issue
                
                #TODO: This is a pretty dirty hack, see if you can do something better
                vlanName = vlanMo.Dn[vlanMo.Dn.index("/if-") + 4:]

                #Delete all VLANs from the vNIC Template that aren't in the "production" group of the configuration
                if vlanName in self.config['vlans']['prod'].values():
                    pass
                else:
                    newfxns.removeVnicVlan(vnic[0], vlanName)

        """ VHBA TEMPLATES """

        # Create vHBA Templates
        for fabricid in self.FABRICS:
            #TODO: that weird "return as list" issue (resulting in the list index below)
            vhba = newfxns.createVhbaTemplate(fabricid)[0]

            # No removal method necessary; will override existing VSAN setting
            for vsanid, vsanname in self.config['vsans'][fabricid.lower()].iteritems():
                newfxns.createVhbaVsan(vhba, vsanname)

        """ SP TEMPLATES """

        spt = newfxns.createSPTemplate(self.config['ucs']['sptname'])

        vnics = [ #TODO: This is an ugly way to do this
            "ESX-MGMT-A",
            "ESX-MGMT-B",
            "ESX-NFS-A",
            "ESX-NFS-B",
            "ESX-PROD-A",
            "ESX-PROD-B"
        ]

        vhbas = [
            "ESX-VHBA-A",
            "ESX-VHBA-B"
        ]
        
        #Create vNIC VCON assignments
        for vnic in vnics:
            transport = "ethernet"
            order = str(vnics.index(vnic) + 1)
            newfxns.setVconOrder(spt[0], vnic, transport, order)
            newfxns.addVnicFromTemplate(spt[0], vnic)

        for vhba in vhbas:
            transport = "fc"
            order = str(vhbas.index(vhba) + 1)
            newfxns.setVconOrder(spt[0], vhba, transport, order)
            newfxns.addVhbaFromTemplate(spt[0], vhba)

        newfxns.setWWNNPool(spt[0], "ESXi-WWNN")
        newfxns.setPowerState(spt[0], "admin-up")

        newfxns.spawnZerglings(
                spt[0], 
                self.config['ucs']['spprefix'], 
                self.config['ucs']['numbertospawn']
            )
