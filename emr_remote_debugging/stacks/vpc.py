from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_s3 as s3
from constructs import Construct


class VPCStack(Stack):
    dev_vpc: ec2.Vpc
    emr_vpc: ec2.Vpc
    bucket: s3.Bucket

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.dev_vpc = ec2.Vpc(
            self,
            "Dev VPC",
            max_azs=3,
            ip_addresses=ec2.IpAddresses.cidr("10.0.10.0/24"),
        )
        self.emr_vpc = ec2.Vpc(
            self,
            "EMR VPC",
            max_azs=3,
            ip_addresses=ec2.IpAddresses.cidr("10.0.20.0/24"),
        )

        # We setup peering between these VPC private subnets
        peer = ec2.CfnVPCPeeringConnection(self, "VPCPeer", vpc_id=self.emr_vpc.vpc_id, peer_vpc_id=self.dev_vpc.vpc_id)
        index = 0
        for subnet in self.dev_vpc.private_subnets:
            ec2.CfnRoute(
                self,
                f"VPCPeer_{index}",
                destination_cidr_block=self.emr_vpc.vpc_cidr_block,
                route_table_id=subnet.route_table.route_table_id,
                vpc_peering_connection_id=peer.ref,
            )
            index += 1
        for subnet in self.emr_vpc.private_subnets:
            ec2.CfnRoute(
                self,
                f"VPCPeer_{index}",
                destination_cidr_block=self.dev_vpc.vpc_cidr_block,
                route_table_id=subnet.route_table.route_table_id,
                vpc_peering_connection_id=peer.ref,
            )
            index += 1

        # And create a bucket here as it's shared with the other stacks
        self.bucket = s3.Bucket(
            self,
            "EMRArtifacts",
            versioned=True,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        CfnOutput(self, "S3Bucket", value=self.bucket.bucket_name)
