# frozen_string_literal: true

require 'tealrb'
require 'pry'

class Vault < TEALrb::Contract
  @version = 8

  # @subroutine
  # @param [account] receiver
  # @param [uint64] amount
  def send_payment(receiver, amount)
    InnerTxn.begin
    InnerTxn.type_enum = TxnType.pay
    InnerTxn.receiver = receiver
    InnerTxn.amount = amount
    InnerTxn.fee = 0
    InnerTxn.submit
  end

  # @subroutine
  # @param [asset] asa
  # @param [account] receiver
  def send_asa(asa, receiver)
    InnerTxn.begin
    InnerTxn.type_enum = TxnType.asset_transfer
    InnerTxn.asset_receiver = receiver
    InnerTxn.fee = 0
    InnerTxn.asset_amount = Txn.sender.asset_balance(asa)
    InnerTxn.xfer_asset = asa
    InnerTxn.asset_close_to = receiver
    InnerTxn.submit
  end

  # @abi
  # Method called for creation of the vault
  # @param receiver [account] The account that can claim ASAs from this vault
  # @param mbr_payment [pay] The payment that covers the MBR for the vault MBR
  def create(receiver, mbr_payment)
    box_create 'creator', 40
    box_create 'receiver', 32

    Box['creator'] = concat(mbr_payment.sender, itob(mbr_payment.amount))
    Box['receiver'] = receiver
  end

  # @abi
  # Opts into the given asa
  # @param mbr_amount [uint64] The amount of uALGO being sent to the contract to cover the MBR
  # @param mbr_funder [address] The address of the funder of the MBR
  # @param asa [asset] The asset to opt-in to
  def opt_in(mbr_amount, mbr_funder, asa)
    box_create(itob(asa), 40)
    Box[itob(asa)] = concat(mbr_funder, itob(mbr_amount))

    InnerTxn.begin
    InnerTxn.type_enum = TxnType.asset_transfer
    InnerTxn.asset_receiver = Global.current_application_address
    InnerTxn.asset_amount = 0
    InnerTxn.fee = 0
    InnerTxn.xfer_asset = asa
    InnerTxn.submit
  end

  # @abi
  # Sends the ASA to the intended receiver
  # @param asa [asset] The ASA to send
  # @param mbr_funder [account] The account that funded the MBR for the ASA
  def claim(asa, mbr_funder)
    assert Box[itob(asa)]
    # assert Txn.sender == Box['receiver']

    $asa_mbr_funder = box_extract(itob(asa), 0, 32)
    $asa_mbr_amount = box_extract(itob(asa), 32, 8)
    box_del itob(asa)

    $vault_mbr_funder = box_extract('creator', 0, 32)
    $vault_mbr_amount = box_extract('creator', 32, 8)

    assert mbr_funder == $asa_mbr_funder
    send_asa(itob(asa), Txn.sender)
    send_payment($asa_mbr_funder, $asa_mbr_amount)

    if Global.current_application_address.balance == $vault_mbr_amount
      assert Txn.on_completion == int('DeleteApplication')
      box_del 'creator'

      InnerTxn.begin
      InnerTxn.type_enum = TxnType.pay
      InnerTxn.receiver = $vault_mbr_funder
      InnerTxn.amount = Global.current_application_address.balance
      InnerTxn.fee = 0
      InnerTxn.close_remainder_to = $vault_mbr_funder
      InnerTxn.submit
    end
  end

  def main
    nil
  end
end

vault = Vault.new
vault.compile
vault.dump
