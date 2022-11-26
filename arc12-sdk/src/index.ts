import algosdk from 'algosdk';
import vaultABI from './vault.abi.json';
import masterABI from './master.abi.json';

const ZERO_ADDRESS = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ';

interface Holding {
  optedIn: boolean,
  vault?: number,
  vaultOptedIn?: boolean,
}

class ARC12 {
  indexer: algosdk.Indexer;

  masterApp: number;

  algodClient: algosdk.Algodv2;

  vaultContract: algosdk.ABIContract;

  masterContract: algosdk.ABIContract;

  constructor(indexer: algosdk.Indexer, algodClient: algosdk.Algodv2, masterApp: number) {
    this.indexer = indexer;
    this.masterApp = masterApp;
    this.algodClient = algodClient;
    this.vaultContract = new algosdk.ABIContract(vaultABI);
    this.masterContract = new algosdk.ABIContract(masterABI);
  }

  async getVault(address: string) {
    const pubKey = algosdk.decodeAddress(address).publicKey;
    try {
      const boxResponse = await this.indexer
        .lookupApplicationBoxByIDandName(this.masterApp, pubKey).do();

      return algosdk.decodeUint64(boxResponse.value, 'safe');
    } catch (e: any) {
      if (e.response.body.message.includes('no application boxes found')) {
        return undefined;
      }

      throw e;
    }
  }

  async claim(
    atc: algosdk.AtomicTransactionComposer,
    sender: string,
    signer: algosdk.TransactionSigner,
    asa: number,
    vault: number,
  ): Promise<algosdk.AtomicTransactionComposer> {
    const vaultCreator: string = (await this.indexer.searchForApplications().index(vault).do())
      .params.creator;

    const boxResponse = await this.indexer
      .lookupApplicationBoxByIDandName(vault, algosdk.encodeUint64(asa)).do();

    let asaFunder = algosdk.encodeAddress(boxResponse.value);

    if (asaFunder == vaultCreator) {
      asaFunder = ZERO_ADDRESS;
    }

    const appSp = await this.algodClient.getTransactionParams().do();
    appSp.fee = (appSp.fee || 1_000) * 7;
    appSp.flatFee = true;

    atc.addMethodCall({
      appID: vault,
      method: algosdk.getMethodByName(this.vaultContract.methods, 'create_vault'),
      methodArgs: [asa, vaultCreator, asaFunder],
      sender,
      suggestedParams: appSp,
      signer,
    });

    // TODO: Logic for deleting vault

    return atc;
  }

  async createVault(
    atc: algosdk.AtomicTransactionComposer,
    sender: string,
    signer: algosdk.TransactionSigner,
    receiver: string,
    master: number,
  ): Promise<algosdk.AtomicTransactionComposer> {
    const suggestedParams = await this.algodClient.getTransactionParams().do();
    const payTxn = algosdk.makePaymentTxnWithSuggestedParams(
      sender,
      algosdk.getApplicationAddress(master),
      347_000,
      undefined,
      undefined,
      suggestedParams,
    );

    const appSp = await this.algodClient.getTransactionParams().do();
    appSp.fee = (appSp.fee || 1_000) * 3;
    appSp.flatFee = true;

    atc.addMethodCall({
      appID: master,
      method: algosdk.getMethodByName(this.vaultContract.methods, 'create_vault'),
      methodArgs: [receiver, { txn: payTxn, signer }],
      sender,
      suggestedParams: appSp,
      signer,
    });

    return atc;
  }

  async vaultOptIn(
    atc: algosdk.AtomicTransactionComposer,
    sender: string,
    signer: algosdk.TransactionSigner,
    asa: number,
    vault: number,
  ): Promise<algosdk.AtomicTransactionComposer> {
    const suggestedParams = await this.algodClient.getTransactionParams().do();
    const payTxn = algosdk.makePaymentTxnWithSuggestedParams(
      sender,
      algosdk.getApplicationAddress(vault),
      118_500,
      undefined,
      undefined,
      suggestedParams,
    );

    const appSp = await this.algodClient.getTransactionParams().do();
    appSp.fee = (appSp.fee || 1_000) * 2;
    appSp.flatFee = true;

    atc.addMethodCall({
      appID: vault,
      method: algosdk.getMethodByName(this.vaultContract.methods, 'opt_in'),
      methodArgs: [asa, { txn: payTxn, signer }],
      sender,
      suggestedParams: appSp,
      signer,
    });

    return atc;
  }

  async getHolding(address: string, asa: number): Promise<Holding> {
    const accountAssets: any[] = (await this.indexer.lookupAccountAssets(address)
      .assetId(asa).do()).assets;

    if (accountAssets.length !== 0) {
      return {
        optedIn: true,
      };
    }

    const holding: Holding = { optedIn: false };

    holding.vault = await this.getVault(address);

    if (holding.vault) {
      const appAddr = algosdk.getApplicationAddress(holding.vault);
      const vaultAssets: any[] = (await this.indexer.lookupAccountAssets(appAddr)
        .assetId(asa).do()).assets;

      holding.vaultOptedIn = vaultAssets.length > 0;
    }

    return holding;
  }
}

(async () => {
  const vaultAsa = 1812;
  const indexerClient = new algosdk.Indexer('', 'http://localhost', 8980);
  const algodClient = new algosdk.Algodv2('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'http://localhost', 4001);

  const arc12 = new ARC12(indexerClient, algodClient, vaultAsa);
  console.log(await arc12.getHolding('BKD6AHZUQ5OJEBFZMTANYHGIOR4JNC5MNPCAEWRTZCYCNGG453I6ZKBRNU', 1818));
  console.log(await arc12.getHolding('BKD6AHZUQ5OJEBFZMTANYHGIOR4JNC5MNPCAEWRTZCYCNGG453I6ZKBRNU', 1));
  console.log(await arc12.getHolding(algosdk.generateAccount().addr, 1818));
})();
