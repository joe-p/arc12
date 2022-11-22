from beaker import *
from beaker.client.logic_error import LogicException
from pyteal import *
from pathlib import Path
from algosdk.future import transaction
from algosdk.encoding import decode_address
from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
)
from algosdk.error import AlgodHTTPError
import re
import json
import pytest


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
        self, reciever: abi.Account, vault_axfer: abi.AssetTransferTransaction
    ):
        return Reject()

    @external
    def get_vault_id(self, reciever: abi.Account, *, output: abi.Uint64):
        return Reject()

    @external
    def get_vault_addr(self, reciever: abi.Account, *, output: abi.Address):
        return Reject()

    @external
    def delete_vault(
        self, reciever: abi.Account, vault: abi.Application, creator: abi.Account
    ):
        return Reject()


class Vault(Application):
    @external
    def opt_in(self, asa: abi.Asset, mbr_payment: abi.PaymentTransaction):
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

    master_client.create(args=[get_method_spec(Master.create).get_selector()])


@pytest.fixture(scope="module")
def create_vault():
    global vault_client

    sp = master_client.get_suggested_params()
    sp.fee = sp.min_fee * 2

    pay_txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            sender=creator.address,
            receiver=master_client.app_addr,
            amt=418_500,
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


@pytest.fixture(scope="module")
def opt_in():
    global asa_id

    txn = transaction.AssetConfigTxn(
        sender=creator.address,
        sp=master_client.get_suggested_params(),
        total=1000,
        default_frozen=False,
        unit_name="LATINUM",
        asset_name="latinum",
        decimals=0,
        strict_empty_address_check=False,
    )

    stxn = txn.sign(creator.private_key)
    txid = master_client.client.send_transaction(stxn)
    confirmed_txn = transaction.wait_for_confirmation(master_client.client, txid, 4)
    asa_id = confirmed_txn["asset-index"]

    sp = vault_client.get_suggested_params()
    sp.fee = sp.min_fee * 2

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


@pytest.mark.create_master
def test_create_master(create_master):
    pass


@pytest.mark.create_vault
def test_create_vault_id(create_master, create_vault):
    assert vault_client.app_id > 0


@pytest.mark.create_vault
def test_create_vault_box_name(create_master, create_vault):
    box_names = master_client.get_box_names()
    assert len(box_names) == 1
    assert box_names[0] == decode_address(receiver.address)


@pytest.mark.create_vault
def test_create_vault_box_value(create_master, create_vault):
    box_value = int.from_bytes(
        master_client.get_box_contents(decode_address(receiver.address)),
        byteorder="big",
    )
    assert box_value == vault_client.app_id


@pytest.mark.create_vault
def test_create_vault_creator(create_master, create_vault):
    assert decode_address(creator.address) == bytes.fromhex(
        vault_client.get_application_state()["creator"]
    )


@pytest.mark.create_vault
def test_create_vault_receiver(create_master, create_vault):
    assert decode_address(receiver.address) == bytes.fromhex(
        vault_client.get_application_state()["receiver"]
    )


@pytest.mark.opt_in
def test_opt_in_box_name(create_master, create_vault, opt_in):
    box_names = vault_client.get_box_names()
    assert len(box_names) == 1
    assert box_names[0] == asa_id.to_bytes(8, "big")


@pytest.mark.opt_in
def test_opt_in_box_value(create_master, create_vault, opt_in):
    box_value = vault_client.get_box_contents(asa_id.to_bytes(8, "big"))
    assert box_value == decode_address(creator.address)
