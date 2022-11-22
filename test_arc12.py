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
import base64


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


def call(app_client, *args, **kwargs):
    try:
        return app_client.call(*args, **kwargs)
    except LogicException as e:
        pc = int(re.findall("(?<=at PC).*?\d+", str(e))[0])
        src_map = json.load(Path("master.src_map.json").open())

        teal_line = "Unknown"
        rb_line = "Unknown"
        for teal_ln, data in src_map.items():
            print(data)
            if "pcs" in data.keys() and pc in data["pcs"]:
                teal_line = (
                    Path("master.teal")
                    .read_text()
                    .splitlines()[int(teal_ln) - 1]
                    .strip()
                )

                teal_line = f"./master.teal:{teal_ln} => {teal_line}"

                print(data["location"])
                rb_line = (
                    Path("arc12.rb")
                    .read_text()
                    .splitlines()[int(data["location"].split(":")[1]) - 1]
                    .strip()
                )

                rb_line = f"./{data['location']} => {rb_line}"
                break

        raise AlgodHTTPError(f"{str(e).splitlines()[0]}\n{teal_line}\n{rb_line}")


accounts = sorted(
    sandbox.get_accounts(),
    key=lambda a: sandbox.clients.get_algod_client().account_info(a.address)["amount"],
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
    method=Master.create_vault,
    receiver=receiver.address,
    mbr_payment=pay_txn,
    boxes=[[master_client.app_id, decode_address(receiver.address)]],
    foreign_apps=[0],
).return_value

print(vault_id)
