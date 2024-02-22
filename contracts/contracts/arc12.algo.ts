/* eslint-disable no-undef */
/* eslint-disable max-classes-per-file */

// eslint-disable-next-line import/no-unresolved, import/extensions
import { Contract } from '@algorandfoundation/tealscript';

// eslint-disable-next-line no-unused-vars
class Vault extends Contract {
  creator = GlobalStateKey<Address>();

  master = GlobalStateKey<AppID>();

  owner = GlobalStateKey<Address>();

  funderMap = BoxMap<AssetID, Address>();

  private closeAcct(): void {
    /// Send the MBR to the vault creator
    sendPayment({
      receiver: this.creator.value,
      amount: globals.currentApplicationAddress.minBalance,
      closeRemainderTo: this.owner.value,
    });

    const deleteVaultTxn = this.txnGroup[this.txn.groupIndex + 1];
    /// Ensure Master.deleteVault is being called for this vault
    assert(deleteVaultTxn.applicationID === this.master.value);
    assert(deleteVaultTxn.applicationArgs[0] === method('deleteVault(application,account)void'));
    assert(deleteVaultTxn.applications[1] === this.app);
  }

  @allow.create('NoOp')
  create(owner: Address, sender: Address): void {
    this.creator.value = sender;
    this.owner.value = owner;
    this.master.value = globals.callerApplicationID;
  }

  reject(asa: AssetID): void {
    assert(this.txn.sender === this.owner.value);
    const feeSink = addr('Y76M3MSY6DKBRHBL7C3NNDXGS5IIMQVQVUAB6MP4XEMMGVF2QWNPL226CA')
    const preMbr = globals.currentApplicationAddress.minBalance;

    /// Send asset back to creator since they are guranteed to be opted in
    sendAssetTransfer({
      assetReceiver: asa.creator,
      xferAsset: asa,
      assetAmount: 0,
      assetCloseTo: asa.creator,
    });

    this.funderMap(asa).delete();

    const mbrAmt = preMbr - globals.currentApplicationAddress.minBalance;

    /// Send MBR to fee sink
    sendPayment({
      receiver: feeSink,
      amount: mbrAmt - this.txn.fee,
    });

    /// Send fee back to sender
    sendPayment({
      receiver: this.txn.sender,
      amount: this.txn.fee,
    });

    if (globals.currentApplicationAddress.totalAssets === 0) this.closeAcct();
  }

  optIn(asa: AssetID, mbrPayment: PayTxn): void {
    assert(!this.funderMap(asa).exists);
    assert(mbrPayment.sender === this.txn.sender);
    assert(mbrPayment.receiver === globals.currentApplicationAddress);

    const preMbr = globals.currentApplicationAddress.minBalance;

    this.funderMap(asa).value = this.txn.sender;

    /// Opt vault into asa
    sendAssetTransfer({
      assetReceiver: globals.currentApplicationAddress,
      assetAmount: 0,
      xferAsset: asa,
    });

    assert(mbrPayment.amount === globals.currentApplicationAddress.minBalance - preMbr);
  }

  claim(asa: AssetID): void {
    assert(this.funderMap(asa).exists);
    assert(this.txn.sender === this.owner.value);

    const initialMbr = globals.currentApplicationAddress.minBalance;

    this.funderMap(asa).delete();

    /// Transfer all of the asset to the receiver
    sendAssetTransfer({
      assetReceiver: this.txn.sender,
      assetAmount: globals.currentApplicationAddress.assetBalance(asa),
      xferAsset: asa,
      assetCloseTo: this.txn.sender,
    });

    /// Send MBR to the funder
    sendPayment({
      receiver: this.funderMap(asa).value,
      amount: initialMbr - globals.currentApplicationAddress.minBalance,
    });

    if (globals.currentApplicationAddress.totalAssets === 0) this.closeAcct();
  }

  @allow.bareCall('DeleteApplication')
  delete(): void {
    assert(!globals.currentApplicationAddress.isInLedger);
    assert(this.txn.sender === globals.creatorAddress);
  }
}

// eslint-disable-next-line no-unused-vars
class Master extends Contract {
  vaultMap = BoxMap<Address, AppID>();

  @allow.bareCreate()
  create() { }

  createVault(owner: Address, mbrPayment: PayTxn): AppID {
    assert(!this.vaultMap(owner).exists);
    assert(mbrPayment.receiver === globals.currentApplicationAddress);
    assert(mbrPayment.sender === this.txn.sender);

    const preCreateMBR = globals.currentApplicationAddress.minBalance;

    /// Create the vault
    sendMethodCall<typeof Vault.prototype.create>({
      methodArgs: [owner, this.txn.sender],
      clearStateProgram: Vault.clearProgram(),
      approvalProgram: Vault.approvalProgram(),
      globalNumByteSlice: Vault.schema.global.numByteSlice,
      globalNumUint: Vault.schema.global.numUint,
    });

    const vault = this.itxn.createdApplicationID;

    /// Fund the vault with account MBR
    sendPayment({
      receiver: vault.address,
      amount: globals.minBalance,
    });

    this.vaultMap(owner).value = vault;

    assert(mbrPayment.amount === (globals.currentApplicationAddress.minBalance - preCreateMBR) + globals.minBalance);

    return vault;
  }

  verifyAxfer(owner: Address, vaultAxfer: AssetTransferTxn, vault: AppID): void {
    assert(this.vaultMap(owner).exists);

    assert(this.vaultMap(owner).value === vault);
    assert(vaultAxfer.assetReceiver === vault.address);
    assert(vaultAxfer.assetCloseTo === globals.zeroAddress);
  }

  hasVault(owner: Address): uint64 {
    // @ts-expect-error Need to fix the return type for .exists in TEALScript
    return this.vaultMap(owner).exists;
  }

  getVaultId(owner: Address): AppID {
    return this.vaultMap(owner).value;
  }

  getVaultAddr(owner: Address): Address {
    return this.vaultMap(owner).value.address;
  }

  deleteVault(vault: AppID): void {
    /// The fee needs to be 0 because all of the fees need to paid by the vault call
    /// This ensures the sender will be refunded for all fees if they are rejecting the last ASA
    assert(this.txn.fee === 0);
    assert(vault === this.vaultMap(this.txn.sender).value);

    const preDeleteMBR = globals.currentApplicationAddress.minBalance;

    /// Call delete on the vault
    sendAppCall({
      applicationID: vault,
      onCompletion: OnCompletion.DeleteApplication,
    });

    this.vaultMap(this.txn.sender).delete();

    /// Send the MBR back to the vault creator
    sendPayment({
      receiver: vault.globalState('creator') as Address,
      amount: preDeleteMBR - globals.currentApplicationAddress.minBalance,
    });
  }
}
