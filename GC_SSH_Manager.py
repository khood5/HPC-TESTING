# !/usr/bin/env python

# Copyright 2018 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Example of using the OS Login API to apply public SSH keys for a service
account, and use that service account to execute commands on a remote
instance over SSH. This example uses zonal DNS names to address instances
on the same internal VPC network.
"""

# [START imports_and_variables]
import time
import subprocess
import uuid
import logging
import requests
import os
import argparse
import datetime
import googleapiclient.discovery

# Global variables
SERVICE_ACCOUNT_METADATA_URL = (
    'http://metadata.google.internal/computeMetadata/v1/instance/'
    'service-accounts/default/email')
HEADERS = {'Metadata-Flavor': 'Google'}

# [START run_command_local]
def execute(cmd, cwd=None, capture_output=False, env=None, raise_errors=True):
    """Execute an external command (wrapper for Python subprocess)."""
    logging.info('Executing command: {cmd}'.format(cmd=str(cmd)))
    stdout = subprocess.PIPE if capture_output else None
    process = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=stdout)
    output = process.communicate()[0]
    returncode = process.returncode
    if returncode:
        # Error
        if raise_errors:
            raise subprocess.CalledProcessError(returncode, cmd)
        else:
            logging.info('Command returned error status %s', returncode)
    if output:
        logging.info(output)
    return returncode, output


# [END run_command_local]


# [START create_key]
def create_ssh_key(oslogin, account, private_key_file=None, expire_time=300):
    """Generate an SSH key pair and apply it to the specified account."""
    private_key_file = private_key_file or '/tmp/key-' + str(uuid.uuid4())
    execute(['ssh-keygen', '-t', 'rsa', '-N', '', '-f', private_key_file])

    with open(private_key_file + '.pub', 'r') as original:
        public_key = original.read().strip()

    # Expiration time is in microseconds.
    expiration = int((time.time() + expire_time) * 1000000)

    body = {
        'key': public_key,
        'expirationTimeUsec': expiration,
    }
    oslogin.users().importSshPublicKey(parent=account, body=body).execute()
    return private_key_file


# [END create_key]


# [START run_command_remote]
def run_ssh(cmd, private_key_file, username, hostname, pathForOutput):
    """Run a command on a remote system."""
    ssh_command = [
        'ssh', '-i', private_key_file, '-o', 'StrictHostKeyChecking=no',
        '{username}@{hostname}'.format(username=username, hostname=hostname),
        cmd,
    ]
    print("----------------- issuing command:" + cmd + " at:" + hostname + "----------------- ")
    path = os.path.join(pathForOutput, 'command at {hn}_{time}.log'.format(hn=hostname, time= datetime.datetime.now().strftime("%I:%M:%S%p on %B %d, %Y")) )
    log = open(path, 'a')
    log.write("----------------- issuing command:" + cmd + " at:" + hostname + "----------------- ")
    subprocess.Popen(
        ssh_command, shell=False, stdout=log,
        stderr=log)
    print("-----------------  Wait commands to finish: " + datetime.datetime.now().strftime("%I:%M%p on %B %d, %Y") + "----------------- ")
    time.sleep(60)

def runCommands(cmds, project, instance=None, zone=None,
                oslogin=None, account=None, hostname=None, pathForOutput=None):
    """Run a command on a remote system."""

    print("Create the OS Login API object.")
    oslogin = oslogin or googleapiclient.discovery.build('oslogin', 'v1')

    # Identify the service account ID if it is not already provided.
    account = account or requests.get(
        SERVICE_ACCOUNT_METADATA_URL, headers=HEADERS).text
    if not account.startswith('users/'):
        account = 'users/' + account
    print("account:" + account)
    print("Create a new SSH key pair and associate it with the service account.")
    private_key_file = create_ssh_key(oslogin, account)

    print("Using the OS Login API, get the POSIX user name from the login profile for the service account.")
    profile = oslogin.users().getLoginProfile(name=account).execute()
    username = profile.get('posixAccounts')[0].get('username')

    print("Create the hostname of the target instance using the instance name, \n the zone where the instance is located, and the project that owns the \n instance.")
    hostname = hostname or '{instance}.{zone}.c.{project}.internal'.format(
        instance=instance, zone=zone, project=project)

    for c in cmds:
        print("account:" + account)
        print("Create a new SSH key pair and associate it with the service account.")
        private_key_file = create_ssh_key(oslogin, account)

        print("Using the OS Login API, get the POSIX user name from the login profile for the service account.")
        profile = oslogin.users().getLoginProfile(name=account).execute()
        username = profile.get('posixAccounts')[0].get('username')

        print("Create the hostname of the target instance using the instance name, \n the zone where the instance is located, and the project that owns the \n instance.")
        hostname = hostname or '{instance}.{zone}.c.{project}.internal'.format(
            instance=instance, zone=zone, project=project)
        run_ssh(c, private_key_file, username, hostname, pathForOutput)
        os.system("ssh-keygen -f \"/home/ciuser/.ssh/known_hosts\" -R \"{hostname}\"".format(hostname = hostname))


    print("Shred the private key and delete the pair.")
    execute(['shred', private_key_file])
    execute(['rm', private_key_file])
    execute(['rm', private_key_file + '.pub'])


