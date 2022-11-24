from fixtures import *
from algosdk.error import AlgodHTTPError


@pytest.mark.reject
def test_two_reject_vault_asa_balance(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
    second_reject,
):
    with pytest.raises(AlgodHTTPError) as e:
        TestVars.algod.account_asset_info(
            TestVars.receiver.address, TestVars.second_asa_id
        )
    assert e.match("account asset info not found")


@pytest.mark.reject
def test_two_claim_vault_balance(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
    second_reject,
):
    info = TestVars.algod.account_info(TestVars.vault_client.app_addr)
    assert info["amount"] == info["min-balance"]
