from typing import List

import aws_cdk.aws_ec2 as ec2
from aws_cdk import CfnOutput, Stack
from constructs import Construct


class DevBox(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        source_security_groups: List[ec2.SecurityGroup],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a security group that will allow access from EMR
        devbox_sg: ec2.SecurityGroup = ec2.SecurityGroup(self, "DevBoxSecurityGroup", vpc=vpc)
        for source_sg in source_security_groups:
            devbox_sg.add_ingress_rule(source_sg, ec2.Port.tcp(3535))

        # We create a role for the instance that includes SSM for remote access

        # Create the instance with the latest Amazon Linux 2023
        instance: ec2.Instance = ec2.Instance(
            self,
            "DevBox",
            vpc=vpc,
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.C6A, ec2.InstanceSize.LARGE),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            ssm_session_permissions=True,
            security_group=devbox_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # Allow remote port forwarding
        instance.add_user_data("echo GatewayPorts yes | sudo tee -a /etc/ssh/sshd_config")
        instance.add_user_data("sudo systemctl restart sshd.service")

        CfnOutput(self, "DevBoxID", value=instance.instance_id)
