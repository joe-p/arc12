from fixtures import *


@pytest.mark.reject
def test_two_vault_asa_balance(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
):
    asa_info = TestVars.algod.account_asset_info(
        TestVars.vault_client.app_addr, TestVars.asa_id
    )

    second_asa_info = TestVars.algod.account_asset_info(
        TestVars.vault_client.app_addr, TestVars.second_asa_id
    )

    assert asa_info["asset-holding"]["amount"] == 1
    assert second_asa_info["asset-holding"]["amount"] == 1


@pytest.mark.reject
def test_two_vault_balance(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
):
    info = TestVars.algod.account_info(TestVars.vault_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.reject
def test_two_claim_receiver_balance(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
    second_claim,
):
    info = TestVars.algod.account_asset_info(
        TestVars.receiver.address, TestVars.second_asa_id
    )
    assert info["asset-holding"]["amount"] == 1


@pytest.mark.reject
def test_two_claim_vault_balance(
    create_master,
    create_vault,
    opt_in,
    verify_axfer,
    second_opt_in,
    second_verify_axfer,
    second_claim,
):
    info = TestVars.algod.account_info(TestVars.vault_client.app_addr)
    assert info["amount"] == info["min-balance"]
