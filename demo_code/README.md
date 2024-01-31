# Remote debugging with PySpark and EMR

What we'll do is build a simple demo that just reads some data from S3.

It will utilize environment variables to determine remote debugger host and port as these can change.

In addition, we'll generate a virtualenv archive that just includes pydevd.

## Spark environment variables

In order to set driver environment variables, each cluster manager (YARN, Kubernetes, EMR Serverless) utilize different Spark config entries.

- YARN (cluster mode): `spark.yarn.appMasterEnv.[EnvironmentVariableName]`
- Kubernetes: `spark.kubernetes.driverEnv.[EnvironmentVariableName]`
- EMR Serverless: `spark.emr-serverless.driverEnv.[EnvironmentVariableName]`

Executor environment variables are the same: `spark.executorEnv.[EnvironmentVariableName]`

## PyCharm Debugger

PyCharm uses `pydevd` - for this tutorial, we're using the latest version of PyCharm at the time (`2023.3.3`) and `pydevd-pycharm~=241.9959.30'`.

We use the [Dockerfile](./Dockerfile) to build a pydevd archive for EMR 6.x releases.

```bash
docker build --output dist .
```

## EMR on EKS

We'll start here. First, let's upload our dependencies and job to S3.

Replace the outputs below from your `cdk deploy` console output.

```bash
S3_BUCKET=<Output EMRServerless.S3Bucket>
VIRTUAL_CLUSTER_ID=<Output EMRContainers.EMRVirtualClusterID>
EMR_EKS_JOB_ROLE=<Output EMRContainers.JobRoleArn>

aws s3 cp debug_demo.py s3://${S3_BUCKET}/code/remote-debugging/
aws s3 cp dist/pyspark_deps.tar.gz s3://${S3_BUCKET}/code/remote-debugging/
```

Next, we trigger a job. First, we'll just run the job to make sure it works.

```bash
aws emr-containers start-job-run \
    --name remote-debug \
    --virtual-cluster-id ${VIRTUAL_CLUSTER_ID} \
    --release-label emr-6.15.0-latest \
    --execution-role-arn ${EMR_EKS_JOB_ROLE} \
    --job-driver '{
      "sparkSubmitJobDriver": {
        "entryPoint": "s3://'${S3_BUCKET}'/code/remote-debugging/debug_demo.py",
        "sparkSubmitParameters": "--archives s3://'${S3_BUCKET}'/code/remote-debugging/pyspark_deps.tar.gz#environment"
      }
    }' \
    --configuration-overrides '{
        "monitoringConfiguration": {
            "s3MonitoringConfiguration": { "logUri": "s3://'${S3_BUCKET}'/logs/emr-eks/remote-debug" }
        },
        "applicationConfiguration": [
          {
            "classification": "spark-defaults", 
            "properties": {
              "spark.pyspark.python":"./environment/bin/python"
            }
          }
        ]
    }'
```

Now we check the status of the job...

```bash
JOB_RUN_ID=<id from start-job-run output>
aws emr-containers describe-job-run --virtual-cluster-id ${VIRTUAL_CLUSTER_ID} --id ${JOB_RUN_ID}
```

Great, it completed. Check the logs as well.

```bash
aws s3 cp s3://${S3_BUCKET}/logs/emr-eks/remote-debug/${VIRTUAL_CLUSTER_ID}/jobs/${JOB_RUN_ID}/containers/spark-${JOB_RUN_ID}/spark-${JOB_RUN_ID}-driver/stdout.gz - | gunzip
214 records for 2023
365 records for 2022
Row(location_title='Seattle Boeing Field, WA US')
```

> [!TIP]
> If you have the [EMR CLI](https://github.com/awslabs/amazon-emr-cli) installed, you can also submit your job with the following command.

```shell
emr run \
  --entry-point debug_demo.py \
  --virtual-cluster-id ${VIRTUAL_CLUSTER_ID} \
  --job-role ${EMR_EKS_JOB_ROLE} \
  --s3-code-uri s3://${S3_BUCKET}/code/remote-debugging/ \
  --s3-logs-uri s3://${S3_BUCKET}/logs/emr-eks/ \
  --show-stdout
```

Now we need to try to debug. Our instance ID is `i-079d818ede57eed37`. 

We use SSM to SSH in, but let's also get the IP address.

```bash
INSTANCE_ID=i-079d818ede57eed37
DEBUG_IP=$(aws ec2 describe-instances --instance-ids ${INSTANCE_ID} \
    --query 'Reservations[*].Instances[*].PrivateIpAddress' \
    --output text)
DEBUG_PORT=3535
```

```shell
ssh -R '3535:localhost:3535' ec2-user@${INSTANCE_ID}
```

Now, let's start the job again and enable our remote debugger by passing in `DEBUG_HOST` and `DEBUG_PORT` environment variables.

```bash
aws emr-containers start-job-run \
    --name remote-debug \
    --virtual-cluster-id ${VIRTUAL_CLUSTER_ID} \
    --release-label emr-6.11.0-latest \
    --execution-role-arn ${EMR_EKS_JOB_ROLE} \
    --job-driver '{
      "sparkSubmitJobDriver": {
        "entryPoint": "s3://'${S3_BUCKET}'/code/remote-debugging/debug_demo.py",
        "sparkSubmitParameters": "--archives s3://'${S3_BUCKET}'/code/remote-debugging/pyspark_deps.tar.gz#environment --conf spark.kubernetes.driverEnv.DEBUG_HOST='${DEBUG_IP}' --conf spark.kubernetes.driverEnv.DEBUG_PORT=3535"
      }
    }' \
    --configuration-overrides '{
        "monitoringConfiguration": {
            "s3MonitoringConfiguration": { "logUri": "s3://'${S3_BUCKET}'/logs/emr-eks/remote-debug" }
        },
        "applicationConfiguration": [
          {
            "classification": "spark-defaults", 
            "properties": {
              "spark.pyspark.python":"./environment/bin/python"
            }
          }
        ]
    }'
```

Or for EMR CLI

```shell
emr run \
  --entry-point debug_demo.py \
  --virtual-cluster-id ${VIRTUAL_CLUSTER_ID} \
  --job-role ${EMR_EKS_JOB_ROLE} \
  --s3-code-uri s3://${S3_BUCKET}/code/remote-debugging/ \
  --s3-logs-uri s3://${S3_BUCKET}/logs/emr-eks/ \
  --show-stdout \
  --spark-submit-opts "--conf spark.kubernetes.driverEnv.DEBUG_HOST=${DEBUG_IP} --conf spark.kubernetes.driverEnv.DEBUG_PORT=3535"
```

Check status

```bash
JOB_RUN_ID=000000032dv4obhu6fl
aws emr-containers describe-job-run \
    --virtual-cluster-id ${VIRTUAL_CLUSTER_ID} \
    --id ${JOB_RUN_ID}
```

Hurray it works!

Now we can step through our code in PyCharm.

## EMR Serverless

We can _also_ do the same on EMR Serverless. We just need to make sure it's set up in a VPC and that, again, the security group has access to our devbox. Let's give it a shot!

```bash
aws emr-serverless start-job-run \
    --name remote-debug \
    --application-id $APPLICATION_ID \
    --execution-role-arn $JOB_ROLE_ARN \
    --job-driver '{
        "sparkSubmit": {
            "entryPoint": "s3://'${S3_BUCKET}'/code/remote-debugging/debug_demo.py",
            "sparkSubmitParameters": "--archives s3://'${S3_BUCKET}'/code/remote-debugging/pyspark_deps.tar.gz#environment --conf spark.emr-serverless.driverEnv.DEBUG_HOST='${DEBUG_IP}' --conf spark.emr-serverless.driverEnv.DEBUG_PORT=3535"   
        }
    }' \
    --configuration-overrides '{
        "monitoringConfiguration": {
            "s3MonitoringConfiguration": {
                "logUri": "s3://'${S3_BUCKET}'/logs/emr-serverless/"
            }
        },
        "applicationConfiguration": [
          {
            "classification": "spark-defaults", 
            "properties": {
              "spark.pyspark.python":"./environment/bin/python"
            }
          }
        ]
    }'
```

Check the status!

```bash
JOB_RUN_ID=00fc66ht05qlhg0m
aws emr-serverless get-job-run \
    --application-id ${APPLICATION_ID} \
    --job-run-id ${JOB_RUN_ID}
```

Again, we can use the EMR CLI to run this same job just by changing the parameters:


```shell
emr run \
  --entry-point debug_demo.py \
  --application-id ${APPLICATION_ID} \
  --job-role ${JOB_ROLE_ARN} \
  --s3-code-uri s3://${S3_BUCKET}/code/remote-debugging/ \
  --s3-logs-uri s3://${S3_BUCKET}/logs/emr-eks/ \
  --show-stdout \
  --spark-submit-opts "--conf spark.emr-serverless.driverEnv.DEBUG_HOST=${DEBUG_IP} --conf spark.emr-serverless.driverEnv.DEBUG_PORT=3535"
```