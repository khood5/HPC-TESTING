from google.cloud import storage


def Bucket_Creator(project=None,bucket_name=None):
    storage_clinet = storage.Client(project=project)
    bucket = storage_clinet.create_bucket(bucket_name)
    print('Bucket {} Created.'.format(bucket.name))
    return bucket

def delete_bucket(project=None,bucket_name=None):
    """Deletes a bucket. The bucket must be empty."""
    storage_client = storage.Client(project=project)
    bucket = storage_client.get_bucket(bucket_name)
    bucket.delete()
    print('Bucket {} deleted'.format(bucket.name))