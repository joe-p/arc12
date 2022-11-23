from fixtures import *
from algosdk.error import AlgodHTTPError


@pytest.mark.reject
def test_reject_axfer(create_master, create_vault, opt_in, verify_axfer, reject):
    asa_info = TestVars.algod.account_asset_info(
        TestVars.creator.address, TestVars.asa_id
    )
    assert asa_info["asset-holding"]["amount"] == 1


@pytest.mark.reject
def test_reject_delete_vault(create_master, create_vault, opt_in, verify_axfer, reject):
    with pytest.raises(AlgodHTTPError) as e:
        TestVars.algod.application_info(TestVars.vault_client.app_id)
    assert e.match("application does not exist")


@pytest.mark.reject
def test_reject_vault_balance(
    create_master, create_vault, opt_in, verify_axfer, reject
):
    info = TestVars.algod.account_info(TestVars.vault_client.app_addr)
    assert info["amount"] == 0


@pytest.mark.reject
def test_reject_master_balance(
    create_master, create_vault, opt_in, verify_axfer, reject
):
    info = TestVars.algod.account_info(TestVars.master_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.skip("TODO: Fix this test to have proper amount")
def test_reject_creator_balance(
    create_master, create_vault, opt_in, verify_axfer, reject
):
    assert (
        TestVars.algod.account_info(TestVars.creator.address)["amount"]
        == TestVars.creator_pre_reject_balance
    )


@pytest.mark.reject
def test_reject_receiver_balance(
    create_master, create_vault, opt_in, verify_axfer, reject
):
    assert (
        TestVars.algod.account_info(TestVars.receiver.address)["amount"]
        == TestVars.receiver_pre_reject_balance
    )
