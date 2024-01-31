import aws_cdk as core
import aws_cdk.assertions as assertions

from emr_remote_debugging.emr_remote_debugging_stack import EmrRemoteDebuggingStack

# example tests. To run these tests, uncomment this file along with the example
# resource in emr_remote_debugging/emr_remote_debugging_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = EmrRemoteDebuggingStack(app, "emr-remote-debugging")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
