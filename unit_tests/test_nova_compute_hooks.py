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

import sys
import yaml

from mock import (
    ANY,
    call,
    patch,
    MagicMock
)

from nova_compute_hooks import update_nrpe_config

# python-apt is not installed as part of test-requirements but is imported by
# some charmhelpers modules so create a fake import.
sys.modules['apt'] = MagicMock()
sys.modules['apt_pkg'] = MagicMock()

from test_utils import CharmTestCase

with patch('charmhelpers.contrib.hardening.harden.harden') as mock_dec:
    mock_dec.side_effect = (lambda *dargs, **dkwargs: lambda f:
                            lambda *args, **kwargs: f(*args, **kwargs))
    with patch("nova_compute_utils.restart_map"):
        with patch("nova_compute_utils.register_configs"):
            import nova_compute_hooks as hooks


TO_PATCH = [
    # charmhelpers.core.hookenv
    'Hooks',
    'config',
    'log',
    'is_relation_made',
    'relation_get',
    'relation_ids',
    'relation_set',
    'service_name',
    'related_units',
    'unit_get',
    'remote_service_name',
    # charmhelpers.core.host
    'apt_install',
    'apt_purge',
    'apt_update',
    'filter_installed_packages',
    'restart_on_change',
    'service_restart',
    # charmhelpers.contrib.openstack.utils
    'configure_installation_source',
    'openstack_upgrade_available',
    # nova_compute_context
    'nova_metadata_requirement',
    # nova_compute_utils
    # 'PACKAGES',
    'create_libvirt_secret',
    'restart_map',
    'determine_packages',
    'import_authorized_keys',
    'import_keystone_ca_cert',
    'initialize_ssh_keys',
    'migration_enabled',
    'do_openstack_upgrade',
    'public_ssh_key',
    'register_configs',
    'disable_shell',
    'enable_shell',
    'update_nrpe_config',
    'git_install',
    'git_install_requested',
    'network_manager',
    'libvirt_daemon',
    # misc_utils
    'ensure_ceph_keyring',
    'execd_preinstall',
    'assert_libvirt_rbd_imagebackend_allowed',
    'is_request_complete',
    'send_request_if_needed',
    'destroy_libvirt_network',
    # socket
    'gethostname',
    'create_sysctl',
    'install_hugepages',
    'uuid',
    # unitdata
    'unitdata',
    # templating
    'render',
]


class NovaComputeRelationsTests(CharmTestCase):

    def setUp(self):
        super(NovaComputeRelationsTests, self).setUp(hooks,
                                                     TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.filter_installed_packages.side_effect = \
            MagicMock(side_effect=lambda pkgs: pkgs)
        self.gethostname.return_value = 'testserver'

    def test_install_hook(self):
        repo = 'cloud:precise-grizzly'
        self.test_config.set('openstack-origin', repo)
        self.determine_packages.return_value = ['foo', 'bar']
        hooks.install()
        self.configure_installation_source.assert_called_with(repo)
        self.assertTrue(self.apt_update.called)
        self.apt_install.assert_called_with(['foo', 'bar'], fatal=True)
        self.assertTrue(self.execd_preinstall.called)

    def test_install_hook_git(self):
        self.git_install_requested.return_value = True
        self.determine_packages.return_value = ['foo', 'bar']
        repo = 'cloud:trusty-juno'
        openstack_origin_git = {
            'repositories': [
                {'name': 'requirements',
                 'repository': 'git://git.openstack.org/openstack/requirements',  # noqa
                 'branch': 'stable/juno'},
                {'name': 'nova',
                 'repository': 'git://git.openstack.org/openstack/nova',
                 'branch': 'stable/juno'}
            ],
            'directory': '/mnt/openstack-git',
        }
        projects_yaml = yaml.dump(openstack_origin_git)
        self.test_config.set('openstack-origin', repo)
        self.test_config.set('openstack-origin-git', projects_yaml)
        hooks.install()
        self.configure_installation_source.assert_called_with(repo)
        self.assertTrue(self.apt_update.called)
        self.apt_install.assert_called_with(['foo', 'bar'], fatal=True)
        self.git_install.assert_called_with(projects_yaml)
        self.assertTrue(self.execd_preinstall.called)

    @patch.object(hooks, 'ceph_changed')
    @patch.object(hooks, 'neutron_plugin_joined')
    def test_config_changed_with_upgrade(self, neutron_plugin_joined,
                                         ceph_changed):
        self.git_install_requested.return_value = False
        self.openstack_upgrade_available.return_value = True

        def rel_ids(x):
            return {'neutron-plugin': ['rid1'],
                    'ceph': ['ceph:0']}.get(x, [])
        self.relation_ids.side_effect = rel_ids
        self.related_units.return_value = ['ceph/0']
        hooks.config_changed()
        self.assertTrue(self.do_openstack_upgrade.called)
        neutron_plugin_joined.assert_called_with('rid1', remote_restart=True)
        ceph_changed.assert_called_with(rid='ceph:0', unit='ceph/0')

    @patch.object(hooks, 'git_install_requested')
    def test_config_changed_with_openstack_upgrade_action(self, git_requested):
        git_requested.return_value = False
        self.openstack_upgrade_available.return_value = True
        self.test_config.set('action-managed-upgrade', True)

        hooks.config_changed()
        self.assertFalse(self.do_openstack_upgrade.called)

    @patch.object(hooks, 'neutron_plugin_joined')
    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_migration(self, compute_joined,
                                           neutron_plugin_joined):
        self.git_install_requested.return_value = False
        self.migration_enabled.return_value = True
        _zmq_joined = self.patch('zeromq_configuration_relation_joined')
        self.test_config.set('migration-auth-type', 'ssh')
        self.relation_ids.return_value = [
            'cloud-compute:0',
            'cloud-compute:1'
        ]
        hooks.config_changed()
        ex = [
            call('cloud-compute:0'),
            call('cloud-compute:1'),
        ]
        self.assertEqual(ex, compute_joined.call_args_list)
        self.assertTrue(self.initialize_ssh_keys.called)
        self.assertTrue(_zmq_joined.called)

    @patch.object(hooks, 'neutron_plugin_joined')
    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_resize(self, compute_joined,
                                        neutron_plugin_joined):
        self.git_install_requested.return_value = False
        self.test_config.set('enable-resize', True)
        _zmq_joined = self.patch('zeromq_configuration_relation_joined')
        self.relation_ids.return_value = [
            'cloud-compute:0',
            'cloud-compute:1'
        ]
        hooks.config_changed()
        ex = [
            call('cloud-compute:0'),
            call('cloud-compute:1'),
        ]
        self.assertEqual(ex, compute_joined.call_args_list)
        self.initialize_ssh_keys.assert_called_with(user='nova')
        self.enable_shell.assert_called_with(user='nova')
        self.assertTrue(_zmq_joined.called)

    @patch.object(hooks, 'neutron_plugin_joined')
    @patch.object(hooks, 'compute_joined')
    def test_config_changed_without_resize(self, compute_joined,
                                           neutron_plugin_joined):
        self.git_install_requested.return_value = False
        self.test_config.set('enable-resize', False)
        _zmq_joined = self.patch('zeromq_configuration_relation_joined')
        self.relation_ids.return_value = [
            'cloud-compute:0',
            'cloud-compute:1'
        ]
        hooks.config_changed()
        ex = [
            call('cloud-compute:0'),
            call('cloud-compute:1'),
        ]
        self.assertEqual(ex, compute_joined.call_args_list)
        self.disable_shell.assert_called_with(user='nova')
        self.assertTrue(_zmq_joined.called)

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_no_upgrade_no_migration(self, compute_joined):
        self.git_install_requested.return_value = False
        self.openstack_upgrade_available.return_value = False
        self.migration_enabled.return_value = False
        hooks.config_changed()
        self.assertFalse(self.do_openstack_upgrade.called)
        self.assertFalse(compute_joined.called)

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_sysctl(self, compute_joined):
        self.git_install_requested.return_value = False
        self.test_config.set(
            'sysctl',
            '{ kernel.max_pid : "1337", vm.swappiness : 10 }')
        hooks.config_changed()
        self.create_sysctl.assert_called_with(
            "{kernel.max_pid: '1337', vm.swappiness: 10}\n",
            '/etc/sysctl.d/50-nova-compute.conf')

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_sysctl_swappy_default(self, compute_joined):
        self.git_install_requested.return_value = False
        self.test_config.set(
            'sysctl',
            '{ kernel.max_pid : "1337" }')
        hooks.config_changed()
        self.create_sysctl.assert_called_with(
            "{kernel.max_pid: '1337', vm.swappiness: 1}\n",
            '/etc/sysctl.d/50-nova-compute.conf')

    @patch.object(hooks, 'config_value_changed')
    def test_config_changed_git(self, config_val_changed):
        self.git_install_requested.return_value = True
        repo = 'cloud:trusty-juno'
        openstack_origin_git = {
            'repositories': [
                {'name': 'requirements',
                 'repository':
                 'git://git.openstack.org/openstack/requirements',
                 'branch': 'stable/juno'},
                {'name': 'nova',
                 'repository': 'git://git.openstack.org/openstack/nova',
                 'branch': 'stable/juno'}
            ],
            'directory': '/mnt/openstack-git',
        }
        projects_yaml = yaml.dump(openstack_origin_git)
        self.test_config.set('openstack-origin', repo)
        self.test_config.set('openstack-origin-git', projects_yaml)
        hooks.config_changed()
        self.git_install.assert_called_with(projects_yaml)
        self.assertFalse(self.do_openstack_upgrade.called)

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_no_nrpe(self, compute_joined):
        self.git_install_requested.return_value = False
        self.openstack_upgrade_available.return_value = False
        self.migration_enabled.return_value = False
        self.is_relation_made.return_value = False
        hooks.config_changed()
        self.assertFalse(self.update_nrpe_config.called)

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_nrpe(self, compute_joined):
        self.git_install_requested.return_value = False
        self.openstack_upgrade_available.return_value = False
        self.migration_enabled.return_value = False
        self.is_relation_made.return_value = True
        hooks.config_changed()
        self.assertTrue(self.update_nrpe_config.called)

    @patch('nova_compute_hooks.nrpe')
    @patch('nova_compute_hooks.services')
    @patch('charmhelpers.core.hookenv')
    def test_nrpe_services_no_qemu_kvm(self, hookenv, services, nrpe):
        '''
        The qemu-kvm service is not monitored by NRPE, since it's one-shot.
        '''
        services.return_value = ['libvirtd', 'qemu-kvm', 'libvirt-bin']
        update_nrpe_config()
        nrpe.add_init_service_checks.assert_called_with(
            ANY, ['libvirtd', 'libvirt-bin'], ANY)

    def test_amqp_joined(self):
        hooks.amqp_joined()
        self.relation_set.assert_called_with(
            username='nova', vhost='openstack',
            relation_id=None)

    @patch.object(hooks, 'CONFIGS')
    def test_amqp_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.amqp_changed()
        self.log.assert_called_with(
            'amqp relation incomplete. Peer not ready?'
        )

    def _amqp_test(self, configs, neutron=False):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['amqp']
        configs.write = MagicMock()
        hooks.amqp_changed()

    @patch.object(hooks, 'CONFIGS')
    def test_amqp_changed_with_data_no_neutron(self, configs):
        self._amqp_test(configs)
        self.assertEqual([call('/etc/nova/nova.conf')],
                         configs.write.call_args_list)

    def test_db_joined(self):
        self.unit_get.return_value = 'nova.foohost.com'
        self.is_relation_made.return_value = False
        hooks.db_joined()
        self.relation_set.assert_called_with(relation_id=None,
                                             nova_database='nova',
                                             nova_username='nova',
                                             nova_hostname='nova.foohost.com')
        self.unit_get.assert_called_with('private-address')

    def test_postgresql_db_joined(self):
        self.unit_get.return_value = 'nova.foohost.com'
        self.is_relation_made.return_value = False
        hooks.pgsql_db_joined()
        self.relation_set.assert_called_with(database='nova'),

    def test_db_joined_with_postgresql(self):
        self.is_relation_made.return_value = True

        with self.assertRaises(Exception) as context:
            hooks.db_joined()
        self.assertEqual(context.exception.message,
                         'Attempting to associate a mysql database when there '
                         'is already associated a postgresql one')

    def test_postgresql_joined_with_db(self):
        self.is_relation_made.return_value = True

        with self.assertRaises(Exception) as context:
            hooks.pgsql_db_joined()
        self.assertEqual(context.exception.message,
                         'Attempting to associate a postgresql database when'
                         ' there is already associated a mysql one')

    @patch.object(hooks, 'CONFIGS')
    def test_db_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.db_changed()
        self.log.assert_called_with(
            'shared-db relation incomplete. Peer not ready?'
        )

    @patch.object(hooks, 'CONFIGS')
    def test_postgresql_db_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.postgresql_db_changed()
        self.log.assert_called_with(
            'pgsql-db relation incomplete. Peer not ready?'
        )

    def _shared_db_test(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['shared-db']
        configs.write = MagicMock()
        hooks.db_changed()

    def _postgresql_db_test(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['pgsql-db']
        configs.write = MagicMock()
        hooks.postgresql_db_changed()

    @patch.object(hooks, 'CONFIGS')
    def test_db_changed_with_data(self, configs):
        self._shared_db_test(configs)
        self.assertEqual([call('/etc/nova/nova.conf')],
                         configs.write.call_args_list)

    @patch.object(hooks, 'CONFIGS')
    def test_postgresql_db_changed_with_data(self, configs):
        self._postgresql_db_test(configs)
        self.assertEqual([call('/etc/nova/nova.conf')],
                         configs.write.call_args_list)

    @patch.object(hooks, 'CONFIGS')
    def test_image_service_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.image_service_changed()
        self.log.assert_called_with(
            'image-service relation incomplete. Peer not ready?'
        )

    @patch.object(hooks, 'CONFIGS')
    def test_image_service_with_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.write = MagicMock()
        configs.complete_contexts.return_value = ['image-service']
        hooks.image_service_changed()
        configs.write.assert_called_with('/etc/nova/nova.conf')

    def test_compute_joined_no_migration_no_resize(self):
        self.migration_enabled.return_value = False
        hooks.compute_joined()
        self.assertFalse(self.relation_set.called)

    def test_compute_joined_with_ssh_migration(self):
        self.migration_enabled.return_value = True
        self.test_config.set('migration-auth-type', 'ssh')
        self.public_ssh_key.return_value = 'foo'
        hooks.compute_joined()
        self.relation_set.assert_called_with(
            relation_id=None,
            ssh_public_key='foo',
            migration_auth_type='ssh',
            hostname='testserver',
        )
        hooks.compute_joined(rid='cloud-compute:2')
        self.relation_set.assert_called_with(
            relation_id='cloud-compute:2',
            ssh_public_key='foo',
            migration_auth_type='ssh',
            hostname='testserver',
        )

    def test_compute_joined_with_resize(self):
        self.migration_enabled.return_value = False
        self.test_config.set('enable-resize', True)
        self.public_ssh_key.return_value = 'bar'
        hooks.compute_joined()
        self.relation_set.assert_called_with(
            relation_id=None,
            nova_ssh_public_key='bar',
            hostname='testserver',
        )
        hooks.compute_joined(rid='cloud-compute:2')
        self.relation_set.assert_called_with(
            relation_id='cloud-compute:2',
            nova_ssh_public_key='bar',
            hostname='testserver',
        )

    def test_compute_changed(self):
        hooks.compute_changed()
        self.assertTrue(self.import_keystone_ca_cert.called)
        self.import_authorized_keys.assert_has_calls([
            call(),
            call(user='nova', prefix='nova'),
        ])

    def test_compute_changed_nonstandard_authorized_keys_path(self):
        self.migration_enabled.return_value = False
        self.test_config.set('enable-resize', True)
        hooks.compute_changed()
        self.import_authorized_keys.assert_called_with(
            user='nova',
            prefix='nova',
        )

    def test_ceph_joined(self):
        self.libvirt_daemon.return_value = 'libvirt-bin'
        hooks.ceph_joined()
        self.apt_install.assert_called_with(['ceph-common'], fatal=True)
        self.service_restart.assert_called_with('libvirt-bin')
        self.libvirt_daemon.assert_called()

    @patch.object(hooks, 'CONFIGS')
    def test_ceph_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.ceph_changed()
        self.log.assert_called_with(
            'ceph relation incomplete. Peer not ready?'
        )

    @patch.object(hooks, 'CONFIGS')
    def test_ceph_changed_no_keyring(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['ceph']
        self.ensure_ceph_keyring.return_value = False
        hooks.ceph_changed()
        self.log.assert_called_with(
            'Could not create ceph keyring: peer not ready?'
        )

    @patch.object(hooks, 'mark_broker_action_done')
    @patch.object(hooks, 'is_broker_action_done')
    @patch('nova_compute_context.service_name')
    @patch.object(hooks, 'CONFIGS')
    def test_ceph_changed_with_key_and_relation_data(self, configs,
                                                     service_name,
                                                     is_broker_action_done,
                                                     mark_broker_action_done):
        self.test_config.set('libvirt-image-backend', 'rbd')
        self.is_request_complete.return_value = True
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['ceph']
        configs.write = MagicMock()
        service_name.return_value = 'nova-compute'
        self.ensure_ceph_keyring.return_value = True
        is_broker_action_done.return_value = False
        hooks.ceph_changed()
        self.assertTrue(mark_broker_action_done.called)
        ex = [
            call('/var/lib/charm/nova-compute/ceph.conf'),
            call('/etc/ceph/secret.xml'),
            call('/etc/nova/nova.conf'),
        ]
        self.assertEqual(ex, configs.write.call_args_list)
        self.service_restart.assert_called_with('nova-compute')

        is_broker_action_done.return_value = True
        mark_broker_action_done.reset_mock()
        hooks.ceph_changed()
        self.assertFalse(mark_broker_action_done.called)

    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_pool')
    def test_get_ceph_request(self, mock_create_pool,
                              mock_request_access):
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        self.test_config.set('rbd-pool', 'nova')
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 28)
        hooks.get_ceph_request()
        mock_create_pool.assert_not_called()
        mock_request_access.assert_not_called()

    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_pool')
    def test_get_ceph_request_rbd(self, mock_create_pool,
                                  mock_request_access):
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        self.test_config.set('rbd-pool', 'nova')
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 28)
        self.test_config.set('libvirt-image-backend', 'rbd')
        hooks.get_ceph_request()
        mock_create_pool.assert_called_with(name='nova', replica_count=3,
                                            weight=28,
                                            group='vms')
        mock_request_access.assert_not_called()

    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_pool')
    def test_get_ceph_request_perms(self, mock_create_pool,
                                    mock_request_access):
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        self.test_config.set('rbd-pool', 'nova')
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 28)
        self.test_config.set('libvirt-image-backend', 'rbd')
        self.test_config.set('restrict-ceph-pools', True)
        hooks.get_ceph_request()
        mock_create_pool.assert_called_with(name='nova', replica_count=3,
                                            weight=28,
                                            group='vms')
        mock_request_access.assert_has_calls([
            call(name='volumes', permission='rwx'),
            call(name='images', permission='rwx'),
            call(name='vms', permission='rwx'),
        ])

    @patch.object(hooks, 'service_restart_handler')
    @patch.object(hooks, 'CONFIGS')
    def test_neutron_plugin_changed(self, configs,
                                    service_restart_handler):
        self.nova_metadata_requirement.return_value = (True,
                                                       'sharedsecret')
        hooks.neutron_plugin_changed()
        self.assertTrue(self.apt_update.called)
        self.apt_install.assert_called_with(['nova-api-metadata'],
                                            fatal=True)
        configs.write.assert_called_with('/etc/nova/nova.conf')
        service_restart_handler.assert_called_with(
            default_service='nova-compute')

    @patch.object(hooks, 'service_restart_handler')
    @patch.object(hooks, 'CONFIGS')
    def test_neutron_plugin_changed_nometa(self, configs,
                                           service_restart_handler):
        self.nova_metadata_requirement.return_value = (False, None)
        hooks.neutron_plugin_changed()
        self.apt_purge.assert_called_with('nova-api-metadata',
                                          fatal=True)
        configs.write.assert_called_with('/etc/nova/nova.conf')
        service_restart_handler.assert_called_with(
            default_service='nova-compute')

    @patch.object(hooks, 'service_restart_handler')
    @patch.object(hooks, 'CONFIGS')
    def test_neutron_plugin_changed_meta(self, configs,
                                         service_restart_handler):
        self.nova_metadata_requirement.return_value = (True, None)
        hooks.neutron_plugin_changed()
        self.apt_install.assert_called_with(['nova-api-metadata'],
                                            fatal=True)
        configs.write.assert_called_with('/etc/nova/nova.conf')
        service_restart_handler.assert_called_with(
            default_service='nova-compute')

    @patch.object(hooks, 'get_hugepage_number')
    def test_neutron_plugin_joined_relid(self, get_hugepage_number):
        get_hugepage_number.return_value = None
        hooks.neutron_plugin_joined(relid='relid23')
        expect_rel_settings = {
            'hugepage_number': None,
            'default_availability_zone': 'nova',
        }
        self.relation_set.assert_called_with(
            relation_id='relid23',
            **expect_rel_settings
        )

    @patch.object(hooks, 'get_hugepage_number')
    def test_neutron_plugin_joined_huge(self, get_hugepage_number):
        get_hugepage_number.return_value = 12
        hooks.neutron_plugin_joined()
        expect_rel_settings = {
            'hugepage_number': 12,
            'default_availability_zone': 'nova',
        }
        self.relation_set.assert_called_with(
            relation_id=None,
            **expect_rel_settings
        )

    @patch.object(hooks, 'get_hugepage_number')
    def test_neutron_plugin_joined_remote_restart(self, get_hugepage_number):
        get_hugepage_number.return_value = None
        self.uuid.uuid4.return_value = 'e030b959-7207'
        hooks.neutron_plugin_joined(remote_restart=True)
        expect_rel_settings = {
            'hugepage_number': None,
            'restart-trigger': 'e030b959-7207',
            'default_availability_zone': 'nova',
        }
        self.relation_set.assert_called_with(
            relation_id=None,
            **expect_rel_settings
        )

    @patch.object(hooks, 'is_unit_paused_set')
    def test_service_restart_handler(self,
                                     is_unit_paused_set):
        self.relation_get.return_value = None
        mock_kv = MagicMock()
        mock_kv.get.return_value = None
        self.unitdata.kv.return_value = mock_kv

        hooks.service_restart_handler(default_service='foorbar')

        self.relation_get.assert_called_with(
            attribute='restart-nonce',
            unit=None,
            rid=None
        )
        is_unit_paused_set.assert_not_called()

    @patch.object(hooks, 'is_unit_paused_set')
    def test_service_restart_handler_with_service(self,
                                                  is_unit_paused_set):
        self.relation_get.side_effect = ['nonce', 'foobar-service']
        mock_kv = MagicMock()
        mock_kv.get.return_value = None
        self.unitdata.kv.return_value = mock_kv
        is_unit_paused_set.return_value = False

        hooks.service_restart_handler()

        self.relation_get.assert_has_calls([
            call(attribute='restart-nonce',
                 unit=None,
                 rid=None),
            call(attribute='remote-service',
                 unit=None,
                 rid=None),
        ])
        self.service_restart.assert_called_with('foobar-service')
        mock_kv.set.assert_called_with('restart-nonce',
                                       'nonce')
        self.assertTrue(mock_kv.flush.called)

    @patch.object(hooks, 'is_unit_paused_set')
    def test_service_restart_handler_when_paused(self,
                                                 is_unit_paused_set):
        self.relation_get.side_effect = ['nonce', 'foobar-service']
        mock_kv = MagicMock()
        mock_kv.get.return_value = None
        self.unitdata.kv.return_value = mock_kv
        is_unit_paused_set.return_value = True

        hooks.service_restart_handler()

        self.relation_get.assert_has_calls([
            call(attribute='restart-nonce',
                 unit=None,
                 rid=None),
        ])
        self.service_restart.assert_not_called()
        mock_kv.set.assert_called_with('restart-nonce',
                                       'nonce')
        self.assertTrue(mock_kv.flush.called)

    def test_ceph_access_incomplete(self):
        self.relation_get.return_value = None
        self.test_config.set('virt-type', 'kvm')
        hooks.ceph_access()
        self.relation_get.assert_has_calls([
            call('key', None, None),
            call('secret-uuid', None, None),
        ])
        self.render.assert_not_called()
        self.create_libvirt_secret.assert_not_called()

    def test_ceph_access_lxd(self):
        self.relation_get.side_effect = ['mykey', 'uuid2']
        self.test_config.set('virt-type', 'lxd')
        hooks.ceph_access()
        self.relation_get.assert_has_calls([
            call('key', None, None),
            call('secret-uuid', None, None),
        ])
        self.render.assert_not_called()
        self.create_libvirt_secret.assert_not_called()

    def test_ceph_access_complete(self):
        self.relation_get.side_effect = ['mykey', 'uuid2']
        self.remote_service_name.return_value = 'cinder-ceph'
        self.test_config.set('virt-type', 'kvm')
        hooks.ceph_access()
        self.relation_get.assert_has_calls([
            call('key', None, None),
            call('secret-uuid', None, None),
        ])
        self.render.assert_called_with(
            'secret.xml',
            '/etc/ceph/secret-cinder-ceph.xml',
            context={'ceph_secret_uuid': 'uuid2',
                     'service_name': 'cinder-ceph'}
        )
        self.create_libvirt_secret.assert_called_with(
            secret_file='/etc/ceph/secret-cinder-ceph.xml',
            secret_uuid='uuid2',
            key='mykey',
        )
