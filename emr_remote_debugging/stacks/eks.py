from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_eks as eks
from aws_cdk import aws_iam as iam
from aws_cdk.lambda_layer_kubectl_v28 import KubectlV28Layer
from cdk_eks_karpenter import Karpenter
from constructs import Construct


class EKSStack(Stack):
    cluster_name: str
    cluster: eks.Cluster

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.cluster_name = "data-team"

        # EKS cluster
        self.cluster: eks.Cluster = eks.Cluster(
            self,
            "EksForSpark",
            cluster_name=self.cluster_name,
            version=eks.KubernetesVersion.V1_28,
            default_capacity=1,
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,
            vpc=vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            kubectl_layer=KubectlV28Layer(self, "kubectl"),
            core_dns_compute_type=eks.CoreDnsComputeType.FARGATE,
        )

        # Use Karpenter to manage capacity
        self.cluster.add_fargate_profile(
            "karpenter",
            selectors=[{"namespace": "karpenter"}, {"namespace": "kube-system", "labels": {"k8s-app": "kube-dns"}}],
        )
        karpenter = Karpenter(self, "Karpenter", cluster=self.cluster, version="v0.32.5")
        self.add_nodes(karpenter, vpc)
        karpenter.add_managed_policy_to_karpenter_role(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        self.add_admin_role_to_cluster()
        self.add_cluster_admin()

        # We like to use the Kubernetes Dashboard
        # self.enable_dashboard()

        # This is emr-specific, but we have to do it here to prevent circular dependencies
        self.map_iam_to_eks()

    def add_nodes(self, karp: Karpenter, vpc: ec2.IVpc) -> None:
        node_class = karp.add_ec2_node_class(
            "nodeclass",
            {
                "amiFamily": "AL2",
                "subnetSelectorTerms": [{"tags": {"Name": f"{vpc.stack.stack_name}/{vpc.node.id}/PrivateSubnet*"}}],
                "securityGroupSelectorTerms": [{"tags": {"aws:eks:cluster-name": self.cluster.cluster_name}}],
                "role": karp.node_role.role_name,
            },
        )

        # Note our requirements here are somewhat specific to EMR
        # EMR recommends using instances >= m5.xl
        # https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/getting-started.html
        karp.add_node_pool(
            "nodepool",
            {
                "template": {
                    "spec": {
                        "nodeClassRef": {
                            "apiVersion": "karpenter.k8s.aws/v1beta1",
                            "kind": "EC2NodeClass",
                            "name": node_class.get("name"),
                        },
                        "requirements": [
                            {
                                "key": "karpenter.k8s.aws/instance-category",
                                "operator": "In",
                                "values": ["m", "c", "r"],
                            },
                            {
                                "key": "kubernetes.io/arch",
                                "operator": "In",
                                "values": ["amd64"],
                            },
                            {
                                "key": "karpenter.k8s.aws/instance-generation",
                                "operator": "Gt",
                                "values": ["5"],
                            },
                            {
                                "key": "karpenter.k8s.aws/instance-cpu",
                                "operator": "In",
                                "values": ["4", "8", "16", "32"],
                            },
                        ],
                    },
                },
            },
        )

    def add_provisioner(self, karp: Karpenter) -> None:
        karp.add_provisioner(
            "spot-provisioner",
            provisioner_spec={
                "requirements": [
                    {
                        "key": "karpenter.sh/capacity-type",
                        "operator": "In",
                        "values": ["spot"],
                    }
                ],
                "limits": {"resources": {"cpu": 20}},
                "provider": {
                    "subnet_selector": {"Name": "PrivateSubnet*"},
                    "security_group_selector": {"aws:eks:cluster-name": self.cluster.cluster_name},
                },
            },
        )

    def add_admin_role_to_cluster(self) -> None:
        admin_role_name = self.node.try_get_context("eks_admin_role_name")
        if admin_role_name is None:
            return

        account_id = self.account
        admin_role = iam.Role.from_role_arn(self, "admin_role", f"arn:aws:iam::{account_id}:role/{admin_role_name}")
        self.cluster.aws_auth.add_masters_role(admin_role)

    def add_cluster_admin(self, name="eks-admin"):
        # Add admin privileges so we can sign in to the dashboard as the service account
        sa = self.cluster.add_manifest(
            "eks-admin-sa",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": name,
                    "namespace": "kube-system",
                },
            },
        )
        binding = self.cluster.add_manifest(
            "eks-admin-rbac",
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": name},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "cluster-admin",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": name,
                        "namespace": "kube-system",
                    }
                ],
            },
        )

    def enable_dashboard(self, namespace: str = "kubernetes-dashboard"):
        # The name here needs to be tiny because metadata.name can't be more than 63 characters and it's stack/stack/hart/resource/uniqid/nginx-something-something
        chart = self.cluster.add_helm_chart(
            "k8d",
            namespace=namespace,
            chart="kubernetes-dashboard",
            repository="https://kubernetes.github.io/dashboard/",
            values={
                "fullnameOverride": "kubernetes-dashboard",  # This must be set to access the UI via `kubectl proxy`
                "extraArgs": ["--token-ttl=0"],
            },
        )

    def map_iam_to_eks(self):
        service_role_name = f"arn:aws:iam::{self.account}:role/AWSServiceRoleForAmazonEMRContainers"
        emrsvcrole = iam.Role.from_role_arn(self, "EmrSvcRole", service_role_name, mutable=False)
        self.cluster.aws_auth.add_role_mapping(emrsvcrole, groups=[], username="emr-containers")

    def add_emr_containers_for_airflow(self) -> eks.ServiceAccount:
        sa = self.cluster.add_service_account("AirflowServiceAccount", namespace="airflow")

        sa.add_to_principal_policy(
            iam.PolicyStatement(
                actions=[
                    "emr-containers:StartJobRun",
                    "emr-containers:ListJobRuns",
                    "emr-containers:DescribeJobRun",
                    "emr-containers:CancelJobRun",
                ],
                resources=["*"],
            )
        )

        return sa
