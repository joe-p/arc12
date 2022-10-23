# frozen_string_literal: true

require 'tealrb'
require 'pry'

module CommonSubroutines
  include TEALrb::Opcodes

  # @subroutine
  # @param [Asset] asa
  # @param [Account] receiver
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

  # @subroutine
  # @param [Account] receiver
  # @param [Uint64] amount
  def send_payment(receiver, amount)
    InnerTxn.begin
    InnerTxn.type_enum = TxnType.pay
    InnerTxn.receiver = receiver
    InnerTxn.amount = amount
    InnerTxn.fee = 0
    InnerTxn.submit
  end
end

class Vault < TEALrb::Contract
  @version = 8

  include CommonSubroutines

  # @abi
  # Method called for creation of the vault
  # @param receiver [Account] The account that can claim ASAs from this vault
  # @param sender [Account]
  def create(receiver, sender)
    assert Txn.application_id == 0
    Global['assets'] = 0
    Global['creator'] = sender
    Global['receiver'] = receiver
  end

  # @abi
  # Opts into the given asa
  # @param sender [Account] The account that is sending the ASA
  # @param asa [Asset] The asset to opt-in to
  # @param mbr_payment [Pay] The payment to cover this contracts MBR
  def opt_in(sender, asa, mbr_payment)
    assert mbr_payment.sender == sender
    assert mbr_payment.receiver == Global.current_application_address
    assert Global.current_application_address.balance == mbr_payment.amount

    Global['assets'] = Global['assets'] + 1

    $asa_bytes = itob(asa)
    box_create($asa_bytes, 32)
    Box[$asa_bytes] = sender

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
  # @param asa [Asset] The ASA to send
  # @param mbr_funder [Account] The account that funded the MBR for the ASA
  def claim(asa, mbr_funder)
    $asa_bytes = itob(asa)
    assert box_exists?($asa_bytes)
    assert Txn.sender == Global['receiver']

    assert mbr_funder == Box[$asa_bytes]
    box_del $asa_bytes
    send_asa(asa, Txn.sender)

    available_balance = Global.current_application_address.balance - Global.current_application_address.min_balance
    send_payment(mbr_funder, available_balance)
    Global['assets'] = Global['assets'] - 1

    if Global['assets'] == 0
      box_del 'creator'

      InnerTxn.begin
      InnerTxn.type_enum = TxnType.pay
      InnerTxn.receiver = mbr_funder
      InnerTxn.amount = Global.current_application_address.balance
      InnerTxn.fee = 0
      InnerTxn.close_remainder_to = mbr_funder
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
