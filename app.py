#!/usr/bin/env python3
import aws_cdk as cdk

from emr_remote_debugging.stacks.devbox import DevBox
from emr_remote_debugging.stacks.eks import EKSStack
from emr_remote_debugging.stacks.emr_containers import EMRContainersStack
from emr_remote_debugging.stacks.emr_serverless import EMRServerlessStack
from emr_remote_debugging.stacks.vpc import VPCStack

app = cdk.App()

# This creates two VPCs - one for dev boxes and one for EMR resources
vpc_stack = VPCStack(app, "VPCStack")

# Create an EKS cluster for EMR on EKS and an EMR Virtual Cluster
eks = EKSStack(app, "EKSStack", vpc_stack.emr_vpc)
emrc = EMRContainersStack(app, "EMRContainers", vpc_stack.emr_vpc, eks.cluster, vpc_stack.bucket)
emrs = EMRServerlessStack(app, "EMRServerless", vpc_stack.emr_vpc, vpc_stack.bucket)

# Create a devbox for remote debugging
devbox = DevBox(
    app,
    "DevBox",
    vpc_stack.dev_vpc,
    [eks.cluster.cluster_security_group, emrs.security_group],
)

app.synth()
