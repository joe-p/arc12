import pytest
from fixtures import *
from algosdk.error import AlgodHTTPError


@pytest.mark.reject
def test_premature_claim_delete(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
):
    with pytest.raises(AlgodHTTPError) as e:
        claim_from(TestVars.receiver)
    assert e.match("assert failed pc=424")


@pytest.mark.reject
def test_wrong_claimer(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
):
    with pytest.raises(AlgodHTTPError) as e:
        claim_from(TestVars.random_acct)
    assert e.match("assert failed pc=486")
