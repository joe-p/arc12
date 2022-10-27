# frozen_string_literal: true

require 'tealrb'
require 'pry'

class Vault < TEALrb::Contract
  @version = 8

  # @subroutine
  # @param [Asset] asa
  # @param [Account] receiver
  def inner_asa_close(asa, receiver)
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
  def inner_payment(receiver, amount)
    InnerTxn.begin
    InnerTxn.type_enum = TxnType.pay
    InnerTxn.receiver = receiver
    InnerTxn.amount = amount
    InnerTxn.fee = 0
    InnerTxn.submit
  end

  # @abi
  # @create
  # Method called for creation of the vault
  # @param receiver [Account] The account that can claim ASAs from this vault
  # @param sender [Account]
  def create(receiver, sender)
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
    $asa_bytes = itob(asa)
    assert !box_exists?($asa_bytes)
    assert mbr_payment.sender == sender
    assert mbr_payment.receiver == Global.current_application_address

    $pre_mbr = Global.current_application_address.min_balance

    Global['assets'] = Global['assets'] + 1

    box_create($asa_bytes, 32)
    Box[$asa_bytes] = sender

    InnerTxn.begin
    InnerTxn.type_enum = TxnType.asset_transfer
    InnerTxn.asset_receiver = Global.current_application_address
    InnerTxn.asset_amount = 0
    InnerTxn.fee = 0
    InnerTxn.xfer_asset = asa
    InnerTxn.submit

    assert mbr_payment.amount == Global.current_application_address.min_balance - $pre_mbr
  end

  # @abi
  # @on_completion [NoOp, DeleteApplication]
  # Sends the ASA to the intended receiver
  # @param asa [Asset] The ASA to send
  # @param creator [Account] The account that funded the MBR for the application
  # @param receiver [Account] The account that can claim from this vault
  # @param asa_mbr_funder [Account] The account that funded the MBR for the ASA
  def claim(asa, receiver, creator, asa_mbr_funder)
    $asa_bytes = itob(asa)

    assert box_exists?($asa_bytes)
    assert asa_mbr_funder == Box[$asa_bytes]
    assert receiver == Global['receiver']
    assert creator == Global['creator']
    assert Txn.sender == receiver

    $initial_mbr = Global.current_application_address.min_balance

    box_del $asa_bytes
    inner_asa_close(asa, Txn.sender)

    inner_payment(asa_mbr_funder, Global.current_application_address.min_balance - $initial_mbr)
    Global['assets'] = Global['assets'] - 1

    if Global['assets'] == 0
      InnerTxn.begin
      InnerTxn.type_enum = TxnType.pay
      InnerTxn.receiver = creator
      InnerTxn.amount = Global.current_application_address.min_balance
      InnerTxn.fee = 0
      InnerTxn.close_remainder_to = receiver
      InnerTxn.submit
    end
  end

  def main
    nil
  end
end

class Master < TEALrb::Contract
  @version = 8

  def initialize(vault_program)
    @vault_program = -> { vault_program }
    super()
  end

  # @abi
  # Create Vault
  # @param receiver [Account]
  # @return [Uint64] Application ID of the vault for receiver
  def create_vault(receiver)
    assert !box_exists?(receiver)

    # // Create vault
    InnerTxn.begin
    InnerTxn.type_enum = TxnType.application_call
    InnerTxn.application_id = 0
    InnerTxn.approval_program = byte_b64 @vault_program
    InnerTxn.on_completion = int('NoOp')
    InnerTxn.accounts = receiver
    InnerTxn.accounts = Txn.sender
    InnerTxn.fee = 0
    # TODO: InnerTxn.application_args = Vault.create
    InnerTxn.submit

    # // Fund vault with account MBR
    InnerTxn.begin
    InnerTxn.type_enum = TxnType.pay
    InnerTxn.receiver = Txn.created_application_id.address
    InnerTxn.amount = Global.min_balance
    InnerTxn.fee = 0
    InnerTxn.submit

    box_create receiver, 32
    Box[receiver] = itob Txn.created_application_id

    return itob Txn.created_application_id
  end

  # @abi
  # @param receiver [Account]
  # @param vault_axfer [Axfer]
  def verify_axfer(receiver, vault_axfer)
    assert box_exists?(receiver)
    assert vault_axfer.receiver == Box[receiver]
    assert vault_axfer.close_remainder_to == Global.zero_address
  end

  # @abi
  # @param receiver [Account]
  # @return [Uint64] Application ID of the vault for receiver
  def get_vault_id(receiver)
    assert box_exists?(receiver)
    return Box[receiver]
  end

  # @abi
  # @param receiver [Account]
  # @return [Address] Address of the vault for receiver
  def get_vault_addr(receiver)
    assert box_exists?(receiver)
    return Application.new(btoi(Box[receiver])).address
  end

  def main
    nil
  end
end

vault = Vault.new
vault.dump

Master.new(vault.compiled_program).dump
