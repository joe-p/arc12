from beaker import *
from pyteal import *
from pathlib import Path
from algosdk.future import transaction
from algosdk.encoding import decode_address
from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
    AtomicTransactionComposer,
)


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
        amt=100_000,
        sp=sp,
    ),
    signer=creator.signer,
)

# master_client.call(
#    Master.create_vault,
#    receiver=receiver.address,
#    mbr_payment=pay_txn,
#    boxes=[[0, decode_address(receiver.address)]], # <- TODO: Get this working
#    foreign_apps=[0],
# )
