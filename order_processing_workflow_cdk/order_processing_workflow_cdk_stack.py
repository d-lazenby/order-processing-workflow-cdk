from constructs import Construct
from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_sns as sns,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks 
)


class OrderProcessingWorkflowCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1 Create initial infrastructure resources
        # LAMBDA FUNCTIONS
        payment_verifier_lambda = lambda_.Function(
            self, 
            "PaymentVerifier_CDK",
            code=lambda_.Code.from_asset("lambda"),
            handler="payment_verifier.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11
        )

        items_in_stock_retriver_lambda = lambda_.Function(
            self, 
            "ItemsInStockRetriever_CDK",
            code=lambda_.Code.from_asset("lambda"),
            handler="items_in_stock_retriever.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11
        )

        charge_payment_method_lambda = lambda_.Function(
            self, 
            "ChargePaymentMethod_CDK",
            code=lambda_.Code.from_asset("lambda"),
            handler="charge_payment_method.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11
        )
        
        #DYNAMODB TABLE
        customer_orders_table = dynamodb.Table(
            self,
            table_name="CustomerOrders_CDK",
            id="CustomerOrders_CDK",
            partition_key=dynamodb.Attribute(
                name="OrderId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
        )
        
        # SNS TOPIC
        order_updates_sns = sns.Topic(
            self, 
            display_name="OrderUpdates_CDK",
            id="OrderUpdates_CDK"
        )

        # Create Invoke Tasks
        verify_payment_lambda_invoke = tasks.LambdaInvoke(
            self,
            "Verify Payment Details",
            lambda_function=payment_verifier_lambda,
            output_path="$.Payload"
        )

        items_in_stock_retriver_lambda_invoke = tasks.LambdaInvoke(
            self,
            "Retrieve Item Stock Levels",
            lambda_function=items_in_stock_retriver_lambda,
            payload=sfn.TaskInput.from_object({
                "items.$": "$.orderContents.items"
            }),
            output_path="$.Payload"
        )

        charge_payment_method_lambda_invoke = tasks.LambdaInvoke(
            self,
            "Charge Customer",
            lambda_function=charge_payment_method_lambda,
            result_path="$.output"
        )

        # Create Parallel task with output transformer

        fail_entire_workflow = sfn.Fail(self, "Fail")

        parallel_task = (sfn.Parallel(
            self,
            "ParallelTask",
            result_selector={
                "paymentVerified.$": "$[0].paymentVerified",
                "items.$": "$[1]"
            },
            result_path="$.output"
            )
            .branch(verify_payment_lambda_invoke)
            .branch(items_in_stock_retriver_lambda_invoke)
            .add_catch(fail_entire_workflow)
        )

        output_transformer_pass = sfn.Pass(
            self,
            "Output Transformer",
            parameters={
                "items.$": "$.output.items",
                "orderTotal.$": "$.orderTotal",
                "customerId.$": "$.customerId",
                "paymentDetails.$": "$.paymentDetails",
                "paymentVerified.$": "$.output.paymentVerified"
            }
        )

        parallel_task.next(output_transformer_pass)

        # Create Map task

        map_task = sfn.Map(
            self,
            "Validate quantity of items > 0",
            max_concurrency=1,
            items_path="$.items",
            result_path=sfn.JsonPath.DISCARD
        ).add_catch(fail_entire_workflow)


        map_tassk_fail_not_in_stock = sfn.Fail(self, "Item not in stock")
        map_task_pass_placeholder = sfn.Pass(self, "Pass placeholder")

        map_choice = sfn.Choice(self, "Item in stock or not?")
        choice_item_not_in_stock_condition = sfn.Condition.number_equals(
            "$.quantityInStock", 0
        )

        map_choice.when(
            choice_item_not_in_stock_condition, map_tassk_fail_not_in_stock
            ).otherwise(map_task_pass_placeholder)
        
        map_task.iterator(map_choice)

        output_transformer_pass.next(map_task)
        
        # Create Charge customer, save, publish

        map_task.next(charge_payment_method_lambda_invoke)

        ddb_put_item_payment_processed = tasks.DynamoPutItem(
            self,
            "Create order with state PAYMENT_PROCESSED",
            table=customer_orders_table,
            item={
                "OrderId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("States.UUID()")),
                "State": tasks.DynamoAttributeValue.from_string("PAYMENT_PROCESSED"),
                "CustomerId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.customerId")),
                "OrderTotal": tasks.DynamoAttributeValue.from_number(sfn.JsonPath.number_at("States.Format('{}', $.orderTotal)")),
                "Items": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("States.JsonToString($.items)"))
            },
            result_path=sfn.JsonPath.DISCARD
        )

        ddb_put_item_payment_failed = tasks.DynamoPutItem(
            self,
            "Create order with state PAYMENT_FAILED",
            table=customer_orders_table,
            item={
                "OrderId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("States.UUID()")),
                "State": tasks.DynamoAttributeValue.from_string("PAYMENT_FAILED"),
                "CustomerId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.customerId")),
                "OrderTotal": tasks.DynamoAttributeValue.from_number(sfn.JsonPath.number_at("States.Format('{}', $.orderTotal)")),
                "Items": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("States.JsonToString($.items)"))
            },
            result_path=sfn.JsonPath.DISCARD
        )

        charge_payment_method_lambda_invoke.next(ddb_put_item_payment_processed)
        charge_payment_method_lambda_invoke.add_catch(
            ddb_put_item_payment_failed, 
            result_path="$.output",
            errors=["PaymentError"]
            )
        
        sns_publish = tasks.SnsPublish(
            self,
            "Publish to interested parties",
            topic=order_updates_sns,
            message=sfn.TaskInput.from_json_path_at("$")
        )

        ddb_put_item_payment_failed.next(sns_publish)
        ddb_put_item_payment_processed.next(sns_publish)

        state_machine = sfn.StateMachine(
            self, "OrderProcessingWorkflowCdk", definition=parallel_task
            )
        
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=["lambda:*", "states:*", "dynamodb:*", "sns:*"]
            )
        )


    