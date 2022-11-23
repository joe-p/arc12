import pytest
from fixtures import *
from algosdk.error import AlgodHTTPError


@pytest.mark.create_master
def test_create_master(create_master):
    pass


@pytest.mark.create_vault
def test_create_vault_id(create_master, create_vault):
    assert TestVars.vault_client.app_id > 0


@pytest.mark.create_vault
def test_create_vault_box_name(create_master, create_vault):
    box_names = TestVars.master_client.get_box_names()
    assert len(box_names) == 1
    assert box_names[0] == decode_address(TestVars.receiver.address)


@pytest.mark.create_vault
def test_create_vault_box_value(create_master, create_vault):
    box_value = int.from_bytes(
        TestVars.master_client.get_box_contents(
            decode_address(TestVars.receiver.address)
        ),
        byteorder="big",
    )
    assert box_value == TestVars.vault_client.app_id


@pytest.mark.create_vault
def test_create_vault_creator(create_master, create_vault):
    assert decode_address(TestVars.creator.address) == bytes.fromhex(
        TestVars.vault_client.get_application_state()["creator"]
    )


@pytest.mark.create_vault
def test_create_vault_receiver(create_master, create_vault):
    assert decode_address(TestVars.receiver.address) == bytes.fromhex(
        TestVars.vault_client.get_application_state()["receiver"]
    )


@pytest.mark.create_vault
def test_create_vault_mbr(create_master, create_vault, opt_in):
    info = TestVars.algod.account_info(TestVars.master_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.opt_in
def test_opt_in_box_name(create_master, create_vault, opt_in):
    box_names = TestVars.vault_client.get_box_names()
    assert len(box_names) == 1
    assert box_names[0] == TestVars.asa_id.to_bytes(8, "big")


@pytest.mark.opt_in
def test_opt_in_box_value(create_master, create_vault, opt_in):
    box_value = TestVars.vault_client.get_box_contents(
        TestVars.asa_id.to_bytes(8, "big")
    )
    assert box_value == decode_address(TestVars.creator.address)


@pytest.mark.opt_in
def test_opt_in_mbr(create_master, create_vault, opt_in):
    info = TestVars.algod.account_info(TestVars.vault_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.verify_axfer
def test_verify_axfer(create_master, create_vault, opt_in, verify_axfer):
    asa_info = TestVars.algod.account_asset_info(
        TestVars.vault_client.app_addr, TestVars.asa_id
    )
    assert asa_info["asset-holding"]["amount"] == 1


@pytest.mark.claim
def test_claim_axfer(create_master, create_vault, opt_in, verify_axfer, claim):
    asa_info = TestVars.algod.account_asset_info(
        TestVars.receiver.address, TestVars.asa_id
    )
    assert asa_info["asset-holding"]["amount"] == 1


@pytest.mark.claim
def test_claim_delete_vault(create_master, create_vault, opt_in, verify_axfer, claim):
    with pytest.raises(AlgodHTTPError) as e:
        TestVars.algod.application_info(TestVars.vault_client.app_id)
    assert e.match("application does not exist")


@pytest.mark.claim
def test_claim_vault_balance(create_master, create_vault, opt_in, verify_axfer, claim):
    info = TestVars.algod.account_info(TestVars.vault_client.app_addr)
    assert info["amount"] == 0


@pytest.mark.claim
def test_claim_master_balance(create_master, create_vault, opt_in, verify_axfer, claim):
    info = TestVars.algod.account_info(TestVars.master_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.claim
def test_claim_creator_balance(
    create_master, create_vault, opt_in, verify_axfer, claim
):
    amt = TestVars.algod.account_info(TestVars.creator.address)["amount"]
    expected_amt = TestVars.creator_pre_vault_balance - 1_000 * 10
    assert amt == expected_amt


@pytest.mark.claim
def test_claim_receiver_balance(
    create_master, create_vault, opt_in, verify_axfer, claim
):
    amt = TestVars.algod.account_info(TestVars.receiver.address)["amount"]
    expected_amt = TestVars.receiver_pre_vault_balance - 1_000 * 8
    assert amt == expected_amt
