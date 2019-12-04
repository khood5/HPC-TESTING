import base64
import json
import time
import os
import random
import time
import subprocess
import uuid
import logging
import requests
import googleapiclient.discovery
from google.oauth2 import service_account
import GC_Project_Creator as PC
import googleapiclient
import GC_VM_Manager as VMM
import GC_Bucket_Creator as BC
import GC_SSH_Manager as SSHM

# Global variables
SERVICE_ACCOUNT_METADATA_URL = (
    'http://metadata.google.internal/computeMetadata/v1/instance/'
    'serviceAccounts/email')
HEADERS = {'Metadata-Flavor': 'Google'}

#Part One Create Project
#=============================================================================================================
#PC.Project_Creator('ci12122019-2')
#=============================================================================================================



#Part Two Create Bucket
#=============================================================================================================
#BC.Bucket_Creator('cloud-infrastructure-project','ci12122019-2')
#=============================================================================================================



#Part Three Create VM Instances
#=============================================================================================================
compute = googleapiclient.discovery.build('compute', 'v1')
project = 'cloud-infrastructure-project'
zone = 'us-central1-f'
instance_name = 'vm1'
bucket = 'ci12122019-2'
#operation = VMM.create_instance(compute, project, zone, instance_name, bucket)
#VMM.wait_for_operation(compute, project, zone, operation['name'])
#=============================================================================================================


#Part Four List All VMS and Get Network Interface Information
#=============================================================================================================
compute = googleapiclient.discovery.build('compute', 'v1')
project = 'cloud-infrastructure-project'
zone = 'us-central1-f'
bucket = 'ci12122019-2'
instances = VMM.list_instances(compute, project, zone)
print('Instances in project %s and zone %s:' % (project, zone))
print(googleapiclient.discovery.DISCOVERY_URI)
# Create a temporary firewall on the default network to allow SSH tests
# only for instances with the temporary service account.
firewall_config = {
    'name': instances[0]['name'],
    'network': '/global/networks/default',
    'targetServiceAccounts': [
        'ciproject12052019'
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
try:
    compute.firewalls().insert(
        project=project,
        body=firewall_config).execute()
except Exception as e:
    print(str(e))


for instance in instances:
    print(' - ' + instance['name'])
#    hostname = compute.instances().get(
#        project=project,
#        zone=zone,
#        instance=instance['name'],
#        fields='networkInterfaces/accessConfigs/natIP'
#    ).execute()['networkInterfaces'][0]['accessConfigs'][0]['natIP']
#    print(hostname)

#=============================================================================================================

#Part SSH
#=============================================================================================================
    test_id = 'testing-{id}'.format(id=str(random.randint(0, 1000000)))
    account_email = '{test_id} @ {project}.iam.gserviceaccount.com'.format(test_id=test_id, project=project)
    iam = googleapiclient.discovery.build(
        'iam', 'v1', cache_discovery=False)
    # Create a temporary service account.
    iam.projects().serviceAccounts().create(
        name='projects/' + project,
        body={
            'accountId': test_id
        }).execute()
    # Grant the service account access to itself.
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
    service_account_key = iam.projects().serviceAccounts().keys().create(
        name='projects/' + project + '/serviceAccounts/' + account_email,
        body={}
        ).execute()
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
           'role': 'roles/compute.osLogin'
          }
         ]
        }).execute()
    # Wait for the IAM policy to take effect.
    while compute.instances().getIamPolicy(
            project=project,
            zone=zone,
            resource=test_id,
            fields='bindings/role'
            ).execute()['bindings'][0]['role'] != 'roles/compute.osLogin':
        time.sleep(5)

    # Get the target host name for the instance
    hostname = compute.instances().get(
        project=project,
        zone=zone,
        instance=test_id,
        fields='networkInterfaces/accessConfigs/natIP'
    ).execute()['networkInterfaces'][0]['accessConfigs'][0]['natIP']

    # Create a credentials object and use it to initialize the OS Login API.
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(base64.b64decode(
            service_account_key['privateKeyData']).decode('utf-8')))

    oslogin = googleapiclient.discovery.build(
        'oslogin', 'v1', cache_discovery=False, credentials=credentials)
    account = 'users/' + account_email
    # Give OS Login some time to catch up.
    time.sleep(30)

    # Test SSH to the instance.
    cmd = 'uname -a'
    SSHM.runCommands(cmd, project, test_id, zone, oslogin, account, hostname)


#=============================================================================================================

#Part Five Delete All VMs After Docker Job is Done
#=============================================================================================================
#compute = googleapiclient.discovery.build('compute', 'v1')
#project = 'cloud-infrastructure-project'
#zone = 'us-central1-f'
#bucket = 'ci12122019-2'
#instances = VMM.list_instances(compute, project, zone)
#for instance in instances:
#    operation = VMM.delete_instance(compute, project, zone, instance['name'])
#    VMM.wait_for_operation(compute, project, zone, operation['name'])
#BC.delete_bucket('cloud-infrastructure-project','ci12122019-2')
#=============================================================================================================
