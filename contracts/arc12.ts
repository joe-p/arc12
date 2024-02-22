/* eslint-disable no-undef */
/* eslint-disable max-classes-per-file */

// eslint-disable-next-line import/no-unresolved, import/extensions
import { Contract } from '@algorandfoundation/tealscript';

// eslint-disable-next-line no-unused-vars
class Vault extends Contract {
  creator = GlobalStateKey<Address>();

  master = GlobalStateKey<AppID>();

  receiver = GlobalStateKey<Address>();

  funderMap = BoxMap<AssetID, Address>();

  private closeAcct(vaultCreator: Address): void {
    assert(vaultCreator === this.creator.value);

    /// Send the MBR to the vault creator
    sendPayment({
      receiver: vaultCreator,
      amount: globals.currentApplicationAddress.minBalance,
      fee: 0,
      /// Any remaining balance is sent the receiver for the vault
      closeRemainderTo: this.txn.sender,
    });

    const deleteVaultTxn = this.txnGroup[this.txn.groupIndex + 1];
    /// Ensure Master.deleteVault is being called for this vault
    assert(deleteVaultTxn.applicationID === this.master.value);
    assert(deleteVaultTxn.applicationArgs[0] === method('deleteVault(application,account)void'));
    assert(deleteVaultTxn.applications[1] === this.app);
  }

  @allow.create('NoOp')
  create(receiver: Address, sender: Address): void {
    this.creator.value = sender;
    this.receiver.value = receiver;
    this.master.value = globals.callerApplicationID;
  }

  reject(asaCreator: Address, feeSink: Address, asa: AssetID, vaultCreator: Address): void {
    assert(this.txn.sender === this.receiver.value);
    assert(feeSink === addr('Y76M3MSY6DKBRHBL7C3NNDXGS5IIMQVQVUAB6MP4XEMMGVF2QWNPL226CA'));
    const preMbr = globals.currentApplicationAddress.minBalance;

    /// Send asset back to creator since they are guranteed to be opted in
    sendAssetTransfer({
      assetReceiver: asaCreator,
      xferAsset: asa,
      assetAmount: 0,
      assetCloseTo: asaCreator,
      fee: 0,
    });

    this.funderMap(asa).delete();

    const mbrAmt = preMbr - globals.currentApplicationAddress.minBalance;

    /// Send MBR to fee sink
    sendPayment({
      receiver: feeSink,
      amount: mbrAmt - this.txn.fee,
      fee: 0,
    });

    /// Send fee back to sender
    sendPayment({
      receiver: this.txn.sender,
      amount: this.txn.fee,
      fee: 0,
    });

    if (globals.currentApplicationAddress.totalAssets === 0) this.closeAcct(vaultCreator);
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
      fee: 0,
      xferAsset: asa,
    });

    assert(mbrPayment.amount === globals.currentApplicationAddress.minBalance - preMbr);
  }

  claim(asa: AssetID, creator: Address, asaMbrFunder: Address): void {
    assert(this.funderMap(asa).exists);
    assert(asaMbrFunder === this.funderMap(asa).value);
    assert(this.txn.sender === this.receiver.value);
    assert(this.creator.value === creator);

    const initialMbr = globals.currentApplicationAddress.minBalance;

    this.funderMap(asa).delete();

    /// Transfer all of the asset to the receiver
    sendAssetTransfer({
      assetReceiver: this.txn.sender,
      fee: 0,
      assetAmount: globals.currentApplicationAddress.assetBalance(asa),
      xferAsset: asa,
      assetCloseTo: this.txn.sender,
    });

    /// Send MBR to the funder
    sendPayment({
      receiver: asaMbrFunder,
      amount: initialMbr - globals.currentApplicationAddress.minBalance,
      fee: 0,
    });

    if (globals.currentApplicationAddress.totalAssets === 0) this.closeAcct(creator);
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

  createVault(receiver: Address, mbrPayment: PayTxn): AppID {
    assert(!this.vaultMap(receiver).exists);
    assert(mbrPayment.receiver === globals.currentApplicationAddress);
    assert(mbrPayment.sender === this.txn.sender);

    const preCreateMBR = globals.currentApplicationAddress.minBalance;

    /// Create the vault
    sendMethodCall<[Address, Address], void>({
      name: 'create',
      onCompletion: OnCompletion.NoOp,
      fee: 0,
      methodArgs: [receiver, this.txn.sender],
      clearStateProgram: this.app.clearStateProgram,
      approvalProgram: Vault.approvalProgram(),
      globalNumByteSlice: Vault.schema.global.numByteSlice,
      globalNumUint: Vault.schema.global.numUint,
    });

    const vault = this.itxn.createdApplicationID;

    /// Fund the vault with account MBR
    sendPayment({
      receiver: vault.address,
      amount: globals.minBalance,
      fee: 0,
    });

    this.vaultMap(receiver).value = vault;

    // eslint-disable-next-line max-len
    assert(mbrPayment.amount === (globals.currentApplicationAddress.minBalance - preCreateMBR) + globals.minBalance);

    return vault;
  }

  verifyAxfer(receiver: Address, vaultAxfer: AssetTransferTxn, vault: AppID): void {
    assert(this.vaultMap(receiver).exists);

    assert(this.vaultMap(receiver).value === vault);
    assert(vaultAxfer.assetReceiver === vault.address);
    assert(vaultAxfer.assetCloseTo === globals.zeroAddress);
  }

  hasVault(receiver: Address): uint64 {
    // @ts-expect-error Need to fix the return type for .exists in TEALScript
    return this.vaultMap(receiver).exists;
  }

  getVaultId(receiver: Address): AppID {
    return this.vaultMap(receiver).value;
  }

  getVaultAddr(receiver: Address): Address {
    return this.vaultMap(receiver).value.address;
  }

  deleteVault(vault: AppID, vaultCreator: Address): void {
    /// The fee needs to be 0 because all of the fees need to paid by the vault call
    /// This ensures the sender will be refunded for all fees if they are rejecting the last ASA
    assert(this.txn.fee === 0);
    assert(vault === this.vaultMap(this.txn.sender).value);

    assert(vault.globalState('creator') as Address === vaultCreator);

    const preDeleteMBR = globals.currentApplicationAddress.minBalance;

    /// Call delete on the vault
    sendAppCall({
      applicationID: vault,
      onCompletion: OnCompletion.DeleteApplication,
      fee: 0,
    });

    this.vaultMap(this.txn.sender).delete();

    /// Send the MBR back to the vault creator
    sendPayment({
      receiver: vaultCreator,
      amount: preDeleteMBR - globals.currentApplicationAddress.minBalance,
      fee: 0,
    });
  }
}
