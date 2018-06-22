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

import os
import re
import shutil
import pwd
import subprocess
import platform

from itertools import chain
from base64 import b64decode
from copy import deepcopy
from subprocess import (
    check_call,
    check_output,
    CalledProcessError
)

from charmhelpers.fetch import (
    apt_update,
    apt_upgrade,
    apt_install,
)

from charmhelpers.core.fstab import Fstab
from charmhelpers.core.host import (
    adduser,
    add_group,
    add_user_to_group,
    mkdir,
    service_restart,
    lsb_release,
    write_file,
)

from charmhelpers.core.hookenv import (
    charm_dir,
    config,
    log,
    related_units,
    relation_ids,
    relation_get,
    status_set,
    DEBUG,
    INFO,
    WARNING,
)

from charmhelpers.core.templating import render
from charmhelpers.core.decorators import retry_on_exception
from charmhelpers.contrib.openstack import templating, context
from charmhelpers.contrib.openstack.alternatives import install_alternative

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    get_os_codename_install_source,
    git_clone_and_install,
    git_default_repos,
    git_generate_systemd_init_files,
    git_install_requested,
    git_pip_venv_dir,
    git_src_dir,
    git_yaml_value,
    os_release,
    is_unit_paused_set,
    make_assess_status_func,
    pause_unit,
    resume_unit,
    os_application_version_set,
)

from charmhelpers.contrib.python.packages import (
    pip_install,
)

from charmhelpers.core.hugepage import hugepage_support
from charmhelpers.core.host import (
    rsync,
)

from nova_compute_context import (
    nova_metadata_requirement,
    CloudComputeContext,
    MetadataServiceContext,
    NovaComputeLibvirtContext,
    NovaComputeLibvirtOverrideContext,
    NovaComputeCephContext,
    NeutronComputeContext,
    InstanceConsoleContext,
    CEPH_CONF,
    ceph_config_file,
    HostIPContext,
    DesignateContext,
    NovaComputeVirtContext,
    NOVA_API_AA_PROFILE,
    NOVA_COMPUTE_AA_PROFILE,
    NOVA_NETWORK_AA_PROFILE,
    NovaAPIAppArmorContext,
    NovaComputeAppArmorContext,
    NovaNetworkAppArmorContext,
    SerialConsoleContext,
    NovaComputeAvailabilityZoneContext,
)

CA_CERT_PATH = '/usr/local/share/ca-certificates/keystone_juju_ca_cert.crt'

TEMPLATES = 'templates/'

BASE_PACKAGES = [
    'nova-compute',
    'genisoimage',  # was missing as a package dependency until raring.
    'librbd1',  # bug 1440953
    'python-six',
    'python-psutil',
]

VERSION_PACKAGE = 'nova-common'

BASE_GIT_PACKAGES = [
    'libffi-dev',
    'libssl-dev',
    'libvirt-bin',
    'libxml2-dev',
    'libxslt1-dev',
    'libvirt-dev',
    'libyaml-dev',
    'openstack-pkg-tools',
    'python-dev',
    'python-pip',
    'python-setuptools',
    'zlib1g-dev',
]

LATE_GIT_PACKAGES = [
    'bridge-utils',
    'dnsmasq-base',
    'dnsmasq-utils',
    'ebtables',
    'genisoimage',
    'iptables',
    'iputils-arping',
    'kpartx',
    'kvm',
    'netcat',
    'open-iscsi',
    'parted',
    'python-libvirt',
    'qemu',
    'qemu-system',
    'qemu-utils',
    'vlan',
    'xen-system-amd64',
]

# ubuntu packages that should not be installed when deploying from git
GIT_PACKAGE_BLACKLIST = [
    'neutron-plugin-openvswitch',
    'neutron-plugin-openvswitch-agent',
    'neutron-server',
    'nova-api',
    'nova-api-metadata',
    'nova-compute',
    'nova-compute-kvm',
    'nova-compute-lxc',
    'nova-compute-lxd',
    'nova-compute-qemu',
    'nova-compute-uml',
    'nova-compute-xen',
    'nova-network',
    'python-six',
    'quantum-plugin-openvswitch',
    'quantum-plugin-openvswitch-agent',
    'quantum-server',
]

DEFAULT_INSTANCE_PATH = '/var/lib/nova/instances'
NOVA_CONF_DIR = "/etc/nova"
QEMU_CONF = '/etc/libvirt/qemu.conf'
LIBVIRTD_CONF = '/etc/libvirt/libvirtd.conf'
LIBVIRT_BIN = '/etc/default/libvirt-bin'
LIBVIRT_BIN_OVERRIDES = '/etc/init/libvirt-bin.override'
NOVA_CONF = '%s/nova.conf' % NOVA_CONF_DIR
QEMU_KVM = '/etc/default/qemu-kvm'
NOVA_API_AA_PROFILE_PATH = ('/etc/apparmor.d/{}'.format(NOVA_API_AA_PROFILE))
NOVA_COMPUTE_AA_PROFILE_PATH = ('/etc/apparmor.d/{}'
                                ''.format(NOVA_COMPUTE_AA_PROFILE))
NOVA_NETWORK_AA_PROFILE_PATH = ('/etc/apparmor.d/{}'
                                ''.format(NOVA_NETWORK_AA_PROFILE))


BASE_RESOURCE_MAP = {
    NOVA_CONF: {
        'services': ['nova-compute'],
        'contexts': [context.AMQPContext(ssl_dir=NOVA_CONF_DIR),
                     context.SharedDBContext(
                         relation_prefix='nova', ssl_dir=NOVA_CONF_DIR),
                     context.PostgresqlDBContext(),
                     context.ImageServiceContext(),
                     context.OSConfigFlagContext(),
                     CloudComputeContext(),
                     NovaComputeLibvirtContext(),
                     NovaComputeCephContext(),
                     context.SyslogContext(),
                     context.SubordinateConfigContext(
                         interface=['neutron-plugin', 'nova-ceilometer',
                                    'ephemeral-backend'],
                         service=['nova-compute', 'nova'],
                         config_file=NOVA_CONF),
                     InstanceConsoleContext(),
                     context.ZeroMQContext(),
                     context.NotificationDriverContext(),
                     MetadataServiceContext(),
                     HostIPContext(),
                     DesignateContext(),
                     NovaComputeVirtContext(),
                     context.LogLevelContext(),
                     context.InternalEndpointContext(),
                     SerialConsoleContext(),
                     NovaComputeAvailabilityZoneContext()],
    },
    NOVA_API_AA_PROFILE_PATH: {
        'services': ['nova-api'],
        'contexts': [NovaAPIAppArmorContext()],
    },
    NOVA_COMPUTE_AA_PROFILE_PATH: {
        'services': ['nova-compute'],
        'contexts': [NovaComputeAppArmorContext()],
    },
    NOVA_NETWORK_AA_PROFILE_PATH: {
        'services': ['nova-network'],
        'contexts': [NovaNetworkAppArmorContext()],
    },
}

LIBVIRTD_DAEMON = 'libvirtd'
LIBVIRT_BIN_DAEMON = 'libvirt-bin'

LIBVIRT_RESOURCE_MAP = {
    QEMU_CONF: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtContext()],
    },
    QEMU_KVM: {
        'services': ['qemu-kvm'],
        'contexts': [NovaComputeLibvirtContext()],
    },
    LIBVIRTD_CONF: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtContext()],
    },
    LIBVIRT_BIN: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtContext()],
    },
    LIBVIRT_BIN_OVERRIDES: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtOverrideContext()],
    },
}
LIBVIRT_RESOURCE_MAP.update(BASE_RESOURCE_MAP)

CEPH_SECRET = '/etc/ceph/secret.xml'
CEPH_BACKEND_SECRET = '/etc/ceph/secret-{}.xml'

CEPH_RESOURCES = {
    CEPH_SECRET: {
        'contexts': [NovaComputeCephContext()],
        'services': [],
    }
}

# Maps virt-type config to a compute package(s).
VIRT_TYPES = {
    'kvm': ['nova-compute-kvm'],
    'qemu': ['nova-compute-qemu'],
    'xen': ['nova-compute-xen'],
    'uml': ['nova-compute-uml'],
    'lxc': ['nova-compute-lxc'],
    'lxd': ['nova-compute-lxd'],
}

# Maps virt-type config to a libvirt URI.
LIBVIRT_URIS = {
    'kvm': 'qemu:///system',
    'qemu': 'qemu:///system',
    'xen': 'xen:///',
    'uml': 'uml:///system',
    'lxc': 'lxc:///',
}

# The interface is said to be satisfied if anyone of the interfaces in the
# list has a complete context.
REQUIRED_INTERFACES = {
    'messaging': ['amqp', 'zeromq-configuration'],
    'image': ['image-service'],
}


def libvirt_daemon():
    '''Resolve the correct name of the libvirt daemon service'''
    distro_codename = lsb_release()['DISTRIB_CODENAME'].lower()
    if distro_codename >= 'yakkety':
        return LIBVIRTD_DAEMON
    else:
        return LIBVIRT_BIN_DAEMON


def resource_map():
    '''
    Dynamically generate a map of resources that will be managed for a single
    hook execution.
    '''
    # TODO: Cache this on first call?
    if config('virt-type').lower() == 'lxd':
        resource_map = deepcopy(BASE_RESOURCE_MAP)
    else:
        resource_map = deepcopy(LIBVIRT_RESOURCE_MAP)
    net_manager = network_manager()

    # Network manager gets set late by the cloud-compute interface.
    # FlatDHCPManager only requires some extra packages.
    if (net_manager in ['flatmanager', 'flatdhcpmanager'] and
            config('multi-host').lower() == 'yes'):
        resource_map[NOVA_CONF]['services'].extend(
            ['nova-api', 'nova-network']
        )
    else:
        resource_map.pop(NOVA_API_AA_PROFILE_PATH)
        resource_map.pop(NOVA_NETWORK_AA_PROFILE_PATH)

    distro_codename = lsb_release()['DISTRIB_CODENAME'].lower()
    if distro_codename >= 'yakkety':
        for data in resource_map.values():
            if LIBVIRT_BIN_DAEMON in data['services']:
                data['services'].remove(LIBVIRT_BIN_DAEMON)
                data['services'].append(LIBVIRTD_DAEMON)

    # Neutron/quantum requires additional contexts, as well as new resources
    # depending on the plugin used.
    # NOTE(james-page): only required for ovs plugin right now
    if net_manager in ['neutron', 'quantum']:
        resource_map[NOVA_CONF]['contexts'].append(NeutronComputeContext())

    if relation_ids('ceph'):
        CEPH_RESOURCES[ceph_config_file()] = {
            'contexts': [NovaComputeCephContext()],
            'services': ['nova-compute']
        }
        resource_map.update(CEPH_RESOURCES)

    enable_nova_metadata, _ = nova_metadata_requirement()
    if enable_nova_metadata:
        resource_map[NOVA_CONF]['services'].append('nova-api-metadata')
    return resource_map


def restart_map():
    '''
    Constructs a restart map based on charm config settings and relation
    state.
    '''
    return {k: v['services'] for k, v in resource_map().iteritems()}


def services():
    ''' Returns a list of services associated with this charm '''
    return list(set(chain(*restart_map().itervalues())))


def register_configs():
    '''
    Returns an OSTemplateRenderer object with all required configs registered.
    '''
    release = os_release('nova-common')
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    if relation_ids('ceph'):
        # Add charm ceph configuration to resources and
        # ensure directory actually exists
        mkdir(os.path.dirname(ceph_config_file()))
        mkdir(os.path.dirname(CEPH_CONF))
        # Install ceph config as an alternative for co-location with
        # ceph and ceph-osd charms - nova-compute ceph.conf will be
        # lower priority that both of these but thats OK
        if not os.path.exists(ceph_config_file()):
            # touch file for pre-templated generation
            open(ceph_config_file(), 'w').close()
        install_alternative(os.path.basename(CEPH_CONF),
                            CEPH_CONF, ceph_config_file())

    for cfg, d in resource_map().iteritems():
        configs.register(cfg, d['contexts'])
    return configs


def determine_packages_arch():
    '''Generate list of architecture-specific packages'''
    packages = []
    distro_codename = lsb_release()['DISTRIB_CODENAME'].lower()
    if platform.machine() == 'aarch64' and distro_codename >= 'wily':
        packages.extend(['qemu-efi']),  # AArch64 cloud images require UEFI fw

    return packages


def determine_packages():
    packages = [] + BASE_PACKAGES

    net_manager = network_manager()
    if (net_manager in ['flatmanager', 'flatdhcpmanager'] and
            config('multi-host').lower() == 'yes'):
        packages.extend(['nova-api', 'nova-network'])

    if relation_ids('ceph'):
        packages.append('ceph-common')

    virt_type = config('virt-type')
    try:
        packages.extend(VIRT_TYPES[virt_type])
    except KeyError:
        log('Unsupported virt-type configured: %s' % virt_type)
        raise
    enable_nova_metadata, _ = nova_metadata_requirement()
    if enable_nova_metadata:
        packages.append('nova-api-metadata')

    packages.extend(determine_packages_arch())

    if git_install_requested():
        packages = list(set(packages))
        packages.extend(BASE_GIT_PACKAGES)
        # don't include packages that will be installed from git
        for p in GIT_PACKAGE_BLACKLIST:
            if p in packages:
                packages.remove(p)

    return packages


def migration_enabled():
    # XXX: confirm juju-core bool behavior is the same.
    return config('enable-live-migration')


def _network_config():
    '''
    Obtain all relevant network configuration settings from nova-c-c via
    cloud-compute interface.
    '''
    settings = ['network_manager', 'neutron_plugin', 'quantum_plugin']
    net_config = {}
    for rid in relation_ids('cloud-compute'):
        for unit in related_units(rid):
            for setting in settings:
                value = relation_get(setting, rid=rid, unit=unit)
                if value:
                    net_config[setting] = value
    return net_config


def neutron_plugin():
    return (_network_config().get('neutron_plugin') or
            _network_config().get('quantum_plugin'))


def network_manager():
    '''
    Obtain the network manager advertised by nova-c-c, renaming to Quantum
    if required
    '''
    manager = _network_config().get('network_manager')
    if manager:
        manager = manager.lower()
        if manager != 'neutron':
            return manager
        else:
            return 'neutron'
    return manager


def public_ssh_key(user='root'):
    home = pwd.getpwnam(user).pw_dir
    try:
        with open(os.path.join(home, '.ssh', 'id_rsa.pub')) as key:
            return key.read().strip()
    except:
        return None


def initialize_ssh_keys(user='root'):
    home_dir = pwd.getpwnam(user).pw_dir
    ssh_dir = os.path.join(home_dir, '.ssh')
    if not os.path.isdir(ssh_dir):
        os.mkdir(ssh_dir)

    priv_key = os.path.join(ssh_dir, 'id_rsa')
    if not os.path.isfile(priv_key):
        log('Generating new ssh key for user %s.' % user)
        cmd = ['ssh-keygen', '-q', '-N', '', '-t', 'rsa', '-b', '2048',
               '-f', priv_key]
        check_output(cmd)

    pub_key = '%s.pub' % priv_key
    if not os.path.isfile(pub_key):
        log('Generating missing ssh public key @ %s.' % pub_key)
        cmd = ['ssh-keygen', '-y', '-f', priv_key]
        p = check_output(cmd).strip()
        with open(pub_key, 'wb') as out:
            out.write(p)
    check_output(['chown', '-R', user, ssh_dir])


def set_ppc64_cpu_smt_state(smt_state):
    """Set ppc64_cpu smt state."""

    current_smt_state = check_output(['ppc64_cpu', '--smt'])
    # Possible smt state values are integer or 'off'
    #   Ex. common ppc64_cpu query command output values:
    #      SMT=8
    #   -or-
    #      SMT is off

    if 'SMT={}'.format(smt_state) in current_smt_state:
        log('Not changing ppc64_cpu smt state ({})'.format(smt_state))
    elif smt_state == 'off' and 'SMT is off' in current_smt_state:
        log('Not changing ppc64_cpu smt state (already off)')
    else:
        log('Setting ppc64_cpu smt state: {}'.format(smt_state))
        cmd = ['ppc64_cpu', '--smt={}'.format(smt_state)]
        try:
            check_output(cmd)
        except CalledProcessError as e:
            # Known to fail in a container (host must pre-configure smt)
            msg = 'Failed to set ppc64_cpu smt state: {}'.format(smt_state)
            log(msg, level=WARNING)
            status_set('blocked', msg)
            raise e


def import_authorized_keys(user='root', prefix=None):
    """Import SSH authorized_keys + known_hosts from a cloud-compute relation.
    Store known_hosts in user's $HOME/.ssh and authorized_keys in a path
    specified using authorized-keys-path config option.
    """
    known_hosts = []
    authorized_keys = []
    if prefix:
        known_hosts_index = relation_get(
            '{}_known_hosts_max_index'.format(prefix))
        if known_hosts_index:
            for index in range(0, int(known_hosts_index)):
                known_hosts.append(relation_get(
                                   '{}_known_hosts_{}'.format(prefix, index)))
        authorized_keys_index = relation_get(
            '{}_authorized_keys_max_index'.format(prefix))
        if authorized_keys_index:
            for index in range(0, int(authorized_keys_index)):
                authorized_keys.append(relation_get(
                    '{}_authorized_keys_{}'.format(prefix, index)))
    else:
        # XXX: Should this be managed via templates + contexts?
        known_hosts_index = relation_get('known_hosts_max_index')
        if known_hosts_index:
            for index in range(0, int(known_hosts_index)):
                known_hosts.append(relation_get(
                    'known_hosts_{}'.format(index)))
        authorized_keys_index = relation_get('authorized_keys_max_index')
        if authorized_keys_index:
            for index in range(0, int(authorized_keys_index)):
                authorized_keys.append(relation_get(
                    'authorized_keys_{}'.format(index)))

    # XXX: Should partial return of known_hosts or authorized_keys
    #      be allowed ?
    if not len(known_hosts) or not len(authorized_keys):
        return
    homedir = pwd.getpwnam(user).pw_dir
    dest_auth_keys = config('authorized-keys-path').format(
        homedir=homedir, username=user)
    dest_known_hosts = os.path.join(homedir, '.ssh/known_hosts')
    log('Saving new known_hosts file to %s and authorized_keys file to: %s.' %
        (dest_known_hosts, dest_auth_keys))

    with open(dest_known_hosts, 'wb') as _hosts:
        for index in range(0, int(known_hosts_index)):
            _hosts.write('{}\n'.format(known_hosts[index]))
    with open(dest_auth_keys, 'wb') as _keys:
        for index in range(0, int(authorized_keys_index)):
            _keys.write('{}\n'.format(authorized_keys[index]))


def do_openstack_upgrade(configs):
    # NOTE(jamespage) horrible hack to make utils forget a cached value
    import charmhelpers.contrib.openstack.utils as utils
    utils.os_rel = None
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)
    log('Performing OpenStack upgrade to %s.' % (new_os_rel))

    configure_installation_source(new_src)
    apt_update(fatal=True)

    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]

    apt_upgrade(options=dpkg_opts, fatal=True, dist=True)
    apt_install(determine_packages(), fatal=True)

    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()
    if not is_unit_paused_set():
        for s in services():
            service_restart(s)


def import_keystone_ca_cert():
    """If provided, improt the Keystone CA cert that gets forwarded
    to compute nodes via the cloud-compute interface
    """
    ca_cert = relation_get('ca_cert')
    if not ca_cert:
        return
    log('Writing Keystone CA certificate to %s' % CA_CERT_PATH)
    with open(CA_CERT_PATH, 'wb') as out:
        out.write(b64decode(ca_cert))
    check_call(['update-ca-certificates'])


def create_libvirt_secret(secret_file, secret_uuid, key):
    uri = LIBVIRT_URIS[config('virt-type')]
    if secret_uuid in check_output(['virsh', '-c', uri, 'secret-list']):
        old_key = check_output(['virsh', '-c', uri, 'secret-get-value',
                                secret_uuid])
        old_key = old_key.strip()
        if old_key == key:
            log('Libvirt secret already exists for uuid %s.' % secret_uuid,
                level=DEBUG)
            return
        else:
            log('Libvirt secret changed for uuid %s.' % secret_uuid,
                level=INFO)
    log('Defining new libvirt secret for uuid %s.' % secret_uuid)
    cmd = ['virsh', '-c', uri, 'secret-define', '--file', secret_file]
    check_call(cmd)
    cmd = ['virsh', '-c', uri, 'secret-set-value', '--secret', secret_uuid,
           '--base64', key]
    check_call(cmd)


def destroy_libvirt_network(netname):
    """Delete a network using virsh net-destroy"""
    try:
        out = check_output(['virsh', 'net-list']).split('\n')
        if len(out) < 3:
            return

        for line in out[2:]:
            res = re.search("^\s+{} ".format(netname), line)
            if res:
                check_call(['virsh', 'net-destroy', netname])
                return

    except CalledProcessError:
        log("Failed to destroy libvirt network '{}'".format(netname),
            level=WARNING)
    except OSError as e:
        if e.errno == 2:
            log("virsh is unavailable. Virt Type is '{}'. Not attempting to "
                "destroy libvirt network '{}'"
                "".format(config('virt-type'), netname), level=DEBUG)
        else:
            raise e


def configure_lxd(user='nova'):
    ''' Configure lxd use for nova user '''
    if not git_install_requested():
        if lsb_release()['DISTRIB_CODENAME'].lower() < "vivid":
            raise Exception("LXD is not supported for Ubuntu "
                            "versions less than 15.04 (vivid)")

    configure_subuid(user)
    lxc_list(user)


@retry_on_exception(5, base_delay=2, exc_type=CalledProcessError)
def lxc_list(user):
    cmd = ['sudo', '-u', user, 'lxc', 'list']
    check_call(cmd)


def configure_subuid(user):
    cmd = ['usermod', '-v', '100000-200000', '-w', '100000-200000', user]
    check_call(cmd)


def enable_shell(user):
    cmd = ['usermod', '-s', '/bin/bash', user]
    check_call(cmd)


def disable_shell(user):
    cmd = ['usermod', '-s', '/bin/false', user]
    check_call(cmd)


def fix_path_ownership(path, user='nova'):
    cmd = ['chown', user, path]
    check_call(cmd)


def get_topics():
    return ['compute']


def assert_charm_supports_ipv6():
    """Check whether we are able to support charms ipv6."""
    if lsb_release()['DISTRIB_CODENAME'].lower() < "trusty":
        raise Exception("IPv6 is not supported in the charms for Ubuntu "
                        "versions less than Trusty 14.04")


def git_install(projects_yaml):
    """Perform setup, and install git repos specified in yaml parameter."""
    if git_install_requested():
        git_pre_install()
        projects_yaml = git_default_repos(projects_yaml)
        git_clone_and_install(projects_yaml, core_project='nova')
        git_post_install(projects_yaml)


def git_pre_install():
    """Perform pre-install setup."""
    dirs = [
        '/var/lib/nova',
        '/var/lib/nova/buckets',
        '/var/lib/nova/CA',
        '/var/lib/nova/CA/INTER',
        '/var/lib/nova/CA/newcerts',
        '/var/lib/nova/CA/private',
        '/var/lib/nova/CA/reqs',
        '/var/lib/nova/images',
        '/var/lib/nova/instances',
        '/var/lib/nova/keys',
        '/var/lib/nova/networks',
        '/var/lib/nova/tmp',
        '/var/log/nova',
    ]

    logs = [
        '/var/log/nova/nova-api.log',
        '/var/log/nova/nova-compute.log',
        '/var/log/nova/nova-manage.log',
        '/var/log/nova/nova-network.log',
    ]

    adduser('nova', shell='/bin/bash', system_user=True)
    check_call(['usermod', '--home', '/var/lib/nova', 'nova'])
    add_group('nova', system_group=True)
    add_user_to_group('nova', 'nova')
    add_user_to_group('nova', 'libvirtd')

    for d in dirs:
        mkdir(d, owner='nova', group='nova', perms=0755, force=False)

    for l in logs:
        write_file(l, '', owner='nova', group='nova', perms=0644)


def git_post_install(projects_yaml):
    """Perform post-install setup."""
    http_proxy = git_yaml_value(projects_yaml, 'http_proxy')
    if http_proxy:
        pip_install('libvirt-python', proxy=http_proxy,
                    venv=git_pip_venv_dir(projects_yaml))
    else:
        pip_install('libvirt-python',
                    venv=git_pip_venv_dir(projects_yaml))

    src_etc = os.path.join(git_src_dir(projects_yaml, 'nova'), 'etc/nova')
    configs = [
        {'src': src_etc,
         'dest': '/etc/nova'},
    ]

    for c in configs:
        if os.path.exists(c['dest']):
            shutil.rmtree(c['dest'])
        shutil.copytree(c['src'], c['dest'])

    # NOTE(coreycb): Need to find better solution than bin symlinks.
    symlinks = [
        {'src': os.path.join(git_pip_venv_dir(projects_yaml),
                             'bin/nova-rootwrap'),
         'link': '/usr/local/bin/nova-rootwrap'},
        {'src': os.path.join(git_pip_venv_dir(projects_yaml),
                             'bin/privsep-helper'),
         'link': '/usr/local/bin/privsep-helper'},
    ]

    for s in symlinks:
        if os.path.lexists(s['link']):
            os.remove(s['link'])
        os.symlink(s['src'], s['link'])

    virt_type = VIRT_TYPES[config('virt-type')][0]
    nova_compute_conf = 'git/{}.conf'.format(virt_type)
    render(nova_compute_conf, '/etc/nova/nova-compute.conf', {}, perms=0o644)
    render('git/nova_sudoers', '/etc/sudoers.d/nova_sudoers', {}, perms=0o440)

    bin_dir = os.path.join(git_pip_venv_dir(projects_yaml), 'bin')
    # Use systemd init units/scripts from ubuntu wily onward
    if lsb_release()['DISTRIB_RELEASE'] >= '15.10':
        templates_dir = os.path.join(charm_dir(), 'templates/git')
        daemons = ['nova-api', 'nova-api-metadata', 'nova-compute',
                   'nova-network']
        for daemon in daemons:
            nova_compute_context = {
                'daemon_path': os.path.join(bin_dir, daemon),
            }
            template_file = 'git/{}.init.in.template'.format(daemon)
            init_in_file = '{}.init.in'.format(daemon)
            render(template_file, os.path.join(templates_dir, init_in_file),
                   nova_compute_context, perms=0o644)
        git_generate_systemd_init_files(templates_dir)
    else:
        service_name = 'nova-compute'
        nova_user = 'nova'
        start_dir = '/var/lib/nova'
        nova_conf = '/etc/nova/nova.conf'
        nova_api_context = {
            'service_description': 'Nova API server',
            'service_name': service_name,
            'user_name': nova_user,
            'start_dir': start_dir,
            'process_name': 'nova-api',
            'executable_name': os.path.join(bin_dir, 'nova-api'),
            'config_files': [nova_conf],
        }
        nova_api_metadata_context = {
            'service_description': 'Nova Metadata API server',
            'service_name': service_name,
            'user_name': nova_user,
            'start_dir': start_dir,
            'process_name': 'nova-api-metadata',
            'executable_name': os.path.join(bin_dir, 'nova-api-metadata'),
            'config_files': [nova_conf],
        }
        nova_compute_context = {
            'service_description': 'Nova compute worker',
            'service_name': service_name,
            'user_name': nova_user,
            'process_name': 'nova-compute',
            'executable_name': os.path.join(bin_dir, 'nova-compute'),
            'config_files': [nova_conf, '/etc/nova/nova-compute.conf'],
        }
        nova_network_context = {
            'service_description': 'Nova network worker',
            'service_name': service_name,
            'user_name': nova_user,
            'start_dir': start_dir,
            'process_name': 'nova-network',
            'executable_name': os.path.join(bin_dir, 'nova-network'),
            'config_files': [nova_conf],
        }
        templates_dir = 'hooks/charmhelpers/contrib/openstack/templates'
        templates_dir = os.path.join(charm_dir(), templates_dir)
        render('git.upstart', '/etc/init/nova-api-metadata.conf',
               nova_api_metadata_context, perms=0o644,
               templates_dir=templates_dir)
        render('git.upstart', '/etc/init/nova-api.conf',
               nova_api_context, perms=0o644,
               templates_dir=templates_dir)
        render('git/upstart/nova-compute.upstart',
               '/etc/init/nova-compute.conf',
               nova_compute_context, perms=0o644)
        render('git.upstart', '/etc/init/nova-network.conf',
               nova_network_context, perms=0o644,
               templates_dir=templates_dir)

    apt_update()
    apt_install(LATE_GIT_PACKAGES, fatal=True)


def get_hugepage_number():
    # TODO: defaults to 2M - this should probably be configurable
    #       and support multiple pool sizes - e.g. 2M and 1G.
    hugepage_size = 2048
    hugepage_config = config('hugepages')
    hugepages = None
    if hugepage_config:
        if hugepage_config.endswith('%'):
            import psutil
            mem = psutil.virtual_memory()
            hugepage_config_pct = hugepage_config.strip('%')
            hugepage_multiplier = float(hugepage_config_pct) / 100
            hugepages = int((mem.total * hugepage_multiplier) / hugepage_size)
        else:
            hugepages = int(hugepage_config)
    return hugepages


def install_hugepages():
    """ Configure hugepages """
    hugepage_config = config('hugepages')
    if hugepage_config:
        mnt_point = '/run/hugepages/kvm'
        hugepage_support(
            'nova',
            mnt_point=mnt_point,
            group='root',
            nr_hugepages=get_hugepage_number(),
            mount=False,
            set_shmmax=True,
        )
        # Remove hugepages entry if present due to Bug #1518771
        Fstab.remove_by_mountpoint(mnt_point)
        if subprocess.call(['mountpoint', mnt_point]):
            service_restart('qemu-kvm')
        rsync(
            charm_dir() + '/files/qemu-hugefsdir',
            '/etc/init.d/qemu-hugefsdir'
        )
        subprocess.check_call('/etc/init.d/qemu-hugefsdir')
        subprocess.check_call(['update-rc.d', 'qemu-hugefsdir', 'defaults'])


def get_optional_relations():
    """Return a dictionary of optional relations.

    @returns {relation: relation_name}
    """
    optional_interfaces = {}
    if relation_ids('ceph'):
        optional_interfaces['storage-backend'] = ['ceph']
    if relation_ids('neutron-plugin'):
        optional_interfaces['neutron-plugin'] = ['neutron-plugin']
    if relation_ids('shared-db') or relation_ids('pgsql-db'):
        optional_interfaces['database'] = ['shared-db', 'pgsql-db']
    return optional_interfaces


def assess_status(configs):
    """Assess status of current unit
    Decides what the state of the unit should be based on the current
    configuration.
    SIDE EFFECT: calls set_os_workload_status(...) which sets the workload
    status of the unit.
    Also calls status_set(...) directly if paused state isn't complete.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    assess_status_func(configs)()
    os_application_version_set(VERSION_PACKAGE)


def assess_status_func(configs):
    """Helper function to create the function that will assess_status() for
    the unit.
    Uses charmhelpers.contrib.openstack.utils.make_assess_status_func() to
    create the appropriate status function and then returns it.
    Used directly by assess_status() and also for pausing and resuming
    the unit.

    NOTE(ajkavanagh) ports are not checked due to race hazards with services
    that don't behave sychronously w.r.t their service scripts.  e.g.
    apache2.
    @param configs: a templating.OSConfigRenderer() object
    @return f() -> None : a function that assesses the unit's workload status
    """
    required_interfaces = REQUIRED_INTERFACES.copy()
    required_interfaces.update(get_optional_relations())
    return make_assess_status_func(
        configs, required_interfaces,
        services=services(), ports=None)


def pause_unit_helper(configs):
    """Helper function to pause a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.pause_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(pause_unit, configs)


def resume_unit_helper(configs):
    """Helper function to resume a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.resume_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(resume_unit, configs)


def _pause_resume_helper(f, configs):
    """Helper function that uses the make_assess_status_func(...) from
    charmhelpers.contrib.openstack.utils to create an assess_status(...)
    function that can be used with the pause/resume of the unit
    @param f: the function to be used with the assess_status(...) function
    @returns None - this function is executed for its side-effect
    """
    # TODO(ajkavanagh) - ports= has been left off because of the race hazard
    # that exists due to service_start()
    f(assess_status_func(configs),
      services=services(),
      ports=None)
