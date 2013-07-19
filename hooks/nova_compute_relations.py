#!/usr/bin/python

import os

from charmhelpers.core.hookenv import (
    Hooks,
    config,
    log,
    relation_ids,
    relation_set,
    service_name,
    unit_get,
)

from charmhelpers.core.host import (
    apt_install,
    apt_update,
    restart_on_change,
)

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    openstack_upgrade_available,
)

from nova_compute_utils import (
    determine_packages,
    import_authorized_keys,
    import_keystone_ca_cert,
    migration_enabled,
    configure_live_migration,
    configure_network_service,
    configure_volume_service,
    do_openstack_upgrade,
    quantum_attribute,
    quantum_enabled,
    quantum_plugin,
    public_ssh_key,
    restart_map,
    register_configs,
)

from misc_utils import (
    ensure_ceph_keyring,
)

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook()
def install():
    configure_installation_source(config('openstack-origin'))
    apt_update()
    apt_install(determine_packages(), fatal=True)


@hooks.hook('config-changed')
@restart_on_change(restart_map())
def config_changed():
    if openstack_upgrade_available('nova-common'):
        do_openstack_upgrade()

    configure_live_migration()
    if migration_enabled() and config('migration-auth-type') == 'ssh':
        # Check-in with nova-c-c and register new ssh key, if it has just been
        # generated.
        [compute_joined(rid) for rid in relation_ids('cloud-compute')]


@hooks.hook('amqp-relation-joined')
@restart_on_change(restart_map())
def amqp_joined():
    relation_set(username=config('rabbit-user'), vhost=config('rabbit-vhost'))


@hooks.hook('amqp-relation-changed')
@restart_on_change(restart_map())
def amqp_changed():
    if 'amqp' not in CONFIGS.complete_contexts():
        log('amqp relation incomplete. Peer not ready?')
        return
    CONFIGS.write('/etc/nova/nova.conf')
    if quantum_enabled():
        CONFIGS.write('/etc/quantum/quantum.conf')


@hooks.hook('shared-db-relation-joined')
def db_joined():
    relation_set(database=config('database'), username=config('database-user'),
                 hostname=unit_get('private-address'))


@hooks.hook('shared-db-relation-changed')
@restart_on_change(restart_map())
def db_changed():
    if 'shared-db' not in CONFIGS.complete_contexts():
        log('shared-db relation incomplete. Peer not ready?')
        return
    CONFIGS.write('/etc/nova/nova.conf')
    if quantum_enabled():
        plugin = quantum_plugin()
        CONFIGS.write(quantum_attribute(plugin, 'config'))


@hooks.hook('image-service-relation-changed')
@restart_on_change(restart_map())
def image_service_changed():
    if 'image-service' not in CONFIGS.complete_contexts():
        log('image-service relation incomplete. Peer not ready?')
        return
    CONFIGS.write('/etc/nova/nova.conf')


@hooks.hook('cloud-compute-relation-joined')
def compute_joined(rid=None):
    if not migration_enabled():
        return
    auth_type = config('migration-auth-type')
    settings = {
        'migration_auth_type': auth_type
    }
    if auth_type == 'ssh':
        settings['ssh_public_key'] = public_ssh_key()
    relation_set(relation_id=rid, **settings)


@hooks.hook('cloud-compute-relation-changed')
@restart_on_change(restart_map())
def compute_changed():
    configure_network_service()
    configure_volume_service()
    import_authorized_keys()
    import_keystone_ca_cert()


@hooks.hook('ceph-relation-joined')
@restart_on_change(restart_map())
def ceph_joined():
    if not os.path.isdir('/etc/ceph'):
        os.mkdir('/etc/ceph')
    apt_install('ceph-common')


@hooks.hook('ceph-relation-changed')
@restart_on_change(restart_map())
def ceph_changed():
    if 'ceph' not in CONFIGS.complete_contexts():
        log('ceph relation incomplete. Peer not ready?')
        return
    svc = service_name()
    if not ensure_ceph_keyring(service=svc):
        log('Could not create ceph keyring: peer not ready?')
        return
    CONFIGS.write('/etc/ceph/ceph.conf')
    CONFIGS.write('/etc/ceph/secret.xml')
    CONFIGS.write('/etc/nova/nova.conf')
