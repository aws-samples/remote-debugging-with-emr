from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_emrserverless as emrs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class EMRServerlessStack(Stack):
    serverless_app: emrs.CfnApplication
    security_group: ec2.SecurityGroup
    bucket: s3.IBucket

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, bucket: s3.IBucket, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a security group
        self.security_group = self.create_security_group(vpc)

        # Create a bucket for code artifacts and logs
        self.bucket = bucket

        # Create an EMR 6.15.0 Spark application in a VPC with pre-initialized capacity
        self.serverless_app = emrs.CfnApplication(
            self,
            "spark_app",
            release_label="emr-6.15.0",
            type="SPARK",
            name="remote-debug",
            network_configuration=emrs.CfnApplication.NetworkConfigurationProperty(
                subnet_ids=vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnet_ids,
                security_group_ids=[self.security_group.security_group_id],
            ),
            initial_capacity=[
                emrs.CfnApplication.InitialCapacityConfigKeyValuePairProperty(
                    key="Driver",
                    value=emrs.CfnApplication.InitialCapacityConfigProperty(
                        worker_count=2,
                        worker_configuration=emrs.CfnApplication.WorkerConfigurationProperty(
                            cpu="4vCPU", memory="16gb"
                        ),
                    ),
                ),
                emrs.CfnApplication.InitialCapacityConfigKeyValuePairProperty(
                    key="Executor",
                    value=emrs.CfnApplication.InitialCapacityConfigProperty(
                        worker_count=10,
                        worker_configuration=emrs.CfnApplication.WorkerConfigurationProperty(
                            cpu="4vCPU", memory="16gb"
                        ),
                    ),
                ),
            ],
            auto_stop_configuration=emrs.CfnApplication.AutoStopConfigurationProperty(
                enabled=True, idle_timeout_minutes=15
            ),
        )

        self.serverless_job_role = self.create_job_execution_role()

        CfnOutput(self, "ApplicationID", value=self.serverless_app.attr_application_id)
        CfnOutput(self, "JobRoleArn", value=self.serverless_job_role.role_arn)

    def create_security_group(self, vpc: ec2.IVpc) -> ec2.SecurityGroup:
        return ec2.SecurityGroup(self, "EMRServerlessSG", vpc=vpc)

    def create_job_execution_role(self) -> iam.Role:
        role = iam.Role(self, "JobRole", assumed_by=iam.ServicePrincipal("emr-serverless.amazonaws.com"))
        self.bucket.grant_read_write(role)
        s3.Bucket.from_bucket_name(self, "NOAABucket", "noaa-gsod-pds").grant_read(role)
        return role
