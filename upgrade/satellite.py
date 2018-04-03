import os
import sys

from upgrade.helpers.tools import (
    host_pings,
    host_ssh_availability_check,
    reboot
)
from automation_tools import (
    enable_ostree,
    subscribe,
    install_prerequisites
)
from automation_tools.satellite6.hammer import hammer, set_hammer_config
from automation_tools.utils import distro_info
from datetime import datetime
from fabric.api import env, execute, run
from upgrade.helpers.logger import logger
from upgrade.helpers.rhevm import (
    create_rhevm_instance,
    delete_rhevm_instance
)
from upgrade.helpers.tasks import (
    setup_foreman_maintain,
    upgrade_using_foreman_maintain
)

logger = logger()


def satellite6_setup(os_version):
    """Sets up required things on upgrade running machine and on Satellite to
    perform satellite upgrade later

    :param string os_version: The OS version onto which the satellite installed
        e.g: rhel6, rhel7
    """
    # If Personal Satellite Hostname provided
    if os.environ.get('SATELLITE_HOSTNAME'):
        sat_host = os.environ.get('SATELLITE_HOSTNAME')
    # Else run upgrade on rhevm satellite
    else:
        # Get image name and Hostname from Jenkins environment
        missing_vars = [
            var for var in ('RHEV_SAT_IMAGE', 'RHEV_SAT_HOST')
            if var not in os.environ]
        # Check if image name and Hostname in jenkins are set
        if missing_vars:
            logger.warning('The following environment variable(s) must be set '
                           'in jenkin environment: {0}.'.format(
                                ', '.join(missing_vars)))
            sys.exit(1)
        sat_image = os.environ.get('RHEV_SAT_IMAGE')
        sat_host = os.environ.get('RHEV_SAT_HOST')
        sat_instance = 'upgrade_satellite_auto_{0}'.format(os_version)
        execute(delete_rhevm_instance, sat_instance)
        execute(create_rhevm_instance, sat_instance, sat_image)
        if not host_pings(sat_host):
            sys.exit(1)
        execute(host_ssh_availability_check, sat_host)
        # start's/enables/install's ntp
        # Check that hostname and localhost resolve correctly
        execute(install_prerequisites, host=sat_host)
        # Subscribe the instance to CDN
        execute(subscribe, host=sat_host)
        execute(lambda: run('katello-service restart'), host=sat_host)
    # Set satellite hostname in fabric environment
    env['satellite_host'] = sat_host
    logger.info('Satellite {} is ready for Upgrade!'.format(sat_host))
    return sat_host


def satellite6_upgrade():
    """Upgrades satellite from old version to latest version.

    The following environment variables affect this command:

    BASE_URL
        Optional, defaults to available satellite version in CDN.
        URL for the compose repository
    TO_VERSION
        Satellite version to upgrade to and enable repos while upgrading.
        e.g '6.1','6.2', '6.3'
    """
    logger.highlight('\n========== SATELLITE UPGRADE =================\n')
    to_version = os.environ.get('TO_VERSION')
    base_url = os.environ.get('BASE_URL')
    if to_version not in ['6.1', '6.2', '6.3']:
        logger.warning('Wrong Satellite Version Provided to upgrade to. '
                       'Provide one of 6.1, 6.2, 6.3')
        sys.exit(1)
    # Setting Satellite to_version Repos
    major_ver = distro_info()[1]
    if base_url is None:
        os.environ['DISTRIBUTION'] = "CDN"
    else:
        os.environ['DISTRIBUTION'] = "DOWNSTREAM"
    # setup foreman-maintain
    setup_foreman_maintain()
    preup_time = datetime.now().replace(microsecond=0)
    # perform upgrade using foreman-maintain
    upgrade_using_foreman_maintain()
    postup_time = datetime.now().replace(microsecond=0)
    logger.highlight('Time taken for Satellite Upgrade - {}'.format(
        str(postup_time - preup_time)))
    set_hammer_config()
    # Rebooting the satellite for kernel update if any
    reboot(180)
    host_ssh_availability_check(env.get('satellite_host'))
    # Test the Upgrade is successful
    hammer('ping')
    run('katello-service status', warn_only=True)
    # Enable ostree feature only for rhel7 and sat6.2
    if to_version == '6.2' and major_ver == 7:
        enable_ostree(sat_version='6.2')


def satellite6_zstream_upgrade():
    """Upgrades Satellite Server to its latest zStream version

    Note: For zstream upgrade both 'To' and 'From' version should be same

    FROM_VERSION
        Current satellite version which will be upgraded to latest version
    TO_VERSION
        Next satellite version to which satellite will be upgraded
    """
    logger.highlight('\n========== SATELLITE UPGRADE =================\n')
    from_version = os.environ.get('FROM_VERSION')
    to_version = os.environ.get('TO_VERSION')
    base_url = os.environ.get('BASE_URL')
    if not from_version == to_version:
        logger.warning('zStream Upgrade on Satellite cannot be performed as '
                       'FROM and TO versions are not same!')
        sys.exit(1)
    if base_url is None:
        os.environ['DISTRIBUTION'] = "CDN"
    else:
        os.environ['DISTRIBUTION'] = "DOWNSTREAM"
    # setup foreman-maintain
    setup_foreman_maintain()
    preup_time = datetime.now().replace(microsecond=0)
    # perform upgrade using foreman-maintain
    upgrade_using_foreman_maintain()
    postup_time = datetime.now().replace(microsecond=0)
    logger.highlight('Time taken for Satellite Upgrade - {}'.format(
        str(postup_time - preup_time)))
    # Rebooting the satellite for kernel update if any
    reboot(180)
    host_ssh_availability_check(env.get('satellite_host'))
    # Test the Upgrade is successful
    set_hammer_config()
    hammer('ping')
    run('katello-service status', warn_only=True)
