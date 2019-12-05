# Copyright 2019, Google, Inc.
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

import os
import time
import random
import threading
import base64
import json
import googleapiclient.discovery
from google.oauth2 import service_account
from GC_SSH_Manager import runCommands
import argparse

'''
The service account that runs this test must have the following roles:
- roles/compute.instanceAdmin.v1
- roles/compute.securityAdmin
- roles/iam.serviceAccountAdmin
- roles/iam.serviceAccountKeyAdmin
- roles/iam.serviceAccountUser
The Project Editor legacy role is not sufficient because it does not grant
several necessary permissions.
'''
def setup_resources(
        compute, iam, project, test_id, zone,
        image_family, machine_type, account_email):

    print("Create a temporary service account.")
    iam.projects().serviceAccounts().create(
        name='projects/' + project,
        body={
            'accountId': test_id,
            'serviceAccount': {
                'displayName': test_id
            }

        }).execute()

    print("Grant the service account access to itself.")
    iam.projects().serviceAccounts().setIamPolicy(
        resource='projects/' + project + '/serviceAccounts/' + account_email,
        body={
         'policy': {
          'bindings': [
           {
            'members': [
             'serviceAccount:' + account_email
            ],
            'role': 'roles/iam.serviceAccountUser'
           }
          ]
         }
        }).execute()

    print("Create a service account key.")
    service_account_key = iam.projects().serviceAccounts().keys().create(
        name='projects/' + project + '/serviceAccounts/' + account_email,
        body={}
        ).execute()

    print("Create a temporary firewall on the default network to allow SSH tests only for instances with the temporary service account.")
    firewall_config = {
        'name': test_id,
        'network': '/global/networks/default',
        'targetServiceAccounts': [
            account_email
        ],
        'sourceRanges': [
            '0.0.0.0/0'
        ],
        'allowed': [{
            'IPProtocol': 'tcp',
            'ports': [
                '22'
            ],
        }]
    }

    compute.firewalls().insert(
        project=project,
        body=firewall_config).execute()

    print("Create a new test instance.")
    instance_config = {
        'name': test_id,
        'machineType': machine_type,
        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': image_family,
                }
            }
        ],
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [
                {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
            ]
        }],
        'serviceAccounts': [{
            'email': account_email,
            'scopes': [
                'https://www.googleapis.com/auth/cloud-platform'
            ]
        }],
        'metadata': {
            'items': [{
                'key': 'enable-oslogin',
                'value': 'TRUE'
            }]
        }
    }

    operation = compute.instances().insert(
        project=project,
        zone=zone,
        body=instance_config).execute()

    # Wait for the instance to start.
    while compute.zoneOperations().get(
            project=project,
            zone=zone,
            operation=operation['name']).execute()['status'] != 'DONE':
        time.sleep(5)

    # Grant the service account osLogin access on the test instance.
    compute.instances().setIamPolicy(
        project=project,
        zone=zone,
        resource=test_id,
        body={
            'bindings': [
                {
                    'members': [
                        'serviceAccount:' + account_email
                    ],
                    'role': 'roles/compute.osAdminLogin'
                }
            ]
        }).execute()

    # Wait for the IAM policy to take effect.
    while compute.instances().getIamPolicy(
            project=project,
            zone=zone,
            resource=test_id,
            fields='bindings/role'
    ).execute()['bindings'][0]['role'] != 'roles/compute.osAdminLogin':
        time.sleep(5)

    return service_account_key


def cleanup_resources(compute, iam, project, test_id, zone, account_email):

    print("Delete the temporary firewall.")
    try:
        compute.firewalls().delete(
                project=project,
                firewall=test_id).execute()
    except Exception:
        pass

    print("Delete the test instance.")
    try:
        delete = compute.instances().delete(
            project=project, zone=zone, instance=test_id).execute()

        while compute.zoneOperations().get(
                project=project, zone=zone, operation=delete['name']
                ).execute()['status'] != 'DONE':
            time.sleep(5)
    except Exception:
        pass

    print("Delete the temporary service account and its associated keys.")
    try:
        iam.projects().serviceAccounts().delete(
            name='projects/' + project + '/serviceAccounts/' + account_email
            ).execute()
    except Exception:
        pass

def runDocker(dockerImage):
    update = ['sudo apt update']
    prerequisite = ['sudo apt install apt-transport-https ca-certificates curl gnupg2 software-properties-common -y']
    AddTheGpgKey = ['curl -fsSL https://download.docker.com/linux/debian/gpg | sudo apt-key add -']
    addDockerRepo = ['sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/debian $(lsb_release -cs) stable"']
    installDocker = ['sudo apt install docker-ce -y']
    installContainer = ['sudo docker pull {container}'.format(container=dockerImage)]
    runContainer = ['sudo docker run {container}'.format(container=dockerImage)]

    return update + prerequisite + AddTheGpgKey + addDockerRepo + update + installDocker + update + installContainer + runContainer

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="GCloud util")
    parser.add_argument('numberOfVms', metavar='numberOfVms', type=int)
    parser.add_argument('container', metavar='container')
    parser.add_argument('pathToOutput', metavar='pathToOutput')
    args = parser.parse_args()
    numberOfVms = args.numberOfVms
    container = args.container
    pathToOutput = args.pathToOutput
    print("Initialize variables.")
    cmd = runDocker(container)
    project = 'cloud-infrastructure-project'
    zone = 'us-east1-d'
    image_family = 'projects/debian-cloud/global/images/family/debian-9'
    machine_type = 'zones/{zone}/machineTypes/f1-micro'.format(zone=zone)
    ids = []
    accounts = []
    keys = []

    for i in range(0, numberOfVms):

        test_id = 'oslogin-worker-{id}'.format(id=i+100)
        account_email = '{test_id}@{project}.iam.gserviceaccount.com'.format(
            test_id=test_id, project=project)
        ids.append(test_id)
        accounts.append(account_email)

        print("Initialize the necessary APIs.")
        iam = googleapiclient.discovery.build(
            'iam', 'v1', cache_discovery=False)
        compute = googleapiclient.discovery.build(
            'compute', 'v1', cache_discovery=False)

        print("Create the necessary test resources and retrieve the service account email and account key.")
        try:
            print('Creating test resources.')
            service_account_key = setup_resources(
                compute, iam, project, test_id, zone, image_family,
                machine_type, account_email)
            keys.append(service_account_key)
        except Exception as e:
            print('Cleaning up partially created test resources.')
            cleanup_resources(compute, iam, project, test_id, zone, account_email)
            print(e)
            raise Exception('Could not set up the necessary test resources.')

    print("Setup threads")
    threads = []
    computes = []
    iams = []
    for i in range(0, len(ids)):
        print("Create a credentials object and use it to initialize the OS Login API.")
        account = 'users/' + accounts[i]
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(base64.b64decode(
                keys[i]['privateKeyData']).decode('utf-8')))
        oslogin = googleapiclient.discovery.build(
            'oslogin', 'v1', cache_discovery=False, credentials=credentials)
        print("Give OS Login some time to catch up.")
        time.sleep(120)

        print("Initialize the necessary APIs.")
        iam = googleapiclient.discovery.build(
            'iam', 'v1', cache_discovery=False)
        iams.append(iam)
        compute = googleapiclient.discovery.build(
            'compute', 'v1', cache_discovery=False)

        print("Get the target host name for the instance")
        hostname = compute.instances().get(
            project=project,
            zone=zone,
            instance=ids[i],
            fields='networkInterfaces/accessConfigs/natIP'
        ).execute()['networkInterfaces'][0]['accessConfigs'][0]['natIP']
        computes.append(compute)
        thread = threading.Thread(target=runCommands, args=(cmd, project, ids[i], zone, oslogin, account, hostname, pathToOutput))
        threads.append(thread)

    print("Test SSH to the instance.")
    for t in threads:
        t.start()

    for t in threads:
        t.join()

    for i in range(0, len(ids)):
        cleanup_resources(computes[i], iams[i], project, ids[i], zone, ids[i])