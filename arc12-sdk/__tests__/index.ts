import algosdk from 'algosdk';
import fs from 'fs';
import path from 'path';
import ARC12 from '../src/index';
import masterABI from '../../artifacts/master.abi.json';

const token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const server = 'http://localhost';
const indexerClient = new algosdk.Indexer('', server, 8980);
const algodClient = new algosdk.Algodv2(token, server, 4001);
const kmdClient = new algosdk.Kmd(token, server, 4002);
const kmdWallet = 'unencrypted-default-wallet';
const kmdPassword = '';

jest.setTimeout(10_000);
interface TestState {
  master: number,
  vault: number,
  asa: number,
  sender: algosdk.Account
  receiver: algosdk.Account
  arc12: ARC12
}

// Based on https://github.com/algorand-devrel/demo-abi/blob/master/js/sandbox.ts
async function getAccounts(): Promise<algosdk.Account[]> {
  const wallets = await kmdClient.listWallets();

  // find kmdWallet
  let walletId;
  for (const wallet of wallets.wallets) {
    if (wallet.name === kmdWallet) walletId = wallet.id;
  }
  if (walletId === undefined) throw Error(`No wallet named: ${kmdWallet}`);

  // get handle
  const handleResp = await kmdClient.initWalletHandle(walletId, kmdPassword);
  const handle = handleResp.wallet_handle_token;

  // get account keys
  const addresses = await kmdClient.listKeys(handle);
  const acctPromises = [];
  for (const addr of addresses.addresses) {
    acctPromises.push(kmdClient.exportKey(handle, kmdPassword, addr));
  }
  const keys = await Promise.all(acctPromises);

  // release handle
  kmdClient.releaseWalletHandle(handle);

  // return all algosdk.Account objects derived from kmdWallet
  return keys.map((k) => {
    const addr = algosdk.encodeAddress(k.private_key.slice(32));
    return { sk: k.private_key, addr } as algosdk.Account;
  });
}

// https://developer.algorand.org/docs/get-details/dapps/smart-contracts/frontend/apps/#create
async function compileProgram(programSource: string) {
  const encoder = new TextEncoder();
  const programBytes = encoder.encode(programSource);
  const compileResponse = await algodClient.compile(programBytes).do();
  return new Uint8Array(Buffer.from(compileResponse.result, 'base64'));
}

async function createMaster(state: TestState) {
  const masterContract = new algosdk.ABIContract(masterABI);
  const creator = state.sender as algosdk.Account;

  const txn = algosdk.makeApplicationCreateTxn(
    creator.addr,
    await algodClient.getTransactionParams().do(),
    algosdk.OnApplicationComplete.NoOpOC,
    await compileProgram(fs.readFileSync(path.join(__dirname, '../../artifacts/master.teal')).toString()),
    await compileProgram(fs.readFileSync(path.join(__dirname, 'clear.teal')).toString()),
    0,
    0,
    0,
    0,
    [algosdk.getMethodByName(masterContract.methods, 'create').getSelector()],
  ).signTxn(creator.sk);

  const { txId } = await algodClient.sendRawTransaction(txn).do();
  state.master = (await algosdk.waitForConfirmation(algodClient, txId, 3))['application-index'];

  const payTxn = algosdk.makePaymentTxnWithSuggestedParams(
    state.sender.addr,
    algosdk.getApplicationAddress(state.master),
    100_000,
    undefined,
    undefined,
    await algodClient.getTransactionParams().do(),
  ).signTxn(state.sender.sk);

  await algodClient.sendRawTransaction(payTxn).do();
}

describe('ARC12 SDK', () => {
  // @ts-ignore
  const state: TestState = {};

  beforeAll(async () => {
    const accounts = await getAccounts();
    state.sender = accounts.pop() as algosdk.Account;
    state.receiver = accounts.pop() as algosdk.Account;
    await createMaster(state);
    state.arc12 = new ARC12(indexerClient, algodClient, state.master);
  });

  it('Creates Vault', async () => {
    const atc = new algosdk.AtomicTransactionComposer();
    const signer = algosdk.makeBasicAccountTransactionSigner(state.sender);
    await state.arc12.createVault(
      atc,
      state.sender.addr,
      signer,
      state.receiver.addr,
      state.master,
    );
    const res = await atc.execute(algodClient, 3);

    // Wait for indexer to catch up
    await new Promise((r) => setTimeout(r, 10));

    state.vault = Number(res.methodResults[0].returnValue as algosdk.ABIValue);
    expect(await state.arc12.getVault(state.receiver.addr)).toBe(state.vault);
  });
});
