from charmhelpers.core.hookenv import unit_private_ip
from charmhelpers.contrib.openstack import context

from charmhelpers.core.host import apt_install, filter_installed_packages

# This is just a label and it must be consistent across
# nova-compute nodes to support live migration.
CEPH_SECRET_UUID = '514c9fca-8cbe-11e2-9c52-3bc8c7819472'

class NovaComputeLibvirtContext(context.OSContextGenerator):
    interfaces = []

    def __call__(self):
        pass


class NovaComputeVirtContext(context.OSContextGenerator):
    interfaces = []
    def __call__(self):
        return {}

class NovaComputeCephContext(context.CephContext):
    def __call__(self):
        ctxt = super(NovaComputeCephContext, self).__call__()
        if not ctxt:
            return {}
        ctxt['ceph_secret_uuid'] = CEPH_SECRET_UUID
        return ctxt

class CloudComputeContext(context.OSContextGenerator):
    '''
    Generates main context for writing nova.conf and quantum.conf templates
    from a cloud-compute relation changed hook

    Note: individual quantum plugin contexts are handled elsewhere.
    '''
    interfaces = ['cloud-compute']

    def flat_dhcp_context(self):
        ec2_host = relation_get('ec2_host')
        if not ec2_host:
            return {}
        return {
            'network_manager': 'nova.network.manager.FlatDHCPManager',
            'flat_interface': config_get('flat_interface'),
            'ec2_host': ec2_host,
        }

    def quantum_context(self):
        quantum_ctxt = {
            'quantum_auth_strategy': 'keystone',
            'keystone_host': relation_get('keystone_host'),
            'auth_port': relation_get('auth_port'),
            'quantum_url': relation_get('quantum_url'),
            'quantum_admin_tenant_name': relation_get('service_tenant'),
            'quantum_admin_username': relation_get('service_username'),
            'quantum_admin_password': relation_get('service_password'),
            'quantum_security_groups': relation_get('quantum_security_groups'),
            'quantum_plugin': relation_get('quantum_plugin'),
        }
        missing = [k for k, v in quantum_ctxt.iteritems() if k == None]
        if missing:
            log('Missing required relation settings for Quantum: ' +
                ' '.join(missing))
            return {}

        ks_url = 'http://%s:%s/v2.0' % (quantum_ctxt['keystone_host'],
                                        quantum_ctxt['auth_port'])
        quantum_ctxt['quantum_admin_auth_url'] = ks_url
        quantum_ctxt['network_api_class'] = 'nova.network.quantumv2.api.API'

    def volume_context(self):
        vol_ctxt = {}
        vol_service = relation_get('volume_service')
        if vol_service == 'cinder':
            vol_ctxt['volume_api_class'] = 'nova.volume.cinder.API'
        elif vol_service == 'nova-volume':
            if get_os_codename_package('nova-common') in ['essex', 'folsom']:
                vol_ctxt['volume_api_class'] = 'nova.volume.api.API'
        else:
            log('Invalid volume service received via cloud-compute: %s' %
                vol_service, level=ERROR)
            raise
        return vol_ctxt

    def __call__(self):
        rids = relation_list('cloud-compute')
        if not rids:
            return {}

        ctxt = {}

        net_manager = relation_get('network_manager').lower()
        if net_manager == 'flatdhcpmanager':
            ctxt.update(self.flat_dhcp_context())
        elif net_manager == 'quantum':
            ctxt.update(self.quantum_context())

        vol_service = relation_get('volume_service')
        if vol_service:
            ctxt.update(self.volume_context())


class QuantumPluginContext(context.OSContextGenerator):
    interfaces = []

    def _ensure_packages(self, packages):
        '''Install but do not upgrade required plugin packages'''
        apt_install(filter_installed_packages(packages))

    def ovs_context(self):
        q_driver = 'quantum.plugins.openvswitch.ovs_quantum_plugin.'\
                   'OVSQuantumPluginV2'
        q_fw_driver  = 'quantum.agent.linux.iptables_firewall.'\
                       'OVSHybridIptablesFirewallDriver'

        if get_os_codename_package('nova-common') in ['essex', 'folsom']:
            n_driver = 'nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver'
        else:
            n_driver = 'nova.virt.libvirt.vif.LibvirtGenericVIFDriver'
        n_fw_driver = 'nova.virt.firewall.NoopFirewallDriver'

        ovs_ctxt = {
            # quantum.conf
            'core_plugin': driver,
            # nova.conf
            'libvirt_vif_driver': n_driver,
            'libvirt_use_virtio_for_bridges': True,
            # ovs config
            'tenant_network_type': 'gre',
            'enable_tunneling': True,
            'tunnel_id_ranges': '1:1000',
            'local_ip': unit_private_ip(),
        }

        if relation_get('quantum_security_groups').lower() == 'yes':
            ovs_ctxt['security_group_api'] = 'quantum'
            ovs_ctxt['nova_firewall_driver'] = n_fw_driver
            ovs_ctxt['ovs_firewall_driver'] = q_fw_driver

        return ovs_ctxt

    def __call__(self):
        from nova_compute_utils import quantum_attribute

        plugin = relation_get('quantum_plugin')
        if not plugin:
            return {}
        self._ensure_pacakges(quantum_attribute(plugin, 'packages'))

        ctxt = {}

        if plugin == 'ovs':
            ctxt.update(self.ovs_context())
