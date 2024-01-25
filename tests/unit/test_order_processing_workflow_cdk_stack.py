import aws_cdk as core
import aws_cdk.assertions as assertions
from order_processing_workflow_cdk.order_processing_workflow_cdk_stack import OrderProcessingWorkflowCdkStack


def test_sqs_queue_created():
    app = core.App()
    stack = OrderProcessingWorkflowCdkStack(app, "order-processing-workflow-cdk")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::SQS::Queue", {
        "VisibilityTimeout": 300
    })


def test_sns_topic_created():
    app = core.App()
    stack = OrderProcessingWorkflowCdkStack(app, "order-processing-workflow-cdk")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::SNS::Topic", 1)
