#!/usr/bin/env python3

import aws_cdk as cdk

from order_processing_workflow_cdk.order_processing_workflow_cdk_stack import OrderProcessingWorkflowCdkStack


app = cdk.App()
OrderProcessingWorkflowCdkStack(app, "OrderProcessingWorkflowCdkStack")

app.synth()
