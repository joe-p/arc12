from fixtures import *


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


# TODO: Fix below balance assertions
# TODO: Reduce fee cost for receiver as much as possible


@pytest.mark.skip(reason="Need to update the balances")
def test_reject_creator_balance(
    create_master, create_vault, opt_in, verify_axfer, reject
):
    amt = TestVars.algod.account_info(TestVars.creator.address)["amount"]
    expected_amt = TestVars.creator_pre_vault_balance - 1_000 * 10
    assert amt == expected_amt


@pytest.mark.skip(reason="Need to update the balances")
def test_reject_receiver_balance(
    create_master, create_vault, opt_in, verify_axfer, reject
):
    amt = TestVars.algod.account_info(TestVars.receiver.address)["amount"]
    expected_amt = TestVars.receiver_pre_vault_balance - 1_000 * 8
    assert amt == expected_amt
