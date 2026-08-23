import pytest

from aioa_cloudops_agent.domain import (
    AuthorityGate,
    AwsBoundaryViolationError,
    AwsOperation,
    AwsOperationClass,
    ContractValidationError,
    HumanApprovalState,
    assess_aws_operation,
    classify_aws_operation,
)


@pytest.mark.parametrize(
    "operation",
    [
        AwsOperation.DESCRIBE_ADDRESSES,
        AwsOperation.DESCRIBE_SECURITY_GROUPS,
        AwsOperation.DESCRIBE_INSTANCES,
        AwsOperation.DESCRIBE_TAGS,
    ],
)
def test_read_only_operation_may_use_auto(operation: AwsOperation) -> None:
    assessment = assess_aws_operation(operation, AuthorityGate.AUTO)

    assert classify_aws_operation(operation) is AwsOperationClass.READ_ONLY
    assert assessment.operation_class is AwsOperationClass.READ_ONLY
    assert assessment.may_execute is True
    assert assessment.human_approval_required is False


@pytest.mark.parametrize(
    "operation",
    [AwsOperation.RELEASE_ADDRESS, AwsOperation.MODIFY_SECURITY_GROUP_RULES],
)
def test_mutation_with_auto_is_rejected(operation: AwsOperation) -> None:
    with pytest.raises(AwsBoundaryViolationError, match="must never use the AUTO"):
        assess_aws_operation(operation, AuthorityGate.AUTO)


def test_plan_and_confirm_mutation_may_be_proposed_but_is_not_approved() -> None:
    assessment = assess_aws_operation(
        AwsOperation.RELEASE_ADDRESS,
        AuthorityGate.PLAN_AND_CONFIRM,
        aws_mutations_enabled=True,
    )

    assert assessment.may_propose is True
    assert assessment.may_execute is False
    assert assessment.human_approval_required is True
    assert assessment.human_approval_granted is False


def test_configuration_flag_alone_is_not_human_approval() -> None:
    assessment = assess_aws_operation(
        AwsOperation.RELEASE_ADDRESS,
        AuthorityGate.PLAN_AND_CONFIRM,
        aws_mutations_enabled=True,
        human_approval=HumanApprovalState.NOT_GRANTED,
    )

    assert assessment.may_execute is False


def test_approval_cannot_bypass_global_mutation_disable() -> None:
    assessment = assess_aws_operation(
        AwsOperation.RELEASE_ADDRESS,
        AuthorityGate.PLAN_AND_CONFIRM,
        aws_mutations_enabled=False,
        human_approval=HumanApprovalState.GRANTED,
    )

    assert assessment.may_execute is False


def test_plan_and_confirm_requires_both_independent_controls() -> None:
    assessment = assess_aws_operation(
        AwsOperation.RELEASE_ADDRESS,
        AuthorityGate.PLAN_AND_CONFIRM,
        aws_mutations_enabled=True,
        human_approval=HumanApprovalState.GRANTED,
    )

    assert assessment.may_execute is True
    assert assessment.human_approval_granted is True


def test_never_autonomous_mutation_cannot_execute() -> None:
    assessment = assess_aws_operation(
        AwsOperation.MODIFY_SECURITY_GROUP_RULES,
        AuthorityGate.NEVER_AUTONOMOUS,
        aws_mutations_enabled=True,
        human_approval=HumanApprovalState.GRANTED,
    )

    assert assessment.may_propose is True
    assert assessment.may_execute is False


def test_security_group_mutation_rejects_plan_and_confirm() -> None:
    with pytest.raises(AwsBoundaryViolationError, match="requires the NEVER_AUTONOMOUS"):
        assess_aws_operation(
            AwsOperation.MODIFY_SECURITY_GROUP_RULES,
            AuthorityGate.PLAN_AND_CONFIRM,
            aws_mutations_enabled=True,
            human_approval=HumanApprovalState.GRANTED,
        )


def test_configuration_boolean_cannot_be_used_as_human_approval() -> None:
    with pytest.raises(ContractValidationError, match="HumanApprovalState"):
        assess_aws_operation(
            AwsOperation.RELEASE_ADDRESS,
            AuthorityGate.PLAN_AND_CONFIRM,
            aws_mutations_enabled=True,
            human_approval=True,
        )


def test_unknown_operation_has_no_silent_fallback() -> None:
    with pytest.raises(ContractValidationError, match="AwsOperation"):
        classify_aws_operation("DESCRIBE_VOLUMES")
