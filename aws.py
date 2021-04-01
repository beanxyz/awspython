# Author: Yuan Li
# Date: 01/04/2021

import boto3

BLOCK = '10.1.0.0/16'
PUBLIC = '10.1.1.0/24'
PRIVATE = '10.1.2.0/24'
AMI = 'ami-06202e06492f46177'
INSTANCE = 't2.micro'
REGION = 'ap-southeast-2'
MY_IP = '0.0.0.0/0'
# mgmt is an existing key pair in my ec2 service
KEY_NAME = 'mgmt'

ec2 = boto3.resource('ec2', region_name=REGION)
ec2_client = boto3.client('ec2', region_name=REGION)

# create VPC
vpc = ec2.create_vpc(CidrBlock=BLOCK)
vpc.create_tags(Tags=[{"Key": "Name", "Value": "vpc_test"}])
vpc.wait_until_available()
print("VPC ID:", vpc.id)

# create then attach internet gateway
ig = ec2.create_internet_gateway()
vpc.attach_internet_gateway(InternetGatewayId=ig.id)
print("Internet Gateway", ig.id)

# create a public route table
route_table = vpc.create_route_table()
route = route_table.create_route(
    DestinationCidrBlock='0.0.0.0/0',
    GatewayId=ig.id
)
print("Public subnet Routing Table:", route_table.id)

# Create public subnet
pub_subnet = ec2.create_subnet(CidrBlock=PUBLIC, VpcId=vpc.id)
pub_subnet.create_tags(Tags=[{"Key": "Name","Value": "public subnet"}])
print("Public Subnet ID:", pub_subnet.id)

# Create private subnet
pri_subnet = ec2.create_subnet(CidrBlock=PRIVATE, VpcId=vpc.id)
pri_subnet.create_tags(Tags=[{"Key": "Name","Value": "private subnet"}])
print("Private Subnet ID:", pri_subnet.id)

# Associate the route table with the public subnet
route_table.associate_with_subnet(SubnetId=pub_subnet.id)


# Create EIP for Jump box
jump_eip = ec2_client.allocate_address(Domain='vpc')


# Create EIP and Nat Gateway
nat_eip = ec2_client.allocate_address(Domain='vpc')
nat = ec2_client.create_nat_gateway(
    AllocationId=nat_eip['AllocationId'],
    SubnetId=pub_subnet.id
)

print("Creating NAT GW, please wait...")
# Wait until NAT GW is ready
ec2_client.get_waiter('nat_gateway_available').wait(
    NatGatewayIds=[nat['NatGateway']['NatGatewayId']])

print("NAT GW ID:", [nat['NatGateway']['NatGatewayId']])

# Create a private route table
private_route_table = vpc.create_route_table()
private_route_table.create_route(
    DestinationCidrBlock='0.0.0.0/0',
    NatGatewayId=nat['NatGateway']['NatGatewayId'])
private_route_table.associate_with_subnet(
    SubnetId=pri_subnet.id)

# Create pub sec group
pub_sec_group = ec2.create_security_group(
    GroupName='Jump_box', Description='jump box sec group', VpcId=vpc.id)
public_ip_permissions = [{
    'IpProtocol': 'icmp',
    'FromPort': -1,
    'ToPort': -1,
    'IpRanges': [{'CidrIp': MY_IP}]
},
    {
        'IpProtocol': 'TCP',
        'FromPort': 22,
        'ToPort': 22,
        'IpRanges': [{'CidrIp': MY_IP}]
    }]

pub_sec_group.authorize_ingress(
    IpPermissions=public_ip_permissions
)
print("Public SG ID:", pub_sec_group.id)

# Create pri sec group
pri_sec_group = ec2.create_security_group(
    GroupName='App', Description='app sec group', VpcId=vpc.id)
private_ip_permissions = [{
    'IpProtocol': 'icmp',
    'FromPort': -1,
    'ToPort': -1,
    'IpRanges': [{'CidrIp': PUBLIC}]
},
    {
        'IpProtocol': 'TCP',
        'FromPort': 22,
        'ToPort': 22,
        'IpRanges': [{'CidrIp': PUBLIC}]
    }]

pri_sec_group.authorize_ingress(
    IpPermissions=private_ip_permissions
)
print("Private SG ID:", pri_sec_group.id)


# create keypair
# key_pair = ec2.create_key_pair(KeyName=KEY_NAME)


# Create public instance
instances = ec2.create_instances(
    ImageId=AMI, InstanceType=INSTANCE, MaxCount=1, MinCount=1, KeyName=KEY_NAME,
    NetworkInterfaces=[{'SubnetId': pub_subnet.id, 'DeviceIndex': 0, 'AssociatePublicIpAddress': True,
                        'Groups': [pub_sec_group.group_id]}])

# instances.create_tags(Tags=[{"Key": "Name","Value": "Jump box"}])
ec2.create_tags(Resources=[instances[0].id], Tags=[{'Key':'Name', 'Value':'Jump box'}])

print("Creating Jump Box, pleas wait..")
instances[0].wait_until_running()

# Associate EIP to jump box
ec2_client.associate_address(AllocationId=jump_eip['AllocationId'],InstanceId=instances[0].id)


print("Public Instance ID", instances[0].id)

# Create private instance
instances2 = ec2.create_instances(
    ImageId=AMI, InstanceType=INSTANCE, MaxCount=1, MinCount=1, KeyName=KEY_NAME,
    NetworkInterfaces=[{'SubnetId': pri_subnet.id, 'DeviceIndex': 0, 'AssociatePublicIpAddress': False,
                        'Groups': [pri_sec_group.group_id]}])

ec2.create_tags(Resources=[instances2[0].id], Tags=[{'Key':'Name', 'Value':'App'}])

print("Creating App Box, pleas wait..")
instances[0].wait_until_running()
print("Private Instance ID",instances2[0].id)