from diagrams import Cluster, Diagram
from diagrams.aws.analytics import EMRCluster
from diagrams.aws.compute import EC2Instance
from diagrams.aws.network import VPCPeering
from diagrams.programming.language import Python

with Diagram("EMR Remote Debugging", show=False):
    with Cluster("Corp"):
        dev = Python("Local dev machine")

    with Cluster("AWS"):
        with Cluster("DevBox VPC"):
            devbox = [EC2Instance("Bastion Host")]
            vpc1peer = VPCPeering()

        with Cluster("EMR VPC"):
            vpc2peer = VPCPeering()
            emrs = EMRCluster("EMR Serverless")
            with Cluster("EKS Cluster"):
                emrk8s = EMRCluster("EMR Virtual Cluster")

        vpc1peer >> vpc2peer
        emrs >> devbox
        emrk8s >> devbox
    
    devbox >> dev
