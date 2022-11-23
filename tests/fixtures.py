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
from contracts import Vault, Master

ZERO_ADDR = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"
ARTIFACTS = Path.joinpath(Path(__file__).parent.parent, "artifacts")


class TestVars:
    creator = None
    receiver = None
    master_client = None
    algod = None
    vault_client = None
    asa_id = None


def tealrb_exception_handler(e, file_name):
    file_name = Path.joinpath(ARTIFACTS, file_name)

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

            teal_line = f"{file_name}.teal:{teal_ln} => {teal_line}"

            rb_line = (
                Path("arc12.rb")
                .read_text()
                .splitlines()[int(data["location"].split(":")[1]) - 1]
                .strip()
            )

            rb_line = f"{data['location']} => {rb_line}"
            break

    raise AlgodHTTPError(f"{str(e)}\n{teal_line}\n{rb_line}")


def tealrb_src_mapper(fn):
    def wrapper():
        try:
            fn()
        except (LogicException, AlgodHTTPError) as e:
            tealrb_exception_handler(e, fn.__name__)

    return wrapper


@pytest.fixture(scope="module")
def create_master():
    accounts = sorted(
        sandbox.get_accounts(),
        key=lambda a: sandbox.clients.get_algod_client().account_info(a.address)[
            "amount"
        ],
    )

    TestVars.creator = accounts.pop()
    TestVars.receiver = accounts.pop()

    master_app = Master(version=8)
    master_app.approval_program = Path.joinpath(ARTIFACTS, "master.teal").read_text()
    TestVars.master_client = client.ApplicationClient(
        client=sandbox.get_algod_client(),
        app=master_app,
        signer=TestVars.creator.signer,
    )

    TestVars.algod = TestVars.master_client.client

    TestVars.master_client.create(args=[get_method_spec(Master.create).get_selector()])
    TestVars.master_client.fund(100_000)


@pytest.fixture(scope="module")
def create_vault():
    TestVars.creator_pre_vault_balance = TestVars.algod.account_info(
        TestVars.creator.address
    )["amount"]
    TestVars.receiver_pre_vault_balance = TestVars.algod.account_info(
        TestVars.receiver.address
    )["amount"]

    sp = TestVars.master_client.get_suggested_params()
    sp.fee = sp.min_fee * 3
    sp.flat_fee = True

    pay_txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            sender=TestVars.creator.address,
            receiver=TestVars.master_client.app_addr,
            amt=347_000,
            sp=sp,
        ),
        signer=TestVars.creator.signer,
    )

    vault_id = TestVars.master_client.call(
        method=Master.create_vault,
        receiver=TestVars.receiver.address,
        mbr_payment=pay_txn,
        boxes=[
            [TestVars.master_client.app_id, decode_address(TestVars.receiver.address)]
        ],
        foreign_apps=[0],
    ).return_value

    vault_app = Vault(version=8)
    vault_app.approval_program = Path.joinpath(ARTIFACTS, "vault.teal").read_text()
    TestVars.vault_client = client.ApplicationClient(
        client=sandbox.get_algod_client(),
        app=vault_app,
        signer=TestVars.creator.signer,
        app_id=vault_id,
    )


@pytest.fixture(scope="module")
def opt_in():
    txn = transaction.AssetConfigTxn(
        sender=TestVars.creator.address,
        sp=TestVars.master_client.get_suggested_params(),
        total=1,
        default_frozen=False,
        unit_name="LATINUM",
        asset_name="latinum",
        decimals=0,
        strict_empty_address_check=False,
    )

    stxn = txn.sign(TestVars.creator.private_key)
    txid = TestVars.algod.send_transaction(stxn)
    confirmed_txn = transaction.wait_for_confirmation(TestVars.algod, txid, 4)
    TestVars.asa_id = confirmed_txn["asset-index"]

    sp = TestVars.vault_client.get_suggested_params()
    sp.fee = sp.min_fee * 2
    sp.flat_fee = True

    pay_txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            sender=TestVars.creator.address,
            receiver=TestVars.vault_client.app_addr,
            amt=118_500,
            sp=sp,
        ),
        signer=TestVars.creator.signer,
    )

    TestVars.vault_client.call(
        method=Vault.opt_in,
        asa=TestVars.asa_id,
        mbr_payment=pay_txn,
        boxes=[[TestVars.vault_client.app_id, TestVars.asa_id.to_bytes(8, "big")]],
    )


@pytest.fixture(scope="module")
def verify_axfer():
    axfer = TransactionWithSigner(
        txn=transaction.AssetTransferTxn(
            sender=TestVars.creator.address,
            receiver=TestVars.vault_client.app_addr,
            amt=1,
            sp=TestVars.vault_client.get_suggested_params(),
            index=TestVars.asa_id,
        ),
        signer=TestVars.creator.signer,
    )

    TestVars.master_client.call(
        method=Master.verify_axfer,
        receiver=TestVars.receiver.address,
        vault_axfer=axfer,
        vault=TestVars.vault_client.app_id,
        boxes=[
            [TestVars.master_client.app_id, decode_address(TestVars.receiver.address)]
        ],
    )


@pytest.fixture(scope="module")
def claim():
    atc = AtomicTransactionComposer()
    claim_sp = TestVars.algod.suggested_params()
    claim_sp.fee = claim_sp.min_fee * 4
    claim_sp.flat_fee = True

    del_sp = TestVars.algod.suggested_params()
    del_sp.fee = del_sp.min_fee * 3
    del_sp.flat_fee = True

    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.AssetOptInTxn(
                sender=TestVars.receiver.address,
                sp=TestVars.algod.suggested_params(),
                index=TestVars.asa_id,
            ),
            signer=TestVars.receiver.signer,
        )
    )

    atc.add_method_call(
        app_id=TestVars.vault_client.app_id,
        sender=TestVars.receiver.address,
        signer=TestVars.receiver.signer,
        sp=claim_sp,
        method=application.get_method_spec(Vault.claim),
        method_args=[TestVars.asa_id, TestVars.creator.address, ZERO_ADDR],
        boxes=[[TestVars.vault_client.app_id, TestVars.asa_id.to_bytes(8, "big")]],
    )

    atc.add_method_call(
        app_id=TestVars.master_client.app_id,
        sender=TestVars.receiver.address,
        signer=TestVars.receiver.signer,
        sp=del_sp,
        method=application.get_method_spec(Master.delete_vault),
        method_args=[TestVars.vault_client.app_id, TestVars.creator.address],
        boxes=[
            [TestVars.master_client.app_id, decode_address(TestVars.receiver.address)]
        ],
    )

    atc.execute(TestVars.algod, 3)


@pytest.fixture(scope="module")
def reject():
    atc = AtomicTransactionComposer()
    reject_sp = TestVars.algod.suggested_params()
    reject_sp.fee = reject_sp.min_fee * 2
    reject_sp.flat_fee = True

    del_sp = TestVars.algod.suggested_params()
    del_sp.fee = del_sp.min_fee * 3
    del_sp.flat_fee = True

    atc.add_method_call(
        app_id=TestVars.vault_client.app_id,
        sender=TestVars.receiver.address,
        signer=TestVars.receiver.signer,
        sp=reject_sp,
        method=application.get_method_spec(Vault.reject),
        method_args=[
            TestVars.creator.address,
            "Y76M3MSY6DKBRHBL7C3NNDXGS5IIMQVQVUAB6MP4XEMMGVF2QWNPL226CA",
            TestVars.asa_id,
            ZERO_ADDR,
        ],
        boxes=[[TestVars.vault_client.app_id, TestVars.asa_id.to_bytes(8, "big")]],
    )

    atc.add_method_call(
        app_id=TestVars.master_client.app_id,
        sender=TestVars.receiver.address,
        signer=TestVars.receiver.signer,
        sp=del_sp,
        method=application.get_method_spec(Master.delete_vault),
        method_args=[TestVars.vault_client.app_id, TestVars.creator.address],
        boxes=[
            [TestVars.master_client.app_id, decode_address(TestVars.receiver.address)]
        ],
    )

    atc.execute(TestVars.algod, 3)
