# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import tempfile

import nova_compute_context as compute_context
import nova_compute_utils as utils

from mock import (
    patch,
    MagicMock,
    call
)
from test_utils import (
    CharmTestCase,
    patch_open
)

VIRSH_NET_LIST = """ Name                 State      Autostart     Persistent
----------------------------------------------------------
 somenet              active     yes           yes
 default              active     yes           yes
 altnet               active     yes           yes
"""

TO_PATCH = [
    'apt_install',
    'apt_update',
    'config',
    'git_src_dir',
    'git_pip_venv_dir',
    'os_release',
    'log',
    'pip_install',
    'related_units',
    'relation_ids',
    'relation_get',
    'render',
    'service_restart',
    'mkdir',
    'install_alternative',
    'add_user_to_group',
    'MetadataServiceContext',
    'lsb_release',
    'charm_dir',
    'hugepage_support',
    'rsync',
    'Fstab',
    'os_application_version_set',
    'lsb_release',
]

openstack_origin_git = \
    """repositories:
         - {name: requirements,
            repository: 'git://git.openstack.org/openstack/requirements',
            branch: stable/juno}
         - {name: nova,
            repository: 'git://git.openstack.org/openstack/nova',
            branch: stable/juno}"""


class NovaComputeUtilsTests(CharmTestCase):

    def setUp(self):
        super(NovaComputeUtilsTests, self).setUp(utils, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.charm_dir.return_value = 'mycharm'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'precise'}

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    @patch.object(utils, 'git_install_requested')
    @patch('platform.machine')
    def test_determine_packages_nova_network(self, machine, git_requested,
                                             net_man, en_meta):
        git_requested.return_value = False
        en_meta.return_value = (False, None)
        net_man.return_value = 'flatdhcpmanager'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = []
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + [
            'nova-api',
            'nova-network',
            'nova-compute-kvm'
        ]
        self.assertEqual(ex, result)

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch.object(utils, 'git_install_requested')
    @patch('platform.machine')
    def test_determine_packages_neutron(self, machine, git_requested, net_man,
                                        n_plugin, en_meta):
        git_requested.return_value = False
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = []
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + ['nova-compute-kvm']
        self.assertEqual(ex, result)

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch.object(utils, 'git_install_requested')
    @patch('platform.machine')
    def test_determine_packages_neutron_aarch64_xenial(self, machine,
                                                       git_requested,
                                                       net_man, n_plugin,
                                                       en_meta):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'xenial'
        }
        git_requested.return_value = False
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'aarch64'
        self.relation_ids.return_value = []
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + ['nova-compute-kvm', 'qemu-efi']
        self.assertEqual(ex, result)

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch.object(utils, 'git_install_requested')
    @patch('platform.machine')
    def test_determine_packages_neutron_aarch64_trusty(self, machine,
                                                       git_requested,
                                                       net_man, n_plugin,
                                                       en_meta):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'trusty'
        }
        git_requested.return_value = False
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'aarch64'
        self.relation_ids.return_value = []
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + ['nova-compute-kvm']
        self.assertEqual(ex, result)

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch.object(utils, 'git_install_requested')
    @patch('platform.machine')
    def test_determine_packages_neutron_ceph(self, machine, git_requested,
                                             net_man, n_plugin, en_meta):
        git_requested.return_value = False
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = ['ceph:0']
        result = utils.determine_packages()
        ex = (utils.BASE_PACKAGES + ['ceph-common', 'nova-compute-kvm'])
        self.assertEqual(ex, result)

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch.object(utils, 'git_install_requested')
    def test_determine_packages_metadata(self, git_requested, net_man,
                                         n_plugin, en_meta):
        git_requested.return_value = False
        en_meta.return_value = (True, None)
        net_man.return_value = 'bob'
        n_plugin.return_value = 'ovs'
        self.relation_ids.return_value = []
        result = utils.determine_packages()
        self.assertTrue('nova-api-metadata' in result)

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_nova_network_no_multihost(self, net_man, en_meta):
        self.test_config.set('multi-host', 'no')
        en_meta.return_value = (False, None)
        net_man.return_value = 'flatdhcpmanager'
        result = utils.resource_map()
        ex = {
            '/etc/default/libvirt-bin': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/qemu.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/nova/nova.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/ceph/secret.xml': {
                'contexts': [],
                'services': []
            },
            '/var/lib/charm/nova_compute/ceph.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/default/qemu-kvm': {
                'contexts': [],
                'services': ['qemu-kvm']
            },
            '/etc/init/libvirt-bin.override': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/libvirtd.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/apparmor.d/usr.bin.nova-compute': {
                'contexts': [],
                'services': ['nova-compute']
            },
        }
        # Mocking contexts is tricky but we can still test that
        # the correct files are monitored and the correct services
        # will be started
        self.assertEqual(set(ex.keys()), set(result.keys()))
        for k in ex.keys():
            self.assertEqual(set(ex[k]['services']),
                             set(result[k]['services']))

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_nova_network(self, net_man, en_meta):

        en_meta.return_value = (False, None)
        self.test_config.set('multi-host', 'yes')
        net_man.return_value = 'flatdhcpmanager'
        result = utils.resource_map()

        ex = {
            '/etc/default/libvirt-bin': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/qemu.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/nova/nova.conf': {
                'contexts': [],
                'services': ['nova-compute', 'nova-api', 'nova-network']
            },
            '/etc/ceph/secret.xml': {
                'contexts': [],
                'services': []
            },
            '/var/lib/charm/nova_compute/ceph.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/default/qemu-kvm': {
                'contexts': [],
                'services': ['qemu-kvm']
            },
            '/etc/init/libvirt-bin.override': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/libvirtd.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/apparmor.d/usr.bin.nova-network': {
                'contexts': [],
                'services': ['nova-network']
            },
            '/etc/apparmor.d/usr.bin.nova-compute': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/apparmor.d/usr.bin.nova-api': {
                'contexts': [],
                'services': ['nova-api']
            },

        }
        # Mocking contexts is tricky but we can still test that
        # the correct files are monitored and the correct services
        # will be started
        self.assertEqual(set(ex.keys()), set(result.keys()))
        for k in ex.keys():
            self.assertEqual(set(ex[k]['services']),
                             set(result[k]['services']))

    def _test_resource_map_neutron(self, net_man, en_meta,
                                   libvirt_daemon):
        en_meta.return_value = (False, None)
        self.test_config.set('multi-host', 'yes')
        net_man.return_value = 'neutron'
        result = utils.resource_map()

        ex = {
            '/etc/default/libvirt-bin': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/libvirt/qemu.conf': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/nova/nova.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/ceph/secret.xml': {
                'contexts': [],
                'services': []
            },
            '/var/lib/charm/nova_compute/ceph.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/default/qemu-kvm': {
                'contexts': [],
                'services': ['qemu-kvm']
            },
            '/etc/init/libvirt-bin.override': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/libvirt/libvirtd.conf': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/apparmor.d/usr.bin.nova-compute': {
                'contexts': [],
                'services': ['nova-compute']
            },
        }
        # Mocking contexts is tricky but we can still test that
        # the correct files are monitored and the correct services
        # will be started
        self.assertEqual(set(ex.keys()), set(result.keys()))
        for k in ex.keys():
            self.assertEqual(set(ex[k]['services']),
                             set(result[k]['services']))

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_neutron(self, net_man, en_meta):
        self._test_resource_map_neutron(net_man, en_meta, 'libvirt-bin')

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_neutron_yakkety(self, net_man, en_meta,):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'yakkety'}
        self._test_resource_map_neutron(net_man, en_meta, 'libvirtd')

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    def test_resource_map_metadata(self, net_man, _plugin, _metadata):
        _metadata.return_value = (True, None)
        net_man.return_value = 'bob'
        _plugin.return_value = 'ovs'
        self.relation_ids.return_value = []
        result = utils.resource_map()['/etc/nova/nova.conf']['services']
        self.assertTrue('nova-api-metadata' in result)

    def fake_user(self, username='foo'):
        user = MagicMock()
        user.pw_dir = '/home/' + username
        return user

    @patch('__builtin__.open')
    @patch('pwd.getpwnam')
    def test_public_ssh_key_not_found(self, getpwnam, _open):
        _open.side_effect = Exception
        getpwnam.return_value = self.fake_user('foo')
        self.assertEqual(None, utils.public_ssh_key())

    @patch('pwd.getpwnam')
    def test_public_ssh_key(self, getpwnam):
        getpwnam.return_value = self.fake_user('foo')
        with patch_open() as (_open, _file):
            _file.read.return_value = 'mypubkey'
            result = utils.public_ssh_key('foo')
        self.assertEqual(result, 'mypubkey')

    def test_import_authorized_keys_missing_data(self):
        self.relation_get.return_value = None
        with patch_open() as (_open, _file):
            utils.import_authorized_keys(user='foo')
            self.assertFalse(_open.called)

    @patch('pwd.getpwnam')
    def _test_import_authorized_keys_base(self, getpwnam, prefix=None,
                                          auth_key_path='/home/foo/.ssh/'
                                                        'authorized_keys'):
        getpwnam.return_value = self.fake_user('foo')
        self.relation_get.side_effect = [
            3,          # relation_get('known_hosts_max_index')
            'k_h_0',    # relation_get_('known_hosts_0')
            'k_h_1',    # relation_get_('known_hosts_1')
            'k_h_2',    # relation_get_('known_hosts_2')
            3,          # relation_get('authorized_keys_max_index')
            'auth_0',   # relation_get('authorized_keys_0')
            'auth_1',   # relation_get('authorized_keys_1')
            'auth_2',   # relation_get('authorized_keys_2')
        ]

        ex_open = [
            call('/home/foo/.ssh/known_hosts', 'wb'),
            call(auth_key_path, 'wb')
        ]
        ex_write = [
            call('k_h_0\n'),
            call('k_h_1\n'),
            call('k_h_2\n'),
            call('auth_0\n'),
            call('auth_1\n'),
            call('auth_2\n')
        ]

        with patch_open() as (_open, _file):
            utils.import_authorized_keys(user='foo', prefix=prefix)
            self.assertEqual(ex_open, _open.call_args_list)
            self.assertEqual(ex_write, _file.write.call_args_list)
            authkey_root = 'authorized_keys_'
            known_hosts_root = 'known_hosts_'
            if prefix:
                authkey_root = prefix + '_authorized_keys_'
                known_hosts_root = prefix + '_known_hosts_'
            expected_relations = [
                call(known_hosts_root + 'max_index'),
                call(known_hosts_root + '0'),
                call(known_hosts_root + '1'),
                call(known_hosts_root + '2'),
                call(authkey_root + 'max_index'),
                call(authkey_root + '0'),
                call(authkey_root + '1'),
                call(authkey_root + '2')
            ]
            self.assertEqual(sorted(self.relation_get.call_args_list),
                             sorted(expected_relations))

    def test_import_authorized_keys_noprefix(self):
        self._test_import_authorized_keys_base()

    def test_import_authorized_keys_prefix(self):
        self._test_import_authorized_keys_base(prefix='bar')

    def test_import_authorized_keys_authkeypath(self):
        nonstandard_path = '/etc/ssh/user-authorized-keys/{username}'
        self.test_config.set('authorized-keys-path', nonstandard_path)
        self._test_import_authorized_keys_base(
            auth_key_path='/etc/ssh/user-authorized-keys/foo')

    @patch('subprocess.check_call')
    def test_import_keystone_cert_missing_data(self, check_call):
        self.relation_get.return_value = None
        with patch_open() as (_open, _file):
            utils.import_keystone_ca_cert()
            self.assertFalse(_open.called)
        self.assertFalse(check_call.called)

    @patch.object(utils, 'check_call')
    def test_import_keystone_cert(self, check_call):
        self.relation_get.return_value = 'Zm9vX2NlcnQK'
        with patch_open() as (_open, _file):
            utils.import_keystone_ca_cert()
            _open.assert_called_with(utils.CA_CERT_PATH, 'wb')
            _file.write.assert_called_with('foo_cert\n')
        check_call.assert_called_with(['update-ca-certificates'])

    @patch.object(utils, 'ceph_config_file')
    @patch('charmhelpers.contrib.openstack.templating.OSConfigRenderer')
    @patch.object(utils, 'resource_map')
    def test_register_configs(self, resource_map, renderer,
                              mock_ceph_config_file):
        self.os_release.return_value = 'havana'
        fake_renderer = MagicMock()
        fake_renderer.register = MagicMock()
        renderer.return_value = fake_renderer
        ctxt1 = MagicMock()
        ctxt2 = MagicMock()
        rsc_map = {
            '/etc/nova/nova.conf': {
                'services': ['nova-compute'],
                'contexts': [ctxt1],
            },
            '/etc/nova/nova-compute.conf': {
                'services': ['nova-compute'],
                'contexts': [ctxt2],
            },
        }
        resource_map.return_value = rsc_map
        with tempfile.NamedTemporaryFile() as tmpfile:
            mock_ceph_config_file.return_value = tmpfile.name
            utils.register_configs()
            renderer.assert_called_with(
                openstack_release='havana', templates_dir='templates/')
            ex_reg = [
                call('/etc/nova/nova-compute.conf', [ctxt2]),
                call('/etc/nova/nova.conf', [ctxt1])
            ]
            self.assertEqual(fake_renderer.register.call_args_list, ex_reg)

    @patch.object(utils, 'check_call')
    def test_enable_shell(self, _check_call):
        utils.enable_shell('dummy')
        _check_call.assert_called_with(['usermod', '-s', '/bin/bash', 'dummy'])

    @patch.object(utils, 'check_call')
    def test_disable_shell(self, _check_call):
        utils.disable_shell('dummy')
        _check_call.assert_called_with(['usermod', '-s', '/bin/false',
                                        'dummy'])

    @patch.object(utils, 'check_call')
    def test_configure_subuid(self, _check_call):
        utils.configure_subuid('dummy')
        _check_call.assert_called_with(['usermod', '-v', '100000-200000',
                                        '-w', '100000-200000', 'dummy'])

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_create_libvirt_key(self, _check_output, _check_call):
        key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        self.test_config.set('virt-type', 'kvm')
        utils.create_libvirt_secret(utils.CEPH_SECRET,
                                    compute_context.CEPH_SECRET_UUID, key)
        _check_output.assert_called_with(['virsh', '-c',
                                          utils.LIBVIRT_URIS['kvm'],
                                          'secret-list'])
        _check_call.assert_called_with(['virsh', '-c',
                                        utils.LIBVIRT_URIS['kvm'],
                                        'secret-set-value', '--secret',
                                        compute_context.CEPH_SECRET_UUID,
                                        '--base64', key])

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_create_libvirt_key_existing(self, _check_output, _check_call):
        key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        old_key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg==\n'
        self.test_config.set('virt-type', 'kvm')
        _check_output.side_effect = [compute_context.CEPH_SECRET_UUID,
                                     old_key]
        utils.create_libvirt_secret(utils.CEPH_SECRET,
                                    compute_context.CEPH_SECRET_UUID, key)
        expected = [call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-list']),
                    call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-get-value',
                          compute_context.CEPH_SECRET_UUID])]
        _check_output.assert_has_calls(expected)
        self.assertFalse(_check_call.called)

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_create_libvirt_key_stale(self, _check_output, _check_call):
        key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        old_key = 'CCCCCdRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        self.test_config.set('virt-type', 'kvm')
        _check_output.side_effect = [compute_context.CEPH_SECRET_UUID, old_key]
        utils.create_libvirt_secret(utils.CEPH_SECRET,
                                    compute_context.CEPH_SECRET_UUID, key)
        expected = [call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-list']),
                    call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-get-value',
                          compute_context.CEPH_SECRET_UUID])]
        _check_output.assert_has_calls(expected)
        _check_call.assert_any_call(['virsh', '-c',
                                     utils.LIBVIRT_URIS['kvm'],
                                     'secret-set-value', '--secret',
                                     compute_context.CEPH_SECRET_UUID,
                                     '--base64', key])

    @patch.object(utils, 'lxc_list')
    @patch.object(utils, 'configure_subuid')
    def test_configure_lxd_vivid(self, _configure_subuid, _lxc_list):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'vivid'
        }
        utils.configure_lxd('nova')
        _configure_subuid.assert_called_with('nova')
        _lxc_list.assert_called_with('nova')

    @patch.object(utils, 'git_install_requested')
    @patch.object(utils, 'lxc_list')
    @patch.object(utils, 'configure_subuid')
    def test_configure_lxd_pre_vivid(self, _configure_subuid, _lxc_list,
                                     _git_install):
        _git_install.return_value = False
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'trusty'
        }
        with self.assertRaises(Exception):
            utils.configure_lxd('nova')
        self.assertFalse(_configure_subuid.called)

    @patch.object(utils, 'git_install_requested')
    @patch.object(utils, 'git_clone_and_install')
    @patch.object(utils, 'git_post_install')
    @patch.object(utils, 'git_pre_install')
    def test_git_install(self, git_pre, git_post, git_clone_and_install,
                         git_requested):
        projects_yaml = openstack_origin_git
        git_requested.return_value = True
        utils.git_install(projects_yaml)
        self.assertTrue(git_pre.called)
        git_clone_and_install.assert_called_with(openstack_origin_git,
                                                 core_project='nova')
        self.assertTrue(git_post.called)

    @patch.object(utils, 'mkdir')
    @patch.object(utils, 'write_file')
    @patch.object(utils, 'add_user_to_group')
    @patch.object(utils, 'add_group')
    @patch.object(utils, 'adduser')
    @patch.object(utils, 'check_call')
    def test_git_pre_install(self, check_call, adduser, add_group,
                             add_user_to_group, write_file, mkdir):
        utils.git_pre_install()
        adduser.assert_called_with('nova', shell='/bin/bash',
                                   system_user=True)
        check_call.assert_called_with(['usermod', '--home', '/var/lib/nova',
                                       'nova'])
        add_group.assert_called_with('nova', system_group=True)
        expected = [
            call('nova', 'nova'),
            call('nova', 'libvirtd'),
        ]
        self.assertEqual(add_user_to_group.call_args_list, expected)
        expected = [
            call('/var/lib/nova', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/buckets', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/CA', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/CA/INTER', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/CA/newcerts', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/CA/private', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/CA/reqs', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/images', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/instances', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/keys', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/networks', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/lib/nova/tmp', owner='nova',
                 group='nova', perms=0755, force=False),
            call('/var/log/nova', owner='nova',
                 group='nova', perms=0755, force=False),
        ]
        self.assertEqual(mkdir.call_args_list, expected)
        expected = [
            call('/var/log/nova/nova-api.log', '', owner='nova',
                 group='nova', perms=0644),
            call('/var/log/nova/nova-compute.log', '', owner='nova',
                 group='nova', perms=0644),
            call('/var/log/nova/nova-manage.log', '', owner='nova',
                 group='nova', perms=0644),
            call('/var/log/nova/nova-network.log', '', owner='nova',
                 group='nova', perms=0644),
        ]
        self.assertEqual(write_file.call_args_list, expected)

    @patch('os.path.join')
    @patch('os.path.exists')
    @patch('os.symlink')
    @patch('shutil.copytree')
    @patch('shutil.rmtree')
    @patch('subprocess.check_call')
    def test_git_post_install_upstart(self, check_call, rmtree, copytree,
                                      symlink, exists, join):
        projects_yaml = openstack_origin_git
        join.return_value = 'joined-string'
        self.lsb_release.return_value = {'DISTRIB_RELEASE': '15.04'}
        self.git_pip_venv_dir.return_value = '/mnt/openstack-git/venv'
        utils.git_post_install(projects_yaml)
        expected = [
            call('joined-string', '/etc/nova'),
        ]
        copytree.assert_has_calls(expected)
        expected = [
            call('joined-string', '/usr/local/bin/nova-rootwrap'),
        ]
        symlink.assert_has_calls(expected, any_order=True)

        service_name = 'nova-compute'
        nova_user = 'nova'
        start_dir = '/var/lib/nova'
        nova_conf = '/etc/nova/nova.conf'
        nova_api_metadata_context = {
            'service_description': 'Nova Metadata API server',
            'service_name': service_name,
            'user_name': nova_user,
            'start_dir': start_dir,
            'process_name': 'nova-api-metadata',
            'executable_name': 'joined-string',
            'config_files': [nova_conf],
        }
        nova_api_context = {
            'service_description': 'Nova API server',
            'service_name': service_name,
            'user_name': nova_user,
            'start_dir': start_dir,
            'process_name': 'nova-api',
            'executable_name': 'joined-string',
            'config_files': [nova_conf],
        }
        nova_compute_context = {
            'service_description': 'Nova compute worker',
            'service_name': service_name,
            'user_name': nova_user,
            'process_name': 'nova-compute',
            'executable_name': 'joined-string',
            'config_files': [nova_conf, '/etc/nova/nova-compute.conf'],
        }
        nova_network_context = {
            'service_description': 'Nova network worker',
            'service_name': service_name,
            'user_name': nova_user,
            'start_dir': start_dir,
            'process_name': 'nova-network',
            'executable_name': 'joined-string',
            'config_files': [nova_conf],
        }
        expected = [
            call('git/nova-compute-kvm.conf', '/etc/nova/nova-compute.conf',
                 {}, perms=0o644),
            call('git/nova_sudoers', '/etc/sudoers.d/nova_sudoers',
                 {}, perms=0o440),
            call('git.upstart', '/etc/init/nova-api-metadata.conf',
                 nova_api_metadata_context, perms=0o644,
                 templates_dir='joined-string'),
            call('git.upstart', '/etc/init/nova-api.conf',
                 nova_api_context, perms=0o644,
                 templates_dir='joined-string'),
            call('git/upstart/nova-compute.upstart',
                 '/etc/init/nova-compute.conf',
                 nova_compute_context, perms=420),
            call('git.upstart', '/etc/init/nova-network.conf',
                 nova_network_context, perms=0o644,
                 templates_dir='joined-string'),
        ]
        self.assertEqual(self.render.call_args_list, expected)
        self.assertTrue(self.apt_update.called)
        self.apt_install.assert_called_with(
            ['bridge-utils', 'dnsmasq-base',
             'dnsmasq-utils', 'ebtables', 'genisoimage', 'iptables',
             'iputils-arping', 'kpartx', 'kvm', 'netcat', 'open-iscsi',
             'parted', 'python-libvirt', 'qemu', 'qemu-system',
             'qemu-utils', 'vlan', 'xen-system-amd64'], fatal=True)

    @patch('os.listdir')
    @patch('os.path.join')
    @patch('os.path.exists')
    @patch('os.symlink')
    @patch('shutil.copytree')
    @patch('shutil.rmtree')
    @patch('subprocess.check_call')
    def test_git_post_install_systemd(self, check_call, rmtree, copytree,
                                      symlink, exists, join, listdir):
        projects_yaml = openstack_origin_git
        join.return_value = 'joined-string'
        self.lsb_release.return_value = {'DISTRIB_RELEASE': '15.10'}
        self.git_pip_venv_dir.return_value = '/mnt/openstack-git/venv'
        utils.git_post_install(projects_yaml)
        expected = [
            call('git/nova-compute-kvm.conf', '/etc/nova/nova-compute.conf',
                 {}, perms=420),
            call('git/nova_sudoers', '/etc/sudoers.d/nova_sudoers',
                 {}, perms=288),
            call('git/nova-api.init.in.template', 'joined-string',
                 {'daemon_path': 'joined-string'}, perms=420),
            call('git/nova-api-metadata.init.in.template', 'joined-string',
                 {'daemon_path': 'joined-string'}, perms=420),
            call('git/nova-compute.init.in.template', 'joined-string',
                 {'daemon_path': 'joined-string'}, perms=420),
            call('git/nova-network.init.in.template', 'joined-string',
                 {'daemon_path': 'joined-string'}, perms=420),
        ]
        self.assertEqual(self.render.call_args_list, expected)

    @patch('psutil.virtual_memory')
    @patch('subprocess.check_call')
    @patch('subprocess.call')
    def test_install_hugepages(self, _call, _check_call, _virt_mem):
        class mem(object):
            def __init__(self):
                self.total = 10000000
        self.test_config.set('hugepages', '10%')
        _virt_mem.side_effect = mem
        _call.return_value = 1
        utils.install_hugepages()
        self.hugepage_support.assert_called_with(
            'nova',
            mnt_point='/run/hugepages/kvm',
            group='root',
            nr_hugepages=488,
            mount=False,
            set_shmmax=True,
        )
        check_call_calls = [
            call('/etc/init.d/qemu-hugefsdir'),
            call(['update-rc.d', 'qemu-hugefsdir', 'defaults']),
        ]
        _check_call.assert_has_calls(check_call_calls)
        self.Fstab.remove_by_mountpoint.assert_called_with(
            '/run/hugepages/kvm')

    @patch('psutil.virtual_memory')
    @patch('subprocess.check_call')
    @patch('subprocess.call')
    def test_install_hugepages_explicit_size(self, _call, _check_call,
                                             _virt_mem):
        self.test_config.set('hugepages', '2048')
        utils.install_hugepages()
        self.hugepage_support.assert_called_with(
            'nova',
            mnt_point='/run/hugepages/kvm',
            group='root',
            nr_hugepages=2048,
            mount=False,
            set_shmmax=True,
        )

    def test_assess_status(self):
        with patch.object(utils, 'assess_status_func') as asf:
            callee = MagicMock()
            asf.return_value = callee
            utils.assess_status('test-config')
            asf.assert_called_once_with('test-config')
            callee.assert_called_once_with()
            self.os_application_version_set.assert_called_with(
                utils.VERSION_PACKAGE
            )

    @patch.object(utils, 'REQUIRED_INTERFACES')
    @patch.object(utils, 'services')
    @patch.object(utils, 'make_assess_status_func')
    @patch.object(utils, 'get_optional_relations')
    def test_assess_status_func(self,
                                get_optional_relations,
                                make_assess_status_func,
                                services,
                                REQUIRED_INTERFACES):
        services.return_value = 's1'
        REQUIRED_INTERFACES.copy.return_value = {'test-interface': True}
        get_optional_relations.return_value = {'optional': False}
        test_interfaces = {
            'test-interface': True,
            'optional': False,
        }
        utils.assess_status_func('test-config')
        # ports=None whilst port checks are disabled.
        make_assess_status_func.assert_called_once_with(
            'test-config', test_interfaces, services='s1', ports=None)

    def test_pause_unit_helper(self):
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.pause_unit_helper('random-config')
            prh.assert_called_once_with(utils.pause_unit, 'random-config')
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.resume_unit_helper('random-config')
            prh.assert_called_once_with(utils.resume_unit, 'random-config')

    @patch.object(utils, 'services')
    def test_pause_resume_helper(self, services):
        f = MagicMock()
        services.return_value = 's1'
        with patch.object(utils, 'assess_status_func') as asf:
            asf.return_value = 'assessor'
            utils._pause_resume_helper(f, 'some-config')
            asf.assert_called_once_with('some-config')
            # ports=None whilst port checks are disabled.
            f.assert_called_once_with('assessor', services='s1', ports=None)

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_destroy_libvirt_network(self, mock_check_output, mock_check_call):
        mock_check_output.return_value = VIRSH_NET_LIST
        utils.destroy_libvirt_network('default')
        cmd = ['virsh', 'net-destroy', 'default']
        mock_check_call.assert_has_calls([call(cmd)])

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_destroy_libvirt_network_no_exist(self, mock_check_output,
                                              mock_check_call):
        mock_check_output.return_value = VIRSH_NET_LIST
        utils.destroy_libvirt_network('defaultX')
        self.assertFalse(mock_check_call.called)

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_destroy_libvirt_network_no_virsh(self, mock_check_output,
                                              mock_check_call):
        mock_check_output.side_effect = OSError(2, 'No such file')
        utils.destroy_libvirt_network('default')

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_destroy_libvirt_network_no_virsh_unknown_error(self,
                                                            mock_check_output,
                                                            mock_check_call):
        mock_check_output.side_effect = OSError(100, 'Break things')
        with self.assertRaises(OSError):
            utils.destroy_libvirt_network('default')

    def test_libvirt_daemon_yakkety(self):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'yakkety'
        }
        self.assertEqual(utils.libvirt_daemon(), utils.LIBVIRTD_DAEMON)

    def test_libvirt_daemon_preyakkety(self):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'xenial'
        }
        self.assertEqual(utils.libvirt_daemon(), utils.LIBVIRT_BIN_DAEMON)
