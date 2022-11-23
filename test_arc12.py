from beaker import *
from beaker.client.logic_error import LogicException
from pyteal import *
from pathlib import Path
from algosdk.future import transaction
from algosdk.encoding import decode_address
from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
    AtomicTransactionComposer,
)
from algosdk.error import AlgodHTTPError
import re
import json
import pytest
import time

ZERO_ADDR = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"


class Master(Application):
    @external
    def create(self):
        return Reject()

    @external
    def create_vault(
        self,
        receiver: abi.Account,
        mbr_payment: abi.PaymentTransaction,
        *,
        output: abi.Uint64,
    ):
        return Reject()

    @external
    def verify_axfer(
        self,
        receiver: abi.Account,
        vault_axfer: abi.AssetTransferTransaction,
        vault: abi.Application,
    ):
        return Reject()

    @external
    def get_vault_id(self, receiver: abi.Account, *, output: abi.Uint64):
        return Reject()

    @external
    def get_vault_addr(self, receiver: abi.Account, *, output: abi.Address):
        return Reject()

    @external
    def delete_vault(self, vault: abi.Application, creator: abi.Account):
        return Reject()


class Vault(Application):
    @external
    def opt_in(self, asa: abi.Asset, mbr_payment: abi.PaymentTransaction):
        return Reject()

    @external
    def claim(
        self,
        asa: abi.Asset,
        creator: abi.Account,
        asa_mbr_funder: abi.Account,
    ):
        return Reject()

    @external
    def reject(
        self,
        asa_creator: abi.Account,
        fee_sink: abi.Account,
        asa: abi.Asset,
        vault_creator: abi.Account,
    ):
        return Reject()


def call(app_client, file_name, *args, **kwargs):
    try:
        return app_client.call(*args, **kwargs)

    except (LogicException, AlgodHTTPError) as e:
        if e.__class__.__name__ == "LogicException":
            pc = int(re.findall(r"(?<=at PC).*?\d+", str(e))[0])
        elif "pc" in str(e):
            pc = int(re.findall(r"(?<=pc=).*?\d+", str(e))[0])
        else:
            raise e

        src_map = json.load(Path(f"{file_name}.src_map.json").open())

        teal_line = "Unknown"
        rb_line = "Unknown"
        for teal_ln, data in src_map.items():
            if "pcs" in data.keys() and pc in data["pcs"]:
                teal_line = (
                    Path(f"{file_name}.teal")
                    .read_text()
                    .splitlines()[int(teal_ln) - 1]
                    .strip()
                )

                teal_line = f"./{file_name}.teal:{teal_ln} => {teal_line}"

                rb_line = (
                    Path("arc12.rb")
                    .read_text()
                    .splitlines()[int(data["location"].split(":")[1]) - 1]
                    .strip()
                )

                rb_line = f"./{data['location']} => {rb_line}"
                break

        raise AlgodHTTPError(f"{str(e)}\n{teal_line}\n{rb_line}")


@pytest.fixture(scope="module")
def create_master():
    global creator
    global receiver
    global master_client
    global algod

    accounts = sorted(
        sandbox.get_accounts(),
        key=lambda a: sandbox.clients.get_algod_client().account_info(a.address)[
            "amount"
        ],
    )

    creator = accounts.pop()
    receiver = accounts.pop()

    master_app = Master(version=8)
    master_app.approval_program = Path("master.teal").read_text()
    master_client = client.ApplicationClient(
        client=sandbox.get_algod_client(),
        app=master_app,
        signer=creator.signer,
    )

    algod = master_client.client

    master_client.create(args=[get_method_spec(Master.create).get_selector()])
    master_client.fund(100_000)


def create_vault():
    global vault_client
    global creator_pre_vault_balance
    global receiver_pre_vault_balance

    creator_pre_vault_balance = algod.account_info(creator.address)["amount"]
    receiver_pre_vault_balance = algod.account_info(receiver.address)["amount"]

    sp = master_client.get_suggested_params()
    sp.fee = sp.min_fee * 3
    sp.flat_fee = True

    pay_txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            sender=creator.address,
            receiver=master_client.app_addr,
            amt=347_000,
            sp=sp,
        ),
        signer=creator.signer,
    )

    vault_id = call(
        master_client,
        "master",
        method=Master.create_vault,
        receiver=receiver.address,
        mbr_payment=pay_txn,
        boxes=[[master_client.app_id, decode_address(receiver.address)]],
        foreign_apps=[0],
    ).return_value

    vault_app = Vault(version=8)
    vault_app.approval_program = Path("vault.teal").read_text()
    vault_client = client.ApplicationClient(
        client=sandbox.get_algod_client(),
        app=vault_app,
        signer=creator.signer,
        app_id=vault_id,
    )


def opt_in():
    global asa_id

    txn = transaction.AssetConfigTxn(
        sender=creator.address,
        sp=master_client.get_suggested_params(),
        total=1,
        default_frozen=False,
        unit_name="LATINUM",
        asset_name="latinum",
        decimals=0,
        strict_empty_address_check=False,
    )

    stxn = txn.sign(creator.private_key)
    txid = algod.send_transaction(stxn)
    confirmed_txn = transaction.wait_for_confirmation(algod, txid, 4)
    asa_id = confirmed_txn["asset-index"]

    sp = vault_client.get_suggested_params()
    sp.fee = sp.min_fee * 2
    sp.flat_fee = True

    pay_txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            sender=creator.address,
            receiver=vault_client.app_addr,
            amt=118_500,
            sp=sp,
        ),
        signer=creator.signer,
    )

    call(
        vault_client,
        "vault",
        method=Vault.opt_in,
        asa=asa_id,
        mbr_payment=pay_txn,
        boxes=[[vault_client.app_id, asa_id.to_bytes(8, "big")]],
    )


def verify_axfer():
    axfer = TransactionWithSigner(
        txn=transaction.AssetTransferTxn(
            sender=creator.address,
            receiver=vault_client.app_addr,
            amt=1,
            sp=vault_client.get_suggested_params(),
            index=asa_id,
        ),
        signer=creator.signer,
    )

    res = call(
        master_client,
        "master",
        method=Master.verify_axfer,
        receiver=receiver.address,
        vault_axfer=axfer,
        vault=vault_client.app_id,
        boxes=[[master_client.app_id, decode_address(receiver.address)]],
    )


@pytest.fixture(scope="module")
def claim():
    atc = AtomicTransactionComposer()
    claim_sp = algod.suggested_params()
    claim_sp.fee = claim_sp.min_fee * 4
    claim_sp.flat_fee = True

    del_sp = algod.suggested_params()
    del_sp.fee = del_sp.min_fee * 3
    del_sp.flat_fee = True

    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.AssetOptInTxn(
                sender=receiver.address, sp=algod.suggested_params(), index=asa_id
            ),
            signer=receiver.signer,
        )
    )

    atc.add_method_call(
        app_id=vault_client.app_id,
        sender=receiver.address,
        signer=receiver.signer,
        sp=claim_sp,
        method=application.get_method_spec(Vault.claim),
        method_args=[asa_id, creator.address, ZERO_ADDR],
        boxes=[[vault_client.app_id, asa_id.to_bytes(8, "big")]],
    )

    atc.add_method_call(
        app_id=master_client.app_id,
        sender=receiver.address,
        signer=receiver.signer,
        sp=del_sp,
        method=application.get_method_spec(Master.delete_vault),
        method_args=[vault_client.app_id, creator.address],
        boxes=[[master_client.app_id, decode_address(receiver.address)]],
    )

    atc.execute(algod, 3)


@pytest.fixture(scope="module")
def reject():
    atc = AtomicTransactionComposer()
    reject_sp = algod.suggested_params()
    reject_sp.fee = reject_sp.min_fee * 2
    reject_sp.flat_fee = True

    del_sp = algod.suggested_params()
    del_sp.fee = del_sp.min_fee * 3
    del_sp.flat_fee = True

    atc.add_method_call(
        app_id=vault_client.app_id,
        sender=receiver.address,
        signer=receiver.signer,
        sp=reject_sp,
        method=application.get_method_spec(Vault.reject),
        method_args=[
            creator.address,
            "Y76M3MSY6DKBRHBL7C3NNDXGS5IIMQVQVUAB6MP4XEMMGVF2QWNPL226CA",
            asa_id,
            ZERO_ADDR,
        ],
        boxes=[[vault_client.app_id, asa_id.to_bytes(8, "big")]],
    )

    atc.add_method_call(
        app_id=master_client.app_id,
        sender=receiver.address,
        signer=receiver.signer,
        sp=del_sp,
        method=application.get_method_spec(Master.delete_vault),
        method_args=[vault_client.app_id, creator.address],
        boxes=[[master_client.app_id, decode_address(receiver.address)]],
    )

    atc.execute(algod, 3)


@pytest.fixture(scope="module")
def create_vault_claim():
    create_vault()


@pytest.fixture(scope="module")
def opt_in_claim():
    opt_in()


@pytest.fixture(scope="module")
def opt_in_claim():
    opt_in()


@pytest.fixture(scope="module")
def verify_axfer_claim():
    verify_axfer()


@pytest.fixture(scope="module")
def create_vault_reject():
    create_vault()


@pytest.fixture(scope="module")
def opt_in_reject():
    opt_in()


@pytest.fixture(scope="module")
def opt_in_reject():
    opt_in()


@pytest.fixture(scope="module")
def verify_axfer_reject():
    verify_axfer()


@pytest.mark.create_master
def test_create_master(create_master):
    pass


@pytest.mark.create_vault
def test_create_vault_id(create_master, create_vault_claim):
    assert vault_client.app_id > 0


@pytest.mark.create_vault
def test_create_vault_box_name(create_master, create_vault_claim):
    box_names = master_client.get_box_names()
    assert len(box_names) == 1
    assert box_names[0] == decode_address(receiver.address)


@pytest.mark.create_vault
def test_create_vault_box_value(create_master, create_vault_claim):
    box_value = int.from_bytes(
        master_client.get_box_contents(decode_address(receiver.address)),
        byteorder="big",
    )
    assert box_value == vault_client.app_id


@pytest.mark.create_vault
def test_create_vault_creator(create_master, create_vault_claim):
    assert decode_address(creator.address) == bytes.fromhex(
        vault_client.get_application_state()["creator"]
    )


@pytest.mark.create_vault
def test_create_vault_receiver(create_master, create_vault_claim):
    assert decode_address(receiver.address) == bytes.fromhex(
        vault_client.get_application_state()["receiver"]
    )


@pytest.mark.create_vault
def test_create_vault_mbr(create_master, create_vault_claim, opt_in_claim):
    info = algod.account_info(master_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.opt_in
def test_opt_in_box_name(create_master, create_vault_claim, opt_in_claim):
    box_names = vault_client.get_box_names()
    assert len(box_names) == 1
    assert box_names[0] == asa_id.to_bytes(8, "big")


@pytest.mark.opt_in
def test_opt_in_box_value(create_master, create_vault_claim, opt_in_claim):
    box_value = vault_client.get_box_contents(asa_id.to_bytes(8, "big"))
    assert box_value == decode_address(creator.address)


@pytest.mark.opt_in
def test_opt_in_mbr(create_master, create_vault_claim, opt_in_claim):
    info = algod.account_info(vault_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.verify_axfer
def test_verify_axfer(
    create_master, create_vault_claim, opt_in_claim, verify_axfer_claim
):
    asa_info = algod.account_asset_info(vault_client.app_addr, asa_id)
    assert asa_info["asset-holding"]["amount"] == 1


@pytest.mark.claim
def test_claim_axfer(
    create_master, create_vault_claim, opt_in_claim, verify_axfer_claim, claim
):
    asa_info = algod.account_asset_info(receiver.address, asa_id)
    assert asa_info["asset-holding"]["amount"] == 1


@pytest.mark.claim
def test_claim_delete_vault(
    create_master, create_vault_claim, opt_in_claim, verify_axfer_claim, claim
):
    with pytest.raises(AlgodHTTPError) as e:
        algod.application_info(vault_client.app_id)
    assert e.match("application does not exist")


@pytest.mark.claim
def test_claim_vault_balance(
    create_master, create_vault_claim, opt_in_claim, verify_axfer_claim, claim
):
    info = algod.account_info(vault_client.app_addr)
    assert info["amount"] == 0


@pytest.mark.claim
def test_claim_master_balance(
    create_master, create_vault_claim, opt_in_claim, verify_axfer_claim, claim
):
    info = algod.account_info(master_client.app_addr)
    assert info["amount"] == info["min-balance"]


@pytest.mark.claim
def test_claim_creator_balance(
    create_master, create_vault_claim, opt_in_claim, verify_axfer_claim, claim
):
    amt = algod.account_info(creator.address)["amount"]
    expected_amt = creator_pre_vault_balance - 1_000 * 10
    assert amt == expected_amt


@pytest.mark.claim
def test_claim_receiver_balance(
    create_master, create_vault_claim, opt_in_claim, verify_axfer_claim, claim
):
    amt = algod.account_info(receiver.address)["amount"]
    expected_amt = receiver_pre_vault_balance - 1_000 * 8
    assert amt == expected_amt


@pytest.mark.reject
def test_reject_axfer(
    create_master, create_vault_reject, opt_in_reject, verify_axfer_reject, reject
):
    asa_info = algod.account_asset_info(creator.address, asa_id)
    assert asa_info["asset-holding"]["amount"] == 1


@pytest.mark.reject
def test_reject_delete_vault(
    create_master, create_vault_reject, opt_in_reject, verify_axfer_reject, claim
):
    with pytest.raises(AlgodHTTPError) as e:
        algod.application_info(vault_client.app_id)
    assert e.match("application does not exist")


@pytest.mark.reject
def test_reject_vault_balance(
    create_master, create_vault_reject, opt_in_reject, verify_axfer_reject, claim
):
    info = algod.account_info(vault_client.app_addr)
    assert info["amount"] == 0


@pytest.mark.reject
def test_reject_master_balance(
    create_master, create_vault_reject, opt_in_reject, verify_axfer_reject, claim
):
    info = algod.account_info(master_client.app_addr)
    assert info["amount"] == info["min-balance"]


# TODO: Fix below balance assertions
# TODO: Reduce fee cost for receiver as much as possible


@pytest.mark.skip(reason="Need to update the balances")
def test_reject_creator_balance(
    create_master, create_vault_reject, opt_in_reject, verify_axfer_reject, claim
):
    amt = algod.account_info(creator.address)["amount"]
    expected_amt = creator_pre_vault_balance - 1_000 * 10
    assert amt == expected_amt


@pytest.mark.skip(reason="Need to update the balances")
def test_reject_receiver_balance(
    create_master, create_vault_reject, opt_in_reject, verify_axfer_reject, claim
):
    amt = algod.account_info(receiver.address)["amount"]
    expected_amt = receiver_pre_vault_balance - 1_000 * 8
    assert amt == expected_amt
